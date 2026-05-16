"""T-V3-B-17 + T-V3-B-18: Violations backend API (F-012).

Endpoints (per ``docs/api-design/2026-05-16_v3/openapi.yaml`` F-012):

  GET  /api/workspaces/{id}/violations  list workspace violations (admin)  [T-V3-B-18]
  GET  /api/violations/{id}             inspect a violation       (admin)  [T-V3-B-17]
  POST /api/violations/{id}/approve     workspace_admin resolves           [T-V3-B-17/18]
  POST /api/violations/{id}/reject      workspace_admin denies             [T-V3-B-17/18]

T-V3-B-18 expands on T-V3-B-17:
  - Adds GET /api/workspaces/{id}/violations (was only in red_lines.py)
  - Uses ``schemas.violations.ViolationResolveRequest`` (single source of truth)
  - Delegates to ``services.violations`` (thin façade over services.red_lines)

AC mapping (T-V3-B-18 audit MD docs/audit/2026-05-16_v3/T-V3-B-18.md):
  AC-F1 EVENT-DRIVEN  approve by workspace_admin → resume session.
  AC-F2 UNWANTED      approve already-resolved → 409.
  AC-F3 EVENT-DRIVEN  GET workspaces/{id}/violations → 2xx + violations[].
  AC-F4 UNWANTED      GET violations without auth → 401.
  AC-F5 UNWANTED      GET violations invalid query/path → 422.
  AC-F6 EVENT-DRIVEN  POST approve valid input → 2xx + approved_at.
  AC-F7 UNWANTED      POST approve without auth → 401.
  AC-F8 EVENT-DRIVEN  POST reject valid input → 2xx + rejected_at.
  AC-F9 UNWANTED      POST reject without auth → 401.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import ValidationError

from schemas.violations import ViolationResolveRequest
from services import violations as svc


router = APIRouter(tags=["safety"])


# ─────────────────────────────────────────────────────────────────────────────
# Error helpers
# ─────────────────────────────────────────────────────────────────────────────


def _error(
    code: str,
    message: str,
    *,
    status_code: int = 400,
    errors: Optional[list[dict[str, Any]]] = None,
) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if errors:
        detail["errors"] = errors
    return HTTPException(status_code=status_code, detail=detail)


def _map_service_error(e: svc.ViolationServiceError) -> HTTPException:
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


def _parse_resolve_body(body: Any) -> ViolationResolveRequest:
    """Shared body parser for approve / reject. Returns 422 envelope on failure."""
    if not isinstance(body, dict):
        raise _error(
            "red_lines.invalid_input",
            "request body must be a JSON object",
            status_code=422,
            errors=[{"loc": ["body"], "msg": "must be an object"}],
        )
    try:
        return ViolationResolveRequest(**body)
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


# ─────────────────────────────────────────────────────────────────────────────
# T-V3-B-18 / AC-F3 / AC-F4 / AC-F5 — GET /api/workspaces/{id}/violations
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/api/workspaces/{workspace_id}/violations",
    summary="List violations for workspace (F-012 / admin) [T-V3-B-18]",
)
async def get_workspace_violations(
    workspace_id: str,
    status: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """AC-F3 happy / AC-F4 401 / AC-F5 422 / 403 forbidden.

    Returns: ``{violations: RedLineViolation[], count: int}``.
    """
    _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)

    if not workspace_id or not workspace_id.strip():
        raise _error(
            "red_lines.invalid_input",
            "workspace_id path param must not be empty",
            status_code=422,
            errors=[{"loc": ["path", "workspace_id"], "msg": "non-empty required"}],
        )
    if status is not None and status not in svc.VIOLATION_STATUSES:
        raise _error(
            "red_lines.invalid_input",
            f"unknown status filter: {status!r}",
            status_code=422,
            errors=[
                {
                    "loc": ["query", "status"],
                    "msg": f"must be one of {sorted(svc.VIOLATION_STATUSES)}",
                }
            ],
        )

    try:
        items = svc.list_violations(workspace_id, status=status)
    except svc.ViolationServiceError as e:
        raise _map_service_error(e) from None
    return {"violations": items, "count": len(items)}


# ─────────────────────────────────────────────────────────────────────────────
# Sub-router for /api/violations/{id}/...
# ─────────────────────────────────────────────────────────────────────────────


_violation_router = APIRouter(prefix="/api/violations", tags=["safety"])


@_violation_router.get("/{violation_id}", summary="Get violation detail (F-012)")
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
    except svc.ViolationServiceError as e:
        raise _map_service_error(e) from None


@_violation_router.post(
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
    """AC-F1 happy / AC-F2 409 / AC-F6 2xx with approved_at / AC-F7 401."""
    user_id = _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)

    payload = _parse_resolve_body(body)
    try:
        out = svc.approve_violation(
            violation_id, actor_user_id=user_id, reason=payload.reason,
        )
    except svc.ViolationServiceError as e:
        raise _map_service_error(e) from None
    return out


@_violation_router.post(
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
    """AC-F2 409 / AC-F8 2xx with rejected_at / AC-F9 401."""
    user_id = _validate_auth(authorization, x_user_id)
    _require_admin(x_user_role)

    payload = _parse_resolve_body(body)
    try:
        out = svc.reject_violation(
            violation_id, actor_user_id=user_id, reason=payload.reason,
        )
    except svc.ViolationServiceError as e:
        raise _map_service_error(e) from None
    return out


# Wire the /api/violations sub-router into the main router so a single
# include_router(violations_router) (main.py) hosts both surfaces.
router.include_router(_violation_router)


__all__ = ["router"]
