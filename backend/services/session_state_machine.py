"""T-010b-05: sessions table 状態遷移管理 サービス.

sessions.status の遷移を機械的に管理する.
許容される状態: running / done / crashed / cancelled / paused (DDL CHECK と一致).

許容遷移 (state machine):
  running   → done / crashed / cancelled / paused
  paused    → running / cancelled
  crashed   → running (resume) / cancelled
  done      → (terminal, 遷移不可)
  cancelled → (terminal, 遷移不可)

公開 API:
  - is_valid_transition(from_status, to_status) -> bool
  - transition_session(session_id, to_status, *, reason, store_fn) -> dict
  - SessionStateMachineError
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class SessionStateMachineError(RuntimeError):
    pass


class SessionNotFoundError(SessionStateMachineError):
    pass


class InvalidTransitionError(SessionStateMachineError):
    pass


VALID_STATES = ("running", "done", "crashed", "cancelled", "paused")
TERMINAL_STATES = frozenset({"done", "cancelled"})

# from → 許容 to の set
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "running":   frozenset({"done", "crashed", "cancelled", "paused"}),
    "paused":    frozenset({"running", "cancelled"}),
    "crashed":   frozenset({"running", "cancelled"}),
    "done":      frozenset(),         # terminal
    "cancelled": frozenset(),         # terminal
}


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """from → to の遷移が許可されているか."""
    if from_status not in VALID_STATES or to_status not in VALID_STATES:
        return False
    if from_status == to_status:
        # 同状態遷移は idempotent (許可しない: 明示的な error を返したい)
        return False
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


@dataclass
class TransitionResult:
    session_id: int
    from_status: str
    to_status: str
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "reason": self.reason,
        }


# 注入用 loader / writer 型
SessionLoader = Callable[[int], Awaitable[Optional[dict]]]
SessionStatusUpdater = Callable[[int, str, Optional[str]], Awaitable[None]]


async def transition_session(
    session_id: int,
    to_status: str,
    *,
    reason: Optional[str] = None,
    load_fn: SessionLoader,
    update_fn: SessionStatusUpdater,
) -> TransitionResult:
    """session の status を transitions する.

    invalid なら InvalidTransitionError.
    session が存在しないなら SessionNotFoundError.
    """
    if not isinstance(session_id, int) or session_id <= 0:
        raise SessionStateMachineError(f"session_id must be > 0, got {session_id}")
    if to_status not in VALID_STATES:
        raise InvalidTransitionError(
            f"to_status must be one of {VALID_STATES}, got {to_status!r}"
        )
    if reason is not None and not isinstance(reason, str):
        raise SessionStateMachineError("reason must be a string when provided")
    if reason is not None and len(reason) > 2000:
        raise SessionStateMachineError("reason must be <= 2000 chars")

    record = await load_fn(session_id)
    if record is None:
        raise SessionNotFoundError(f"session not found: {session_id}")
    current = (record.get("status") or "").lower()
    if current not in VALID_STATES:
        raise InvalidTransitionError(
            f"current status invalid: {current!r}"
        )

    if not is_valid_transition(current, to_status):
        raise InvalidTransitionError(
            f"transition {current!r} → {to_status!r} not allowed "
            f"(allowed from {current!r}: {sorted(ALLOWED_TRANSITIONS[current])})"
        )

    await update_fn(session_id, to_status, reason)
    return TransitionResult(
        session_id=session_id,
        from_status=current,
        to_status=to_status,
        reason=reason,
    )
