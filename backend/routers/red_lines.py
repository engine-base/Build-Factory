"""T-V3-B-17: Red-lines backend API (F-012).

Endpoints (per ``docs/api-design/2026-05-16_v3/openapi.yaml`` F-012):

  GET  /api/workspaces/{id}/red-lines        list active red-line rules (member)
  POST /api/workspaces/{id}/red-lines        create custom red-line   (admin)
  POST /api/workspaces/{id}/red-lines/test   evaluate sample text     (member)
  GET  /api/workspaces/{id}/violations       list workspace violations (admin)

AC mapping (T-V3-B-17 audit MD):
  AC-F1 / AC-F6 / AC-F7 / AC-F8 / AC-F9 / AC-F10 / AC-F11 / AC-F12 / AC-F13 / AC-F14

Auth model (Phase 1 baseline):
  - ``Authorization: Bearer <token>`` header required (`X-User-Id` derived).
  - ``X-User-Role`` header: ``member`` | ``workspace_admin``.
  - Missing/empty Bearer → 401 (UNWANTED AC-F7 / AC-F10 / AC-F13).
  - Missing required role for admin endpoint → 403.
  - Request body validation errors → 422 (UNWANTED AC-F8 / AC-F11 / AC-F14).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError

from services import red_lines as svc


router = APIRouter(prefix="/api/workspaces", tags=["safety"])


# ──────────────────────────────────────────────────────────────────────
# Error helpers
# ──────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400,
           errors: Optional[list[dict[str, Any]]] = None) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if errors:
        detail["errors"] = errors
    return HTTPException(status_code=status_code, detail=detail)


def _map_service_error(e: svc.RedLineServiceError) -> HTTPException:
    return _error(e.code, str(e), status_code=e.status_code)


def _validate_auth(
    authorization: Optional[str],
    x_user_id: Optional[str],
) -> str:
    """Return the authenticated user_id. Raise 401 if missing/invalid."""
    if not authorization or not authorization.strip():
        raise _error(
            "red_lines.unauthorized",
            "Authorization header is required",
            status_code=401,
        )
    raw = authorization
    # Tolerate "Bearer <token>" or raw token; "Bearer" / "Bearer  " (no token) → 401.
    if raw.strip().lower() == "bearer":
        raise _error(
            "red_lines.unauthorized",
            "Bearer token must not be empty",
            status_code=401,
        )
    token = raw.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise _error(
            "red_lines.unauthorized",
            "Bearer token must not be empty",
            status_code=401,
        )
    user_id = (x_user_id or "").strip()
    if not user_id:
        raise _error(
            "red_lines.unauthorized",
            "X-User-Id header is required",
            status_code=401,
        )
    return user_id


def _require_admin(x_user_role: Optional[str]) -> str:
    role = (x_user_role or "").strip()
    if role != "workspace_admin":
        raise _error(
            "red_lines.forbidden",
            "workspace_admin role required",
            status_code=403,
        )
    return role


# ──────────────────────────────────────────────────────────────────────
# Pydantic payloads
# ──────────────────────────────────────────────────────────────────────


class RedLineCreate(BaseModel):
    """POST body: openapi.yaml F-012 POST /api/workspaces/{id}/red-lines."""

    category: str = Field(..., min_length=1, max_length=64)
    pattern: str = Field(..., min_length=1, max_length=svc.MAX_PATTERN_LEN)
    action: str = Field(..., min_length=1)
    description: Optional[str] = Field(default="", max_length=2048)


class RedLineTestRequest(BaseModel):
    """POST body: POST /api/workspaces/{id}/red-lines/test."""

    sample_text: str = Field(..., min_length=1, max_length=svc.MAX_SAMPLE_LEN)


# ──────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/red-lines", summary="List red_line rules (F-012)")
async def get_red_lines(
    workspace_id: str,
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """AC-F6 happy / AC-F7 401 / AC-F8 422."""
    _validate_auth(authorization, x_user_id)
    if not workspace_id or not workspace_id.strip():
        raise _error(
            "red_lines.invalid_input",
            "workspace_id path param must not be empty",
            status_code=422,
            errors=[{"loc": ["path", "workspace_id"], "msg": "non-empty required"}],
        )
    try:
        items = svc.list_red_lines(workspace_id)
    except svc.RedLineServiceError as e:
        raise _map_service_error(e) from None
    return {"red_lines": items, "count": len(items)}


@router.post(
    "/{workspace_id}/red-lines",
    status_code=201,
    summary="Create custom red_line rule (F-012)",
)
async def post_red_lines(
    workspace_id: str,
    body: dict[str, Any],  # validate manually so we can return our 422 shape
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """AC-F9 happy / AC-F10 401 / AC-F11 422."""
    _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)

    if not isinstance(body, dict):
        raise _error(
            "red_lines.invalid_input",
            "request body must be a JSON object",
            status_code=422,
            errors=[{"loc": ["body"], "msg": "must be an object"}],
        )
    try:
        payload = RedLineCreate(**body)
    except ValidationError as ve:
        # Field-level error map (AC-F11).
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
        rl = svc.create_red_line(
            workspace_id,
            category=payload.category,
            pattern=payload.pattern,
            action=payload.action,
            description=payload.description or "",
        )
    except svc.RedLineServiceError as e:
        raise _map_service_error(e) from None
    return {"red_line_id": rl["red_line_id"], "red_line": rl}


@router.post(
    "/{workspace_id}/red-lines/test",
    status_code=201,
    summary="Test sample_text against red_line rules (F-012)",
)
async def post_red_lines_test(
    workspace_id: str,
    body: dict[str, Any],
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """AC-F12 happy / AC-F13 401 / AC-F14 422."""
    _validate_auth(authorization, x_user_id)

    if not isinstance(body, dict):
        raise _error(
            "red_lines.invalid_input",
            "request body must be a JSON object",
            status_code=422,
            errors=[{"loc": ["body"], "msg": "must be an object"}],
        )
    try:
        payload = RedLineTestRequest(**body)
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
        result = svc.test_red_line(workspace_id, sample_text=payload.sample_text)
    except svc.RedLineServiceError as e:
        raise _map_service_error(e) from None
    return result


@router.get(
    "/{workspace_id}/violations",
    summary="List red_line violations (F-012 / admin)",
)
async def get_violations(
    workspace_id: str,
    status: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """workspace_admin only."""
    _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)
    try:
        items = svc.list_violations(workspace_id, status=status)
    except svc.RedLineServiceError as e:
        raise _map_service_error(e) from None
    return {"violations": items, "count": len(items)}
