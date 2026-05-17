"""T-022-03 / F-022 + T-V3-B-04 / F-003: AI 社員 CRUD + ハイブリッド統合 API.

既存の legacy routers/employees.py (company-os) は不変. Build-Factory M-22
schema (ai_employees + ai_personas) に対応する CRUD endpoint と F-003
ハイブリッド統合 (org-chart / test / clone-from-user) を提供する.

Endpoint:
  personas:
    POST   /api/ai-personas
    GET    /api/ai-personas
    GET    /api/ai-personas/{id}
    DELETE /api/ai-personas/{id}
  employees:
    POST   /api/ai-employees
    GET    /api/ai-employees                    workspace_id / role_level filter
    GET    /api/ai-employees/org-chart          T-V3-B-04 AC-F1/AC-F4 (F-003)
    GET    /api/ai-employees/{id}
    PATCH  /api/ai-employees/{id}               display_name / persona_id / role_level 更新
    POST   /api/ai-employees/{id}/retire        論理削除 + reason
    POST   /api/ai-employees/{id}/reactivate    退職取消
    POST   /api/ai-employees/{id}/test          T-V3-B-04 AC-F6/AC-F8/AC-F9 (F-003)
    POST   /api/ai-employees/{id}/clone-from-user
                                                T-V3-B-04 AC-F10/AC-F12 + opt-in (F-003)
    DELETE /api/ai-employees/{id}               完全削除

AC マッピング (T-022-03 / F-022):
  AC-1 UBIQUITOUS    : F-022 AI 社員 CRUD (REFACTOR 既存 employees.py 拡張)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 routers/employees.py / staff.py / staff_service.py 不変 +
                       audit emit (employee.created/updated/retired/reactivated/deleted +
                       persona.created/deleted)
  AC-4 UNWANTED      : invalid input / duplicate key / unknown persona / 退職済再退職 を
                       全て 4xx + structured / 失敗時 audit 非発行

AC マッピング (T-V3-B-04 / F-003):
  AC-F1/AC-F4 : GET /org-chart → hierarchical tree (workspace 内非 archived)
  AC-F5       : GET /org-chart 認証なし → 401 (actor_user_id 空文字検知)
  AC-F6       : POST /{id}/test 正常系 → 2xx with output/tokens_used/cost_usd
  AC-F7       : POST /{id}/test 認証なし → 401
  AC-F8       : POST /{id}/test 422 validation error
  AC-F3/AC-F9 : POST /{id}/test > 20/min/workspace → 429
  AC-F10      : POST /{id}/clone-from-user 正常系 → 2xx with clone_id/namespace
  AC-F2       : opt-in FALSE → 403
  AC-F11      : POST /clone-from-user 認証なし → 401
  AC-F12      : POST /clone-from-user validation error → 422
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


def _require_actor(actor: Optional[str]) -> str:
    """T-V3-B-04 AC-F5/AC-F7/AC-F11: 認証 actor を必須にする変種.

    本番では Authorization Bearer から JWT を解決し user_id を取得するが、
    Phase 1 の Auth integration 完成前は actor_user_id を必須にして
    "valid auth token がない" 状態を 401 で表現する.
    """
    if actor is None or not actor.strip():
        raise _error(
            "ai_employee.unauthorized",
            "valid auth token (actor_user_id) is required",
            status_code=401,
        )
    return actor.strip()


def _map_error(e: aes.AIEmployeeError) -> HTTPException:
    msg = str(e)
    # T-V3-B-04: clone opt-in 未承諾 → 403 (AC-F2)
    if isinstance(e, aes.CloneOptInError):
        return _error("ai_employee.forbidden", msg, status_code=403)
    # T-V3-B-04: rate limit 超過 → 429 (AC-F3/AC-F9)
    if isinstance(e, aes.RateLimitError):
        return _error("ai_employee.rate_limited", msg, status_code=429)
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
    parent_employee_id: Optional[int] = Field(None, gt=0)
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


# T-V3-B-04: F-003 新規エンドポイント用 schema
class TestEmployeeRequest(BaseModel):
    input_prompt: str = Field(..., min_length=1, max_length=8_000)
    actor_user_id: str = Field(..., min_length=1)


class CloneFromUserRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=200)
    opt_in_acknowledged: bool
    actor_user_id: str = Field(..., min_length=1)


@employees_router.post("")
async def create_employee(body: EmployeeCreate) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    try:
        e = aes.get_store().create_employee(
            body.employee_key, body.display_name,
            workspace_id=body.workspace_id,
            persona_id=body.persona_id,
            role_level=body.role_level,
            parent_employee_id=body.parent_employee_id,
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
            "parent_employee_id": e.parent_employee_id,
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


@employees_router.get("/org-chart")
async def get_org_chart(
    workspace_id: Optional[int] = Query(None, gt=0),
    include_inactive: bool = Query(False),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    """T-V3-B-04 AC-F1/AC-F4/AC-F5 (F-003): workspace 内の AI 社員 org-chart.

    認可: actor_user_id を必須にして 401 を返す (Phase 1 simplification).
    本番では Authorization Bearer / SupabaseAuth から user_id を解決する.
    """
    _require_actor(actor_user_id)
    try:
        result = aes.get_store().build_org_chart(
            workspace_id=workspace_id,
            include_inactive=include_inactive,
        )
    except aes.AIEmployeeError as ex:
        raise _map_error(ex)
    return result


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


# ──────────────────────────────────────────────────────────────────────────
# T-V3-D-09 (F-003 / drift fix): PUT alias for PATCH /api/ai-employees/{id}
#   mock 宣言は PUT、既存 backend は PATCH のみ (high method-mismatch drift).
#   ADR-016: PATCH を canonical、PUT を alias とし frontend 移行後に deprecate.
# ──────────────────────────────────────────────────────────────────────────


@employees_router.put("/{employee_id}")
async def put_update_employee(employee_id: int, body: EmployeeUpdate) -> dict[str, Any]:
    """T-V3-D-09 (F-003 AC-F1/AC-F2): PUT alias for PATCH /api/ai-employees/{id}.

    See ADR-016. Identical handler logic / response shape to PATCH.
    """
    return await update_employee(employee_id, body)


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


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-04 / F-003: ハイブリッド統合 endpoints
# ──────────────────────────────────────────────────────────────────────


@employees_router.post("/{employee_id}/test")
async def test_employee(
    employee_id: int,
    body: TestEmployeeRequest,
) -> dict[str, Any]:
    """T-V3-B-04 AC-F6/AC-F7/AC-F8/AC-F3/AC-F9 (F-003).

    認可:
      - actor_user_id 空文字/不在 → 401 (AC-F7)
      - input_prompt 空 / 8000 超 → 422 (AC-F8, Pydantic Field)
      - 20/min/workspace 超過 → 429 (AC-F3/AC-F9)
    成功時: {output, tokens_used, cost_usd} (AC-F6, F-003 contract).
    """
    _require_actor(body.actor_user_id)
    if employee_id <= 0:
        raise _error("ai_employee.invalid", "employee_id must be > 0")
    try:
        result = aes.get_store().test_employee(
            employee_id,
            input_prompt=body.input_prompt,
        )
    except aes.AIEmployeeError as ex:
        raise _map_error(ex)
    await _audit(
        "ai_employee_invocation",
        user_id=body.actor_user_id,
        detail={
            "employee_id": employee_id,
            "tokens_used": result["tokens_used"],
            "cost_usd": result["cost_usd"],
        },
    )
    return result


@employees_router.post("/{employee_id}/clone-from-user")
async def clone_from_user(
    employee_id: int,
    body: CloneFromUserRequest,
) -> dict[str, Any]:
    """T-V3-B-04 AC-F10/AC-F11/AC-F12 + AC-F2 (F-003).

    認可:
      - actor_user_id 空文字/不在 → 401 (AC-F11)
      - user_id 空 / opt_in_acknowledged 非 bool → 422 (AC-F12, Pydantic)
      - source user の clone opt-in FALSE → 403 (AC-F2)
      - opt_in_acknowledged FALSE → 403 (AC-F2 + audit trail)
    成功時: {clone_id, namespace} (AC-F10, F-003 contract).
    """
    _require_actor(body.actor_user_id)
    if employee_id <= 0:
        raise _error("ai_employee.invalid", "employee_id must be > 0")
    try:
        rec = aes.get_store().clone_from_user(
            employee_id,
            user_id=body.user_id,
            opt_in_acknowledged=body.opt_in_acknowledged,
        )
    except aes.AIEmployeeError as ex:
        raise _map_error(ex)
    await _audit(
        "ai_employee_clone",
        user_id=body.actor_user_id,
        detail={
            "employee_id": employee_id,
            "clone_id": rec.clone_uuid,
            "user_id": rec.user_id,
            "namespace": rec.namespace,
        },
    )
    return {
        "clone_id": rec.clone_uuid,
        "namespace": rec.namespace,
        "base_employee_id": rec.base_employee_id,
        "workspace_id": rec.workspace_id,
        "consent_version": rec.consent_version,
        "created_at": rec.created_at,
    }
