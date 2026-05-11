"""T-010c-03 / F-010c: 完了次第キュー補充 (FIFO + priority) REST endpoint.

Endpoint:
  POST /api/queue/enqueue                   enqueue 1 件
  POST /api/queue/dequeue                   dequeue 1 件 (priority 順 → FIFO)
  POST /api/queue/{item_id}/done            mark_done
  POST /api/queue/{item_id}/failed          mark_failed (error 文字列付き)
  GET  /api/queue/stats                     全体統計
  GET  /api/queue/peek                      次に dequeue される item を peek
  POST /api/queue/configure                 max_size 変更 (queue 再生成)

T-010c-03 AC:
  AC-1 UBIQUITOUS    : F-010c queue 補充 endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + priority/FIFO 順序保証
  AC-4 UNWANTED      : invalid input / full queue は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import priority_queue as pq

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/queue", tags=["priority-queue"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("priority-queue audit emit failed: %s -- %s", event_type, e)


class EnqueueRequest(BaseModel):
    task_id: int
    priority: str = Field("medium", description="urgent / high / medium / low")
    payload: dict = Field(default_factory=dict)
    actor_user_id: Optional[str] = None


class FailRequest(BaseModel):
    error: str
    actor_user_id: Optional[str] = None


class ConfigureRequest(BaseModel):
    max_size: int = Field(..., ge=1, le=pq.MAX_QUEUE_SIZE)
    actor_user_id: Optional[str] = None


class DequeueRequest(BaseModel):
    actor_user_id: Optional[str] = None


@router.post("/enqueue")
async def enqueue(req: EnqueueRequest) -> dict[str, Any]:
    if req.task_id <= 0:
        raise _error("queue.invalid_task_id", "task_id must be > 0")
    if req.priority not in pq.VALID_PRIORITIES:
        raise _error(
            "queue.invalid_priority",
            f"priority must be one of {pq.VALID_PRIORITIES}",
        )
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("queue.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)

    q = pq.get_queue()
    try:
        item = q.enqueue(
            task_id=req.task_id,
            priority=req.priority,
            payload=req.payload or {},
        )
    except pq.PriorityQueueError as e:
        # full の場合は 409
        msg = str(e)
        if "queue full" in msg:
            raise _error("queue.full", msg, status_code=409)
        raise _error("queue.invalid", msg)

    await _audit(
        "queue.enqueued",
        user_id=req.actor_user_id,
        detail={"item_id": item.id, "task_id": req.task_id,
                 "priority": req.priority},
    )
    return item.to_dict()


@router.post("/dequeue")
async def dequeue(req: DequeueRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("queue.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    q = pq.get_queue()
    item = q.dequeue()
    if item is None:
        return {"item": None}
    await _audit(
        "queue.dequeued",
        user_id=req.actor_user_id,
        detail={"item_id": item.id, "task_id": item.task_id,
                 "priority": item.priority},
    )
    return {"item": item.to_dict()}


@router.post("/{item_id}/done")
async def mark_done(
    item_id: int,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    if item_id <= 0:
        raise _error("queue.invalid_id", "item_id must be > 0")
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error("queue.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    q = pq.get_queue()
    ok = q.mark_done(item_id)
    if not ok:
        # item が存在しないか processing でない
        item = q.get_item(item_id)
        if item is None:
            raise _error("queue.not_found",
                         f"item not found: {item_id}", status_code=404)
        raise _error("queue.invalid_state",
                     f"item not in 'processing' state (got {item.status})",
                     status_code=409)
    await _audit(
        "queue.item.done",
        user_id=actor_user_id,
        detail={"item_id": item_id},
    )
    return {"ok": True, "item_id": item_id}


@router.post("/{item_id}/failed")
async def mark_failed(item_id: int, body: FailRequest) -> dict[str, Any]:
    if item_id <= 0:
        raise _error("queue.invalid_id", "item_id must be > 0")
    if not body.error or not body.error.strip():
        raise _error("queue.invalid_error", "error must not be empty")
    if len(body.error) > 2000:
        raise _error("queue.error_too_long", "error must be <= 2000 chars")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("queue.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    q = pq.get_queue()
    ok = q.mark_failed(item_id, body.error)
    if not ok:
        item = q.get_item(item_id)
        if item is None:
            raise _error("queue.not_found",
                         f"item not found: {item_id}", status_code=404)
        raise _error("queue.invalid_state",
                     f"item not in 'processing' state (got {item.status})",
                     status_code=409)
    await _audit(
        "queue.item.failed",
        user_id=body.actor_user_id,
        detail={"item_id": item_id, "error_len": len(body.error)},
    )
    return {"ok": True, "item_id": item_id}


@router.get("/stats")
async def stats() -> dict[str, Any]:
    return pq.get_queue().stats()


@router.get("/peek")
async def peek() -> dict[str, Any]:
    item = pq.get_queue().peek_next()
    return {"item": item.to_dict() if item else None}


@router.post("/configure")
async def configure(req: ConfigureRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("queue.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        pq.reset_queue(max_size=req.max_size)
    except pq.PriorityQueueError as e:
        raise _error("queue.invalid_max_size", str(e))
    await _audit(
        "queue.configured",
        user_id=req.actor_user_id,
        detail={"max_size": req.max_size},
    )
    return pq.get_queue().stats()
