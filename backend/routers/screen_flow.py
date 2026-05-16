"""T-V3-B-09 / F-005b: Screen-flow map backend router.

Endpoints:
  GET /api/workspaces/{workspace_id}/screen-flow

Auth role: member — enforced via Supabase RLS + workspace_member_select
(access_policies_required: screen:workspace_member_rw).

EARS AC mapping:
  AC-F12 EVENT-DRIVEN  GET /screen-flow → 2xx {nodes, edges}
  AC-F13 UNWANTED      GET /screen-flow w/o token → 401
  AC-F14 UNWANTED      GET /screen-flow bad input → 422
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from schemas.screen_flow import ScreenFlowResponse
from services import screen_flow as svc
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["screen-flow"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _map_service_error(e: Exception) -> HTTPException:
    if isinstance(e, svc.ScreenFlowValidationError):
        return _error("screen_flow.invalid_input", str(e), status_code=422)
    if isinstance(e, svc.ScreenFlowError):
        return _error("screen_flow.invalid", str(e), status_code=400)
    logger.exception("screen_flow.internal_error: %s", e)
    return _error("screen_flow.internal", "internal server error", status_code=500)


def _validate_workspace_id(workspace_id: int) -> int:
    if workspace_id is None or workspace_id <= 0:
        raise _error(
            "screen_flow.invalid_workspace_id",
            "workspace_id must be > 0",
            status_code=422,
        )
    return workspace_id


@router.get(
    "/{workspace_id}/screen-flow",
    response_model=ScreenFlowResponse,
    status_code=status.HTTP_200_OK,
    summary="画面遷移マップ (F-005b)",
)
async def get_screen_flow(
    workspace_id: int,
    user: dict = Depends(require_user),
) -> ScreenFlowResponse:
    """AC-F12 EVENT-DRIVEN / AC-F13 UNWANTED 401 / AC-F14 UNWANTED 422."""
    _validate_workspace_id(workspace_id)
    try:
        result = svc.get_screen_flow(workspace_id)
    except Exception as e:
        raise _map_service_error(e) from e
    return ScreenFlowResponse(**result)
