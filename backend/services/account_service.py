"""
account_service.py — Account（課金単位・AI 社員所有）の CRUD

Account = company-dashboard でいう「会社全体」の概念。
Build-Factory では SaaS マルチテナント前提で各ユーザーが 1 つ以上の Account を持つ。
"""

from __future__ import annotations

import json
from typing import Optional

from db import async_db as aiosqlite

from db.queries import DB_PATH


def _row(r) -> dict:
    return dict(r) if r else {}


async def list_accounts(user_id: str) -> list[dict]:
    """user が member or owner として所属する account 一覧。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT a.*, am.role AS member_role
               FROM accounts a
               JOIN account_members am ON am.account_id = a.id
               WHERE am.user_id = ? AND a.is_active = 1
               ORDER BY a.created_at""",
            (user_id,),
        )
    return [_row(r) for r in rows]


async def get_account(account_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = await cur.fetchone()
    return _row(row) if row else None


async def create_account(
    *,
    name: str,
    type: str = "individual",  # company / individual
    plan: str = "free",
    owner_user_id: str,
    billing_email: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    if type not in ("company", "individual"):
        raise ValueError("type must be 'company' or 'individual'")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO accounts
               (name, type, plan, owner_user_id, billing_email, metadata)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (name, type, plan, owner_user_id, billing_email,
             json.dumps(metadata or {}, ensure_ascii=False)),
        )
        _row = await cur.fetchone()
        account_id = _row["id"]
        await db.execute(
            """INSERT INTO account_members (account_id, user_id, role)
               VALUES (?, ?, 'owner')""",
            (account_id, owner_user_id),
        )
        await db.commit()
    return await get_account(account_id) or {}


async def update_account(account_id: int, **fields) -> dict:
    if not fields:
        return await get_account(account_id) or {}
    cols, vals = [], []
    for k in ("name", "type", "plan", "billing_email"):
        if k in fields:
            cols.append(f"{k} = ?"); vals.append(fields[k])
    if "metadata" in fields:
        cols.append("metadata = ?"); vals.append(json.dumps(fields["metadata"], ensure_ascii=False))
    cols.append("updated_at = datetime('now','localtime')")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE accounts SET {', '.join(cols)} WHERE id = ?",
            [*vals, account_id],
        )
        await db.commit()
    return await get_account(account_id) or {}


async def deactivate_account(account_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET is_active = 0, updated_at = datetime('now','localtime') WHERE id = ?",
            (account_id,),
        )
        await db.commit()
    return await get_account(account_id) or {}


async def list_members(account_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM account_members WHERE account_id = ? ORDER BY created_at",
            (account_id,),
        )
    return [_row(r) for r in rows]
