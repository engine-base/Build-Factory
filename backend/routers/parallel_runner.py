"""T-010c-01 / F-010c: 並列タスク実行制御 endpoint.

既存 task_executor / workflows と連携するための observation/control endpoint.

Endpoint:
  GET    /api/parallel-runner/stats           実行統計
  GET    /api/parallel-runner/outcomes/{id}   単一 outcome
  POST   /api/parallel-runner/configure       max_concurrency 変更 (closes existing)
  POST   /api/parallel-runner/submit-noop     test 用 no-op task 投入

T-010c-01 AC:
  AC-1 UBIQUITOUS    : F-010c の並列実行 service + observation endpoint
  AC-2 EVENT-DRIVEN  : action ごとに audit_logs に emit + 2 秒以内 response
  AC-3 STATE-DRIVEN  : 既存 task_executor の API は不変 (REFACTOR backwards compat) +
                       service 単体の cov 95%+
  AC-4 UNWANTED      : invalid max_concurrency / task_id / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import parallel_task_runner as ptr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/parallel-runner", tags=["parallel-runner"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("parallel-runner audit emit failed: %s -- %s", event_type, e)


@router.get("/stats")
async def stats() -> dict[str, Any]:
    return ptr.get_runner().stats()


@router.get("/outcomes/{task_id}")
async def get_outcome(task_id: int) -> dict[str, Any]:
    if task_id <= 0:
        raise _error("parallel.invalid_task_id", "task_id must be > 0")
    runner = ptr.get_runner()
    outcome = runner.get_outcome(task_id)
    if outcome is None:
        raise _error("parallel.outcome_not_found",
                     f"outcome not found for task_id={task_id}",
                     status_code=404)
    return outcome.to_dict()


class ConfigureRequest(BaseModel):
    max_concurrency: int = Field(..., ge=1, le=100)
    actor_user_id: Optional[str] = None


@router.post("/configure")
async def configure(req: ConfigureRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("parallel.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        ptr.reset_runner(max_concurrency=req.max_concurrency)
    except ptr.ParallelRunnerError as e:
        raise _error("parallel.invalid_max_concurrency", str(e))
    await _audit(
        "parallel.runner.configured",
        user_id=req.actor_user_id,
        detail={"max_concurrency": req.max_concurrency},
    )
    return ptr.get_runner().stats()


class SubmitNoopRequest(BaseModel):
    task_id: int
    delay_ms: int = Field(0, ge=0, le=10000)
    actor_user_id: Optional[str] = None


@router.post("/submit-noop")
async def submit_noop(req: SubmitNoopRequest) -> dict[str, Any]:
    """test 用: no-op (sleep) task を 1 件投入. 完了まで待って outcome を返す."""
    if req.task_id <= 0:
        raise _error("parallel.invalid_task_id", "task_id must be > 0")
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("parallel.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)

    runner = ptr.get_runner()
    if runner.closed:
        raise _error("parallel.runner_closed",
                     "runner is closed; configure first", status_code=503)

    async def _noop() -> str:
        if req.delay_ms > 0:
            await asyncio.sleep(req.delay_ms / 1000.0)
        return "ok"

    try:
        outcome = await runner.submit(req.task_id, _noop)
    except ptr.ParallelRunnerError as e:
        raise _error("parallel.submit_failed", str(e))
    await _audit(
        "parallel.task.submitted",
        user_id=req.actor_user_id,
        detail={
            "task_id": req.task_id,
            "status": outcome.status,
            "delay_ms": req.delay_ms,
        },
    )
    return outcome.to_dict()
