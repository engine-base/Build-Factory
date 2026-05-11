"""T-008-01: bf_phases CRUD API.

  GET    /api/projects/{project_id}/phases       list_phases
  GET    /api/phases/{phase_id}                  get_phase
  POST   /api/projects/{project_id}/phases       create_phase
  PATCH  /api/phases/{phase_id}                  update_phase
  POST   /api/phases/{phase_id}/start            start_phase (in_progress)
  POST   /api/phases/{phase_id}/complete         complete_phase
  DELETE /api/phases/{phase_id}                  soft-delete (status='skipped')

Error contract:
  4xx: {detail: {code, message}}
    invalid_phase_no / invalid_status / invalid_name / phase_not_found /
    phase_duplicate
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import phase_service as ps
from services.phase_service import InvalidPhaseInput, PhaseNotFound

router = APIRouter(tags=["phases"])


class PhaseCreate(BaseModel):
    phase_no: int = Field(..., ge=1, le=10)
    name: str
    artifacts_dir: Optional[str] = None
    notes: Optional[str] = None


class PhaseUpdate(BaseModel):
    phase_no: Optional[int] = None
    name: Optional[str] = None
    status: Optional[str] = None
    artifacts_dir: Optional[str] = None
    notes: Optional[str] = None


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


@router.get("/api/projects/{project_id}/phases")
async def list_phases(project_id: int):
    phases = await ps.list_phases(project_id)
    return {"project_id": project_id, "phases": phases, "count": len(phases)}


@router.get("/api/phases/{phase_id}")
async def get_phase(phase_id: int):
    p = await ps.get_phase(phase_id)
    if not p:
        raise _err("phase_not_found", f"phase not found: {phase_id}", 404)
    return p


@router.post("/api/projects/{project_id}/phases")
async def create_phase(project_id: int, body: PhaseCreate):
    try:
        return await ps.create_phase(
            project_id=project_id,
            phase_no=body.phase_no,
            name=body.name,
            artifacts_dir=body.artifacts_dir,
            notes=body.notes,
        )
    except InvalidPhaseInput as e:
        msg = str(e)
        if "already exists" in msg:
            raise _err("phase_duplicate", msg, 409)
        if "name" in msg:
            raise _err("invalid_name", msg)
        raise _err("invalid_phase_no", msg)


@router.patch("/api/phases/{phase_id}")
async def update_phase(phase_id: int, body: PhaseUpdate):
    fields = body.model_dump(exclude_unset=True)
    try:
        return await ps.update_phase(phase_id, **fields)
    except PhaseNotFound as e:
        raise _err("phase_not_found", str(e), 404)
    except InvalidPhaseInput as e:
        msg = str(e)
        if "name" in msg:
            raise _err("invalid_name", msg)
        if "status" in msg:
            raise _err("invalid_status", msg)
        if "conflicts" in msg:
            raise _err("phase_duplicate", msg, 409)
        raise _err("invalid_phase_no", msg)


@router.post("/api/phases/{phase_id}/start")
async def start_phase(phase_id: int):
    try:
        return await ps.start_phase(phase_id)
    except PhaseNotFound as e:
        raise _err("phase_not_found", str(e), 404)


@router.post("/api/phases/{phase_id}/complete")
async def complete_phase(phase_id: int):
    try:
        return await ps.complete_phase(phase_id)
    except PhaseNotFound as e:
        raise _err("phase_not_found", str(e), 404)


@router.delete("/api/phases/{phase_id}")
async def delete_phase(phase_id: int):
    ok = await ps.delete_phase(phase_id)
    if not ok:
        raise _err("phase_not_found", f"phase not found: {phase_id}", 404)
    return {"deleted": True, "phase_id": phase_id}

# ──────────────────────────────────────────────────────────────────────────
# T-008-03: phase gate 評価 + auto unlock
# ──────────────────────────────────────────────────────────────────────────


import logging as _logging

_log = _logging.getLogger(__name__)


async def _audit_phase(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        _log.warning("phase audit emit failed: %s -- %s", event_type, e)


class GateRuleBody(BaseModel):
    min_completion_rate: float = 1.0
    required_artifact_types: list[str] = Field(default_factory=list)
    required_reviewer_approvals: int = 0
    allow_partial: bool = False


class EvaluateGateRequest(BaseModel):
    tasks: list[dict] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    approvals: int = 0
    rules: Optional[GateRuleBody] = None
    auto_unlock: bool = False
    next_phase_id: Optional[int] = None
    actor_user_id: Optional[str] = None


@router.post("/api/phases/{phase_id}/evaluate-gate")
async def evaluate_phase_gate(phase_id: int, body: EvaluateGateRequest):
    """T-008-03: gate 達成判定 (+ auto_unlock 指定時は次 phase を unlock)."""
    if phase_id <= 0:
        raise _err("invalid_phase_no", "phase_id must be > 0", 400)
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _err("unauthorized", "actor_user_id must not be empty when provided", 401)
    if body.approvals < 0:
        raise _err("invalid_approvals", "approvals must be >= 0", 400)
    if len(body.tasks) > 5000:
        raise _err("tasks_too_many", "tasks must be <= 5000", 400)
    if len(body.artifacts) > 5000:
        raise _err("artifacts_too_many", "artifacts must be <= 5000", 400)
    if body.next_phase_id is not None and body.next_phase_id <= 0:
        raise _err("invalid_next_phase_id", "next_phase_id must be > 0 when provided", 400)

    phase = await ps.get_phase(phase_id)
    if phase is None:
        raise _err("phase_not_found", f"phase not found: {phase_id}", 404)

    from services.phase_gate_evaluator import (
        GateRule, PhaseGateError, evaluate_gate, auto_unlock_next,
    )

    rule_dict = body.rules.model_dump() if body.rules else {}
    try:
        rule = GateRule(**rule_dict)
        evaluation = evaluate_gate(
            phase, body.tasks,
            rules=rule,
            artifacts=body.artifacts,
            approvals=body.approvals,
        )
    except PhaseGateError as e:
        raise _err("gate_evaluation_invalid", str(e), 400)

    out: dict = {"evaluation": evaluation.to_dict(), "unlocked": None}

    # auto_unlock 実行
    if body.auto_unlock:
        if not evaluation.can_auto_unlock:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "gate_not_passed",
                    "message": f"gate not passed; blockers={evaluation.blockers}",
                },
            )
        try:
            unlocked = await auto_unlock_next(
                phase_id, body.next_phase_id,
                complete_fn=ps.complete_phase,
                start_fn=ps.start_phase,
            )
            out["unlocked"] = {
                "completed_id": phase_id,
                "next_started_id": body.next_phase_id,
            }
        except PhaseGateError as e:
            raise _err("auto_unlock_invalid", str(e), 400)
        except PhaseNotFound as e:
            raise _err("phase_not_found", str(e), 404)

    await _audit_phase(
        "phases.gate.evaluated",
        user_id=body.actor_user_id,
        detail={
            "phase_id": phase_id,
            "overall": evaluation.overall,
            "completion_rate": round(evaluation.completion_rate, 4),
            "auto_unlock": body.auto_unlock and out["unlocked"] is not None,
            "next_phase_id": body.next_phase_id if out["unlocked"] else None,
        },
    )
    return out
