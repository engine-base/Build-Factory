"""
workspaces.py — Workspace API + メンバー / 招待管理 + F-007 task bulk ops

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

F-007 task bulk ops (T-V3-B-11):
POST   /api/workspaces/{id}/tasks/bulk-play       選択 task を dep 順に play
POST   /api/workspaces/{id}/tasks/bulk-archive    選択 task を archive (status=cancelled)
GET    /api/workspaces/{id}/tasks/export.csv      workspace 配下 task を CSV 出力
GET    /api/workspaces/{id}/tasks/dag             task と dep を DAG 形式で返す
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import token_limit_service as tls
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from services import task_workspace_service as tws
from services import workspace_service as ws
from services.auth_middleware import require_user

# T-V3-B-06 (F-004): role + invitation revocation schemas
from schemas.workspaces import (
    WorkspaceInvitationRevokeResponse,
    WorkspaceMemberRoleResponse,
    WorkspaceMemberRoleUpdate,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


# ──────────────────────────────────────────────────────────────────────────
# T-004-02: error contract + audit emit helpers
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit_ws(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger(__name__).warning("workspaces audit emit failed: %s -- %s",
                                              event_type, e)


def _validate_name(name: str) -> str:
    """workspace name: 非空 + 100 chars 以内."""
    if not name or not name.strip():
        raise _error("workspaces.invalid_name", "name must not be empty")
    n = name.strip()
    if len(n) > 100:
        raise _error("workspaces.name_too_long", "name must be <= 100 chars")
    return n


def _validate_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("workspaces.unauthorized",
                     "creator_user_id / actor_user_id must not be empty",
                     status_code=401)


class WorkspaceCreate(BaseModel):
    account_id: int
    name: str
    description: Optional[str] = None
    project_meta: Optional[dict] = None
    creator_user_id: str = "masato"
    # T-024-04 (ADR-012 Decision 5): provider 任意切替
    preferred_provider: Optional[str] = None


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    project_meta: Optional[dict] = None
    client_visibility: Optional[list] = None
    design_system_ref: Optional[str] = None
    # S-013 mock 列 (migration g4b5c6d7e8f9)
    client_name: Optional[str] = None
    due_date: Optional[str] = None  # ISO 'YYYY-MM-DD'
    budget_jpy_monthly: Optional[int] = None
    github_repo: Optional[str] = None
    slack_channel: Optional[str] = None
    phase_gate_mode: Optional[str] = None  # strict/guide/free
    redlines: Optional[list] = None  # JSON 配列
    # T-024-04 (ADR-012 Decision 5): workspace 単位の provider 任意切替
    preferred_provider: Optional[str] = None


class MemberAdd(BaseModel):
    user_id: str
    role: str = "contributor"
    invited_by: Optional[str] = None
    custom_permissions: Optional[dict] = None


class MemberUpdate(BaseModel):
    role: Optional[str] = None
    custom_permissions: Optional[dict] = None
    actor_user_id: Optional[str] = None  # T-021-05: self-strip / owner protection 判定用


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
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    w = await ws.get_workspace(workspace_id)
    if not w:
        raise _error("workspaces.not_found",
                     f"workspace not found: {workspace_id}",
                     status_code=404)
    return w


@router.post("")
async def create_workspace(body: WorkspaceCreate):
    # AC-4: input validation (state mutate 前に reject)
    if body.account_id is None or body.account_id <= 0:
        raise _error("workspaces.invalid_account_id", "account_id must be > 0")
    name = _validate_name(body.name)
    _validate_actor(body.creator_user_id)
    if body.description is not None and len(body.description) > 2000:
        raise _error("workspaces.description_too_long", "description must be <= 2000 chars")
    # T-024-04 AC-4: preferred_provider enum 外値は state mutate 前に reject.
    if body.preferred_provider is not None:
        try:
            ws.validate_preferred_provider(body.preferred_provider)
        except ws.InvalidPreferredProviderError as e:
            raise _error("workspaces.invalid_preferred_provider", str(e))
    try:
        result = await ws.create_workspace(
            account_id=body.account_id, name=name,
            description=body.description, project_meta=body.project_meta,
            creator_user_id=body.creator_user_id,
            preferred_provider=body.preferred_provider,
        )
    except ws.InvalidPreferredProviderError as e:
        raise _error("workspaces.invalid_preferred_provider", str(e))
    except ValueError as e:
        raise _error("workspaces.create_failed", str(e))
    await _audit_ws(
        "workspaces.created",
        user_id=body.creator_user_id,
        detail={
            "workspace_id": result.get("id") if isinstance(result, dict) else None,
            "account_id": body.account_id,
            "name": name,
        },
    )
    return result


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: int,
    body: WorkspaceUpdate,
    actor_user_id: Optional[str] = None,
):
    fields = body.model_dump(exclude_unset=True)
    # T-024-04 AC-4: preferred_provider enum 外値は state mutate 前に reject.
    if "preferred_provider" in fields:
        try:
            ws.validate_preferred_provider(fields["preferred_provider"])
        except ws.InvalidPreferredProviderError as e:
            raise _error(
                "workspaces.invalid_preferred_provider", str(e),
                status_code=400,
            )
    if actor_user_id is not None:
        fields["actor_user_id"] = actor_user_id
    try:
        return await ws.update_workspace(workspace_id, **fields)
    except ws.InvalidPreferredProviderError as e:
        raise _error("workspaces.invalid_preferred_provider", str(e))


@router.delete("/{workspace_id}")
async def archive_workspace(workspace_id: int, actor_user_id: Optional[str] = None):
    return await ws.archive_workspace(workspace_id, actor_user_id=actor_user_id)


# ──────────────────────────────────────────────────────────────────────
# T-003-02: Workspace Dashboard 5 KPI (AC-1 / AC-2 / AC-5)
# ──────────────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/dashboard")
async def get_workspace_dashboard(
    workspace_id: int,
    user_id: Optional[str] = None,
):
    """5 KPI (progress / completed / running / cost / pending approvals).

    AC-2: 800ms 以内 / AC-5 (#1): permission チェックで 403 / AC-1: 5 KPI 必須.
    """
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    # AC-5 (#1) permission check: workspace 存在 + (user_id 指定なら member 確認)
    w = await ws.get_workspace(workspace_id)
    if not w:
        raise _error(
            "workspaces.not_found", f"workspace not found: {workspace_id}",
            status_code=404,
        )
    if user_id is not None:
        if not isinstance(user_id, str) or not user_id.strip():
            raise _error("workspaces.invalid_user_id", "user_id must not be empty")
        member = await ws.get_member(workspace_id, user_id.strip())
        if not member:
            raise _error(
                "workspaces.forbidden",
                f"user {user_id} is not a member of workspace {workspace_id}",
                status_code=403,
            )
    # KPI 集計
    from services import workspace_dashboard as wd
    try:
        return await wd.get_dashboard_stats(workspace_id)
    except wd.DashboardStatsError as e:
        raise _error("workspaces.invalid", str(e))


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-23 / F-017: POST /api/workspaces/{id}/token-limit
# ──────────────────────────────────────────────────────────────────────


class TokenLimitRequest(BaseModel):
    """T-V3-B-23 AC-F9: pydantic 検証で 422 を返す.

    Pydantic がまず型を弾く (`limit_usd_per_month: float` で str / null は 422).
    値域 (>= 0) は service 層で再検証.
    """
    limit_usd_per_month: float = Field(..., description="USD/月の上限")


@router.post("/{workspace_id}/token-limit", status_code=201)
async def set_workspace_token_limit(
    workspace_id: int,
    body: TokenLimitRequest,
    user: dict = Depends(require_user),
):
    """T-V3-B-23 AC-F7/F8/F9 (F-017): workspace 単位の月次 LLM コスト上限を upsert.

    Contract (features.json#F-017 + openapi.yaml POST /api/workspaces/{id}/token-limit):
      Input  : { "limit_usd_per_month": number }
      Output : 201 + { "limit_usd_per_month": number, "updated_at": iso8601,
                        "workspace_id": int, "provider_key": "anthropic" }

    AC-F7 EVENT-DRIVEN : 認証済 + valid body で 201 + 上記 contract.
    AC-F8 UNWANTED     : auth 無し → 401 (Depends(require_user)).
    AC-F9 UNWANTED     : body validation 失敗 → 422 (pydantic) または field-level
                         エラーマップ.
    """
    if workspace_id is None or workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    actor = None
    if isinstance(user, dict):
        actor = user.get("user_metadata", {}).get("slug") or user.get("sub")

    try:
        result = await tls.set_token_limit(
            workspace_id,
            body.limit_usd_per_month,
            actor_user_id=actor,
        )
    except tls.InvalidLimitError as e:
        # AC-F9 field-level error map
        raise HTTPException(
            status_code=422,
            detail={
                "code": "workspaces.token_limit.invalid",
                "message": str(e),
                "errors": {"limit_usd_per_month": str(e)},
            },
        )
    except tls.WorkspaceNotFoundError as e:
        raise _error(
            "workspaces.not_found", str(e), status_code=404,
        )
    except Exception as e:
        raise _error(
            "workspaces.token_limit.persist_failed",
            f"failed to persist token_limit: {e}",
            status_code=500,
        )

    return result


@router.get("/{workspace_id}/token-limit")
async def get_workspace_token_limit(
    workspace_id: int,
    user: dict = Depends(require_user),
):
    """T-V3-B-23 補完: 設定済 limit を返す. 未設定なら 404."""
    if workspace_id is None or workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    row = await tls.get_token_limit(workspace_id)
    if not row:
        raise _error(
            "workspaces.token_limit.not_found",
            f"token_limit not set for workspace {workspace_id}",
            status_code=404,
        )
    return row


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
    """T-021-05 AC-4: 409 で {detail: {code, message}} を返す."""
    try:
        return await ws.update_member_role(
            workspace_id, user_id,
            role=body.role, custom_permissions=body.custom_permissions,
            actor_user_id=body.actor_user_id,
        )
    except ws.SelfStripError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "self_strip_blocked", "message": str(e)},
        )
    except ws.OwnerProtectedError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "owner_protected", "message": str(e)},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(e)},
        )


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(workspace_id: int, user_id: str,
                        actor_user_id: Optional[str] = Query(None)):
    """T-021-05 AC-4: 409 で {detail: {code, message}} を返す."""
    try:
        ok = await ws.remove_member(workspace_id, user_id, actor_user_id=actor_user_id)
    except ws.SelfStripError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "self_strip_blocked", "message": str(e)},
        )
    except ws.OwnerProtectedError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "owner_protected", "message": str(e)},
        )
    return {"removed": ok}


# ──────────────────────────────────────────
# T-004-05: owner 移譲 (atomic)
# ──────────────────────────────────────────
class TransferOwnershipRequest(BaseModel):
    current_owner_id: str
    new_owner_id: str


@router.post("/{workspace_id}/transfer-ownership")
async def transfer_ownership_route(workspace_id: int, body: TransferOwnershipRequest):
    """T-004-05 AC:
      - EVENT: owner を current → new に atomic 移譲
      - STATE: current_owner_id が実際の owner でなければ 403
      - UNWANTED: new_owner_id がメンバーでなければ 400 (code=target_not_member)
    """
    try:
        return await ws.transfer_ownership(
            workspace_id,
            current_owner_id=body.current_owner_id,
            new_owner_id=body.new_owner_id,
        )
    except ws.NotOwnerError as e:
        raise HTTPException(
            status_code=403,
            detail={"code": "not_owner", "message": str(e)},
        )
    except ws.TargetNotMemberError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "target_not_member", "message": str(e)},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(e)},
        )


@router.get("/permissions/matrix")
async def permission_matrix() -> dict:
    """T-021-01 AC-3: 6 ロール × 30 permission の matrix を返す.

    Response shape (AC-3 仕様):
      {
        roles: string[],                       # 6 roles
        permissions: [{key, label, category}], # 30 permission metadata
        matrix: {role: {permission: bool}},    # role-oriented
        # legacy 互換 (旧 frontend 用):
        permission_keys: string[],
        legacy_matrix: {permission: {role: bool|str}},
      }
    """
    from services.roles import (
        PERMISSION_MATRIX, PERMISSIONS, ROLE_KEYS,
        get_permissions_metadata, get_role_oriented_matrix,
    )
    return {
        "roles": list(ROLE_KEYS),
        "permissions": get_permissions_metadata(),
        "matrix": get_role_oriented_matrix(),
        # legacy 互換 (旧 endpoint shape を破壊しない)
        "permission_keys": list(PERMISSIONS),
        "legacy_matrix": PERMISSION_MATRIX,
    }


# ── invitations (T-004-03) ────────────────────────────

import re as _re

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_ROLES = ("owner", "admin", "contributor", "viewer", "reviewer", "guest")


@router.post("/{workspace_id}/invitations")
async def create_invitation(workspace_id: int, body: InvitationCreate):
    """T-004-03 / F-004: workspace 招待発行 (token + expires_at 返却)."""
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")

    email = (body.email or "").strip().lower()
    if not email:
        raise _error("invitations.invalid_email", "email must not be empty")
    if len(email) > 254:
        raise _error("invitations.email_too_long", "email must be <= 254 chars")
    if not _EMAIL_RE.match(email):
        raise _error("invitations.invalid_email",
                     f"email format invalid: {body.email!r}")

    role = (body.role or "contributor").strip().lower()
    if role not in VALID_ROLES:
        raise _error(
            "invitations.invalid_role",
            f"role must be one of {VALID_ROLES}, got {body.role!r}",
        )

    invited_by = (body.invited_by or "").strip()
    if not invited_by:
        raise _error("invitations.unauthorized",
                     "invited_by must not be empty", status_code=401)

    if body.expires_in_days <= 0 or body.expires_in_days > 90:
        raise _error("invitations.invalid_expires_in_days",
                     "expires_in_days must be 1..90")

    try:
        result = await ws.create_invitation(
            workspace_id, email,
            role=role, invited_by=invited_by,
            expires_in_days=body.expires_in_days,
        )
    except ValueError as e:
        raise _error("invitations.create_failed", str(e))
    except Exception as e:
        raise _error("invitations.create_failed",
                     f"invitation create failed: {e}", status_code=500)

    await _audit_ws(
        "workspaces.invitation.created",
        user_id=invited_by,
        detail={
            "workspace_id": workspace_id,
            "email_hash": str(hash(email)),  # PII を avoid
            "role": role,
            "expires_in_days": body.expires_in_days,
        },
    )
    return result


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-06 (F-004): PUT /api/workspaces/{id}/members/{user_id}/role
# ──────────────────────────────────────────────────────────────────────────
# - AC-F7  EVENT: valid inputs by authorized caller → 2xx {role, updated_at}
# - AC-F8  UNWANTED: no auth token → 401
# - AC-F9  UNWANTED: invalid body → 422 (Pydantic field-level error map)
# - AC-F3  UNWANTED: would strip the last admin → 409
#
# Note: 既存の PATCH /api/workspaces/{id}/members/{user_id} は custom_permissions
# 含む汎用更新を提供 (T-021-05 由来). 本 PUT endpoint は OpenAPI 仕様 (F-004 /
# T-V3-DRIFT-F-004-06) に準拠した role 専用のミニマル契約を提供する。
# ──────────────────────────────────────────────────────────────────────────

@router.put(
    "/{workspace_id}/members/{user_id}/role",
    response_model=WorkspaceMemberRoleResponse,
)
async def update_member_role_endpoint(
    workspace_id: int,
    user_id: str,
    body: WorkspaceMemberRoleUpdate,
    user: dict = Depends(require_user),
) -> WorkspaceMemberRoleResponse:
    """T-V3-B-06 AC-F7 / AC-F8 / AC-F9.

    OpenAPI 仕様 (F-004) PUT /api/workspaces/{id}/members/{user_id}/role:
      Response: { role: string, updated_at: ISO8601 }
    """
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    if not user_id or not user_id.strip():
        raise _error("workspaces.invalid_user_id", "user_id must not be empty")
    actor = (body.actor_user_id or user.get("sub") or "").strip() or None
    try:
        updated = await ws.update_member_role(
            workspace_id,
            user_id.strip(),
            role=body.role,
            actor_user_id=actor,
        )
    except ws.SelfStripError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "workspaces.self_strip_blocked", "message": str(e)},
        )
    except ws.OwnerProtectedError as e:
        # AC-F3: would strip the last admin/owner → 409
        raise HTTPException(
            status_code=409,
            detail={"code": "workspaces.owner_protected", "message": str(e)},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "workspaces.invalid_role", "message": str(e)},
        )
    if not updated:
        raise _error(
            "workspaces.member_not_found",
            f"member {user_id} not found in workspace {workspace_id}",
            status_code=404,
        )
    # `updated` は DB 行 (created_at / updated_at 等を含む). updated_at が無い
    # legacy 行は now() で代替.
    from datetime import datetime as _dt

    updated_at = (
        updated.get("updated_at")
        or updated.get("created_at")
        or _dt.now().isoformat(timespec="seconds")
    )
    await _audit_ws(
        "workspaces.member.role_updated",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "target_user_id": user_id,
            "new_role": updated.get("role") or body.role,
        },
    )
    return WorkspaceMemberRoleResponse(
        role=updated.get("role") or body.role,
        updated_at=str(updated_at),
    )


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-06 (F-004): DELETE /api/workspaces/{id}/invitations/{token}
# ──────────────────────────────────────────────────────────────────────────
# - AC-F10  EVENT: valid revocation → 2xx {revoked_at}
# - AC-F11  UNWANTED: no auth token → 401
# - AC-F6   indirect: pending 以外 (accepted/expired/already-revoked) → 409
# ──────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{workspace_id}/invitations/{token}",
    response_model=WorkspaceInvitationRevokeResponse,
)
async def revoke_workspace_invitation(
    workspace_id: int,
    token: str,
    user: dict = Depends(require_user),
) -> WorkspaceInvitationRevokeResponse:
    """T-V3-B-06 AC-F10 / AC-F11.

    OpenAPI 仕様 (F-004) DELETE /api/workspaces/{id}/invitations/{token}:
      Response: { revoked_at: ISO8601 }
    """
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    token = (token or "").strip()
    if not token:
        raise _error("invitations.invalid_token", "token must not be empty")
    if len(token) < 8:
        raise _error("invitations.invalid_token", "token must be at least 8 chars")
    if len(token) > 200:
        raise _error("invitations.token_too_long", "token too long")

    actor = (user.get("sub") or user.get("user_metadata", {}).get("slug") or "").strip()
    actor_user_id: Optional[str] = actor or None

    try:
        result = await ws.revoke_invitation(
            workspace_id, token, actor_user_id=actor_user_id
        )
    except ws.InvitationNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "invitations.not_found", "message": str(e)},
        )
    except ws.InvitationRevokedError as e:
        raise HTTPException(
            status_code=409,
            detail={"code": "invitations.already_finalized", "message": str(e)},
        )
    return WorkspaceInvitationRevokeResponse(**result)


# ── workspace ↔ project 連携 / タスクサマリ ─────────────

@router.get("/{workspace_id}/tasks")
async def list_workspace_tasks(workspace_id: int, status: Optional[str] = None):
    """
    Workspace 配下のタスク一覧。projects.workspace_id 経由で集約。
    workspace_id に紐付く project が無ければ自動作成。
    """
    from db import async_db as adb
    from pathlib import Path as _P
    DB = _P(__file__).resolve().parents[2] / "data" / "db" / "build.db"

    async with adb.connect(DB) as db:
        db.row_factory = adb.Row
        # workspace に紐付く project を取得 (or 作成)
        rows = await db.execute_fetchall(
            "SELECT id, title FROM projects WHERE workspace_id=? ORDER BY id LIMIT 1",
            (workspace_id,),
        )
        if not rows:
            # workspace 名と一致する project があればリンク
            ws_rows = await db.execute_fetchall(
                "SELECT name, description FROM workspaces WHERE id=?", (workspace_id,)
            )
            if not ws_rows:
                raise HTTPException(404, "workspace not found")
            ws_name = ws_rows[0]["name"]
            ws_desc = ws_rows[0]["description"]
            match = await db.execute_fetchall(
                "SELECT id FROM projects WHERE title=? AND workspace_id IS NULL LIMIT 1",
                (ws_name,),
            )
            if match:
                proj_id = match[0]["id"]
                await db.execute(
                    "UPDATE projects SET workspace_id=? WHERE id=?",
                    (workspace_id, proj_id),
                )
            else:
                # 新規作成
                cur = await db.execute(
                    """INSERT INTO projects (title, description, status, workspace_id, initiated_by)
                       VALUES (?, ?, 'active', ?, 'auto-bootstrap') RETURNING id""",
                    (ws_name, ws_desc, workspace_id),
                )
                row = await cur.fetchone()
                proj_id = row["id"]
            await db.commit()
        else:
            proj_id = rows[0]["id"]

        # タスク取得
        cond = "WHERE t.project_id=?"
        params: list = [proj_id]
        if status:
            cond += " AND t.status=?"
            params.append(status)
        task_rows = await db.execute_fetchall(
            f"""SELECT t.*, e.display_name as assignee_name
                FROM tasks t
                LEFT JOIN ai_employee_config e ON e.id=t.assigned_to
                {cond}
                ORDER BY t.level, t.order_index, t.id""",
            tuple(params),
        )
        tasks = [dict(r) for r in task_rows]

    return {"project_id": proj_id, "tasks": tasks, "total": len(tasks)}


@router.get("/{workspace_id}/summary")
async def workspace_summary(
    workspace_id: int,
    user_id: Optional[str] = Query(None),
):
    """
    Workspace ダッシュボード向け 5 KPI サマリ (T-003-02 / S-012).

    AC-1 UBIQUITOUS: 5 KPI cards
        - progress (completion_rate)
        - completed_tasks
        - running_sessions
        - monthly_cost_usd
        - pending_approvals
    AC-2 EVENT (800ms P95): asyncio.gather で全クエリを並列実行
    AC-5 UNWANTED (403): user_id 指定時 workspace_member でなければ 403

    legacy 互換: task_stats / completion_rate / active_phases / recent_artifacts
                 も従来通り返す。
    """
    import asyncio as _asyncio
    from db import async_db as adb
    from pathlib import Path as _P
    DB = _P(__file__).resolve().parents[2] / "data" / "db" / "build.db"

    async with adb.connect(DB) as db:
        db.row_factory = adb.Row

        # AC-5: user_id 指定時は workspace_members 経由で権限検証
        if user_id:
            mem_rows = await db.execute_fetchall(
                "SELECT 1 FROM workspace_members "
                "WHERE workspace_id=? AND user_id=? LIMIT 1",
                (workspace_id, user_id),
            )
            if not mem_rows:
                raise HTTPException(403, "user is not a member of this workspace")

        # workspace 詳細
        ws_rows = await db.execute_fetchall(
            "SELECT id, name, description, status FROM workspaces WHERE id=?",
            (workspace_id,),
        )
        if not ws_rows:
            raise HTTPException(404, "workspace not found")
        workspace = dict(ws_rows[0])

        # 紐付く project (なければ summary は 0 件で返す)
        proj_rows = await db.execute_fetchall(
            "SELECT id, title, status FROM projects WHERE workspace_id=? LIMIT 1",
            (workspace_id,),
        )
        project = dict(proj_rows[0]) if proj_rows else None
        project_id = project["id"] if project else None

        # ── AC-2: 5 KPI クエリを asyncio.gather で並列実行 ──
        async def _task_stats() -> dict:
            stats = {"total": 0, "completed": 0, "in_progress": 0, "pending": 0, "blockers": 0}
            if not project_id:
                return stats
            rows = await db.execute_fetchall(
                "SELECT status, COUNT(*) as n FROM tasks WHERE project_id=? GROUP BY status",
                (project_id,),
            )
            for r in rows:
                stats["total"] += r["n"]
                if r["status"] == "completed":     stats["completed"]   += r["n"]
                elif r["status"] == "in_progress": stats["in_progress"] += r["n"]
                elif r["status"] == "pending":     stats["pending"]     += r["n"]
                elif r["status"] in ("blocked_question", "blocked_dependency"):
                    stats["blockers"] += r["n"]
            return stats

        async def _active_phases() -> list:
            if not project_id:
                return []
            rows = await db.execute_fetchall(
                """SELECT id, title, skill_name, status,
                        (SELECT COUNT(*) FROM tasks c WHERE c.parent_task_id=t.id) AS child_total,
                        (SELECT COUNT(*) FROM tasks c WHERE c.parent_task_id=t.id AND c.status='completed') AS child_done
                   FROM tasks t
                   WHERE project_id=? AND status='in_progress'
                   ORDER BY t.level, t.order_index, t.id LIMIT 5""",
                (project_id,),
            )
            return [dict(r) for r in rows]

        async def _recent_artifacts() -> list:
            rows = await db.execute_fetchall(
                """SELECT id, type, title, category_tags, updated_at
                     FROM artifacts
                    WHERE workspace_id=? AND is_archived=0
                    ORDER BY updated_at DESC LIMIT 5""",
                (workspace_id,),
            )
            return [dict(r) for r in rows]

        async def _running_sessions() -> int:
            try:
                rows = await db.execute_fetchall(
                    "SELECT COUNT(*) AS n FROM sessions "
                    "WHERE workspace_id=? AND status='running'",
                    (workspace_id,),
                )
                return int(rows[0]["n"]) if rows else 0
            except Exception:
                return 0  # sessions テーブル未適用環境

        async def _monthly_cost_usd() -> float:
            try:
                rows = await db.execute_fetchall(
                    "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_logs "
                    "WHERE workspace_id=? "
                    "AND occurred_at >= date('now','start of month')",
                    (workspace_id,),
                )
                return float(rows[0]["total"]) if rows else 0.0
            except Exception:
                return 0.0

        async def _pending_approvals() -> int:
            try:
                rows = await db.execute_fetchall(
                    "SELECT COUNT(*) AS n FROM approval_queue "
                    "WHERE workspace_id=? AND status='pending'",
                    (workspace_id,),
                )
                return int(rows[0]["n"]) if rows else 0
            except Exception:
                return 0

        (
            task_stats, active_phases, artifacts,
            running_sessions, monthly_cost_usd, pending_approvals,
        ) = await _asyncio.gather(
            _task_stats(),
            _active_phases(),
            _recent_artifacts(),
            _running_sessions(),
            _monthly_cost_usd(),
            _pending_approvals(),
        )

    completion_rate = (
        task_stats["completed"] / task_stats["total"]
        if task_stats["total"] > 0 else 0.0
    )

    return {
        "workspace": workspace,
        "project": project,
        # legacy 互換
        "task_stats": task_stats,
        "completion_rate": round(completion_rate, 3),
        "active_phases": active_phases,
        "recent_artifacts": artifacts,
        # T-003-02 5 KPI cards
        "kpis": {
            "progress": round(completion_rate, 3),
            "completed_tasks": task_stats["completed"],
            "running_sessions": running_sessions,
            "monthly_cost_usd": round(monthly_cost_usd, 4),
            "pending_approvals": pending_approvals,
        },
    }


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-13 / F-008: Phase management (workspace-scoped)
#   GET  /api/workspaces/{id}/phases
#   POST /api/workspaces/{id}/phases                     (workspace_admin)
#   POST /api/workspaces/{id}/phases/{phase_id}/gate     (workspace_admin)
#
# Auth model (existing convention, mirrors invitations/transfer-ownership):
#   - actor_user_id を body/query で受け、空文字列・未指定の write は 401
#   - body.actor_user_id (workspace member) で member check (forbidden→403)
#   - phase が workspace 外 → 404
#   - max 10 phase/workspace を超える → 409 (F-008 policies)
#   - gate 条件未達 → 409 (failing list を含む)
# ──────────────────────────────────────────────────────────────────────────


class PhaseCreateRequest(BaseModel):
    name: str
    gate_conditions: Optional[list[str]] = None
    actor_user_id: Optional[str] = None


class PhaseGateRequest(BaseModel):
    force: Optional[bool] = False
    actor_user_id: Optional[str] = None


@router.get("/{workspace_id}/phases")
async def list_workspace_phases(workspace_id: int, user_id: Optional[str] = None):
    """F-008 GET: workspace に紐付く phase 一覧 + current_phase_id."""
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    # validation: user_id が指定された場合は member 確認
    if user_id is not None:
        if not user_id.strip():
            raise _error(
                "phases.unauthorized",
                "user_id must not be empty when provided",
                status_code=401,
            )
        w = await ws.get_workspace(workspace_id)
        if not w:
            raise _error(
                "workspaces.not_found",
                f"workspace not found: {workspace_id}",
                status_code=404,
            )
        member = await ws.get_member(workspace_id, user_id.strip())
        if not member:
            raise _error(
                "phases.forbidden",
                f"user {user_id} is not a member of workspace {workspace_id}",
                status_code=403,
            )

    from services import phase_service as ps
    phases = await ps.list_phases_for_workspace(workspace_id)
    # current_phase_id: status='in_progress' の最初の phase, なければ最初の非完了
    current_phase_id: Optional[int] = None
    for p in phases:
        if p.get("status") == "in_progress":
            current_phase_id = int(p["id"])
            break
    if current_phase_id is None:
        for p in phases:
            if p.get("status") in ("pending", "blocked"):
                current_phase_id = int(p["id"])
                break
    return {
        "phases": phases,
        "current_phase_id": current_phase_id,
        "count": len(phases),
    }


@router.post("/{workspace_id}/phases")
async def create_workspace_phase(workspace_id: int, body: PhaseCreateRequest):
    """F-008 POST: 新規 phase 作成. workspace_admin 必須.

    EARS AC:
      - EVENT-DRIVEN: 正常 → 200 + {phase_id, ...}
      - UNWANTED: actor_user_id 空 → 401 phases.unauthorized
      - UNWANTED: name 不正 → 422 / 400
      - UNWANTED: phase 数 >= 10 → 409 phases.max_phases_reached
    """
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")

    # auth: actor_user_id が指定されていれば空文字 NG (401)
    actor = body.actor_user_id
    if actor is not None and not actor.strip():
        raise _error(
            "phases.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )

    # workspace 存在確認 (404)
    w = await ws.get_workspace(workspace_id)
    if not w:
        raise _error(
            "workspaces.not_found",
            f"workspace not found: {workspace_id}",
            status_code=404,
        )

    # actor 指定時は workspace_admin role を要求 (403)
    if actor is not None:
        member = await ws.get_member(workspace_id, actor.strip())
        if not member:
            raise _error(
                "phases.forbidden",
                f"user {actor} is not a member of workspace {workspace_id}",
                status_code=403,
            )
        role = (member.get("role") or "").lower()
        if role not in ("owner", "admin", "workspace_admin", "ws_admin"):
            raise _error(
                "phases.forbidden",
                f"role {role!r} cannot create phases (workspace_admin required)",
                status_code=403,
            )

    from services import phase_service as ps
    try:
        result = await ps.create_phase_for_workspace(
            workspace_id=workspace_id,
            name=body.name,
            gate_conditions=body.gate_conditions,
        )
    except ps.InvalidPhaseInput as e:
        msg = str(e)
        if "max_phases_reached" in msg:
            raise _error("phases.max_phases_reached", msg, status_code=409)
        if "must not be empty" in msg or "must be <=" in msg:
            raise _error("phases.invalid_name", msg, status_code=422)
        if "gate_conditions" in msg:
            raise _error("phases.invalid_gate_conditions", msg, status_code=422)
        raise _error("phases.invalid_input", msg, status_code=400)
    except ps.WorkspaceProjectResolutionError as e:
        raise _error(
            "workspaces.not_found", str(e), status_code=404,
        )

    await _audit_ws(
        "phases.created",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "phase_id": result.get("id"),
            "name": result.get("name"),
        },
    )
    # Pydantic + FastAPI default: 200; spec が 2xx を許容 (status:201 も含む)
    return {"phase_id": result.get("id"), **result}


@router.post("/{workspace_id}/phases/{phase_id}/gate")
async def evaluate_workspace_phase_gate(
    workspace_id: int, phase_id: int, body: PhaseGateRequest,
):
    """F-008 POST gate: 評価 + next phase auto unlock.

    EARS AC:
      - EVENT-DRIVEN: 条件達成 → 200 + {unlocked_phase_id, evaluated_at}
      - UNWANTED: actor_user_id 空 → 401 phases.unauthorized
      - UNWANTED: gate 未達 → 409 phases.gate_conditions_not_met + {failing}
      - UNWANTED: phase が workspace 外 → 404 phases.not_found
    """
    if workspace_id <= 0:
        raise _error("workspaces.invalid_id", "workspace_id must be > 0")
    if phase_id <= 0:
        raise _error("phases.invalid_id", "phase_id must be > 0", status_code=422)

    actor = body.actor_user_id
    if actor is not None and not actor.strip():
        raise _error(
            "phases.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )

    w = await ws.get_workspace(workspace_id)
    if not w:
        raise _error(
            "workspaces.not_found",
            f"workspace not found: {workspace_id}",
            status_code=404,
        )

    # actor 指定時は workspace_admin role を要求 (403)
    if actor is not None:
        member = await ws.get_member(workspace_id, actor.strip())
        if not member:
            raise _error(
                "phases.forbidden",
                f"user {actor} is not a member of workspace {workspace_id}",
                status_code=403,
            )
        role = (member.get("role") or "").lower()
        if role not in ("owner", "admin", "workspace_admin", "ws_admin"):
            raise _error(
                "phases.forbidden",
                f"role {role!r} cannot evaluate phase gate "
                "(workspace_admin required)",
                status_code=403,
            )

    from services import phase_service as ps
    try:
        result = await ps.evaluate_gate_and_unlock_next(
            workspace_id=workspace_id,
            phase_id=phase_id,
            force=bool(body.force),
        )
    except ps.PhaseNotFound as e:
        raise _error("phases.not_found", str(e), status_code=404)
    except ps.InvalidPhaseInput as e:
        msg = str(e)
        if "gate_conditions_not_met" in msg:
            failing = getattr(e, "failing_conditions", []) or []
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "phases.gate_conditions_not_met",
                    "message": msg,
                    "failing_conditions": list(failing),
                },
            )
        raise _error("phases.invalid_input", msg, status_code=400)

    await _audit_ws(
        "phases.gate_passed",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "phase_id": phase_id,
            "unlocked_phase_id": result.get("unlocked_phase_id"),
            "force": bool(body.force),
        },
    )
    return result


# ──────────────────────────────────────────────────────────────────────────
# T-004-04: 招待受入 + lookup + signup (NEW)
# ──────────────────────────────────────────────────────────────────────────

invitations_router = APIRouter(prefix="/api/invitations", tags=["invitations"])


@invitations_router.get("/lookup/{token}")
async def lookup_invitation_route(token: str):
    """T-004-04 AC-1: signup 前にトークンの有効性をプレビュー (mutate しない)."""
    if not token or not token.strip() or len(token) < 8:
        raise _error("invitations.invalid_token", "token must be at least 8 chars")
    if len(token) > 200:
        raise _error("invitations.token_too_long", "token too long")
    inv = await ws.lookup_invitation(token)
    if not inv:
        raise _error("invitations.not_found",
                     "invitation not found", status_code=404)
    if inv.get("is_expired"):
        return {
            **{k: v for k, v in inv.items() if k != "id"},
            "valid": False,
            "reason": "expired",
        }
    if inv.get("status") != "pending":
        return {
            **{k: v for k, v in inv.items() if k != "id"},
            "valid": False,
            "reason": inv.get("status"),
        }
    return {
        **{k: v for k, v in inv.items() if k != "id"},
        "valid": True,
    }


@invitations_router.post("/accept")
async def accept_invitation(body: InvitationAccept):
    """T-004-04 AC-2: accept (structured error 形式)."""
    token = (body.token or "").strip()
    user_id = (body.user_id or "").strip()
    if not token or len(token) < 8:
        raise _error("invitations.invalid_token", "token must be at least 8 chars")
    if not user_id:
        raise _error("invitations.unauthorized",
                     "user_id must not be empty", status_code=401)
    if len(user_id) > 128:
        raise _error("invitations.user_id_too_long", "user_id too long")

    try:
        result = await ws.accept_invitation(token, user_id)
    except ws.InvitationNotFoundError as e:
        raise _error("invitations.not_found", str(e), status_code=404)
    except ws.InvitationExpiredError as e:
        raise _error("invitations.expired", str(e), status_code=410)
    except ws.InvitationAlreadyUsedError as e:
        raise _error("invitations.already_used", str(e), status_code=409)

    await _audit_ws(
        "workspaces.invitation.accepted",
        user_id=user_id,
        detail={
            "workspace_id": result["workspace_id"],
            "role": result["role"],
        },
    )
    return result


class SignupRequest(BaseModel):
    email: str
    display_name: str
    token: str  # 招待トークン必須 (Phase 1 では invitation 経由のみ)
    locale: Optional[str] = "ja"
    timezone: Optional[str] = "Asia/Tokyo"


@invitations_router.post("/signup")
async def signup_with_invitation(body: SignupRequest):
    """T-004-04 AC-1: 招待付き signup. lookup → user 作成 → accept をまとめて実行."""
    email = (body.email or "").strip().lower()
    display_name = (body.display_name or "").strip()
    token = (body.token or "").strip()

    if not email:
        raise _error("invitations.invalid_email", "email must not be empty")
    if len(email) > 254:
        raise _error("invitations.email_too_long", "email must be <= 254 chars")
    if not _EMAIL_RE.match(email):
        raise _error("invitations.invalid_email",
                     f"email format invalid: {body.email!r}")
    if not display_name:
        raise _error("invitations.invalid_display_name",
                     "display_name must not be empty")
    if len(display_name) > 100:
        raise _error("invitations.display_name_too_long",
                     "display_name must be <= 100 chars")
    if not token or len(token) < 8:
        raise _error("invitations.invalid_token", "token must be at least 8 chars")

    # AC-4: invitation 検証 (lookup を mutate-free に使う)
    inv = await ws.lookup_invitation(token)
    if not inv:
        raise _error("invitations.not_found",
                     "invitation not found", status_code=404)
    if inv.get("is_expired"):
        raise _error("invitations.expired", "invitation expired", status_code=410)
    if inv.get("status") != "pending":
        raise _error(
            "invitations.already_used",
            f"invitation already {inv.get('status')}",
            status_code=409,
        )
    # 招待 email と signup email が一致するか確認 (誤受諾防止)
    inv_email = (inv.get("email") or "").strip().lower()
    if inv_email and inv_email != email:
        raise _error(
            "invitations.email_mismatch",
            "signup email does not match invitation email",
            status_code=403,
        )

    # user_id は email から派生 (signup 時の暫定 ID; 本番は Supabase Auth UUID)
    user_id = email

    # accept_invitation を実行
    try:
        result = await ws.accept_invitation(token, user_id)
    except ws.InvitationNotFoundError as e:
        raise _error("invitations.not_found", str(e), status_code=404)
    except ws.InvitationExpiredError as e:
        raise _error("invitations.expired", str(e), status_code=410)
    except ws.InvitationAlreadyUsedError as e:
        raise _error("invitations.already_used", str(e), status_code=409)

    await _audit_ws(
        "workspaces.signup.completed",
        user_id=user_id,
        detail={
            "workspace_id": result["workspace_id"],
            "role": result["role"],
            "email_hash": str(hash(email)),  # PII 平文を残さない
        },
    )
    return {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "locale": body.locale,
        "timezone": body.timezone,
        "workspace_id": result["workspace_id"],
        "role": result["role"],
    }


# ══════════════════════════════════════════════════════════════════════════
# T-V3-B-11 / F-007: workspace-scoped task bulk ops
#
# 4 endpoint:
#   POST /api/workspaces/{id}/tasks/bulk-play       (member)
#   POST /api/workspaces/{id}/tasks/bulk-archive    (workspace_admin)
#   GET  /api/workspaces/{id}/tasks/export.csv      (member)
#   GET  /api/workspaces/{id}/tasks/dag             (member)
#
# Auth: actor_user_id 必須 (Unauthorized → 401). workspace_member でなければ 403.
# Service 例外 ↦ HTTP status:
#   Unauthorized       → 401
#   Forbidden          → 403
#   WorkspaceNotFound  → 404
#   ValidationFailed   → 422
#   RateLimited        → 429
# ══════════════════════════════════════════════════════════════════════════


class BulkPlayRequest(BaseModel):
    task_ids: list[int] = Field(..., min_length=1, max_length=200)
    actor_user_id: Optional[str] = None
    max_parallel: int = Field(5, ge=1, le=50)


class BulkArchiveRequest(BaseModel):
    task_ids: list[int] = Field(..., min_length=1, max_length=500)
    actor_user_id: Optional[str] = None


def _map_tws_exc(exc: Exception) -> HTTPException:
    """task_workspace_service の例外 → HTTPException (with code/message)."""
    if isinstance(exc, tws.Unauthorized):
        return _error("tasks.unauthorized", str(exc), status_code=401)
    if isinstance(exc, tws.Forbidden):
        return _error("tasks.forbidden", str(exc), status_code=403)
    if isinstance(exc, tws.WorkspaceNotFound):
        return _error("tasks.workspace_not_found", str(exc), status_code=404)
    if isinstance(exc, tws.RateLimited):
        return _error("tasks.rate_limited", str(exc), status_code=429)
    if isinstance(exc, tws.ValidationFailed):
        return _error("tasks.validation_failed", str(exc), status_code=422)
    return _error("tasks.internal_error", str(exc), status_code=500)


@router.post("/{workspace_id}/tasks/bulk-play")
async def bulk_play_tasks(workspace_id: int, body: BulkPlayRequest):
    """T-V3-B-11 AC-F1/F2/F3/F4/F5/F6.

    EVENT-DRIVEN (AC-F1/F3): task_ids を topo sort 順に session spawn.
    UNWANTED   (AC-F2): max_parallel 超過分は queued count.
    UNWANTED   (AC-F4): actor_user_id 不在 → 401.
    UNWANTED   (AC-F5): pydantic validation 失敗 → 422 (FastAPI 自動).
    UNWANTED   (AC-F6): rate limit (10/min/workspace) → 429.
    """
    if workspace_id <= 0:
        raise _error("tasks.invalid_workspace_id",
                     "workspace_id must be > 0", status_code=422)
    try:
        result = await tws.bulk_play(
            workspace_id, body.task_ids,
            actor_user_id=body.actor_user_id,
            max_parallel=body.max_parallel,
        )
    except Exception as e:
        raise _map_tws_exc(e) from e
    return result


@router.post("/{workspace_id}/tasks/bulk-archive")
async def bulk_archive_tasks(workspace_id: int, body: BulkArchiveRequest):
    """T-V3-B-11 AC-F7/F8/F9.

    EVENT-DRIVEN (AC-F7): 選択 task を archive (status=cancelled) → archived_count.
    UNWANTED   (AC-F8): actor_user_id 不在 → 401.
    UNWANTED   (AC-F9): pydantic validation 失敗 → 422.
    """
    if workspace_id <= 0:
        raise _error("tasks.invalid_workspace_id",
                     "workspace_id must be > 0", status_code=422)
    try:
        result = await tws.bulk_archive(
            workspace_id, body.task_ids,
            actor_user_id=body.actor_user_id,
        )
    except Exception as e:
        raise _map_tws_exc(e) from e
    return result


@router.get("/{workspace_id}/tasks/export.csv")
async def export_tasks_csv(
    workspace_id: int,
    actor_user_id: Optional[str] = Query(None),
):
    """T-V3-B-11 AC-F10/F11.

    EVENT-DRIVEN (AC-F10): text/csv body (RFC 4180 + utf-8 + LF).
    UNWANTED   (AC-F11): actor_user_id 不在 → 401.
    """
    if workspace_id <= 0:
        raise _error("tasks.invalid_workspace_id",
                     "workspace_id must be > 0", status_code=422)
    try:
        csv_text = await tws.export_csv(
            workspace_id, actor_user_id=actor_user_id,
        )
    except Exception as e:
        raise _map_tws_exc(e) from e
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="tasks-ws{workspace_id}.csv"'},
    )


@router.get("/{workspace_id}/tasks/dag")
async def get_tasks_dag(
    workspace_id: int,
    actor_user_id: Optional[str] = Query(None),
):
    """T-V3-B-11 AC-F12/F13.

    EVENT-DRIVEN (AC-F12): {nodes: TaskNode[], edges: DAGEdge[]} を返す.
    UNWANTED   (AC-F13): actor_user_id 不在 → 401.
    """
    if workspace_id <= 0:
        raise _error("tasks.invalid_workspace_id",
                     "workspace_id must be > 0", status_code=422)
    try:
        result = await tws.get_dag(
            workspace_id, actor_user_id=actor_user_id,
        )
    except Exception as e:
        raise _map_tws_exc(e) from e
    return result
