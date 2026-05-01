"""
workspaces.py — Workspace API + メンバー / 招待管理

GET    /api/workspaces                       user 参加全 workspace
GET    /api/workspaces?account_id=N          account 配下の一覧
POST   /api/workspaces                        新規作成
GET    /api/workspaces/{id}                  詳細
PATCH  /api/workspaces/{id}                  更新
DELETE /api/workspaces/{id}                  archive

GET    /api/workspaces/{id}/members          メンバー一覧
POST   /api/workspaces/{id}/members          追加
PATCH  /api/workspaces/{id}/members/{user}   role 変更
DELETE /api/workspaces/{id}/members/{user}   削除

POST   /api/workspaces/{id}/invitations      招待作成
POST   /api/invitations/accept                招待受諾（token + user_id）
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import workspace_service as ws

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    account_id: int
    name: str
    description: Optional[str] = None
    project_meta: Optional[dict] = None
    creator_user_id: str = "masato"


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    project_meta: Optional[dict] = None
    client_visibility: Optional[list] = None
    design_system_ref: Optional[str] = None


class MemberAdd(BaseModel):
    user_id: str
    role: str = "contributor"
    invited_by: Optional[str] = None
    custom_permissions: Optional[dict] = None


class MemberUpdate(BaseModel):
    role: Optional[str] = None
    custom_permissions: Optional[dict] = None


class InvitationCreate(BaseModel):
    email: str
    role: str = "contributor"
    invited_by: str = "masato"
    expires_in_days: int = 7


class InvitationAccept(BaseModel):
    token: str
    user_id: str


@router.get("")
async def list_workspaces(
    account_id: Optional[int] = None,
    user_id: str = Query("masato"),
    include_archived: bool = False,
):
    if account_id:
        return {"workspaces": await ws.list_workspaces_by_account(account_id, include_archived=include_archived)}
    return {"workspaces": await ws.list_workspaces_for_user(user_id)}


@router.get("/{workspace_id}")
async def get_workspace(workspace_id: int):
    w = await ws.get_workspace(workspace_id)
    if not w:
        raise HTTPException(404, f"workspace not found: {workspace_id}")
    return w


@router.post("")
async def create_workspace(body: WorkspaceCreate):
    try:
        return await ws.create_workspace(
            account_id=body.account_id, name=body.name,
            description=body.description, project_meta=body.project_meta,
            creator_user_id=body.creator_user_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/{workspace_id}")
async def update_workspace(workspace_id: int, body: WorkspaceUpdate):
    fields = body.model_dump(exclude_unset=True)
    return await ws.update_workspace(workspace_id, **fields)


@router.delete("/{workspace_id}")
async def archive_workspace(workspace_id: int):
    return await ws.archive_workspace(workspace_id)


# ── members ────────────────────────────────

@router.get("/{workspace_id}/members")
async def list_members(workspace_id: int):
    return {"members": await ws.list_members(workspace_id)}


@router.post("/{workspace_id}/members")
async def add_member(workspace_id: int, body: MemberAdd):
    try:
        return await ws.add_member(
            workspace_id, body.user_id,
            role=body.role, invited_by=body.invited_by,
            custom_permissions=body.custom_permissions,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/{workspace_id}/members/{user_id}")
async def update_member(workspace_id: int, user_id: str, body: MemberUpdate):
    return await ws.update_member_role(
        workspace_id, user_id,
        role=body.role, custom_permissions=body.custom_permissions,
    )


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(workspace_id: int, user_id: str):
    ok = await ws.remove_member(workspace_id, user_id)
    return {"removed": ok}


# ── invitations ────────────────────────────

@router.post("/{workspace_id}/invitations")
async def create_invitation(workspace_id: int, body: InvitationCreate):
    return await ws.create_invitation(
        workspace_id, body.email,
        role=body.role, invited_by=body.invited_by,
        expires_in_days=body.expires_in_days,
    )


# 招待受諾は accounts router 兄弟として配置（router 切り出し）
invitations_router = APIRouter(prefix="/api/invitations", tags=["invitations"])


@invitations_router.post("/accept")
async def accept_invitation(body: InvitationAccept):
    result = await ws.accept_invitation(body.token, body.user_id)
    if not result:
        raise HTTPException(400, "invalid or expired invitation")
    return result
