"""T-M28-04: Tier 3 9-section structured summary persistence
(SDK auto-generated, DB persist wrapper only).

ADR-010 / requirements §11.6 EVENT に従い, **application code は summary
本体を生成しない**. 本モジュールは claude-agent-sdk が 95% context 閾値で
自動生成した 9-section structured summary を受け取り,
chat_messages.compressed_summary へ persist する **wrapper のみ** を提供する.

公開 API:
  - SECTION_KEYS               : mid_term_layer.SECTION_KEYS の re-export
                                 (G10 cross-module invariant. 重複定義禁止 =
                                 scripts/check-section-keys-uniqueness.py で守る)
  - validate_9_section_summary : SDK 出力を厳密検証する純粋関数 (AC-4)
  - run_compaction             : SDK の memory_compacted event 受信時の persist
                                 wrapper. dual-write (経路 A + B) + audit emit.

設計境界 (REFACTOR の 1 行宣言, IMPLEMENTATION_PROTOCOL Step 4):
  既存 chat_thread_store.py / memory_service.py は無改変. mid_term_layer.py
  から SECTION_KEYS のみ import する. summarization logic (keyword heuristic
  / LLM call / rule-based extractor) は本モジュールに **存在しない** —
  AC-1/AC-4 UNWANTED の lint script (check-section-keys-uniqueness.py) が
  ALLOWED_FILES でないことを担保する.

AC マッピング:
  AC-1 UBIQUITOUS    : SDK 生成 9-section summary を persist; 自前生成しない
                       (lint で機械検知; ALLOWED_FILES = mid_term_layer /
                       tier2_cache のみ; 本モジュールも import only).
  AC-2 EVENT-DRIVEN  : memory_compacted event を emit (summary_message_id +
                       section_keys 付き) within 2 秒.
  AC-3 STATE-DRIVEN  : original messages は不変 (chat_thread_store.add_message
                       は append-only). RLS は memory_service 側で適用.
  AC-4 UNWANTED      : 不正 schema → Tier3PersistError → 4xx + state mutate
                       しない. application code が summary 生成 → lint fail.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services import chat_thread_store as cts
from services.mid_term_layer import SECTION_KEYS  # G10 single source of truth

logger = logging.getLogger(__name__)


class Tier3PersistError(RuntimeError):
    """SDK 出力 schema 違反 / 入力不正 (router 層で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# 制約定数
# ──────────────────────────────────────────────────────────────────────

SUMMARY_ROLE_SYSTEM = "system"  # chat_thread_store の経路 A
COMPACTION_AUDIT_EVENT = "memory_compacted"  # ADR-010 / AC-2 で固定
MAX_ACTOR_USER_ID_LEN = 200


# ──────────────────────────────────────────────────────────────────────
# Validation (AC-4 UNWANTED: invalid schema は 4xx + state mutate 無し)
# ──────────────────────────────────────────────────────────────────────


def _validate_thread_id(thread_id: Any) -> int:
    if isinstance(thread_id, bool) or not isinstance(thread_id, int) or thread_id <= 0:
        raise Tier3PersistError("thread_id must be int > 0")
    return thread_id


def _validate_actor_user_id(actor_user_id: Optional[str]) -> Optional[str]:
    if actor_user_id is None:
        return None
    if not isinstance(actor_user_id, str):
        raise Tier3PersistError("actor_user_id must be string or null")
    s = actor_user_id.strip()
    if not s:
        raise Tier3PersistError("actor_user_id must not be empty when provided")
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise Tier3PersistError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


def validate_9_section_summary(summary: Any) -> dict[str, list[str]]:
    """SDK 出力を **厳密** 検証して正規化 9-section dict を返す.

    AC-4 UNWANTED:
      - dict でない / 9 section のいずれか欠落 → Tier3PersistError
      - section 値が list でない → Tier3PersistError
      - list 内の非 str / None は除外 (defensive; SDK 出力の type drift 吸収)

    AC-1 (re-implementation 禁止):
      - 本関数は schema 検証のみ. summary content は変更しない.
      - extra key (将来拡張) は無視. 9 sections の subset 抽出.
    """
    if not isinstance(summary, dict):
        raise Tier3PersistError("summary must be a dict")
    missing = [k for k in SECTION_KEYS if k not in summary]
    if missing:
        raise Tier3PersistError(
            f"summary missing sections: {missing} (9 sections required)"
        )
    normalized: dict[str, list[str]] = {}
    for k in SECTION_KEYS:
        v = summary[k]
        if v is None:
            normalized[k] = []
        elif isinstance(v, list):
            # list 内の非 str は str() に正規化 (defensive)
            normalized[k] = [str(x) for x in v if x is not None]
        else:
            raise Tier3PersistError(
                f"section '{k}' must be a list, got {type(v).__name__}"
            )
    return normalized


def _require_thread_exists(thread_id: int) -> None:
    """thread の存在を確認 (404 相当 / state mutate なし)."""
    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise Tier3PersistError(f"thread not found: {thread_id}")


# ──────────────────────────────────────────────────────────────────────
# Public API: run_compaction (SDK auto-compaction の persist entry point)
# ──────────────────────────────────────────────────────────────────────


async def run_compaction(
    thread_id: int,
    summary: dict,
    *,
    actor_user_id: Optional[str] = None,
    persist_legacy: bool = True,
) -> dict[str, Any]:
    """SDK の memory_compacted event 受信時に呼ばれる persist wrapper.

    Args:
      thread_id      : 対象 thread (must exist)
      summary        : SDK 生成 9-section dict (必須: 全 SECTION_KEYS 存在)
      actor_user_id  : UNAUTHORIZED 検知 (None なら skip)
      persist_legacy : True なら memory_service.persist_compaction (経路 B)
                       にも書く (best-effort). 失敗は warning でログするが
                       経路 A の結果は維持.

    Returns:
      {
        "thread_id": int,
        "summary_message_id": int,           # 経路 A の message id
        "section_keys": list[str],           # 9 sections (固定順)
        "legacy_result": {...} | None,       # 経路 B (persist_legacy=True 時)
        "audit_event_id": int | None,        # emit_event で得た audit_logs.id
      }

    AC-2 EVENT-DRIVEN:
      audit_logs に event_type='memory_compacted' を emit.
      detail は {summary_message_id, section_keys, thread_id, actor_user_id?}.

    AC-3 STATE-DRIVEN:
      validation で失敗した場合, chat_thread_store / memory_service / audit_logs
      のいずれにも書き込みを行わない (state mutate なし).
    """
    # validation phase (failures here mutate nothing)
    thread_id = _validate_thread_id(thread_id)
    actor_user_id = _validate_actor_user_id(actor_user_id)
    if not isinstance(persist_legacy, bool):
        raise Tier3PersistError("persist_legacy must be bool")
    normalized = validate_9_section_summary(summary)
    _require_thread_exists(thread_id)

    # 経路 A: chat_thread_store に role='system' + compressed_summary で append.
    # add_message は append-only (chat_thread_store.py の不変条件) なので
    # original messages は preserve される (AC-3 STATE-DRIVEN).
    store = cts.get_store()
    persisted = store.add_message(
        thread_id,
        SUMMARY_ROLE_SYSTEM,
        "[tier3_structured_summary] SDK auto-compaction 9-section persist",
        compressed_summary=normalized,
    )

    # 経路 B: memory_service.persist_compaction (sqlite + chat_messages).
    # best-effort: 経路 B 失敗は warning のみ. 経路 A の結果は維持.
    legacy_result: Optional[dict[str, Any]] = None
    if persist_legacy:
        try:
            from services.memory_service import persist_compaction
            legacy_msg_id = await persist_compaction(thread_id, normalized)
            legacy_result = {"status": "ok", "message_id": legacy_msg_id}
        except Exception as e:  # pragma: no cover (sqlite 未配備環境向け)
            logger.warning(
                "tier3 legacy persist failed thread_id=%s: %s", thread_id, e,
            )
            legacy_result = {"status": "error", "reason": f"{type(e).__name__}: {e}"}

    # audit emit (AC-2 EVENT-DRIVEN)
    audit_event_id: Optional[int] = None
    try:
        from services.memory_service import emit_event
        audit_event_id = await emit_event(
            COMPACTION_AUDIT_EVENT,
            session_id=thread_id,
            user_id=actor_user_id,
            detail={
                "thread_id": thread_id,
                "summary_message_id": persisted.id,
                "section_keys": list(SECTION_KEYS),
                "legacy_status": (legacy_result or {}).get("status"),
            },
        )
    except Exception as e:  # pragma: no cover (audit 失敗は warning のみ)
        logger.warning(
            "tier3 audit emit failed thread_id=%s: %s", thread_id, e,
        )

    return {
        "thread_id": thread_id,
        "summary_message_id": persisted.id,
        "section_keys": list(SECTION_KEYS),
        "legacy_result": legacy_result,
        "audit_event_id": audit_event_id,
    }
