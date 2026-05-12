"""T-006-02: task-decomposition AI + EARS AC REST endpoint.

Endpoint:
  POST /api/task-decomposition/decompose  親 brief を sub-tasks に分解.

既存 `routers/tasks.py` (project / task CRUD) は **無改変** (REUSE).
本 router は新規 prefix `/api/task-decomposition` でぶつからない.

T-006-02 AC マッピング:
  AC-1 UBIQUITOUS    : decompose endpoint + ears_classifier 連携可能.
  AC-2 EVENT-DRIVEN  : 2 秒以内 / {detail:{code,message}} 構造化エラー.
  AC-3 STATE-DRIVEN  : audit_logs emit / persistent state 既存 task table 無改変.
  AC-4 UNWANTED      : invalid brief / count / empty actor で 4xx + structured.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.task_decomposition import (
    DEFAULT_SUBTASK_COUNT,
    MAX_SUBTASK_COUNT,
    MIN_SUBTASK_COUNT,
    decompose as decompose_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task-decomposition", tags=["task-decomposition"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning(
            "task-decomposition audit emit failed: %s -- %s", event_type, e,
        )


class DecomposeRequest(BaseModel):
    parent_brief: str = Field(..., min_length=1, max_length=2000)
    subtask_count: int = Field(
        default=DEFAULT_SUBTASK_COUNT,
        ge=MIN_SUBTASK_COUNT,
        le=MAX_SUBTASK_COUNT,
    )
    use_backend: bool = True
    actor_user_id: Optional[str] = None


@router.post("/decompose")
async def decompose_endpoint(body: DecomposeRequest) -> dict[str, Any]:
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error(
            "task_decomposition.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )

    try:
        result = decompose_service(
            body.parent_brief,
            subtask_count=body.subtask_count,
            use_backend=body.use_backend,
        )
    except ValueError as e:
        raise _error("task_decomposition.invalid_input", str(e))

    await _audit(
        "task_decomposition.decomposed",
        user_id=body.actor_user_id,
        detail={
            "count_returned": result["config"]["count_returned"],
            "backend_used": result["config"]["backend_used"],
        },
    )
    return result
