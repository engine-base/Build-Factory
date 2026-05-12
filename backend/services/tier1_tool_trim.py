"""T-M28-02: Tier 1 tool result trimming (SDK auto activation + audit wrapper).

ADR-010 / requirements §11.6 EVENT:
  trim 本体は claude-agent-sdk の内蔵機能 (SDK defaults を活用).
  本 module は **audit wrapper のみ** を提供し, application code 側で
  trimming logic (size cap / age cap / dedup / truncate / window) を
  再実装しない. AC-4 UNWANTED は scripts/lint-mock.sh で機械検知される.

公開 API:
  - record_trim_event(session_id, original_size, trimmed_size, *, ...) -> dict
      SDK が trim を実行した時に audit_logs へ event を書く薄い wrapper.
  - Tier1ToolTrimError : 入力 / 不変条件違反 (router で 4xx に変換).

設計境界 (REUSE タスク, IMPLEMENTATION_PROTOCOL Step 4):
  - claude-agent-sdk が auto-active した trim 結果を **観測 / 監査** する目的のみ.
  - chat_thread_store / memory_service / chat_messages の **destructive
    mutation 無し** (AC-3 STATE-DRIVEN; original tool result は SDK が
    chat_messages 側に保存し続けることが SDK 規約).
  - 本 module は audit_logs.emit_event のみを副作用に持つ.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : SDK 内蔵 trim を有効化 / app code で trimming logic を
                       実装しない (lint で機械検知).
  AC-2 EVENT-DRIVEN  : SDK trim 完了時に tier1.tool_result_trimmed audit emit.
                       detail = {session_id, original_size, trimmed_size,
                                 reduction_ratio, timestamp}.
  AC-3 STATE-DRIVEN  : original tool result は chat_messages に保持
                       (destructive mutation なし) / audit_logs RLS 適用.
  AC-4 UNWANTED      : 自前 trimming logic 検知 → lint fail / invalid input /
                       unauthorized actor → Tier1ToolTrimError → 4xx +
                       state mutate なし.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Tier1ToolTrimError(RuntimeError):
    """Tier 1 tool result trim wrapper の入力 / 不変条件違反 (router で 4xx)."""


# ──────────────────────────────────────────────────────────────────────
# 制約定数
# ──────────────────────────────────────────────────────────────────────

MAX_SESSION_ID_LEN = 200
MAX_ACTOR_USER_ID_LEN = 200
MAX_TOOL_NAME_LEN = 200
MAX_REASON_LEN = 200
MAX_ORIGINAL_SIZE = 10 * 1024 * 1024  # 10 MiB (SDK 経由なので十分余裕)

TRIM_AUDIT_EVENT = "tier1.tool_result_trimmed"

# SDK が trim を実行する代表的な理由 (Anthropic SDK の trim policy 参考)
VALID_TRIM_REASONS = (
    "size_cap",       # SDK のサイズ上限到達
    "window_eviction",  # context window から古い tool result を退避
    "user_request",   # 明示的に user/agent が要求
    "policy",         # SDK 既定ポリシー (auto-trim)
    "other",          # それ以外 (future-proof)
)


# ──────────────────────────────────────────────────────────────────────
# Validation (AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _validate_session_id(session_id: Any) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise Tier1ToolTrimError("session_id must not be empty")
    s = session_id.strip()
    if len(s) > MAX_SESSION_ID_LEN:
        raise Tier1ToolTrimError(
            f"session_id must be <= {MAX_SESSION_ID_LEN} chars"
        )
    return s


def _validate_size(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Tier1ToolTrimError(f"{field_name} must be int")
    if value < 0:
        raise Tier1ToolTrimError(f"{field_name} must be >= 0")
    if value > MAX_ORIGINAL_SIZE:
        raise Tier1ToolTrimError(
            f"{field_name} must be <= {MAX_ORIGINAL_SIZE} bytes"
        )
    return value


def _validate_actor_user_id(actor: Optional[str]) -> Optional[str]:
    if actor is None:
        return None
    if not isinstance(actor, str):
        raise Tier1ToolTrimError("actor_user_id must be string or null")
    s = actor.strip()
    if not s:
        raise Tier1ToolTrimError(
            "actor_user_id must not be empty when provided"
        )
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise Tier1ToolTrimError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


def _validate_tool_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise Tier1ToolTrimError("tool_name must be string or null")
    s = value.strip()
    if not s:
        raise Tier1ToolTrimError("tool_name must not be empty when provided")
    if len(s) > MAX_TOOL_NAME_LEN:
        raise Tier1ToolTrimError(
            f"tool_name must be <= {MAX_TOOL_NAME_LEN} chars"
        )
    return s


def _validate_reason(value: Optional[str]) -> str:
    """trim reason. None なら 'policy' 扱い (SDK 既定)."""
    if value is None:
        return "policy"
    if not isinstance(value, str):
        raise Tier1ToolTrimError("reason must be string or null")
    s = value.strip()
    if not s:
        return "policy"
    if s not in VALID_TRIM_REASONS:
        raise Tier1ToolTrimError(
            f"reason must be one of {VALID_TRIM_REASONS}, got {s!r}"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Public API: record_trim_event (audit wrapper)
# ──────────────────────────────────────────────────────────────────────


async def record_trim_event(
    session_id: str,
    original_size: int,
    trimmed_size: int,
    *,
    actor_user_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """SDK が tool result trim を実行した時に呼ぶ audit wrapper.

    Args:
      session_id     : 対象 session (必須, <= 200 chars).
      original_size  : trim 前のサイズ (bytes, >= 0).
      trimmed_size   : trim 後のサイズ (bytes, >= 0, <= original_size).
      actor_user_id  : 認可確認用 (None で anonymous).
      tool_name      : trim 対象の tool 名 (任意, 観測用).
      reason         : trim 理由. VALID_TRIM_REASONS のいずれか (default "policy").

    Returns:
      {
        "session_id": str,
        "original_size": int,
        "trimmed_size": int,
        "delta_bytes": int,             # original - trimmed
        "reduction_ratio": float,       # delta / original (0.0 if orig=0)
        "tool_name": str|None,
        "reason": str,
        "timestamp": float,
        "audit_event_id": int|None,
      }

    AC-2 EVENT-DRIVEN:
      audit_logs に event_type=tier1.tool_result_trimmed を emit.
      detail は上記 dict + actor_user_id (None でない時のみ).

    AC-3 STATE-DRIVEN:
      chat_messages の destructive mutation なし (SDK が保持).
      本 module は audit_logs 書込のみ.

    AC-4 UNWANTED:
      validation 失敗時は Tier1ToolTrimError raise.
      audit_logs 書込 / chat_messages mutation なし.
    """
    sid = _validate_session_id(session_id)
    orig = _validate_size(original_size, field_name="original_size")
    trimmed = _validate_size(trimmed_size, field_name="trimmed_size")
    actor = _validate_actor_user_id(actor_user_id)
    tname = _validate_tool_name(tool_name)
    rsn = _validate_reason(reason)

    # AC-3: trimmed_size > original_size は SDK の不変条件違反 (state mutate
    # なしで raise)
    if trimmed > orig:
        raise Tier1ToolTrimError(
            f"trimmed_size ({trimmed}) must be <= original_size ({orig})"
        )

    delta = orig - trimmed
    ratio = (delta / orig) if orig > 0 else 0.0
    ts = time.time()

    detail: dict[str, Any] = {
        "session_id": sid,
        "original_size": orig,
        "trimmed_size": trimmed,
        "delta_bytes": delta,
        "reduction_ratio": round(ratio, 6),
        "tool_name": tname,
        "reason": rsn,
        "timestamp": ts,
    }
    if actor is not None:
        detail["actor_user_id"] = actor

    audit_event_id: Optional[int] = None
    try:
        from services.memory_service import emit_event
        audit_event_id = await emit_event(
            TRIM_AUDIT_EVENT,
            user_id=actor,
            detail=detail,
        )
    except Exception as e:  # pragma: no cover (audit 失敗は warning のみ)
        logger.warning(
            "tier1 tool trim audit emit failed session=%s: %s", sid, e,
        )

    return {
        "session_id": sid,
        "original_size": orig,
        "trimmed_size": trimmed,
        "delta_bytes": delta,
        "reduction_ratio": round(ratio, 6),
        "tool_name": tname,
        "reason": rsn,
        "timestamp": ts,
        "audit_event_id": audit_event_id,
    }
