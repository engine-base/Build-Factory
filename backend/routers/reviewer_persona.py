"""T-011-01: Reviewer AI persona REST endpoint.

既存 `backend/routers/reviewer.py` (壁打ち loop CRUD) は **完全無改変** (REFACTOR).
本 router は新規 prefix `/api/reviewer-persona` で 3-phase Plan/Gen/Eval を提供.

Endpoints:
  POST /api/reviewer-persona/plan      Phase 1 plan_review
  POST /api/reviewer-persona/generate  Phase 2 generate_review
  POST /api/reviewer-persona/evaluate  Phase 3 evaluate_review
  POST /api/reviewer-persona/full      Plan → Gen → Eval chain
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import reviewer_persona as rp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviewer-persona", tags=["reviewer-persona"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "reviewer_persona.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


def _map_service_error(e: rp.ReviewerPersonaError) -> HTTPException:
    return _error("reviewer_persona.invalid_input", str(e), status_code=400)


class PlanRequest(BaseModel):
    review_kind: str = Field(default="task_review")
    target_artifact_ids: list[str]
    use_backend: bool = True
    actor_user_id: Optional[str] = None


class GenerateRequest(BaseModel):
    plan: dict
    use_backend: bool = True
    actor_user_id: Optional[str] = None


class EvaluateRequest(BaseModel):
    review: dict
    use_backend: bool = True
    pass_threshold: float = rp.DEFAULT_PASS_THRESHOLD
    actor_user_id: Optional[str] = None


class FullRequest(BaseModel):
    review_kind: str = Field(default="task_review")
    target_artifact_ids: list[str]
    use_backend: bool = True
    pass_threshold: float = rp.DEFAULT_PASS_THRESHOLD
    actor_user_id: Optional[str] = None


@router.post("/plan")
async def plan_endpoint(body: PlanRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return rp.plan_review(
            body.review_kind,
            body.target_artifact_ids,
            use_backend=body.use_backend,
            actor_user_id=actor,
        )
    except rp.ReviewerPersonaError as e:
        raise _map_service_error(e)


@router.post("/generate")
async def generate_endpoint(body: GenerateRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return rp.generate_review(
            body.plan,
            use_backend=body.use_backend,
            actor_user_id=actor,
        )
    except rp.ReviewerPersonaError as e:
        raise _map_service_error(e)


@router.post("/evaluate")
async def evaluate_endpoint(body: EvaluateRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return rp.evaluate_review(
            body.review,
            use_backend=body.use_backend,
            pass_threshold=body.pass_threshold,
            actor_user_id=actor,
        )
    except rp.ReviewerPersonaError as e:
        raise _map_service_error(e)


@router.post("/full")
async def full_endpoint(body: FullRequest) -> dict[str, Any]:
    actor = _check_actor(body.actor_user_id)
    try:
        return rp.run_plan_gen_eval(
            body.review_kind,
            body.target_artifact_ids,
            use_backend=body.use_backend,
            pass_threshold=body.pass_threshold,
            actor_user_id=actor,
        )
    except rp.ReviewerPersonaError as e:
        raise _map_service_error(e)
