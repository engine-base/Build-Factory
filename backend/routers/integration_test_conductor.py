"""T-011-04: integration test conductor REST endpoint.

Endpoint:
  POST /api/integration-test/add               target 登録
  POST /api/integration-test/record            result 記録
  POST /api/integration-test/run               run_pipeline → order
  POST /api/integration-test/reset             target 削除
  GET  /api/integration-test/target/{id}       state
  GET  /api/integration-test/summary           aggregate

REUSE invariant: 既存 reviewer_loop / reviewer_persona / reviewer_turn_counter
無改変. 4xx mapping: invalid_input / cycle_detected / not_found.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import integration_test_conductor as itc

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/integration-test",
    tags=["integration-test"],
)


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _map_service_error(e: itc.IntegrationTestConductorError) -> HTTPException:
    msg = str(e)
    if "cycle" in msg.lower():
        return _error(
            "integration_test_conductor.cycle_detected",
            msg,
            status_code=400,
        )
    if "not found" in msg.lower() or "unknown dep" in msg.lower():
        return _error(
            "integration_test_conductor.not_found",
            msg,
            status_code=404,
        )
    return _error(
        "integration_test_conductor.invalid_input",
        msg,
        status_code=400,
    )


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "integration_test_conductor.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


class AddRequest(BaseModel):
    target_id: str
    deps: list[str] = Field(default_factory=list)
    actor_user_id: Optional[str] = None


class RecordRequest(BaseModel):
    target_id: str
    status: str
    output: Optional[str] = None
    actor_user_id: Optional[str] = None


class RunRequest(BaseModel):
    actor_user_id: Optional[str] = None


class ResetRequest(BaseModel):
    target_id: str
    actor_user_id: Optional[str] = None


@router.post("/add")
async def add_endpoint(body: AddRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return itc.add_target(
            body.target_id,
            deps=body.deps,
            actor_user_id=actor,
        )
    except itc.IntegrationTestConductorError as e:
        raise _map_service_error(e)


@router.post("/record")
async def record_endpoint(body: RecordRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return itc.record_result(
            body.target_id,
            body.status,
            output=body.output,
            actor_user_id=actor,
        )
    except itc.IntegrationTestConductorError as e:
        raise _map_service_error(e)


@router.post("/run")
async def run_endpoint(body: RunRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return itc.run_pipeline(actor_user_id=actor)
    except itc.IntegrationTestConductorError as e:
        raise _map_service_error(e)


@router.post("/reset")
async def reset_endpoint(body: ResetRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        removed = itc.reset(body.target_id)
    except itc.IntegrationTestConductorError as e:
        raise _map_service_error(e)
    return {"target_id": body.target_id.strip(), "removed": removed}


# Static path must precede dynamic /{target_id} so FastAPI routes correctly.
@router.get("/summary")
async def summary_endpoint() -> dict[str, Any]:
    return itc.get_summary()


@router.get("/target/{target_id}")
async def get_endpoint(target_id: str) -> dict[str, Any]:
    try:
        state = itc.get_state(target_id)
    except itc.IntegrationTestConductorError as e:
        raise _map_service_error(e)
    if state is None:
        raise _error(
            "integration_test_conductor.not_found",
            f"target not found: {target_id}",
            status_code=404,
        )
    return state
