"""T-V3-B-28 / F-026: Constitution backend router.

endpoints (features.json#F-026 / openapi.yaml):
  GET    /api/workspaces/{id}/constitution                              member
  POST   /api/workspaces/{id}/constitution/versions                     workspace_admin
  POST   /api/workspaces/{id}/constitution/versions/{v}/approve         workspace_admin

acceptance criteria coverage:
  AC-F1  (EVENT)    POST .../versions → snapshot 作成 (active 不変動)
  AC-F2  (EVENT)    POST .../versions/{v}/approve → v を active 化 + cache flush
  AC-F3  (UNWANTED) content_md > 10 KB → 422
  AC-F4  (EVENT)    GET → 2xx contract (content_md / version / is_active)
  AC-F5  (UNWANTED) 認証 token 不在 → 401
  AC-F6  (UNWANTED) validation 失敗 → 422 field-level error
  AC-F7  (EVENT)    POST .../versions → 2xx contract (version_id, version_number)
  AC-F8  (UNWANTED) 認証 token 不在 → 401
  AC-F9  (UNWANTED) validation 失敗 → 422 field-level error
  AC-F10 (EVENT)    POST approve → 2xx contract (approved_at, active_version)
  AC-F11 (UNWANTED) 認証 token 不在 → 401

auth contract:
  本リポジトリは Bearer JWT を未配備. 代わりに `user_id` (member RBAC) /
  `actor_user_id` (admin RBAC) を query param で受け, 空 / 未指定なら 401.
  workspaces.py の `_validate_actor` と同等の "soft auth" を踏襲.
  本番 deploy では Supabase Auth middleware が追加で挿入される前提.

access control policies (entities.json#E-017 + #E-018):
  - bf_constitutions_workspace_member_select
  - bf_constitutions_workspace_member_write
  - red_lines_workspace_member_select (将来 red_line endpoint で利用)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import status as http_status

from schemas.constitution import (
    ConstitutionResponse,
    ConstitutionVersionApproveResponse,
    ConstitutionVersionCreateRequest,
    ConstitutionVersionCreateResponse,
)
from services import constitution_service as cs

router = APIRouter(prefix="/api/workspaces", tags=["constitution"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _validate_workspace_id(workspace_id: int) -> int:
    if workspace_id is None or workspace_id <= 0:
        raise _error("constitution.invalid_workspace_id",
                     "workspace_id must be > 0", status_code=422)
    return workspace_id


def _require_member(user_id: Optional[str]) -> str:
    """AC-F5: GET 認証 token 不在 → 401.

    本リポジトリは Bearer auth 未配備のため `user_id` query を token surrogate
    として扱う.
    """
    if user_id is None or not isinstance(user_id, str) or not user_id.strip():
        raise _error(
            "constitution.unauthorized",
            "user_id (member token) must be provided",
            status_code=401,
        )
    return user_id.strip()


def _require_admin(actor_user_id: Optional[str]) -> str:
    """AC-F8 / AC-F11: POST 認証 token 不在 → 401.

    `actor_user_id` は workspace_admin role を持つ caller の surrogate.
    """
    if actor_user_id is None or not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise _error(
            "constitution.unauthorized",
            "actor_user_id (workspace_admin token) must be provided",
            status_code=401,
        )
    return actor_user_id.strip()


# ──────────────────────────────────────────────────────────────────────────
# GET /api/workspaces/{id}/constitution
# ──────────────────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/constitution",
    response_model=ConstitutionResponse,
    summary="Get active Constitution (F-026)",
)
async def get_constitution(
    workspace_id: int,
    user_id: Optional[str] = Query(None, description="Member token surrogate"),
):
    """AC-F4 / AC-F5 / AC-F6."""
    _validate_workspace_id(workspace_id)
    _require_member(user_id)
    try:
        result = await cs.get_constitution(workspace_id)
    except cs.WorkspaceNotFoundError as e:
        raise _error("constitution.workspace_not_found", str(e), status_code=404)
    if not result:
        raise _error(
            "constitution.not_found",
            f"no active constitution for workspace {workspace_id}",
            status_code=404,
        )
    return ConstitutionResponse(**result)


# ──────────────────────────────────────────────────────────────────────────
# POST /api/workspaces/{id}/constitution/versions
# ──────────────────────────────────────────────────────────────────────────


@router.post(
    "/{workspace_id}/constitution/versions",
    response_model=ConstitutionVersionCreateResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create new Constitution version snapshot (F-026)",
)
async def create_constitution_version(
    workspace_id: int,
    body: ConstitutionVersionCreateRequest,
    actor_user_id: Optional[str] = Query(
        None, description="workspace_admin token surrogate"
    ),
):
    """AC-F1 / AC-F3 / AC-F7 / AC-F8 / AC-F9."""
    _validate_workspace_id(workspace_id)
    author = _require_admin(actor_user_id)
    try:
        result = await cs.create_version(
            workspace_id=workspace_id,
            content_md=body.content_md,
            message=body.message,
            author=author,
        )
    except cs.WorkspaceNotFoundError as e:
        raise _error("constitution.workspace_not_found", str(e), status_code=404)
    except cs.ContentTooLargeError as e:
        # AC-F3: content_md > 10 KB → 422
        raise _error(
            "constitution.content_too_large", str(e), status_code=422,
        )
    return ConstitutionVersionCreateResponse(**result)


# ──────────────────────────────────────────────────────────────────────────
# POST /api/workspaces/{id}/constitution/versions/{v}/approve
# ──────────────────────────────────────────────────────────────────────────


@router.post(
    "/{workspace_id}/constitution/versions/{version}/approve",
    response_model=ConstitutionVersionApproveResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Approve & activate Constitution version (F-026)",
)
async def approve_constitution_version(
    workspace_id: int,
    version: int,
    actor_user_id: Optional[str] = Query(
        None, description="workspace_admin token surrogate"
    ),
):
    """AC-F2 / AC-F10 / AC-F11.

    409 (already active) は AC-F2 の State 維持 (新 version 採番ルールに準じ
    重複 approve を禁止) を担保.
    """
    _validate_workspace_id(workspace_id)
    if version is None or version <= 0:
        raise _error(
            "constitution.invalid_version",
            "version must be > 0",
            status_code=422,
        )
    approver = _require_admin(actor_user_id)
    try:
        result = await cs.approve_version(
            workspace_id=workspace_id, version=version, approver=approver,
        )
    except cs.WorkspaceNotFoundError as e:
        raise _error("constitution.workspace_not_found", str(e), status_code=404)
    except cs.VersionNotFoundError as e:
        raise _error("constitution.version_not_found", str(e), status_code=404)
    except cs.AlreadyActiveError as e:
        raise _error("constitution.already_active", str(e), status_code=409)
    return ConstitutionVersionApproveResponse(**result)


__all__ = ["router"]
