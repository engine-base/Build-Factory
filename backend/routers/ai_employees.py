"""T-022-03 / F-022: AI 社員 CRUD API (existing employees.py 拡張).

既存の legacy routers/employees.py (company-os) は不変. Build-Factory M-22
schema (ai_employees + ai_personas) に対応する CRUD endpoint を
/api/ai-employees, /api/ai-personas として追加する.

Endpoint:
  personas:
    POST   /api/ai-personas
    GET    /api/ai-personas
    GET    /api/ai-personas/{id}
    DELETE /api/ai-personas/{id}
  employees:
    POST   /api/ai-employees
    GET    /api/ai-employees                    workspace_id / role_level filter
    GET    /api/ai-employees/{id}
    PATCH  /api/ai-employees/{id}               display_name / persona_id / role_level 更新
    POST   /api/ai-employees/{id}/retire        論理削除 + reason
    POST   /api/ai-employees/{id}/reactivate    退職取消
    DELETE /api/ai-employees/{id}               完全削除

AC マッピング:
  AC-1 UBIQUITOUS    : F-022 AI 社員 CRUD (REFACTOR 既存 employees.py 拡張)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 routers/employees.py / staff.py / staff_service.py 不変 +
                       audit emit (employee.created/updated/retired/reactivated/deleted +
                       persona.created/deleted)
  AC-4 UNWANTED      : invalid input / duplicate key / unknown persona / 退職済再退職 を
                       全て 4xx + structured / 失敗時 audit 非発行
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import ai_employee_store as aes

logger = logging.getLogger(__name__)

employees_router = APIRouter(prefix="/api/ai-employees", tags=["ai-employees"])
personas_router = APIRouter(prefix="/api/ai-personas", tags=["ai-personas"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("ai-employee audit emit failed: %s -- %s", event_type, e)


def _check_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("ai_employee.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)


def _map_error(e: aes.AIEmployeeError) -> HTTPException:
    msg = str(e)
    if "already exists" in msg or "already retired" in msg or "already active" in msg:
        return _error("ai_employee.conflict", msg, status_code=409)
    if "not found" in msg:
        return _error("ai_employee.not_found", msg, status_code=404)
    if "max " in msg:
        return _error("ai_employee.quota_exceeded", msg, status_code=409)
    return _error("ai_employee.invalid", msg)


# ──────────────────────────────────────────────────────────────────────
# personas
# ──────────────────────────────────────────────────────────────────────


class PersonaCreate(BaseModel):
    persona_key: str
    persona_name: str
    personality: Optional[str] = None
    tone_style: Optional[str] = None
    catchphrase: Optional[str] = None
    specialty: Optional[str] = None
    handles: Optional[str] = None
    avatar_lucide: Optional[str] = None
    metadata: Optional[dict] = None
    actor_user_id: Optional[str] = None


@personas_router.post("")
async def create_persona(body: PersonaCreate) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    try:
        p = aes.get_store().create_persona(
            body.persona_key, body.persona_name,
            personality=body.personality,
            tone_style=body.tone_style,
            catchphrase=body.catchphrase,
            specialty=body.specialty,
            handles=body.handles,
            avatar_lucide=body.avatar_lucide,
            metadata=body.metadata,
        )
    except aes.AIEmployeeError as e:
        raise _map_error(e)
    await _audit(
        "ai_persona.created",
        user_id=body.actor_user_id,
        detail={"persona_id": p.id, "persona_key": p.persona_key},
    )
    return p.to_dict()


@personas_router.get("")
async def list_personas() -> dict[str, Any]:
    items = aes.get_store().list_personas()
    return {"count": len(items), "personas": [p.to_dict() for p in items]}


@personas_router.get("/{persona_id}")
async def get_persona(persona_id: int) -> dict[str, Any]:
    if persona_id <= 0:
        raise _error("ai_employee.invalid", "persona_id must be > 0")
    p = aes.get_store().get_persona(persona_id)
    if p is None:
        raise _error("ai_employee.not_found",
                     f"persona not found: {persona_id}", status_code=404)
    return p.to_dict()


@personas_router.delete("/{persona_id}")
async def delete_persona(
    persona_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    _check_actor(actor_user_id)
    if persona_id <= 0:
        raise _error("ai_employee.invalid", "persona_id must be > 0")
    ok = aes.get_store().delete_persona(persona_id)
    if not ok:
        raise _error("ai_employee.not_found",
                     f"persona not found: {persona_id}", status_code=404)
    await _audit(
        "ai_persona.deleted",
        user_id=actor_user_id,
        detail={"persona_id": persona_id},
    )
    return {"deleted": True, "persona_id": persona_id}


# ──────────────────────────────────────────────────────────────────────
# employees
# ──────────────────────────────────────────────────────────────────────


class EmployeeCreate(BaseModel):
    employee_key: str
    display_name: str
    workspace_id: Optional[int] = Field(None, gt=0)
    persona_id: Optional[int] = Field(None, gt=0)
    role_level: str = "leader"
    actor_user_id: Optional[str] = None


class EmployeeUpdate(BaseModel):
    display_name: Optional[str] = None
    persona_id: Optional[int] = Field(None, gt=0)
    role_level: Optional[str] = None
    actor_user_id: Optional[str] = None


class RetireRequest(BaseModel):
    reason: Optional[str] = None
    actor_user_id: Optional[str] = None


class ReactivateRequest(BaseModel):
    actor_user_id: Optional[str] = None


@employees_router.post("")
async def create_employee(body: EmployeeCreate) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    try:
        e = aes.get_store().create_employee(
            body.employee_key, body.display_name,
            workspace_id=body.workspace_id,
            persona_id=body.persona_id,
            role_level=body.role_level,
        )
    except aes.AIEmployeeError as ex:
        raise _map_error(ex)
    await _audit(
        "ai_employee.created",
        user_id=body.actor_user_id,
        detail={
            "employee_id": e.id,
            "employee_key": e.employee_key,
            "workspace_id": e.workspace_id,
            "role_level": e.role_level,
        },
    )
    return e.to_dict()


@employees_router.get("")
async def list_employees(
    workspace_id: Optional[int] = Query(None, gt=0),
    role_level: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    limit: int = Query(200, gt=0, le=10_000),
) -> dict[str, Any]:
    try:
        items = aes.get_store().list_employees(
            workspace_id=workspace_id,
            role_level=role_level,
            include_inactive=include_inactive,
            limit=limit,
        )
    except aes.AIEmployeeError as e:
        raise _map_error(e)
    return {"count": len(items), "employees": [e.to_dict() for e in items]}


@employees_router.get("/{employee_id}")
async def get_employee(employee_id: int) -> dict[str, Any]:
    if employee_id <= 0:
        raise _error("ai_employee.invalid", "employee_id must be > 0")
    e = aes.get_store().get_employee(employee_id)
    if e is None:
        raise _error("ai_employee.not_found",
                     f"employee not found: {employee_id}", status_code=404)
    return e.to_dict()


@employees_router.patch("/{employee_id}")
async def update_employee(employee_id: int, body: EmployeeUpdate) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    if employee_id <= 0:
        raise _error("ai_employee.invalid", "employee_id must be > 0")
    try:
        e = aes.get_store().update_employee(
            employee_id,
            display_name=body.display_name,
            persona_id=body.persona_id,
            role_level=body.role_level,
        )
    except aes.AIEmployeeError as ex:
        raise _map_error(ex)
    await _audit(
        "ai_employee.updated",
        user_id=body.actor_user_id,
        detail={
            "employee_id": e.id,
            "fields": [
                k for k, v in {
                    "display_name": body.display_name,
                    "persona_id": body.persona_id,
                    "role_level": body.role_level,
                }.items() if v is not None
            ],
        },
    )
    return e.to_dict()


@employees_router.post("/{employee_id}/retire")
async def retire_employee(employee_id: int, body: RetireRequest) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    if employee_id <= 0:
        raise _error("ai_employee.invalid", "employee_id must be > 0")
    try:
        e = aes.get_store().retire_employee(employee_id, reason=body.reason)
    except aes.AIEmployeeError as ex:
        raise _map_error(ex)
    await _audit(
        "ai_employee.retired",
        user_id=body.actor_user_id,
        detail={"employee_id": e.id, "reason": e.retire_reason},
    )
    return e.to_dict()


@employees_router.post("/{employee_id}/reactivate")
async def reactivate_employee(employee_id: int, body: ReactivateRequest) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    if employee_id <= 0:
        raise _error("ai_employee.invalid", "employee_id must be > 0")
    try:
        e = aes.get_store().reactivate_employee(employee_id)
    except aes.AIEmployeeError as ex:
        raise _map_error(ex)
    await _audit(
        "ai_employee.reactivated",
        user_id=body.actor_user_id,
        detail={"employee_id": e.id},
    )
    return e.to_dict()


@employees_router.delete("/{employee_id}")
async def delete_employee(
    employee_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    _check_actor(actor_user_id)
    if employee_id <= 0:
        raise _error("ai_employee.invalid", "employee_id must be > 0")
    ok = aes.get_store().delete_employee(employee_id)
    if not ok:
        raise _error("ai_employee.not_found",
                     f"employee not found: {employee_id}", status_code=404)
    await _audit(
        "ai_employee.deleted",
        user_id=actor_user_id,
        detail={"employee_id": employee_id},
    )
    return {"deleted": True, "employee_id": employee_id}
