"""T-V3-D-10: workspace export endpoint (F-031, E-020 Artifact).

openapi.yaml#F-031 で定義された endpoint を実装する:

    POST /api/workspaces/{id}/exports
        body : { type: 'spec_pdf' | 'delivery_report', options?: object }
        201  : { job_id, status: 'queued', kind, workspace_id, requested_at }

drift fix mapping (api-drift-summary.md#high-詳細-method-mismatch):
    `POST /api/workspaces/{id}/exports` は backend missing だった
    (T-V3-DRIFT-F-031-01). 本 router で 実装し、workspace membership check
    を Wave 4 のうちに backend 側で完結させる.

AC-F2 EVENT-DRIVEN  : 適切な kind なら 201 + { job_id }
AC-F5 UNWANTED      : membership なし → 403
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from services import export_service as svc
from services import workspace_service as ws
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces", "export"])


def _user_id(user: dict) -> str:
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="unauthenticated")
    meta = user.get("user_metadata") or {}
    if isinstance(meta, dict) and meta.get("slug"):
        return str(meta["slug"])
    if user.get("sub"):
        return str(user["sub"])
    if user.get("email"):
        return str(user["email"])
    raise HTTPException(status_code=401, detail="unauthenticated")


class PostExportBody(BaseModel):
    type: str = Field(..., description="spec_pdf | delivery_report")
    options: Optional[dict] = None


async def _require_membership(workspace_id: int, user_id: str) -> None:
    """AC-F5 enforcement: user が workspace member でなければ 403.

    存在しない workspace は 404. Empty user_id は 401 (require_user 由来).
    """
    if workspace_id <= 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "workspaces.invalid_id",
                    "message": "workspace_id must be > 0"},
        )
    w = await ws.get_workspace(workspace_id)
    if not w:
        raise HTTPException(
            status_code=404,
            detail={"code": "workspaces.not_found",
                    "message": f"workspace not found: {workspace_id}"},
        )
    member = await ws.get_member(workspace_id, user_id)
    if not member:
        raise HTTPException(
            status_code=403,
            detail={"code": "workspaces.forbidden",
                    "message": f"user {user_id} is not a member of workspace {workspace_id}"},
        )


@router.post(
    "/{workspace_id}/exports",
    status_code=201,
    summary="Enqueue a workspace export job (spec_pdf | delivery_report)",
)
async def post_workspaces_by_id_exports(
    body: PostExportBody,
    user: Annotated[dict, Depends(require_user)],
    workspace_id: Annotated[int, Path(..., gt=0)],
) -> dict[str, Any]:
    """AC-F2 EVENT-DRIVEN: 適切な kind なら 201 + { job_id }.

    AC-F5 UNWANTED: membership なし → 403.
    Errors: 401 (no auth) / 403 (no membership) / 404 (workspace 不在) /
    422 (validation).
    """
    uid = _user_id(user)
    await _require_membership(workspace_id, uid)
    try:
        return await svc.enqueue_export(
            workspace_id,
            kind=body.type,
            options=body.options,
            requested_by=uid,
        )
    except svc.ExportValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "export.validation_error",
                "message": "field-level validation failed",
                "fields": e.args[0] if e.args else {},
            },
        )
