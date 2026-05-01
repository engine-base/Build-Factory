"""
workspace_service.py — Workspace（プロジェクト単位）の CRUD + メンバー管理

Workspace = 1 プロジェクト = 1 案件。
Account 配下に複数 Workspace。
Members は workspace 単位で招待・role はカスタマイズ可。

役割:
  - admin       : 全権限
  - contributor : 編集可・承認不可
  - viewer      : 閲覧のみ
  - client      : クライアント招待用（限定タブのみ閲覧 + コメント）
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

from db.queries import DB_PATH


def _row(r) -> dict:
    return dict(r) if r else {}


# ──────────────────────────────────────────
# Workspace CRUD
# ──────────────────────────────────────────

async def list_workspaces_by_account(
    account_id: int, *, include_archived: bool = False,
) -> list[dict]:
    conds = ["account_id = ?"]
    params: list = [account_id]
    if not include_archived:
        conds.append("status != 'archived'")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"SELECT * FROM workspaces WHERE {' AND '.join(conds)} ORDER BY updated_at DESC",
            params,
        )
    return [_row(r) for r in rows]


async def list_workspaces_for_user(user_id: str) -> list[dict]:
    """user が member として参加している全 workspace を返す（account 横断）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT w.*, wm.role AS member_role
               FROM workspaces w
               JOIN workspace_members wm ON wm.workspace_id = w.id
               WHERE wm.user_id = ? AND w.status = 'active'
               ORDER BY w.updated_at DESC""",
            (user_id,),
        )
    return [_row(r) for r in rows]


async def get_workspace(workspace_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        row = await cur.fetchone()
    return _row(row) if row else None


async def create_workspace(
    *,
    account_id: int,
    name: str,
    description: Optional[str] = None,
    project_meta: Optional[dict] = None,
    creator_user_id: str,
) -> dict:
    """workspace 新規作成。creator は自動で admin role で member に追加。"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO workspaces
               (account_id, name, description, project_meta)
               VALUES (?, ?, ?, ?)""",
            (account_id, name, description,
             json.dumps(project_meta or {}, ensure_ascii=False)),
        )
        workspace_id = cur.lastrowid
        await db.execute(
            """INSERT INTO workspace_members
               (workspace_id, user_id, role, invited_by)
               VALUES (?, ?, 'admin', ?)""",
            (workspace_id, creator_user_id, creator_user_id),
        )
        await db.commit()
    return await get_workspace(workspace_id) or {}


async def update_workspace(workspace_id: int, **fields) -> dict:
    if not fields:
        return await get_workspace(workspace_id) or {}
    cols, vals = [], []
    for k in ("name", "description", "status", "design_system_ref"):
        if k in fields:
            cols.append(f"{k} = ?"); vals.append(fields[k])
    for k in ("project_meta", "client_visibility"):
        if k in fields:
            cols.append(f"{k} = ?"); vals.append(json.dumps(fields[k], ensure_ascii=False))
    cols.append("updated_at = datetime('now','localtime')")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE workspaces SET {', '.join(cols)} WHERE id = ?",
            [*vals, workspace_id],
        )
        await db.commit()
    return await get_workspace(workspace_id) or {}


async def archive_workspace(workspace_id: int) -> dict:
    return await update_workspace(workspace_id, status="archived")


# ──────────────────────────────────────────
# Member 管理
# ──────────────────────────────────────────

DEFAULT_ROLES = ("admin", "contributor", "viewer", "client")


async def list_members(workspace_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM workspace_members WHERE workspace_id = ? ORDER BY created_at",
            (workspace_id,),
        )
    return [_row(r) for r in rows]


async def add_member(
    workspace_id: int,
    user_id: str,
    *,
    role: str = "contributor",
    invited_by: Optional[str] = None,
    custom_permissions: Optional[dict] = None,
) -> dict:
    if role not in DEFAULT_ROLES and not custom_permissions:
        # カスタムロールでも custom_permissions が無いと invalid
        raise ValueError(f"unknown role '{role}' (use {DEFAULT_ROLES} or supply custom_permissions)")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO workspace_members
               (workspace_id, user_id, role, custom_permissions, invited_by)
               VALUES (?, ?, ?, ?, ?)""",
            (workspace_id, user_id, role,
             json.dumps(custom_permissions or {}, ensure_ascii=False),
             invited_by),
        )
        await db.commit()
    return await get_member(workspace_id, user_id) or {}


async def update_member_role(
    workspace_id: int, user_id: str,
    *, role: Optional[str] = None, custom_permissions: Optional[dict] = None,
) -> dict:
    cols, vals = [], []
    if role:
        cols.append("role = ?"); vals.append(role)
    if custom_permissions is not None:
        cols.append("custom_permissions = ?")
        vals.append(json.dumps(custom_permissions, ensure_ascii=False))
    if not cols:
        return await get_member(workspace_id, user_id) or {}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE workspace_members SET {', '.join(cols)} "
            f"WHERE workspace_id = ? AND user_id = ?",
            [*vals, workspace_id, user_id],
        )
        await db.commit()
    return await get_member(workspace_id, user_id) or {}


async def remove_member(workspace_id: int, user_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


async def get_member(workspace_id: int, user_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, user_id),
        )
        row = await cur.fetchone()
    return _row(row) if row else None


# ──────────────────────────────────────────
# 招待
# ──────────────────────────────────────────

async def create_invitation(
    workspace_id: int,
    email: str,
    *,
    role: str = "contributor",
    invited_by: str,
    expires_in_days: int = 7,
) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=expires_in_days)).isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO workspace_invitations
               (workspace_id, email, role, token, invited_by, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (workspace_id, email, role, token, invited_by, expires_at),
        )
        await db.commit()
    return {
        "workspace_id": workspace_id,
        "email": email,
        "role": role,
        "token": token,
        "expires_at": expires_at,
        "invitation_url": f"/invite/{token}",
    }


async def accept_invitation(token: str, user_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM workspace_invitations WHERE token = ? AND status = 'pending'",
            (token,),
        )
        inv = await cur.fetchone()
        if not inv:
            return None
        d = dict(inv)
        # 期限チェック
        if d.get("expires_at"):
            try:
                if datetime.fromisoformat(d["expires_at"]) < datetime.now():
                    await db.execute(
                        "UPDATE workspace_invitations SET status='expired' WHERE id=?", (d["id"],)
                    )
                    await db.commit()
                    return None
            except Exception:
                pass
        # member 追加
        await db.execute(
            """INSERT OR REPLACE INTO workspace_members
               (workspace_id, user_id, role, invited_by)
               VALUES (?, ?, ?, ?)""",
            (d["workspace_id"], user_id, d["role"], d.get("invited_by")),
        )
        await db.execute(
            "UPDATE workspace_invitations SET status='accepted' WHERE id=?", (d["id"],)
        )
        await db.commit()
    return {"workspace_id": d["workspace_id"], "user_id": user_id, "role": d["role"]}
