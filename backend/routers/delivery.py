"""T-V3-B-21 / F-013: Delivery REST endpoints (workspace-scoped).

Endpoints:
  GET  /api/workspaces/{id}/delivery               (member,          GET)
  POST /api/workspaces/{id}/delivery/approve       (workspace_admin, POST)
  POST /api/workspaces/{id}/delivery/send-client   (workspace_admin, POST)

Auth: bearerAuth (Supabase JWT) via ``Depends(require_user)``. 401 is
enforced by the dependency. 403 is enforced inside the service when the
caller is not a workspace member / admin. 404 / 409 / 422 surface from
the service layer.

AC mapping (1:1 with audit MD docs/audit/2026-05-16_v3/T-V3-B-21.md Tier 2):
  AC-F1 EVENT-DRIVEN : send-client mints a public token with expires_at + email client
  AC-F2 EVENT-DRIVEN : GET delivery happy returns Delivery contract
  AC-F3 UNWANTED     : GET delivery without auth -> 401
  AC-F4 UNWANTED     : GET delivery 422 on invalid id
  AC-F5 EVENT-DRIVEN : POST approve happy returns {approved_at}
  AC-F6 UNWANTED     : POST approve without auth -> 401
  AC-F7 EVENT-DRIVEN : POST send-client happy returns {sent_at, delivery_token}
  AC-F8 UNWANTED     : POST send-client without auth -> 401
  AC-F9 UNWANTED     : POST send-client invalid body -> 422
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path

from schemas.delivery import (
    ApproveDeliveryResponse,
    GetDeliveryResponse,
    SendClientRequest,
    SendClientResponse,
)
from services import delivery_service as ds
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)


router = APIRouter(tags=["delivery"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _service_error_to_http(e: ds.DeliveryServiceError) -> HTTPException:
    """Map service errors to HTTP responses.

    AC-F4 / AC-F9         : DeliveryValidationError -> 422
    403 (workspace member): DeliveryForbiddenError -> 403
    404                   : DeliveryNotFoundError  -> 404
    409 (state)           : DeliveryConflictError  -> 409
    """
    msg = str(e)
    if isinstance(e, ds.DeliveryNotFoundError):
        return _error("delivery.not_found", msg, status_code=404)
    if isinstance(e, ds.DeliveryForbiddenError):
        return _error("delivery.forbidden", msg, status_code=403)
    if isinstance(e, ds.DeliveryConflictError):
        return _error("delivery.conflict", msg, status_code=409)
    if isinstance(e, ds.DeliveryValidationError):
        return _error("delivery.validation_error", msg, status_code=422)
    return _error("delivery.invalid", msg)


def _extract_user_id(user: dict) -> str:
    uid = user.get("sub") or user.get("user_id") or ""
    if not isinstance(uid, str) or not uid.strip():
        raise _error(
            "delivery.unauthorized",
            "auth claims missing sub", status_code=401,
        )
    return uid.strip()


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/api/workspaces/{id}/delivery",
    operation_id="get_workspaces_by_id_delivery",
    response_model=GetDeliveryResponse,
)
async def get_workspaces_by_id_delivery(
    id: int = Path(..., description="workspace id", ge=1),
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F2 happy / AC-F3 401 (require_user) / AC-F4 422."""
    actor = _extract_user_id(user)
    try:
        return await ds.get_delivery(workspace_id=id, actor_user_id=actor)
    except ds.DeliveryServiceError as e:
        raise _service_error_to_http(e)


@router.post(
    "/api/workspaces/{id}/delivery/approve",
    operation_id="post_workspaces_by_id_delivery_approve",
    status_code=201,
    response_model=ApproveDeliveryResponse,
)
async def post_workspaces_by_id_delivery_approve(
    id: int = Path(..., description="workspace id", ge=1),
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F5 happy / AC-F6 401 (require_user) / 403 / 409 / 500."""
    actor = _extract_user_id(user)
    try:
        return await ds.approve_delivery(
            workspace_id=id, actor_user_id=actor,
        )
    except ds.DeliveryServiceError as e:
        raise _service_error_to_http(e)


@router.post(
    "/api/workspaces/{id}/delivery/send-client",
    operation_id="post_workspaces_by_id_delivery_send_client",
    status_code=201,
    response_model=SendClientResponse,
)
async def post_workspaces_by_id_delivery_send_client(
    id: int = Path(..., description="workspace id", ge=1),
    body: SendClientRequest = ...,  # type: ignore[assignment]
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F1 / AC-F7 happy / AC-F8 401 (require_user) / AC-F9 422 / 403 / 409."""
    actor = _extract_user_id(user)
    try:
        return await ds.send_client(
            workspace_id=id, actor_user_id=actor,
            client_email=body.client_email, ttl_days=body.ttl_days,
        )
    except ds.DeliveryServiceError as e:
        raise _service_error_to_http(e)
