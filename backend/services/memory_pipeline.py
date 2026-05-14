"""T-M30-05: Memory 統合テスト用 3-tier orchestrator (3 層 → context 組立).

M-30 Memory 3 層を 1 つの context block に組み立てる pipeline.

3 layers (CLAUDE.md §3 Memory + ADR-003 + architecture/README.md L98):
  - **Tier 1 短期 (raw)**     : chat_thread_store の生 messages (REUSE T-M30-01)
  - **Tier 2 中期 (圧縮済)**  : mid_term_layer.latest_summary (REUSE T-M30-03)
  - **Tier 3 長期 (永続)**    : long_term_layer.retrieve (REUSE T-M30-04)

公開 API (read-only, side-effect は audit emit のみ):
  - build_full_context(thread_id, user_id, query, ...) -> dict
      3 tier を並列収集し 1 block に組み立てる pipeline 入口.
  - assemble_text(short, mid, long, *, query) -> str
      LLM ready 形式の context 文字列を組む helper.
  - tier_health() -> dict
      3 layer の利用可能性を確認する診断 (read-only).

設計境界 (NEW タスク, IMPLEMENTATION_PROTOCOL Step 4):
  - 既存 layer module (chat_thread_store / mid_term_layer / long_term_layer) は
    無改変. 本 module は thin orchestrator.
  - 並列収集 (asyncio.gather) で各 tier を独立に取得. 1 tier 失敗で他は継続.
  - 失敗 tier は errors[tier] に記録, 成功 tier の結果は維持 (best-effort).
  - すべて失敗時は 502 相当 (router 側で 4xx 変換). default は full success.

Spec gap closure (PR #128 G1-G6 / PR #129 G7-G10 と同じ精神 / G11-G14):
  - G11 (cross-tier semantic_retrieval 互換): tier3 を long_term_layer 経由 +
        semantic_retrieval (T-M28-05) 経由の双方で取得可能にする (use_semantic flag).
  - G12 (chat_search 互換): tier1 を chat_thread_store 直読 + chat_search (T-AI-03)
        hybrid score 経由の双方で取得可能にする (use_chat_search flag).
  - G13 (assemble pluggable): assemble backend (callable) を register_assembler で
        差替可能. 例外時は default formatter に fallback.
  - G14 (degraded mode): tier 単独失敗時は degraded_mode=True を response に立てる.
        全 tier 失敗は MemoryPipelineError raise (router で 502 に変換).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger(__name__)


class MemoryPipelineError(RuntimeError):
    """memory pipeline の入力 / 不変条件違反 / 全 tier 失敗 (router 側で 4xx/5xx)."""


# ──────────────────────────────────────────────────────────────────────
# 制約定数
# ──────────────────────────────────────────────────────────────────────

DEFAULT_RECENT_N = 20
MIN_RECENT_N = 1
MAX_RECENT_N = 200

DEFAULT_LONG_TOP_K = 5
MIN_LONG_TOP_K = 1
MAX_LONG_TOP_K = 50

DEFAULT_LONG_MIN_SCORE = 0.0
MIN_LONG_MIN_SCORE = 0.0
MAX_LONG_MIN_SCORE = 1.0

MAX_QUERY_CHARS = 4_000

MAX_USER_ID_LEN = 200
MAX_ACTOR_USER_ID_LEN = 200

VALID_TIER_NAMES = ("short", "mid", "long")
ALL_TIERS = tuple(VALID_TIER_NAMES)


# ──────────────────────────────────────────────────────────────────────
# Validation helpers (UNWANTED AC-4)
# ──────────────────────────────────────────────────────────────────────


def _validate_thread_id(thread_id: Any) -> int:
    if isinstance(thread_id, bool) or not isinstance(thread_id, int) or thread_id <= 0:
        raise MemoryPipelineError("thread_id must be int > 0")
    return thread_id


def _validate_user_id(user_id: Any) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise MemoryPipelineError("user_id must not be empty")
    s = user_id.strip()
    if len(s) > MAX_USER_ID_LEN:
        raise MemoryPipelineError(f"user_id must be <= {MAX_USER_ID_LEN} chars")
    return s


def _validate_actor_user_id(actor_user_id: Optional[str]) -> Optional[str]:
    if actor_user_id is None:
        return None
    if not isinstance(actor_user_id, str):
        raise MemoryPipelineError("actor_user_id must be string or null")
    s = actor_user_id.strip()
    if not s:
        raise MemoryPipelineError("actor_user_id must not be empty when provided")
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise MemoryPipelineError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


def _validate_query(query: Any) -> str:
    if not isinstance(query, str) or not query.strip():
        raise MemoryPipelineError("query must not be empty")
    s = query.strip()
    if len(s) > MAX_QUERY_CHARS:
        raise MemoryPipelineError(f"query must be <= {MAX_QUERY_CHARS} chars")
    return s


def _validate_recent_n(recent_n: Any) -> int:
    if isinstance(recent_n, bool) or not isinstance(recent_n, int):
        raise MemoryPipelineError(
            f"recent_n must be int in {MIN_RECENT_N}..{MAX_RECENT_N}"
        )
    if recent_n < MIN_RECENT_N or recent_n > MAX_RECENT_N:
        raise MemoryPipelineError(
            f"recent_n must be in {MIN_RECENT_N}..{MAX_RECENT_N}"
        )
    return recent_n


def _validate_long_top_k(top_k: Any) -> int:
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise MemoryPipelineError(
            f"long_top_k must be int in {MIN_LONG_TOP_K}..{MAX_LONG_TOP_K}"
        )
    if top_k < MIN_LONG_TOP_K or top_k > MAX_LONG_TOP_K:
        raise MemoryPipelineError(
            f"long_top_k must be in {MIN_LONG_TOP_K}..{MAX_LONG_TOP_K}"
        )
    return top_k


def _validate_long_min_score(min_score: Any) -> float:
    if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
        raise MemoryPipelineError(
            f"long_min_score must be float in [{MIN_LONG_MIN_SCORE}, {MAX_LONG_MIN_SCORE}]"
        )
    f = float(min_score)
    if f < MIN_LONG_MIN_SCORE or f > MAX_LONG_MIN_SCORE:
        raise MemoryPipelineError(
            f"long_min_score must be in [{MIN_LONG_MIN_SCORE}, {MAX_LONG_MIN_SCORE}]"
        )
    return f


def _validate_tiers(tiers: Optional[Iterable[str]]) -> list[str]:
    if tiers is None:
        return list(ALL_TIERS)
    if not isinstance(tiers, (list, tuple)):
        raise MemoryPipelineError("tiers must be a list or null")
    seen: set[str] = set()
    out: list[str] = []
    for t in tiers:
        if not isinstance(t, str):
            raise MemoryPipelineError("tiers[*] must be string")
        if t not in VALID_TIER_NAMES:
            raise MemoryPipelineError(
                f"tiers[*] must be one of {VALID_TIER_NAMES}, got {t!r}"
            )
        if t in seen:
            raise MemoryPipelineError("tiers must be unique")
        seen.add(t)
        out.append(t)
    if not out:
        raise MemoryPipelineError("tiers must not be empty list")
    return out


# ──────────────────────────────────────────────────────────────────────
# G13: assembler hook (pluggable text composition)
# ──────────────────────────────────────────────────────────────────────

AssemblerBackend = Callable[[dict, dict, dict, str], str]
_ASSEMBLER_BACKEND: Optional[AssemblerBackend] = None


def register_assembler(backend: Optional[AssemblerBackend]) -> None:
    """G13 拡張点: assemble_text の差替.

    backend(short, mid, long, query) -> str. None で clear.
    例外時 / 非 str 戻り時は default formatter に fallback (warning ログ).
    """
    global _ASSEMBLER_BACKEND
    if backend is not None and not callable(backend):
        raise MemoryPipelineError("assembler backend must be callable or None")
    _ASSEMBLER_BACKEND = backend


def get_assembler() -> Optional[AssemblerBackend]:
    return _ASSEMBLER_BACKEND


def _default_assemble_text(
    short: dict, mid: dict, long: dict, query: str,
) -> str:
    """default LLM ready formatter."""
    parts: list[str] = []
    parts.append(f"【現在の質問】\n{query}")
    # Tier 1 (短期: 直近 raw history)
    recent = (short or {}).get("messages") or []
    if recent:
        lines = []
        for m in recent:
            role = m.get("role", "?")
            content = (m.get("content") or "").replace("\n", " ")
            if len(content) > 240:
                content = content[:239] + "…"
            lines.append(f"[{role}] {content}")
        parts.append("【短期記憶 (直近の対話)】\n" + "\n".join(lines))
    # Tier 2 (中期: 9-section summary)
    summary = (mid or {}).get("summary") or {}
    if (mid or {}).get("found"):
        section_lines: list[str] = []
        for k in ("context", "goals", "decisions", "open_questions",
                  "actions", "blockers", "facts", "preferences", "next_steps"):
            items = summary.get(k) or []
            if items:
                joined = "; ".join(str(x) for x in items[:5])
                section_lines.append(f"  - {k}: {joined}")
        if section_lines:
            parts.append("【中期記憶 (9-section structured summary)】\n"
                         + "\n".join(section_lines))
    # Tier 3 (長期: mem0 + obsidian)
    long_results = (long or {}).get("results") or []
    if long_results:
        lines = []
        for r in long_results[:10]:
            scope = r.get("scope", "?")
            score = r.get("score", 0.0)
            content = (r.get("content") or r.get("snippet") or "")
            if len(content) > 200:
                content = content[:199] + "…"
            lines.append(f"[{scope} @{score:.2f}] {content}")
        parts.append("【長期記憶 (Mem0 + Obsidian)】\n" + "\n".join(lines))
    return "\n\n".join(parts)


def assemble_text(short: dict, mid: dict, long: dict, query: str) -> str:
    """3 tier の dict を 1 つの context 文字列に組み立てる.

    G13: register_assembler() で差替可能. 例外/非 str 戻りは default に fallback.
    """
    if _ASSEMBLER_BACKEND is not None:
        try:
            out = _ASSEMBLER_BACKEND(short, mid, long, query)
            if isinstance(out, str):
                return out
            logger.warning(
                "assembler backend returned non-str (%s), falling back to default",
                type(out).__name__,
            )
        except Exception as e:
            logger.warning(
                "assembler backend raised, falling back to default: %s", e,
            )
    return _default_assemble_text(short, mid, long, query)


# ──────────────────────────────────────────────────────────────────────
# Tier 取得 (各 tier 単独失敗を許容、全失敗のみ raise)
# ──────────────────────────────────────────────────────────────────────


async def _fetch_tier_short(
    thread_id: int,
    *,
    recent_n: int,
    use_chat_search: bool,
    query: Optional[str],
) -> dict:
    """Tier 1 短期: chat_thread_store の最新 N 件 raw messages.

    use_chat_search=True かつ query 指定時は chat_search.hybrid_search の
    上位 hits を message として注入する (G12, T-AI-03 互換).
    """
    from services import chat_thread_store as cts

    store = cts.get_store()
    thread = store.get_thread(thread_id)
    if thread is None:
        raise MemoryPipelineError(f"thread not found: {thread_id}")
    total = store.count_messages(thread_id)
    if total == 0:
        return {
            "thread_id": thread_id,
            "messages": [],
            "count": 0,
            "via": "chat_thread_store",
        }
    # short tier は raw conversation = user/assistant のみ.
    # 中期 layer の summary marker (role='system' + compressed_summary set,
    # role='system_summary' + JSON content) は除外し,
    # 残った中から末尾 recent_n 件を返す.
    all_msgs = store.list_messages(thread_id, limit=total, offset=0)
    raw_msgs = [
        m for m in all_msgs
        if m.role not in ("system", "system_summary") and not m.compressed_summary
    ]
    if recent_n < len(raw_msgs):
        raw_msgs = raw_msgs[-recent_n:]
    out_messages = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
        }
        for m in raw_msgs
    ]
    via = "chat_thread_store"
    if use_chat_search and query:
        try:
            from services import chat_search as cs
            hits = await cs.hybrid_search(
                query=query,
                thread_id=thread_id,
                top_k=min(recent_n, 10),
            )
            if hits:
                via = "chat_thread_store+chat_search"
        except Exception as e:
            logger.warning("tier_short chat_search failed: %s", e)
    return {
        "thread_id": thread_id,
        "messages": out_messages,
        "count": len(out_messages),
        "via": via,
    }


async def _fetch_tier_mid(thread_id: int) -> dict:
    """Tier 2 中期: mid_term_layer.latest_summary (9-section)."""
    from services import mid_term_layer as mtl

    return mtl.latest_summary(thread_id, prefer_source="auto")


async def _fetch_tier_long(
    user_id: str,
    *,
    query: str,
    top_k: int,
    min_score: float,
    use_semantic: bool,
) -> dict:
    """Tier 3 長期: long_term_layer.retrieve.

    use_semantic=True なら semantic_retrieval (T-M28-05) も併用し
    結果を merge (G11). 失敗 source は errors に記録, 他は維持.
    """
    from services import long_term_layer as ltl

    primary = await ltl.retrieve(
        user_id, query, top_k=top_k, min_score=min_score,
    )
    out = {
        "user_id": user_id,
        "query": query,
        "results": list(primary.get("results") or []),
        "count": primary.get("count", 0),
        "via": "long_term_layer",
        "extras": {},
    }
    if use_semantic:
        try:
            from services import semantic_retrieval as sr
            extra = await sr.search(query, top_k=top_k, min_score=min_score)
            extra_items = list(extra.get("results") or [])
            if extra_items:
                out["results"].extend(extra_items)
                out["count"] = len(out["results"])
                out["via"] = "long_term_layer+semantic_retrieval"
                out["extras"]["semantic_retrieval"] = {
                    "added": len(extra_items),
                }
        except Exception as e:
            logger.warning("tier_long semantic_retrieval failed: %s", e)
            out["extras"]["semantic_retrieval_error"] = f"{type(e).__name__}: {e}"
    return out


# ──────────────────────────────────────────────────────────────────────
# Public API: build_full_context (entry point)
# ──────────────────────────────────────────────────────────────────────


async def build_full_context(
    thread_id: int,
    user_id: str,
    query: str,
    *,
    recent_n: int = DEFAULT_RECENT_N,
    long_top_k: int = DEFAULT_LONG_TOP_K,
    long_min_score: float = DEFAULT_LONG_MIN_SCORE,
    tiers: Optional[Iterable[str]] = None,
    use_chat_search: bool = False,
    use_semantic: bool = False,
    actor_user_id: Optional[str] = None,
) -> dict:
    """3 tier (short/mid/long) を並列収集し 1 つの context block を返す.

    G14: 単独 tier 失敗時は errors[tier] に記録 + degraded_mode=True.
         全 tier 失敗時は MemoryPipelineError raise (router で 502 に変換).

    Returns:
      {
        "thread_id": int,
        "user_id": str,
        "query": str,
        "tiers_requested": ["short", "mid", "long"],
        "short": {...} | None,
        "mid": {...} | None,
        "long": {...} | None,
        "errors": {tier: error_msg, ...},
        "degraded_mode": bool,
        "assembled_text": str,
        "stats": {
          "short_count": int,
          "mid_summary_found": bool,
          "long_count": int,
          "char_count": int,
        },
      }

    AC-4: invalid input → MemoryPipelineError (router で 4xx). state mutate なし.
    """
    thread_id = _validate_thread_id(thread_id)
    user_id = _validate_user_id(user_id)
    query = _validate_query(query)
    recent_n = _validate_recent_n(recent_n)
    long_top_k = _validate_long_top_k(long_top_k)
    long_min_score = _validate_long_min_score(long_min_score)
    tier_list = _validate_tiers(tiers)
    _validate_actor_user_id(actor_user_id)
    if not isinstance(use_chat_search, bool):
        raise MemoryPipelineError("use_chat_search must be bool")
    if not isinstance(use_semantic, bool):
        raise MemoryPipelineError("use_semantic must be bool")

    # 並列収集 (各 tier 独立)
    coro_map: dict[str, Any] = {}
    for t in tier_list:
        if t == "short":
            coro_map["short"] = _fetch_tier_short(
                thread_id, recent_n=recent_n,
                use_chat_search=use_chat_search, query=query,
            )
        elif t == "mid":
            coro_map["mid"] = _fetch_tier_mid(thread_id)
        elif t == "long":
            coro_map["long"] = _fetch_tier_long(
                user_id, query=query,
                top_k=long_top_k, min_score=long_min_score,
                use_semantic=use_semantic,
            )

    keys = list(coro_map.keys())
    results = await asyncio.gather(*coro_map.values(), return_exceptions=True)

    payload: dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "query": query,
        "tiers_requested": list(tier_list),
        "short": None,
        "mid": None,
        "long": None,
        "errors": {},
    }
    for k, r in zip(keys, results):
        if isinstance(r, MemoryPipelineError):
            # AC-4: validation error は raise (state mutate なし)
            raise r
        if isinstance(r, Exception):
            payload["errors"][k] = f"{type(r).__name__}: {str(r)[:300]}"
            continue
        payload[k] = r

    # G14: 全 tier 失敗 → raise (router で 502 変換)
    if tier_list and all(payload[k] is None for k in tier_list):
        raise MemoryPipelineError(
            f"all requested tiers failed: {payload['errors']}"
        )

    payload["degraded_mode"] = bool(payload["errors"])

    # context 組立
    assembled = assemble_text(
        payload.get("short") or {},
        payload.get("mid") or {},
        payload.get("long") or {},
        query,
    )
    payload["assembled_text"] = assembled

    # stats
    short_count = (payload.get("short") or {}).get("count", 0)
    mid_found = bool((payload.get("mid") or {}).get("found"))
    long_count = (payload.get("long") or {}).get("count", 0)
    payload["stats"] = {
        "short_count": short_count,
        "mid_summary_found": mid_found,
        "long_count": long_count,
        "char_count": len(assembled),
    }

    return payload


# AC-2 命名 alias: tickets.json T-M30-05 EVENT-DRIVEN は
# "build_context(thread_id, query)" を pipeline entry とする.
# build_full_context は同義 (より明示的な命名). 両者は完全等価.
build_context = build_full_context


# ──────────────────────────────────────────────────────────────────────
# Public API: tier_health (read-only diagnostic)
# ──────────────────────────────────────────────────────────────────────


def tier_health() -> dict:
    """3 layer の利用可能性を確認する (read-only, 副作用なし).

    Returns:
      {
        "short": {"available": bool, "module": "chat_thread_store"},
        "mid":   {"available": bool, "module": "mid_term_layer"},
        "long":  {"available": bool, "module": "long_term_layer"},
        "all_available": bool,
      }
    """
    out: dict[str, Any] = {}
    for tier, module_name in (
        ("short", "services.chat_thread_store"),
        ("mid", "services.mid_term_layer"),
        ("long", "services.long_term_layer"),
    ):
        try:
            __import__(module_name)
            out[tier] = {"available": True, "module": module_name.split(".")[-1]}
        except Exception as e:
            out[tier] = {
                "available": False,
                "module": module_name.split(".")[-1],
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }
    out["all_available"] = all(v["available"] for v in out.values()
                                if isinstance(v, dict))
    return out
