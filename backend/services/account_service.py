"""
account_service.py — Account（課金単位・AI 社員所有）の CRUD

Account = company-dashboard でいう「会社全体」の概念。
Build-Factory では SaaS マルチテナント前提で各ユーザーが 1 つ以上の Account を持つ。
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from db import async_db as aiosqlite

from db.queries import DB_PATH


# T-V3-B-05 (F-004): exceptions for account-level operations
class AccountNotFoundError(ValueError):
    """account id が見つからない."""


class TargetNotAccountMemberError(ValueError):
    """transfer-owner の new_owner が account_members に存在しない."""


class CannotRemoveAccountOwnerError(ValueError):
    """account の owner は削除できない (まず transfer-owner)."""


class AccountInvitationNotFoundError(ValueError):
    """account invitation token が見つからない."""


class AccountInvitationExpiredError(ValueError):
    """account invitation が expires_at を過ぎている."""


class AccountInvitationStateError(ValueError):
    """account invitation が pending 以外 (accepted / revoked / expired) の状態."""


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
            cols.append(f"{k} = ?")
            vals.append(fields[k])
    if "metadata" in fields:
        cols.append("metadata = ?")
        vals.append(json.dumps(fields["metadata"], ensure_ascii=False))
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


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-05 (F-004): emit audit helper
# ──────────────────────────────────────────────────────────────────────


async def _emit_audit(
    event_type: str,
    *,
    user_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    """audit ログ emit. memory_service が無くても fail しない."""
    try:
        from services.memory_service import emit_event

        await emit_event(event_type, user_id=user_id, detail=detail or {})
    except Exception:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning(
            "account audit emit failed: %s", event_type
        )


async def _ensure_account_invitations_table() -> None:
    """SQLite test env で alembic 未適用でも動くように lazy create."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS account_invitations (
                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                   account_id   INTEGER NOT NULL,
                   email        TEXT    NOT NULL,
                   role         TEXT    DEFAULT 'member',
                   token        TEXT    NOT NULL UNIQUE,
                   invited_by   TEXT,
                   status       TEXT    DEFAULT 'pending',
                   expires_at   TEXT,
                   created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS ix_account_invitations_account "
            "ON account_invitations (account_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS ix_account_invitations_token "
            "ON account_invitations (token)"
        )
        await db.commit()


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-05 (F-004 / AC-F4 / AC-F1): transfer-owner (atomic)
# ──────────────────────────────────────────────────────────────────────


async def get_account_member(account_id: int, user_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM account_members WHERE account_id = ? AND user_id = ?",
            (account_id, user_id),
        )
        row = await cur.fetchone()
    return _row(row) if row else None


async def transfer_owner(
    account_id: int,
    *,
    new_owner_user_id: str,
    actor_user_id: Optional[str] = None,
) -> dict:
    """T-V3-B-05 AC-F4 / AC-F1.

    EVENT-DRIVEN: 既存 owner → new_owner_user_id へ atomic に移譲。
    UNWANTED: new_owner_user_id が account_members に居なければ 409 相当
              (TargetNotAccountMemberError).
    """
    account = await get_account(account_id)
    if not account:
        raise AccountNotFoundError(f"account not found: {account_id}")

    old_owner_id: str = str(account.get("owner_user_id") or "")
    target = await get_account_member(account_id, new_owner_user_id)
    if not target:
        raise TargetNotAccountMemberError(
            f"user {new_owner_user_id} is not a member of account {account_id}"
        )
    if old_owner_id == new_owner_user_id:
        raise ValueError("new_owner_user_id is already the owner")

    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        # owner 行を降格 (admin) — atomic
        await db.execute(
            "UPDATE account_members SET role = 'admin' "
            "WHERE account_id = ? AND user_id = ?",
            (account_id, old_owner_id),
        )
        # new owner を owner 化
        await db.execute(
            "UPDATE account_members SET role = 'owner' "
            "WHERE account_id = ? AND user_id = ?",
            (account_id, new_owner_user_id),
        )
        # accounts.owner_user_id を更新
        await db.execute(
            "UPDATE accounts SET owner_user_id = ?, "
            "updated_at = datetime('now','localtime') WHERE id = ?",
            (new_owner_user_id, account_id),
        )
        await db.commit()

    await _emit_audit(
        "accounts.owner_transferred",
        user_id=actor_user_id or old_owner_id,
        detail={
            "account_id": account_id,
            "old_owner_id": old_owner_id,
            "new_owner_id": new_owner_user_id,
        },
    )
    return {
        "old_owner_id": old_owner_id,
        "new_owner_id": new_owner_user_id,
        "transferred_at": now,
    }


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-05 (F-004 / AC-F7): account-level invitation create
# ──────────────────────────────────────────────────────────────────────


async def create_account_invitation(
    account_id: int,
    *,
    email: str,
    role: str = "member",
    invited_by: str,
    expires_in_days: int = 7,
) -> dict:
    """T-V3-B-05 AC-F7.

    account_id 検証 + token 発行 + DB 保存.
    """
    account = await get_account(account_id)
    if not account:
        raise AccountNotFoundError(f"account not found: {account_id}")
    await _ensure_account_invitations_table()
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=expires_in_days)).isoformat(
        timespec="seconds"
    )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO account_invitations
               (account_id, email, role, token, invited_by, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, email, role, token, invited_by, expires_at),
        )
        await db.commit()
    return {
        "account_id": account_id,
        "email": email,
        "role": role,
        "invitation_token": token,
        "expires_at": expires_at,
    }


async def lookup_account_invitation(token: str) -> Optional[dict]:
    """T-V3-B-05 AC-F13. mutate-free な token 解決."""
    if not token or not token.strip():
        return None
    await _ensure_account_invitations_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, account_id, email, role, status, expires_at, invited_by, created_at "
            "FROM account_invitations WHERE token = ?",
            (token,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("expires_at"):
        try:
            d["is_expired"] = datetime.fromisoformat(d["expires_at"]) < datetime.now()
        except Exception:
            d["is_expired"] = False
    else:
        d["is_expired"] = False
    return d


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-05 (F-004 / AC-F11): account member removal
# ──────────────────────────────────────────────────────────────────────


async def remove_account_member(
    account_id: int,
    user_id: str,
    *,
    actor_user_id: Optional[str] = None,
) -> dict:
    """T-V3-B-05 AC-F11.

    EVENT-DRIVEN: 指定 user を account_members から削除。
    UNWANTED: 削除対象が owner なら 409 相当 (CannotRemoveAccountOwnerError).
    """
    account = await get_account(account_id)
    if not account:
        raise AccountNotFoundError(f"account not found: {account_id}")

    member = await get_account_member(account_id, user_id)
    if not member:
        raise AccountNotFoundError(
            f"member {user_id} not found in account {account_id}"
        )

    # AC-F11: owner は削除不可 (まず transfer-owner)
    if member.get("role") == "owner" or account.get("owner_user_id") == user_id:
        raise CannotRemoveAccountOwnerError(
            f"cannot remove account owner {user_id}; transfer ownership first"
        )

    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM account_members WHERE account_id = ? AND user_id = ?",
            (account_id, user_id),
        )
        await db.commit()
    await _emit_audit(
        "accounts.member_removed",
        user_id=actor_user_id,
        detail={"account_id": account_id, "removed_user_id": user_id},
    )
    return {"removed_at": now, "account_id": account_id, "user_id": user_id}
