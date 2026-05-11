"""T-007-02 / F-007: task_list view + 一括操作 REST endpoint.

Endpoint:
  GET  /api/task-list/view     filter + sort + pagination
  POST /api/task-list/bulk-update   一括更新 (status/priority/assigned_to/due_date)

T-007-02 AC:
  AC-1 UBIQUITOUS    : F-007 で list-view + bulk-update endpoint
  AC-2 EVENT-DRIVEN  : UI 操作 → backend state 反映 (POST 後 GET で観測可)
  AC-3 STATE-DRIVEN  : audit_logs emit + RLS は migration 側
  AC-4 UNWANTED      : invalid filter/sort/updates は 4xx + structured +
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.task_list_view import (
    MAX_BULK_SIZE,
    MAX_PAGE_SIZE,
    TaskListViewError,
    bulk_update,
    filter_and_sort,
    paginate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task-list", tags=["task-list-view"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("task-list-view audit emit failed: %s -- %s", event_type, e)


# ──────────────────────────────────────────────────────────────────────────
# Default loader: 既存 tasks 表から取得
# 注入式 (test では monkeypatch で差し替え可能)
# ──────────────────────────────────────────────────────────────────────────


async def _default_load_tasks(
    *, status: Optional[str], assigned_to: Optional[int],
    project_id: Optional[int],
) -> list[dict]:
    try:
        from db import async_db as aiosqlite
        from pathlib import Path
        DB = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
        conditions, params = [], []
        if status:
            conditions.append("status=?")
            params.append(status)
        if assigned_to is not None:
            conditions.append("assigned_to=?")
            params.append(assigned_to)
        if project_id is not None:
            conditions.append("project_id=?")
            params.append(project_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        async with aiosqlite.connect(DB) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                f"SELECT * FROM tasks {where} LIMIT 5000",
                tuple(params),
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("default load_tasks failed: %s", e)
        return []


async def _default_update_task(task_id: int, updates: dict) -> dict:
    try:
        from db import async_db as aiosqlite
        from pathlib import Path
        DB = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
        keys = list(updates.keys())
        set_clause = ", ".join(f"{k}=?" for k in keys) + (
            ", updated_at=datetime('now','localtime')"
        )
        values = [updates[k] for k in keys]
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                f"UPDATE tasks SET {set_clause} WHERE id=?",
                (*values, task_id),
            )
            await db.commit()
        return {"task_id": task_id, **updates}
    except Exception:
        raise


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2: list-view (GET)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/view")
async def list_view(
    status: Optional[str] = Query(None),
    assigned_to: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, Any]:
    if assigned_to is not None and assigned_to <= 0:
        raise _error("tasks.invalid_assigned_to",
                     "assigned_to must be > 0 when provided")
    if project_id is not None and project_id <= 0:
        raise _error("tasks.invalid_project_id",
                     "project_id must be > 0 when provided")

    try:
        items = await _default_load_tasks(
            status=status, assigned_to=assigned_to, project_id=project_id,
        )
        sorted_items = filter_and_sort(
            items, status=status, assigned_to=assigned_to,
            project_id=project_id, sort_by=sort_by, sort_order=sort_order,
        )
        pag = paginate(sorted_items, page=page, page_size=page_size)
    except TaskListViewError as e:
        raise _error("tasks.invalid_list_view", str(e))

    return pag.to_dict()


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3 / AC-4: bulk-update (POST)
# ──────────────────────────────────────────────────────────────────────────


class BulkUpdateRequest(BaseModel):
    task_ids: list[int]
    updates: dict
    actor_user_id: Optional[str] = None


@router.post("/bulk-update")
async def bulk_update_endpoint(body: BulkUpdateRequest) -> dict[str, Any]:
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("tasks.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not isinstance(body.task_ids, list) or not body.task_ids:
        raise _error("tasks.invalid_task_ids",
                     "task_ids must be a non-empty list")
    if len(body.task_ids) > MAX_BULK_SIZE:
        raise _error("tasks.bulk_too_large",
                     f"task_ids must be <= {MAX_BULK_SIZE} per request")
    if not isinstance(body.updates, dict) or not body.updates:
        raise _error("tasks.invalid_updates",
                     "updates must be a non-empty dict")

    try:
        result = await bulk_update(
            body.task_ids, body.updates,
            update_fn=_default_update_task,
        )
    except TaskListViewError as e:
        raise _error("tasks.invalid_updates", str(e))

    await _audit(
        "tasks.bulk.updated",
        user_id=body.actor_user_id,
        detail={
            "total": result.total,
            "success_count": len(result.updated),
            "failure_count": len(result.failed),
            "fields": sorted(body.updates.keys()),
        },
    )
    return result.to_dict()
