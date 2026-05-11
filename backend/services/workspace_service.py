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

from db import async_db as aiosqlite

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
               VALUES (?, ?, ?, ?) RETURNING id""",
            (account_id, name, description,
             json.dumps(project_meta or {}, ensure_ascii=False)),
        )
        _row = await cur.fetchone()
        workspace_id = _row["id"]
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

# T-021-01: 6 ロール (v2.1)。旧 "admin" は "ws_admin" の互換 alias。
# 単一ソース: services.roles.ROLE_KEYS
from services.roles import ROLE_KEYS as _SIX_ROLES, validate_custom_permissions as _validate_cp

DEFAULT_ROLES = _SIX_ROLES + ("admin",)  # "admin" は legacy data 互換のために許容


def _normalize_role(role: str) -> str:
    """旧 "admin" を新 "ws_admin" に正規化 (DB 既存 row 互換)。"""
    return "ws_admin" if role == "admin" else role


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
    # T-021-02 (先取り): custom_permissions key の正当性検証
    if custom_permissions:
        unknown = _validate_cp(custom_permissions)
        if unknown:
            raise ValueError(f"unknown permission keys in custom_permissions: {unknown}")
    role = _normalize_role(role)
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


class SelfStripError(ValueError):
    """T-021-05: self-strip block — 自分自身の権限を剥奪することは禁止。"""


class OwnerProtectedError(ValueError):
    """T-021-05: owner ロールは降格/削除できない (最後の 1 人は特に)。"""


async def _count_role(workspace_id: int, role: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM workspace_members WHERE workspace_id = ? AND role = ?",
            (workspace_id, role),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def update_member_role(
    workspace_id: int, user_id: str,
    *, role: Optional[str] = None, custom_permissions: Optional[dict] = None,
    actor_user_id: Optional[str] = None,
) -> dict:
    # T-021-05: self-strip block (DB 不在でも即時 check)
    if actor_user_id is not None and actor_user_id == user_id and role is not None:
        raise SelfStripError("cannot change your own role (self-strip blocked)")
    current = await get_member(workspace_id, user_id)
    # T-021-05: owner protection (最後の owner 降格を阻止)
    if current and current.get("role") == "owner" and role and role != "owner":
        if await _count_role(workspace_id, "owner") <= 1:
            raise OwnerProtectedError("cannot demote the last owner")
    # T-021-02: custom_permissions key 検証
    if custom_permissions:
        unknown = _validate_cp(custom_permissions)
        if unknown:
            raise ValueError(f"unknown permission keys in custom_permissions: {unknown}")
    if role:
        role = _normalize_role(role)

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


async def remove_member(workspace_id: int, user_id: str, *, actor_user_id: Optional[str] = None) -> bool:
    # T-021-05: self-strip block — 自分自身を削除できない
    if actor_user_id is not None and actor_user_id == user_id:
        raise SelfStripError("cannot remove yourself from a workspace (self-strip blocked)")
    # T-021-05: owner protection — 最後の owner は削除不可
    current = await get_member(workspace_id, user_id)
    if current and current.get("role") == "owner":
        if await _count_role(workspace_id, "owner") <= 1:
            raise OwnerProtectedError("cannot remove the last owner")
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
