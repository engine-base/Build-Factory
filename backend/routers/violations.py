"""T-V3-B-17: Violation approve/reject API (F-012).

Endpoints (per openapi.yaml F-012):

  POST /api/violations/{id}/approve   workspace_admin resolves a pending block
  POST /api/violations/{id}/reject    workspace_admin denies and keeps block
  GET  /api/violations/{id}           inspect a violation (workspace_admin)

AC mapping:
  AC-F4 EVENT-DRIVEN  When approve is called by workspace_admin → resume session
  AC-F5 UNWANTED       If approve hits an already-resolved record → 409 Conflict
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError

from services import red_lines as svc


router = APIRouter(prefix="/api/violations", tags=["safety"])


def _error(code: str, message: str, *, status_code: int = 400,
           errors: Optional[list[dict[str, Any]]] = None) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if errors:
        detail["errors"] = errors
    return HTTPException(status_code=status_code, detail=detail)


def _map_service_error(e: svc.RedLineServiceError) -> HTTPException:
    return _error(e.code, str(e), status_code=e.status_code)


def _validate_auth(
    authorization: Optional[str], x_user_id: Optional[str],
) -> str:
    if not authorization or not authorization.strip():
        raise _error("red_lines.unauthorized",
                     "Authorization header is required", status_code=401)
    raw = authorization
    if raw.strip().lower() == "bearer":
        raise _error("red_lines.unauthorized",
                     "Bearer token must not be empty", status_code=401)
    tok = raw.strip()
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    if not tok:
        raise _error("red_lines.unauthorized",
                     "Bearer token must not be empty", status_code=401)
    uid = (x_user_id or "").strip()
    if not uid:
        raise _error("red_lines.unauthorized",
                     "X-User-Id header is required", status_code=401)
    return uid


def _require_admin(x_user_role: Optional[str]) -> str:
    role = (x_user_role or "").strip()
    if role != "workspace_admin":
        raise _error("red_lines.forbidden",
                     "workspace_admin role required", status_code=403)
    return role


class ViolationResolveRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4096)


@router.get("/{violation_id}", summary="Get violation detail (F-012)")
async def get_violation(
    violation_id: str,
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)
    try:
        return svc.get_violation(violation_id)
    except svc.RedLineServiceError as e:
        raise _map_service_error(e) from None


@router.post(
    "/{violation_id}/approve",
    status_code=201,
    summary="Approve pending violation and resume session (F-012)",
)
async def post_violation_approve(
    violation_id: str,
    body: dict[str, Any],
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """AC-F4 happy / AC-F5 409 / 401 / 403 / 422."""
    user_id = _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)

    if not isinstance(body, dict):
        raise _error(
            "red_lines.invalid_input",
            "request body must be a JSON object",
            status_code=422,
            errors=[{"loc": ["body"], "msg": "must be an object"}],
        )
    try:
        payload = ViolationResolveRequest(**body)
    except ValidationError as ve:
        raise _error(
            "red_lines.invalid_input",
            "validation error",
            status_code=422,
            errors=[
                {
                    "loc": list(err["loc"]),
                    "msg": err["msg"],
                    "type": err["type"],
                }
                for err in ve.errors()
            ],
        ) from None
    except TypeError:
        raise _error(
            "red_lines.invalid_input",
            "request body has unexpected fields",
            status_code=422,
        ) from None

    try:
        out = svc.approve_violation(
            violation_id, actor_user_id=user_id, reason=payload.reason,
        )
    except svc.RedLineServiceError as e:
        raise _map_service_error(e) from None
    return out


@router.post(
    "/{violation_id}/reject",
    status_code=201,
    summary="Reject pending violation (F-012)",
)
async def post_violation_reject(
    violation_id: str,
    body: dict[str, Any],
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    user_id = _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)

    if not isinstance(body, dict):
        raise _error(
            "red_lines.invalid_input",
            "request body must be a JSON object",
            status_code=422,
            errors=[{"loc": ["body"], "msg": "must be an object"}],
        )
    try:
        payload = ViolationResolveRequest(**body)
    except ValidationError as ve:
        raise _error(
            "red_lines.invalid_input",
            "validation error",
            status_code=422,
            errors=[
                {
                    "loc": list(err["loc"]),
                    "msg": err["msg"],
                    "type": err["type"],
                }
                for err in ve.errors()
            ],
        ) from None
    except TypeError:
        raise _error(
            "red_lines.invalid_input",
            "request body has unexpected fields",
            status_code=422,
        ) from None

    try:
        out = svc.reject_violation(
            violation_id, actor_user_id=user_id, reason=payload.reason,
        )
    except svc.RedLineServiceError as e:
        raise _map_service_error(e) from None
    return out
