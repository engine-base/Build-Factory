"""T-011-02: reviewer turn counter REST endpoint.

Endpoint:
  POST /api/reviewer-turn/increment        target の count を +1
  POST /api/reviewer-turn/reset            target を削除
  GET  /api/reviewer-turn/{target_id}      state 取得 (404 if absent)
  GET  /api/reviewer-turn/active           active 一覧 (count desc)

REUSE invariant: 既存 reviewer.py / reviewer_loop.py / reviewer_persona.py 無改変.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import reviewer_turn_counter as rtc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviewer-turn", tags=["reviewer-turn"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _map_service_error(e: rtc.ReviewerTurnCounterError) -> HTTPException:
    msg = str(e)
    if "not_found" in msg or "not found" in msg:
        return _error("reviewer_turn_counter.not_found", msg, status_code=404)
    return _error("reviewer_turn_counter.invalid_input", msg, status_code=400)


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "reviewer_turn_counter.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


class IncrementRequest(BaseModel):
    target_id: str
    threshold: int = Field(
        default=rtc.MAX_TURNS_DEFAULT,
        ge=rtc.MIN_THRESHOLD,
        le=rtc.MAX_THRESHOLD,
    )
    actor_user_id: Optional[str] = None


class ResetRequest(BaseModel):
    target_id: str
    actor_user_id: Optional[str] = None


@router.post("/increment")
async def increment_endpoint(body: IncrementRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return rtc.increment(
            body.target_id,
            actor_user_id=actor,
            threshold=body.threshold,
        )
    except rtc.ReviewerTurnCounterError as e:
        raise _map_service_error(e)


@router.post("/reset")
async def reset_endpoint(body: ResetRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        removed = rtc.reset(body.target_id)
    except rtc.ReviewerTurnCounterError as e:
        raise _map_service_error(e)
    return {"target_id": body.target_id.strip(), "removed": removed}


# NOTE: Static path "/active" must be declared BEFORE the dynamic "/{target_id}"
# route so FastAPI routes "active" to the static handler instead of treating it
# as a target_id value.
@router.get("/active")
async def active_endpoint(
    min_count: int = Query(1, ge=0, le=rtc.MAX_COUNT),
    threshold: int = Query(
        rtc.MAX_TURNS_DEFAULT,
        ge=rtc.MIN_THRESHOLD,
        le=rtc.MAX_THRESHOLD,
    ),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    _check_actor(actor_user_id)
    try:
        items = rtc.list_active(min_count=min_count, threshold=threshold)
    except rtc.ReviewerTurnCounterError as e:
        raise _map_service_error(e)
    return {
        "threshold": threshold,
        "min_count": min_count,
        "count": len(items),
        "items": items,
    }


@router.get("/{target_id}")
async def get_endpoint(
    target_id: str,
    threshold: int = Query(
        rtc.MAX_TURNS_DEFAULT,
        ge=rtc.MIN_THRESHOLD,
        le=rtc.MAX_THRESHOLD,
    ),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    _check_actor(actor_user_id)
    try:
        state = rtc.get_state(target_id, threshold=threshold)
    except rtc.ReviewerTurnCounterError as e:
        raise _map_service_error(e)
    if state is None:
        raise _error(
            "reviewer_turn_counter.not_found",
            f"target not found: {target_id}",
            status_code=404,
        )
    return state
