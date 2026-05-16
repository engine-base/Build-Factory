"""T-V3-B-09 / F-005b: Components catalog + usage backend router.

Endpoints:
  GET /api/workspaces/{workspace_id}/components
  GET /api/workspaces/{workspace_id}/components/{component_id}/usage

Auth role: member — enforced via Supabase RLS + workspace_member_select
(access_policies_required: component:workspace_member_rw).

EARS AC mapping (verbatim from features.json#F-005b.ears_ac_seed + 派生):
  AC-F6  EVENT-DRIVEN  GET /components → 2xx {components}
  AC-F7  UNWANTED      GET /components w/o token → 401
  AC-F8  UNWANTED      GET /components bad input → 422
  AC-F9  EVENT-DRIVEN  GET /components/{id}/usage → 2xx {usages}
  AC-F10 UNWANTED      GET /components/{id}/usage w/o token → 401
  AC-F11 UNWANTED      GET /components/{id}/usage bad input → 422
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from schemas.components import (
    ComponentListResponse,
    ComponentUsageResponse,
)
from services import components as svc
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["components"])


# ──────────────────────────────────────────────────────────────────────
# Error helpers
# ──────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _map_service_error(e: Exception) -> HTTPException:
    if isinstance(e, svc.ComponentNotFoundError):
        return _error("components.not_found", str(e), status_code=404)
    if isinstance(e, svc.ComponentValidationError):
        return _error("components.invalid_input", str(e), status_code=422)
    if isinstance(e, svc.ComponentError):
        return _error("components.invalid", str(e), status_code=400)
    logger.exception("components.internal_error: %s", e)
    return _error("components.internal", "internal server error", status_code=500)


def _validate_workspace_id(workspace_id: int) -> int:
    if workspace_id is None or workspace_id <= 0:
        raise _error(
            "components.invalid_workspace_id",
            "workspace_id must be > 0",
            status_code=422,
        )
    return workspace_id


# ──────────────────────────────────────────────────────────────────────
# GET /api/workspaces/{workspace_id}/components
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/components",
    response_model=ComponentListResponse,
    status_code=status.HTTP_200_OK,
    summary="Component カタログ (F-005b)",
)
async def list_components(
    workspace_id: int,
    user: dict = Depends(require_user),
) -> ComponentListResponse:
    """AC-F6 EVENT-DRIVEN / AC-F7 UNWANTED 401 / AC-F8 UNWANTED 422."""
    _validate_workspace_id(workspace_id)
    try:
        result = svc.list_components(workspace_id)
    except Exception as e:
        raise _map_service_error(e) from e
    return ComponentListResponse(**result)


# ──────────────────────────────────────────────────────────────────────
# GET /api/workspaces/{workspace_id}/components/{component_id}/usage
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/components/{component_id}/usage",
    response_model=ComponentUsageResponse,
    status_code=status.HTTP_200_OK,
    summary="Component 使用箇所 (F-005b)",
)
async def get_component_usage(
    workspace_id: int,
    component_id: str,
    user: dict = Depends(require_user),
) -> ComponentUsageResponse:
    """AC-F9 EVENT-DRIVEN / AC-F10 UNWANTED 401 / AC-F11 UNWANTED 422."""
    _validate_workspace_id(workspace_id)
    try:
        result = svc.get_component_usage(workspace_id, component_id)
    except Exception as e:
        raise _map_service_error(e) from e
    return ComponentUsageResponse(**result)
