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
    try:
        result = await ws.create_workspace(
            account_id=body.account_id, name=name,
            description=body.description, project_meta=body.project_meta,
            creator_user_id=body.creator_user_id,
        )
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


# 招待受諾は accounts router 兄弟として配置（router 切り出し）
invitations_router = APIRouter(prefix="/api/invitations", tags=["invitations"])


@invitations_router.post("/accept")
async def accept_invitation(body: InvitationAccept):
    result = await ws.accept_invitation(body.token, body.user_id)
    if not result:
        raise HTTPException(400, "invalid or expired invitation")
    return result
