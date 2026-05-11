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
async def update_workspace(
    workspace_id: int,
    body: WorkspaceUpdate,
    actor_user_id: Optional[str] = None,
):
    fields = body.model_dump(exclude_unset=True)
    if actor_user_id is not None:
        fields["actor_user_id"] = actor_user_id
    return await ws.update_workspace(workspace_id, **fields)


@router.delete("/{workspace_id}")
async def archive_workspace(workspace_id: int, actor_user_id: Optional[str] = None):
    return await ws.archive_workspace(workspace_id, actor_user_id=actor_user_id)


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
    try:
        return await ws.update_member_role(
            workspace_id, user_id,
            role=body.role, custom_permissions=body.custom_permissions,
            actor_user_id=body.actor_user_id,
        )
    except ws.SelfStripError as e:
        raise HTTPException(409, f"self_strip_blocked: {e}")
    except ws.OwnerProtectedError as e:
        raise HTTPException(409, f"owner_protected: {e}")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(workspace_id: int, user_id: str,
                        actor_user_id: Optional[str] = Query(None)):
    try:
        ok = await ws.remove_member(workspace_id, user_id, actor_user_id=actor_user_id)
    except ws.SelfStripError as e:
        raise HTTPException(409, f"self_strip_blocked: {e}")
    except ws.OwnerProtectedError as e:
        raise HTTPException(409, f"owner_protected: {e}")
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
    """T-021-04: 6 ロール × 30 permission の matrix を返す (UI grid 用)。"""
    from services.roles import PERMISSION_MATRIX, PERMISSIONS, ROLE_KEYS
    return {
        "roles": list(ROLE_KEYS),
        "permission_keys": list(PERMISSIONS),
        "matrix": PERMISSION_MATRIX,
    }


# ── invitations ────────────────────────────

@router.post("/{workspace_id}/invitations")
async def create_invitation(workspace_id: int, body: InvitationCreate):
    return await ws.create_invitation(
        workspace_id, body.email,
        role=body.role, invited_by=body.invited_by,
        expires_in_days=body.expires_in_days,
    )


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
async def workspace_summary(workspace_id: int):
    """
    Workspace ダッシュボード向けサマリ。
    タスク件数 / 完了率 / ブロッカー数 / 進行中フェーズ / 直近 artifact 等。
    """
    from db import async_db as adb
    from pathlib import Path as _P
    DB = _P(__file__).resolve().parents[2] / "data" / "db" / "build.db"

    async with adb.connect(DB) as db:
        db.row_factory = adb.Row

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

        # タスク統計
        task_stats = {"total": 0, "completed": 0, "in_progress": 0, "pending": 0, "blockers": 0}
        active_phases: list = []
        if project:
            stat_rows = await db.execute_fetchall(
                """SELECT status, COUNT(*) as n FROM tasks WHERE project_id=? GROUP BY status""",
                (project["id"],),
            )
            for r in stat_rows:
                task_stats["total"] += r["n"]
                if r["status"] == "completed":         task_stats["completed"]   += r["n"]
                elif r["status"] == "in_progress":     task_stats["in_progress"] += r["n"]
                elif r["status"] == "pending":         task_stats["pending"]     += r["n"]
                elif r["status"] in ("blocked_question", "blocked_dependency"):
                    task_stats["blockers"] += r["n"]

            # 進行中フェーズ (level=0 + status=in_progress, または skill_name=feature)
            active_rows = await db.execute_fetchall(
                """SELECT id, title, skill_name, status,
                        (SELECT COUNT(*) FROM tasks c WHERE c.parent_task_id=t.id) AS child_total,
                        (SELECT COUNT(*) FROM tasks c WHERE c.parent_task_id=t.id AND c.status='completed') AS child_done
                   FROM tasks t
                   WHERE project_id=? AND status='in_progress'
                   ORDER BY t.level, t.order_index, t.id LIMIT 5""",
                (project["id"],),
            )
            active_phases = [dict(r) for r in active_rows]

        # workspace 関連の最新 artifact (上位 5)
        art_rows = await db.execute_fetchall(
            """SELECT id, type, title, category_tags, updated_at
               FROM artifacts
               WHERE workspace_id=? AND is_archived=0
               ORDER BY updated_at DESC LIMIT 5""",
            (workspace_id,),
        )
        artifacts = [dict(r) for r in art_rows]

    completion_rate = (task_stats["completed"] / task_stats["total"]) if task_stats["total"] > 0 else 0.0
    return {
        "workspace": workspace,
        "project": project,
        "task_stats": task_stats,
        "completion_rate": round(completion_rate, 3),
        "active_phases": active_phases,
        "recent_artifacts": artifacts,
    }


# 招待受諾は accounts router 兄弟として配置（router 切り出し）
invitations_router = APIRouter(prefix="/api/invitations", tags=["invitations"])


@invitations_router.post("/accept")
async def accept_invitation(body: InvitationAccept):
    result = await ws.accept_invitation(body.token, body.user_id)
    if not result:
        raise HTTPException(400, "invalid or expired invitation")
    return result
