"""T-M28-03: Tier 2 prompt cache friendly composer (cache_control: ephemeral 5min).

Tier 2 (mid-memory) = claude-agent-sdk の auto compaction が 95% で生成する
9-section structured summary. chat_messages に role='system_summary' で格納されている.

本サービスは Tier 2 summary を Anthropic Messages API の prompt cache 用に
`cache_control: {type: ephemeral}` で 1 ブロックにまとめ、cache hit 時の
input cost を 10% に圧縮する payload composer を提供する.

設計:
  - summary + constitution の 2 ブロックまで cache breakpoint を張る
  - user_messages は cache せず (= 動的)
  - audit emit: tier2.cache.compose (AC: action + timestamp)
  - 失敗時 4xx structured / persistent state mutate しない
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Tier2CacheError(RuntimeError):
    pass


DEFAULT_CACHE_TTL_SEC = 300  # Anthropic ephemeral cache = 5 min
MAX_CACHE_BREAKPOINTS = 4
MAX_SUMMARY_CHARS = 100_000
MAX_CONSTITUTION_CHARS = 50_000
MAX_USER_MESSAGES = 200
MAX_MESSAGE_CHARS = 50_000
MAX_TOKENS_LIMIT = 200_000


# ──────────────────────────────────────────────────────────────────────
# 9-section invariant (cross-module 整合: T-M30-03 AC-1 / ADR-010)
# ──────────────────────────────────────────────────────────────────────
# AC-1 spec 文 (T-M30-03):
#   "The 9-section SECTION_KEYS invariant shall hold cross-module
#    (mid_term_layer / tier2_cache / tier3_structured_summary)."
# 本 module は invariant の participant. mid_term_layer.SECTION_KEYS と
# tuple として完全一致 (順序 + 要素) しなければならず, drift は
# test_g6_section_keys_match_tier2_cache (must, not skip) で検出する.
# KNOWN_SUMMARY_SECTIONS は同値の deprecated alias (後方互換のみ).

SECTION_KEYS: tuple[str, ...] = (
    "context",
    "goals",
    "decisions",
    "open_questions",
    "actions",
    "blockers",
    "facts",
    "preferences",
    "next_steps",
)

# Deprecated alias (T-M28-03 互換用). 新規コードは SECTION_KEYS を使うこと.
KNOWN_SUMMARY_SECTIONS = SECTION_KEYS


# ──────────────────────────────────────────────────────────────────────
# Tier 2 summary loader (chat_messages → 9-section dict)
# ──────────────────────────────────────────────────────────────────────


async def load_latest_summary(session_id: int) -> Optional[dict]:
    """chat_messages から最新の role='system_summary' を取得.

    Returns:
      None : summary 無し (新規 session)
      dict : {"message_id": int, "summary": dict, "created_at": str|None}
    """
    if not isinstance(session_id, int) or session_id <= 0:
        raise Tier2CacheError("session_id must be > 0")
    try:
        from services.memory_service import _db, _db_path
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                "SELECT id, content, created_at FROM chat_messages "
                "WHERE thread_id = ? AND role = 'system_summary' "
                "ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            try:
                summary = json.loads(row[1])
            except json.JSONDecodeError:
                raise Tier2CacheError("stored summary is not valid JSON")
            if not isinstance(summary, dict):
                raise Tier2CacheError("stored summary must be a dict")
            return {
                "message_id": row[0],
                "summary": summary,
                "created_at": row[2],
            }
    except Tier2CacheError:
        raise
    except Exception as e:  # pragma: no cover - DB 障害は呼び出し側で 5xx
        logger.warning("tier2 load_latest_summary failed: %s", e)
        raise Tier2CacheError(f"load failed: {e}")


# ──────────────────────────────────────────────────────────────────────
# Summary formatter (dict → markdown text)
# ──────────────────────────────────────────────────────────────────────


def format_summary_text(summary: dict) -> str:
    """9-section summary を ## section\n\nbody 形式の markdown へ.

    順序は SECTION_KEYS (= mid_term_layer.SECTION_KEYS) 固定で出力する.
    これにより cross-module で順序 invariant も維持される (T-M30-03 AC-1).
    SECTION_KEYS 外の extra key は末尾に挿入順で残す (後方互換).
    """
    if not isinstance(summary, dict):
        raise Tier2CacheError("summary must be a dict")
    if not summary:
        raise Tier2CacheError("summary must not be empty")
    for key in summary:
        if not isinstance(key, str) or not key.strip():
            raise Tier2CacheError("summary keys must be non-empty strings")

    def _render(val: Any) -> str:
        if isinstance(val, list):
            return "\n".join(f"- {v}" for v in val)
        if isinstance(val, dict):
            return json.dumps(val, ensure_ascii=False, indent=2)
        if val is None:
            return ""
        return str(val)

    parts: list[str] = []
    seen: set[str] = set()
    for key in SECTION_KEYS:
        if key in summary:
            parts.append(f"## {key}\n\n{_render(summary[key])}")
            seen.add(key)
    for key, val in summary.items():
        if key in seen:
            continue
        parts.append(f"## {key}\n\n{_render(val)}")
    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────────
# Composer: Anthropic prompt-cache payload from Tier 2 summary
# ──────────────────────────────────────────────────────────────────────


def compose_cached_payload(
    *,
    model: str,
    summary_text: Optional[str],
    user_messages: list[dict],
    constitution_text: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    cache_summary: bool = True,
    cache_constitution: bool = True,
) -> dict:
    """Tier 2 summary を cache breakpoint として Anthropic 用 payload を構築する."""
    if not isinstance(model, str) or not model.strip():
        raise Tier2CacheError("model must not be empty")
    if len(model) > 200:
        raise Tier2CacheError("model must be <= 200 chars")
    if not isinstance(user_messages, list) or not user_messages:
        raise Tier2CacheError("user_messages must be a non-empty list")
    if len(user_messages) > MAX_USER_MESSAGES:
        raise Tier2CacheError(
            f"user_messages must be <= {MAX_USER_MESSAGES}"
        )
    for i, m in enumerate(user_messages):
        if not isinstance(m, dict):
            raise Tier2CacheError(f"user_messages[{i}] must be a dict")
        role = m.get("role")
        if role not in ("user", "assistant", "tool"):
            raise Tier2CacheError(
                f"user_messages[{i}].role must be user/assistant/tool"
            )
        content = m.get("content")
        if not isinstance(content, str):
            raise Tier2CacheError(
                f"user_messages[{i}].content must be string"
            )
        if len(content) > MAX_MESSAGE_CHARS:
            raise Tier2CacheError(
                f"user_messages[{i}].content must be <= {MAX_MESSAGE_CHARS} chars"
            )
    if summary_text is not None and not isinstance(summary_text, str):
        raise Tier2CacheError("summary_text must be string or None")
    if summary_text is not None and len(summary_text) > MAX_SUMMARY_CHARS:
        raise Tier2CacheError(
            f"summary_text must be <= {MAX_SUMMARY_CHARS} chars"
        )
    if constitution_text is not None and not isinstance(constitution_text, str):
        raise Tier2CacheError("constitution_text must be string or None")
    if constitution_text is not None and len(constitution_text) > MAX_CONSTITUTION_CHARS:
        raise Tier2CacheError(
            f"constitution_text must be <= {MAX_CONSTITUTION_CHARS} chars"
        )
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise Tier2CacheError("max_tokens must be > 0")
    if max_tokens > MAX_TOKENS_LIMIT:
        raise Tier2CacheError(f"max_tokens must be <= {MAX_TOKENS_LIMIT}")
    if not isinstance(temperature, (int, float)) or not (0.0 <= temperature <= 2.0):
        raise Tier2CacheError("temperature must be 0.0..2.0")

    system_blocks: list[dict] = []
    breakpoints = 0
    if constitution_text:
        block: dict = {"type": "text", "text": constitution_text}
        if cache_constitution:
            block["cache_control"] = {"type": "ephemeral"}
            breakpoints += 1
        system_blocks.append(block)
    if summary_text:
        block = {"type": "text", "text": summary_text}
        if cache_summary:
            block["cache_control"] = {"type": "ephemeral"}
            breakpoints += 1
        system_blocks.append(block)
    if breakpoints > MAX_CACHE_BREAKPOINTS:
        raise Tier2CacheError(
            f"cache breakpoints must be <= {MAX_CACHE_BREAKPOINTS}"
        )

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": m["role"], "content": m["content"]} for m in user_messages],
    }
    if system_blocks:
        payload["system"] = system_blocks

    return {
        "provider": "anthropic",
        "route": "main",
        "payload": payload,
        "cache_meta": {
            "breakpoints": breakpoints,
            "summary_cached": bool(summary_text and cache_summary),
            "constitution_cached": bool(constitution_text and cache_constitution),
            "summary_chars": len(summary_text or ""),
            "constitution_chars": len(constitution_text or ""),
            "ttl_seconds": DEFAULT_CACHE_TTL_SEC,
        },
    }


# ──────────────────────────────────────────────────────────────────────
# Stats helper (テスト + UI dashboard 用)
# ──────────────────────────────────────────────────────────────────────


def summary_stats(loaded: Optional[dict]) -> dict:
    """load_latest_summary の戻り値からメタ情報を作る."""
    if loaded is None:
        return {
            "has_summary": False,
            "sections_count": 0,
            "sections": [],
            "message_id": None,
            "summary_age_seconds": None,
        }
    summary = loaded.get("summary", {})
    sections = list(summary.keys()) if isinstance(summary, dict) else []
    age: Optional[float] = None
    created = loaded.get("created_at")
    if isinstance(created, (int, float)):
        age = max(0.0, time.time() - float(created))
    return {
        "has_summary": True,
        "sections_count": len(sections),
        "sections": sections,
        "message_id": loaded.get("message_id"),
        "summary_age_seconds": age,
    }
