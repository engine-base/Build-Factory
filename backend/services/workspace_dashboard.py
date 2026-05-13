"""T-003-02: Workspace Dashboard KPI 集計サービス (REFACTOR / S2 / F-003).

既存 secretary_chat / delegation_service / workspace_service の symbol surface
は無改変. workspace 単位の 5 KPI を集計する read-only な薄い aggregator のみ
を追加する.

## 5 KPI (AC-1 UBIQUITOUS, S-012-workspace-dashboard.html mock 準拠)

  1. progress              : 全 task のうち完了割合 (0.0 - 1.0)
  2. completed_tasks       : 完了 task 件数
  3. running_sessions      : "running" 状態の session 件数
  4. monthly_cost_jpy      : 当月の cost_logs 合計 (JPY)
  5. pending_approvals     : pending / not yet approved の approval 件数

## AC マッピング (1:1)

  AC-1 UBIQUITOUS    : get_dashboard_stats() が 5 KPI を辞書で返す.
  AC-2 EVENT-DRIVEN  : aggregate 800ms (P95) 以内. 全て in-memory / SELECT
                       COUNT(*) なので余裕で達成.
  AC-3 STATE (#2)    : handoff は claude-agent-sdk Subagent (Task tool) を
                       使う. LangGraph / LangChain は本 module からも import
                       禁止 (本 service は handoff path に居る).
  AC-5 UNWANTED (#1) : workspace 所有 / member でなければ呼び出した caller 側で
                       403 を返す (本 service は permission check と orthogonal).
  AC-5 UNWANTED (#2) : LangGraph / LangChain を本 module / secretary_chat /
                       delegation_service が import したら lint で fail.

## 公開 API

  - DashboardStatsError (router で 4xx 変換)
  - DASHBOARD_KPI_KEYS: tuple[str, ...]  必須 5 件
  - get_dashboard_stats(workspace_id, *, now=None) -> dict[str, Any]
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH

logger = logging.getLogger(__name__)


class DashboardStatsError(RuntimeError):
    """Dashboard 入力 / 不変条件違反 (router 層で 4xx 変換)."""


# AC-1 UBIQUITOUS: 5 KPI 必須キー
DASHBOARD_KPI_KEYS: tuple[str, ...] = (
    "progress",
    "completed_tasks",
    "running_sessions",
    "monthly_cost_jpy",
    "pending_approvals",
)

# 完了タスクと見做す status 値
COMPLETED_TASK_STATUSES = ("done", "completed", "closed")
# 実行中 session と見做す status 値
RUNNING_SESSION_STATUSES = ("running", "executing", "in_progress")


def _validate_workspace_id(workspace_id: Any) -> int:
    if isinstance(workspace_id, bool) or not isinstance(workspace_id, int):
        raise DashboardStatsError("workspace_id must be int")
    if workspace_id <= 0:
        raise DashboardStatsError("workspace_id must be > 0")
    return workspace_id


async def _count_tasks(db, workspace_id: int) -> tuple[int, int]:
    """tasks table の (total, completed) 件数を返す.

    DB schema が無い環境 (Phase 1 dev) では (0, 0) を返す.
    """
    try:
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM tasks WHERE workspace_id = ?",
            (workspace_id,),
        )
        row = await cur.fetchone()
        total = (row["c"] if row else 0) or 0
    except Exception as e:  # pragma: no cover
        logger.warning("count tasks failed ws=%s: %s", workspace_id, e)
        return (0, 0)
    placeholders = ", ".join(["?"] * len(COMPLETED_TASK_STATUSES))
    try:
        cur = await db.execute(
            f"SELECT COUNT(*) AS c FROM tasks "
            f"WHERE workspace_id = ? AND status IN ({placeholders})",
            (workspace_id, *COMPLETED_TASK_STATUSES),
        )
        row = await cur.fetchone()
        completed = (row["c"] if row else 0) or 0
    except Exception:  # pragma: no cover
        completed = 0
    return total, completed


async def _count_running_sessions(db, workspace_id: int) -> int:
    placeholders = ", ".join(["?"] * len(RUNNING_SESSION_STATUSES))
    try:
        cur = await db.execute(
            f"SELECT COUNT(*) AS c FROM sessions "
            f"WHERE workspace_id = ? AND status IN ({placeholders})",
            (workspace_id, *RUNNING_SESSION_STATUSES),
        )
        row = await cur.fetchone()
        return (row["c"] if row else 0) or 0
    except Exception as e:  # pragma: no cover
        logger.warning("count sessions failed ws=%s: %s", workspace_id, e)
        return 0


async def _sum_monthly_cost(db, workspace_id: int, *, now: datetime) -> float:
    """当月の cost_logs 合計 (JPY).

    cost_logs.amount_jpy (or amount * 150 で換算) を月初〜月末で集計.
    table 不在環境では 0.0 を返す.
    """
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    # 次月 1 日
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        nxt = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = nxt.isoformat()
    try:
        cur = await db.execute(
            "SELECT COALESCE(SUM(amount_jpy), 0) AS s FROM cost_logs "
            "WHERE workspace_id = ? "
            "AND created_at >= ? AND created_at < ?",
            (workspace_id, month_start, month_end),
        )
        row = await cur.fetchone()
        return float((row["s"] if row else 0) or 0)
    except Exception as e:  # pragma: no cover (amount_jpy column 不在環境)
        logger.warning("sum monthly cost failed ws=%s: %s", workspace_id, e)
        return 0.0


async def _count_pending_approvals(db, workspace_id: int) -> int:
    try:
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM approval_queue "
            "WHERE workspace_id = ? AND status IN ('pending', 'awaiting')",
            (workspace_id,),
        )
        row = await cur.fetchone()
        return (row["c"] if row else 0) or 0
    except Exception as e:  # pragma: no cover
        logger.warning("count pending approvals failed ws=%s: %s", workspace_id, e)
        return 0


async def get_dashboard_stats(
    workspace_id: int,
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Workspace ダッシュボードの 5 KPI を集計して返す.

    Args:
      workspace_id : 対象 workspace id (> 0)
      now          : テスト注入用 (default: datetime.utcnow())

    Returns:
      {
        "workspace_id": int,
        "progress": float,            # 0.0-1.0
        "completed_tasks": int,
        "running_sessions": int,
        "monthly_cost_jpy": float,
        "pending_approvals": int,
        "total_tasks": int,           # progress 計算の分母 (debug 用)
        "computed_at": float,         # unix ts
        "duration_ms": int,           # 集計所要時間 (P95 検証用)
      }
    """
    wid = _validate_workspace_id(workspace_id)
    started = time.time()
    timestamp = (now or datetime.utcnow())

    async with aiosqlite.connect(DB_PATH) as db:
        total_tasks, completed = await _count_tasks(db, wid)
        running = await _count_running_sessions(db, wid)
        monthly_cost = await _sum_monthly_cost(db, wid, now=timestamp)
        pending = await _count_pending_approvals(db, wid)

    progress = (completed / total_tasks) if total_tasks > 0 else 0.0
    elapsed_ms = int((time.time() - started) * 1000)

    return {
        "workspace_id": wid,
        "progress": round(progress, 6),
        "completed_tasks": completed,
        "running_sessions": running,
        "monthly_cost_jpy": monthly_cost,
        "pending_approvals": pending,
        "total_tasks": total_tasks,
        "computed_at": started,
        "duration_ms": elapsed_ms,
    }
