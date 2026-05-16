"""T-V3-B-27 / F-024: Account dashboard aggregation service.

Powers ``GET /api/accounts/{id}/dashboard`` (S-006 account_dashboard).
Aggregates per-workspace KPI for every workspace the caller belongs to within
the requested account, then rolls them up into account-level totals.

## AC mapping (T-V3-B-27 functional Tier)

  AC-F4 EVENT-DRIVEN : ``get_account_dashboard`` aggregates KPI across all
                       workspaces the caller belongs to within the account.
  AC-F8 EVENT-DRIVEN : Returns ``dict`` matching openapi.yaml#/api/accounts/
                       {id}/dashboard (workspaces + kpi).

This module REUSES ``services.workspace_dashboard.get_dashboard_stats`` (T-003-02)
for per-workspace KPI computation — no duplicate SQL.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AccountDashboardError(RuntimeError):
    """Raised on invariant violation (router converts to 4xx)."""


class AccountNotFoundError(AccountDashboardError):
    """404: account does not exist."""


class AccountForbiddenError(AccountDashboardError):
    """403: caller is not a member of the account."""


def _validate_account_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AccountDashboardError("account_id must be int")
    if value <= 0:
        raise AccountDashboardError("account_id must be > 0")
    return value


async def _list_caller_workspaces_in_account(
    account_id: int, user_id: str,
) -> list[dict]:
    """Workspaces under ``account_id`` where ``user_id`` is a member.

    Joins ``workspaces`` x ``workspace_members``. Returns rows with id/name/
    status/role (caller's role).
    """
    try:
        from db import async_db as aiosqlite
        from db.queries import DB_PATH
    except Exception as e:  # pragma: no cover
        logger.warning("db unavailable: %s", e)
        return []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                """SELECT w.id, w.name, w.status, wm.role AS member_role
                   FROM workspaces w
                   JOIN workspace_members wm ON wm.workspace_id = w.id
                   WHERE w.account_id = ? AND wm.user_id = ?
                   ORDER BY w.updated_at DESC""",
                (account_id, user_id),
            )
        return [dict(r) for r in rows or []]
    except Exception as e:
        logger.warning(
            "list_caller_workspaces_in_account failed acct=%s user=%s: %s",
            account_id, user_id, e,
        )
        return []


async def _get_account(account_id: int) -> Optional[dict]:
    try:
        from services import account_service as acc
        return await acc.get_account(account_id)
    except Exception as e:
        logger.warning("account_service.get_account failed acct=%s: %s", account_id, e)
        return None


async def _is_account_member(account_id: int, user_id: str) -> bool:
    """True if ``user_id`` is in ``account_members`` for ``account_id``."""
    try:
        from db import async_db as aiosqlite
        from db.queries import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT 1 FROM account_members WHERE account_id = ? AND user_id = ? LIMIT 1",
                (account_id, user_id),
            )
            row = await cur.fetchone()
        return bool(row)
    except Exception as e:
        logger.warning("is_account_member failed acct=%s user=%s: %s", account_id, user_id, e)
        return False


async def get_account_dashboard(
    account_id: Any,
    *,
    user_id: str,
) -> dict[str, Any]:
    """Return the per-account dashboard payload for ``user_id``.

    Raises:
      AccountDashboardError    : on invariant violation (mapped to 422 by router)
      AccountNotFoundError     : account row missing (404)
      AccountForbiddenError    : caller is not a member of the account (403)

    Returns:
      Dict matching openapi.yaml#/api/accounts/{id}/dashboard::
        {
          account_id: int,
          workspaces: [WorkspaceSummary, ...],
          kpi: AccountKPIAggregate,
          computed_at: float,
          duration_ms: int,
        }
    """
    aid = _validate_account_id(account_id)
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        raise AccountDashboardError("user_id must be non-empty string")

    started = time.time()

    # 404: account must exist.
    account = await _get_account(aid)
    if not account:
        raise AccountNotFoundError(f"account not found: {aid}")

    # 403: caller must be a member of the account.
    is_member = await _is_account_member(aid, user_id)
    if not is_member:
        raise AccountForbiddenError(
            f"user {user_id} is not a member of account {aid}",
        )

    # Aggregate per-workspace KPI (REUSE workspace_dashboard).
    rows = await _list_caller_workspaces_in_account(aid, user_id)

    try:
        from services import workspace_dashboard as wd
    except Exception as e:  # pragma: no cover
        logger.warning("workspace_dashboard import failed: %s", e)
        wd = None  # type: ignore[assignment]

    workspaces: list[dict[str, Any]] = []
    agg_progress_sum = 0.0
    agg_completed = 0
    agg_running = 0
    agg_cost = 0.0
    agg_pending = 0
    for r in rows:
        wid = r.get("id")
        if not isinstance(wid, int):
            continue
        stats: dict[str, Any] = {}
        if wd is not None:
            try:
                stats = await wd.get_dashboard_stats(wid)
            except Exception as e:
                logger.warning("get_dashboard_stats failed ws=%s: %s", wid, e)
                stats = {}
        progress = float(stats.get("progress", 0.0) or 0.0)
        completed = int(stats.get("completed_tasks", 0) or 0)
        running = int(stats.get("running_sessions", 0) or 0)
        cost = float(stats.get("monthly_cost_jpy", 0.0) or 0.0)
        pending = int(stats.get("pending_approvals", 0) or 0)
        workspaces.append({
            "id": wid,
            "name": r.get("name") or "",
            "status": r.get("status"),
            "role": r.get("member_role"),
            "progress": progress,
            "completed_tasks": completed,
            "running_sessions": running,
            "monthly_cost_jpy": cost,
            "pending_approvals": pending,
        })
        agg_progress_sum += progress
        agg_completed += completed
        agg_running += running
        agg_cost += cost
        agg_pending += pending

    n = len(workspaces)
    avg_progress = (agg_progress_sum / n) if n else 0.0

    return {
        "account_id": aid,
        "workspaces": workspaces,
        "kpi": {
            "workspace_count": n,
            "total_progress": round(avg_progress, 6),
            "completed_tasks": agg_completed,
            "running_sessions": agg_running,
            "monthly_cost_jpy": agg_cost,
            "pending_approvals": agg_pending,
        },
        "computed_at": started,
        "duration_ms": int((time.time() - started) * 1000),
    }
