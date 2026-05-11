"""T-006-03 / F-006: impact-analysis endpoint.

Endpoint:
  POST /api/tasks/{task_id}/impact   downstream task 一覧を返す

T-006-03 AC:
  AC-1 UBIQUITOUS    : F-006 impact-analysis endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit
  AC-4 UNWANTED      : invalid task_id / cycle / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.impact_analyzer import (
    CycleDetectedError,
    ImpactAnalyzerError,
    compute_impact,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("impact-analyzer audit emit failed: %s -- %s", event_type, e)


# default loader: services.task_dependency_service 経由
async def _default_deps_loader(parent_id: int) -> list[dict]:
    try:
        from services.task_dependency_service import list_dependencies_by_task
        rows = await list_dependencies_by_task(parent_id)
        return rows if isinstance(rows, list) else []
    except Exception as e:
        logger.warning("default deps_loader failed for %s: %s", parent_id, e)
        return []


class ImpactRequest(BaseModel):
    max_depth: int = 20
    actor_user_id: Optional[str] = None


@router.post("/{task_id}/impact")
async def analyze_impact(task_id: int, body: ImpactRequest) -> dict[str, Any]:
    if task_id <= 0:
        raise _error("impact.invalid_task_id", "task_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("impact.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if body.max_depth <= 0 or body.max_depth > 100:
        raise _error("impact.invalid_max_depth", "max_depth must be 1..100")

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

    await _audit(
        "tasks.impact.analyzed",
        user_id=body.actor_user_id,
        detail={
            "task_id": task_id,
            "total": report.total,
            "max_depth": report.max_depth,
        },
    )
    return report.to_dict()
