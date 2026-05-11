"""T-009-03 / F-009: 影響範囲 AI ハイライト REST endpoint.

Endpoint:
  POST /api/tasks/{task_id}/impact/highlight
    body: {max_depth, actor_user_id, tasks_meta}
    response: HighlightReport (severity / suggested_action / grouped_by_phase)

T-009-03 AC:
  AC-1 UBIQUITOUS    : F-009 で highlight endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit
  AC-4 UNWANTED      : invalid input は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.impact_analyzer import (
    CycleDetectedError,
    ImpactAnalyzerError,
    compute_impact,
)
from services.impact_highlight import (
    ImpactHighlightError,
    compute_highlights,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks-impact-highlight"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("impact-highlight audit emit failed: %s -- %s", event_type, e)


async def _default_deps_loader(parent_id: int) -> list[dict]:
    try:
        from services.task_dependency_service import list_dependencies_by_task
        rows = await list_dependencies_by_task(parent_id)
        return rows if isinstance(rows, list) else []
    except Exception as e:
        logger.warning("default deps_loader failed for %s: %s", parent_id, e)
        return []


class HighlightRequest(BaseModel):
    max_depth: int = Field(20, ge=1, le=100)
    actor_user_id: Optional[str] = None
    tasks_meta: dict = Field(default_factory=dict)  # {task_id (as str): {title,...}}


@router.post("/{task_id}/impact/highlight")
async def highlight_impact(task_id: int, body: HighlightRequest) -> dict[str, Any]:
    if task_id <= 0:
        raise _error("impact.invalid_task_id", "task_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("impact.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if body.max_depth <= 0 or body.max_depth > 100:
        raise _error("impact.invalid_max_depth", "max_depth must be 1..100")
    if not isinstance(body.tasks_meta, dict):
        raise _error("impact.invalid_tasks_meta", "tasks_meta must be a dict")
    if len(body.tasks_meta) > 5000:
        raise _error("impact.tasks_meta_too_large",
                     "tasks_meta must be <= 5000 entries")

    # impact 計算
    try:
        report = await compute_impact(
            task_id,
            deps_loader=_default_deps_loader,
            max_depth=body.max_depth,
        )
    except CycleDetectedError as e:
        raise _error("impact.cycle_detected", str(e), status_code=409)
    except ImpactAnalyzerError as e:
        raise _error("impact.invalid", str(e))

    # tasks_meta は key が str (JSON) なので int に変換
    meta_typed: dict[int, dict] = {}
    for k, v in body.tasks_meta.items():
        try:
            tid = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            meta_typed[tid] = v

    # highlight 計算
    try:
        highlight = compute_highlights(report.to_dict(), tasks_meta=meta_typed)
    except ImpactHighlightError as e:
        raise _error("impact.highlight_invalid", str(e))

    await _audit(
        "tasks.impact.highlighted",
        user_id=body.actor_user_id,
        detail={
            "task_id": task_id,
            "total": highlight.total,
            "high_count": highlight.high_count,
            "medium_count": highlight.medium_count,
            "low_count": highlight.low_count,
        },
    )
    return highlight.to_dict()
