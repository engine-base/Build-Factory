"""T-011-02: 3 ターンカウンター + state 管理 (reviewer 改善 loop 上限).

BMAD reviewer (quinn) の 3 ターン改善ルールを実装する process-local in-memory
counter. 4 ターン目に到達した時点 (count > 3) で escalate=True を返し、
人間エスカレーション (T-011-03 Slack DM + UI バッジ) のトリガとする.

設計境界 (NEW タスク, IMPLEMENTATION_PROTOCOL Step 4):
  - process-local dict のみ (no DB / no Redis / no aiosqlite).
  - 既存 `reviewer_loop.py` / `reviewer_persona.py` は無改変.
  - REVIEW_DIMENSIONS / PERSONA_NAME を再定義しない (cross-module invariant).

## 公開 API (read/write 分離)

  - increment(target_id, *, actor_user_id=None, threshold=3) -> dict
  - get_count(target_id) -> int
  - get_state(target_id) -> dict | None
  - reset(target_id) -> bool                  (target が存在しなければ False)
  - should_escalate(target_id, *, threshold=3) -> bool
  - list_active(*, min_count=1) -> list[dict] (count desc, 安定 sort)
  - reset_all_state() -> None                 (test cleanup 用)
  - MAX_TURNS_DEFAULT = 3
  - ReviewerTurnCounterError                  (router で 4xx に変換)

## ADR-010 整合

  - LangGraph / LangChain なし.
  - SDK auto 機能を再実装しない. 純粋 in-memory state.

## AC マッピング (T-011-02 NEW)

  AC-1 UBIQUITOUS    : 公開 7 symbol + router + REUSE invariant
                       (reviewer_loop.py / reviewer_persona.py 無改変).
  AC-2 EVENT-DRIVEN  : 2 秒以内 / structured response /
                       escalate = (count > threshold) / list_active 安定 sort.
  AC-3 STATE-DRIVEN  : process-local dict only / no DB / GET request mutate なし /
                       REVIEW_DIMENSIONS / PERSONA_NAME 再定義禁止.
  AC-4 UNWANTED      : empty/non-string target_id / non-int threshold / out of
                       range / empty actor / overflow MAX_COUNT で
                       ReviewerTurnCounterError + 状態 unchanged.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ReviewerTurnCounterError(RuntimeError):
    """Reviewer turn counter の入力 / 不変条件違反 (router で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

MAX_TURNS_DEFAULT = 3
MIN_THRESHOLD = 1
MAX_THRESHOLD = 20
MAX_COUNT = 1000          # 単一 target の overflow 防止
MAX_TARGET_ID_LEN = 200
MAX_ACTOR_USER_ID_LEN = 200


# ──────────────────────────────────────────────────────────────────────
# Process-local state
# ──────────────────────────────────────────────────────────────────────

_LOCK = threading.RLock()
_STATE: dict[str, dict[str, Any]] = {}


def reset_all_state() -> None:
    """test cleanup 用 (production code では呼ばない)."""
    with _LOCK:
        _STATE.clear()


# ──────────────────────────────────────────────────────────────────────
# Validation (AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _validate_target_id(target_id: Any) -> str:
    if not isinstance(target_id, str):
        raise ReviewerTurnCounterError("target_id must be string")
    s = target_id.strip()
    if not s:
        raise ReviewerTurnCounterError("target_id must not be empty")
    if len(s) > MAX_TARGET_ID_LEN:
        raise ReviewerTurnCounterError(
            f"target_id must be <= {MAX_TARGET_ID_LEN} chars"
        )
    return s


def _validate_threshold(threshold: Any) -> int:
    if isinstance(threshold, bool) or not isinstance(threshold, int):
        raise ReviewerTurnCounterError(
            f"threshold must be int in [{MIN_THRESHOLD}, {MAX_THRESHOLD}]"
        )
    if threshold < MIN_THRESHOLD or threshold > MAX_THRESHOLD:
        raise ReviewerTurnCounterError(
            f"threshold must be in [{MIN_THRESHOLD}, {MAX_THRESHOLD}]"
        )
    return threshold


def _validate_min_count(min_count: Any) -> int:
    if isinstance(min_count, bool) or not isinstance(min_count, int):
        raise ReviewerTurnCounterError("min_count must be int")
    if min_count < 0 or min_count > MAX_COUNT:
        raise ReviewerTurnCounterError(
            f"min_count must be in [0, {MAX_COUNT}]"
        )
    return min_count


def _validate_actor_user_id(actor_user_id: Optional[str]) -> Optional[str]:
    if actor_user_id is None:
        return None
    if not isinstance(actor_user_id, str):
        raise ReviewerTurnCounterError("actor_user_id must be string or null")
    s = actor_user_id.strip()
    if not s:
        raise ReviewerTurnCounterError(
            "actor_user_id must not be empty when provided"
        )
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise ReviewerTurnCounterError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Public API: write
# ──────────────────────────────────────────────────────────────────────


def increment(
    target_id: str,
    *,
    actor_user_id: Optional[str] = None,
    threshold: int = MAX_TURNS_DEFAULT,
) -> dict[str, Any]:
    """target の turn count を +1 して新 state を返す.

    Returns:
      {
        "target_id": str,
        "count": int,
        "last_updated_at": float,
        "first_seen_at": float,
        "threshold": int,
        "escalate": bool,                # count > threshold
      }

    Validation 失敗 (target/threshold/actor) → ReviewerTurnCounterError
    (状態は mutate しない).
    """
    tid = _validate_target_id(target_id)
    th = _validate_threshold(threshold)
    _validate_actor_user_id(actor_user_id)

    with _LOCK:
        now = time.time()
        existing = _STATE.get(tid)
        if existing is None:
            new_count = 1
            first_seen = now
        else:
            new_count = existing["count"] + 1
            first_seen = existing.get("first_seen_at", now)
            if new_count > MAX_COUNT:
                # 状態 mutate せず raise (AC-4 UNWANTED)
                raise ReviewerTurnCounterError(
                    f"count would exceed MAX_COUNT ({MAX_COUNT}) for {tid}"
                )
        _STATE[tid] = {
            "target_id": tid,
            "count": new_count,
            "last_updated_at": now,
            "first_seen_at": first_seen,
            "threshold": th,
        }
        return _serialize(_STATE[tid], threshold=th)


def reset(target_id: str) -> bool:
    """target の state を削除. 存在しなければ False."""
    tid = _validate_target_id(target_id)
    with _LOCK:
        return _STATE.pop(tid, None) is not None


# ──────────────────────────────────────────────────────────────────────
# Public API: read
# ──────────────────────────────────────────────────────────────────────


def get_count(target_id: str) -> int:
    """target の current count (存在しなければ 0)."""
    tid = _validate_target_id(target_id)
    with _LOCK:
        entry = _STATE.get(tid)
        return entry["count"] if entry else 0


def get_state(
    target_id: str,
    *,
    threshold: int = MAX_TURNS_DEFAULT,
) -> Optional[dict[str, Any]]:
    """target の state. 存在しなければ None."""
    tid = _validate_target_id(target_id)
    th = _validate_threshold(threshold)
    with _LOCK:
        entry = _STATE.get(tid)
        return _serialize(entry, threshold=th) if entry else None


def should_escalate(
    target_id: str,
    *,
    threshold: int = MAX_TURNS_DEFAULT,
) -> bool:
    """count > threshold なら True. target 未登録なら False."""
    tid = _validate_target_id(target_id)
    th = _validate_threshold(threshold)
    with _LOCK:
        entry = _STATE.get(tid)
        if entry is None:
            return False
        return entry["count"] > th


def list_active(
    *,
    min_count: int = 1,
    threshold: int = MAX_TURNS_DEFAULT,
) -> list[dict[str, Any]]:
    """active な (count >= min_count) target 一覧を count desc + tid asc で返す.

    返す各 entry は increment と同じ shape (escalate 含む).
    """
    mc = _validate_min_count(min_count)
    th = _validate_threshold(threshold)
    with _LOCK:
        items = [
            entry for entry in _STATE.values()
            if entry["count"] >= mc
        ]
    # 安定 sort: count desc, target_id asc on ties.
    items.sort(key=lambda e: (-e["count"], e["target_id"]))
    return [_serialize(e, threshold=th) for e in items]


# ──────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────


def _serialize(entry: dict[str, Any], *, threshold: int) -> dict[str, Any]:
    count = entry["count"]
    return {
        "target_id": entry["target_id"],
        "count": count,
        "last_updated_at": entry["last_updated_at"],
        "first_seen_at": entry.get("first_seen_at", entry["last_updated_at"]),
        "threshold": threshold,
        "escalate": count > threshold,
    }
