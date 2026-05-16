"""T-V3-B-18: Violations backend service module (F-012).

Domain-bounded façade over ``services.red_lines`` for the **violations**
endpoint surface (list / approve / reject).

なぜ薄い wrapper を分けるか:
  - T-V3-B-17 で `services.red_lines` に red_lines + violations を同居実装した。
    Wave 2 で UI / 別 backend task から violation 関数のみ import するため、
    "violations" 名前空間で公開した方が依存方向 (red_lines は detector 由来)
    が明確になり、Wave 2 後段の Postgres backend 置換 (E-032 専用 repository)
    時に変更箇所を 1 ファイルに集約できる。
  - ``red_lines`` モジュールの violation 関数を直接 re-export することで
    behavior parity を保持し、二重実装による drift を防ぐ。

AC マッピング (T-V3-B-18 audit MD):
  AC-F1 EVENT-DRIVEN(approve resume) : approve_violation() の resumed_session_id
  AC-F2 UNWANTED(409 already-resolved): approve/reject 再呼び出しで 409
  AC-F3 EVENT-DRIVEN(list 2xx)        : list_violations() の戻り contract
  AC-F4-F9: router 層 401 / 422 (本 service 層は domain error のみ返す)
"""
from __future__ import annotations

from typing import Any, Optional

from services import red_lines as _rl


# ─────────────────────────────────────────────────────────────────────────────
# Re-exports (errors)
# ─────────────────────────────────────────────────────────────────────────────


ViolationServiceError = _rl.RedLineServiceError
InvalidViolationInput = _rl.InvalidRedLineInput
ViolationNotFound = _rl.ViolationNotFound
ViolationAlreadyResolved = _rl.ViolationAlreadyResolved
WorkspaceNotFound = _rl.WorkspaceNotFound


# ─────────────────────────────────────────────────────────────────────────────
# Re-exports (constants / model)
# ─────────────────────────────────────────────────────────────────────────────


VIOLATION_PENDING = _rl.VIOLATION_PENDING
VIOLATION_APPROVED = _rl.VIOLATION_APPROVED
VIOLATION_REJECTED = _rl.VIOLATION_REJECTED
VIOLATION_STATUSES: frozenset[str] = frozenset(
    (VIOLATION_PENDING, VIOLATION_APPROVED, VIOLATION_REJECTED)
)


# ─────────────────────────────────────────────────────────────────────────────
# Public API (thin delegating wrappers)
# ─────────────────────────────────────────────────────────────────────────────


def list_violations(
    workspace_id: str,
    *,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """AC-F3: list violations for a workspace.

    Returns: list of violation dicts (created_at desc).
    Raises:
      - InvalidViolationInput: workspace_id is empty / status is unknown.
    """
    return _rl.list_violations(workspace_id, status=status)


def get_violation(violation_id: str) -> dict[str, Any]:
    """Look up a single violation by id.

    Raises:
      - InvalidViolationInput: violation_id is empty/non-string.
      - ViolationNotFound: no such violation.
    """
    return _rl.get_violation(violation_id)


def approve_violation(
    violation_id: str,
    *,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    """AC-F1 + AC-F6: approve a pending violation.

    Returns: violation dict including ``approved_at`` + ``resumed_session_id``.
    Raises:
      - InvalidViolationInput: any required field missing.
      - ViolationNotFound: violation_id unknown.
      - ViolationAlreadyResolved: state was not pending (router → 409).
    """
    return _rl.approve_violation(
        violation_id,
        actor_user_id=actor_user_id,
        reason=reason,
    )


def reject_violation(
    violation_id: str,
    *,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    """AC-F8: reject a pending violation (session remains blocked).

    Returns: violation dict including ``rejected_at``.
    Raises:
      - InvalidViolationInput / ViolationNotFound / ViolationAlreadyResolved.
    """
    return _rl.reject_violation(
        violation_id,
        actor_user_id=actor_user_id,
        reason=reason,
    )


def reset_store() -> None:
    """Test helper: forwarded to ``services.red_lines.reset_store``."""
    _rl.reset_store()


__all__ = [
    # errors
    "ViolationServiceError",
    "InvalidViolationInput",
    "ViolationNotFound",
    "ViolationAlreadyResolved",
    "WorkspaceNotFound",
    # constants
    "VIOLATION_PENDING",
    "VIOLATION_APPROVED",
    "VIOLATION_REJECTED",
    "VIOLATION_STATUSES",
    # api
    "list_violations",
    "get_violation",
    "approve_violation",
    "reject_violation",
    "reset_store",
]
