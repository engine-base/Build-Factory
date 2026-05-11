"""T-010c-02 / F-010c: 親子昇格 (依存グラフ尊重) REST endpoint.

Endpoint:
  POST /api/tasks/elevate-priorities

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c 親子昇格 service + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + 計算結果は read-only (state mutate なし)
  AC-4 UNWANTED      : invalid input / cycle (409) は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.priority_elevation import (
    CycleDetectedError,
    PriorityElevationError,
    elevate_priorities,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks-priority-elevation"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("priority-elevation audit emit failed: %s -- %s", event_type, e)


class ElevateRequest(BaseModel):
    tasks: list[dict] = Field(default_factory=list)
    dependencies: list[dict] = Field(default_factory=list)
    actor_user_id: Optional[str] = None


@router.post("/elevate-priorities")
async def elevate_priorities_endpoint(req: ElevateRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("tasks.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not isinstance(req.tasks, list):
        raise _error("tasks.invalid_tasks", "tasks must be a list")
    if not isinstance(req.dependencies, list):
        raise _error("tasks.invalid_dependencies", "dependencies must be a list")
    if len(req.tasks) > 5000:
        raise _error("tasks.tasks_too_large", "tasks must be <= 5000")
    if len(req.dependencies) > 20000:
        raise _error("tasks.dependencies_too_large",
                     "dependencies must be <= 20000")

    try:
        report = elevate_priorities(req.tasks, req.dependencies)
    except CycleDetectedError as e:
        raise _error("tasks.cycle_detected", str(e), status_code=409)
    except PriorityElevationError as e:
        raise _error("tasks.elevate_invalid", str(e))

    await _audit(
        "tasks.priority.elevated",
        user_id=req.actor_user_id,
        detail={
            "total_tasks": report.total_tasks,
            "elevated_count": len(report.elevated),
        },
    )
    return report.to_dict()
