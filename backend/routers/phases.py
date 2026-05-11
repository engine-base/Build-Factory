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