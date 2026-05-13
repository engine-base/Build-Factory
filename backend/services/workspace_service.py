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


# T-024-04 (ADR-012 Decision 5): workspace 単位の provider 切替.
# precedence の workspace 層 source として参照される.
# precedence: per-request header > per-session active_route >
#             per-workspace preferred_provider > BYOK > ADR-010 default >
#             T-AI-08 circuit-breaker fallback
VALID_PREFERRED_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "gemini", "auto")
DEFAULT_PREFERRED_PROVIDER: str = "auto"


class InvalidPreferredProviderError(ValueError):
    """T-024-04 AC-4: enum 外の値で reject (router 層で 4xx 変換)."""


def validate_preferred_provider(value) -> str:
    """preferred_provider の enum check. None / 空文字列は default で埋める."""
    if value is None:
        return DEFAULT_PREFERRED_PROVIDER
    if not isinstance(value, str):
        raise InvalidPreferredProviderError(
            f"preferred_provider must be string, got {type(value).__name__}"
        )
    s = value.strip()
    if not s:
        return DEFAULT_PREFERRED_PROVIDER
    if s not in VALID_PREFERRED_PROVIDERS:
        raise InvalidPreferredProviderError(
            f"preferred_provider must be one of {VALID_PREFERRED_PROVIDERS}, got {s!r}"
        )
    return s


async def _has_column(db, table: str, column: str) -> bool:
    """T-024-04: workspaces.preferred_provider 等の後方互換性 shim.

    既存 build.db に migration h5c6d7e8f9a1 が未適用な環境でも legacy 動作
    できるよう, column 存在を runtime チェックする.
    """
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return any(r[1] == column for r in rows)


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
    preferred_provider: Optional[str] = None,
) -> dict:
    """workspace 新規作成。creator は自動で admin role で member に追加。

    T-024-04: preferred_provider を optional で受ける. enum 外値は
    InvalidPreferredProviderError (router で 4xx 変換).
    """
    pref = validate_preferred_provider(preferred_provider)
    async with aiosqlite.connect(DB_PATH) as db:
        # base INSERT (既存 column のみ. preferred_provider は migration 適用後
        # にのみ UPDATE で設定 = T-024-04 後方互換 shim)
        cur = await db.execute(
            """INSERT INTO workspaces
               (account_id, name, description, project_meta)
               VALUES (?, ?, ?, ?) RETURNING id""",
            (account_id, name, description,
             json.dumps(project_meta or {}, ensure_ascii=False)),
        )
        _row = await cur.fetchone()
        workspace_id = _row["id"]
        # T-024-04: preferred_provider column 存在時のみ UPDATE で値を確定
        # (column 未存在 = migration 未適用なら default 'auto' 相当で legacy 動作)
        if await _has_column(db, "workspaces", "preferred_provider"):
            await db.execute(
                "UPDATE workspaces SET preferred_provider = ? WHERE id = ?",
                (pref, workspace_id),
            )
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
    actor_user_id = fields.pop("actor_user_id", None)
    cols, vals = [], []
    # S-013 一般タブ + S-013 統合タブ + フェーズゲート 列 (migration g4b5c6d7e8f9 で追加)
    for k in (
        "name", "description", "status", "design_system_ref",
        "client_name", "due_date", "github_repo", "slack_channel",
        "phase_gate_mode",
    ):
        if k in fields:
            cols.append(f"{k} = ?"); vals.append(fields[k])
    if "budget_jpy_monthly" in fields:
        cols.append("budget_jpy_monthly = ?")
        vals.append(fields["budget_jpy_monthly"])
    # T-024-04 (ADR-012 Decision 5): provider 任意切替の workspace 層 source.
    # column 未存在環境では UPDATE 文に含めず legacy 動作 (後方互換 shim).
    preferred_to_apply: Optional[str] = None
    if "preferred_provider" in fields:
        # validation: 不正値は InvalidPreferredProviderError を raise (router 層 4xx).
        preferred_to_apply = validate_preferred_provider(fields["preferred_provider"])
    for k in ("project_meta", "client_visibility", "redlines"):
        if k in fields:
            cols.append(f"{k} = ?"); vals.append(json.dumps(fields[k], ensure_ascii=False))
    cols.append("updated_at = datetime('now','localtime')")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE workspaces SET {', '.join(cols)} WHERE id = ?",
            [*vals, workspace_id],
        )
        # T-024-04 shim: preferred_provider column 存在時のみ別 UPDATE で適用
        # (column 未存在 = migration 未適用なら silent skip で legacy 動作)
        if preferred_to_apply is not None and await _has_column(
            db, "workspaces", "preferred_provider"
        ):
            await db.execute(
                "UPDATE workspaces SET preferred_provider = ? WHERE id = ?",
                (preferred_to_apply, workspace_id),
            )
        await db.commit()
    await _emit_audit(
        "workspace.updated",
        user_id=actor_user_id,
        detail={"workspace_id": workspace_id, "changed_fields": list(fields.keys())},
    )
    return await get_workspace(workspace_id) or {}


async def archive_workspace(workspace_id: int, *, actor_user_id: Optional[str] = None) -> dict:
    result = await update_workspace(workspace_id, status="archived", actor_user_id=actor_user_id)
    await _emit_audit(
        "workspace.archived",
        user_id=actor_user_id,
        detail={"workspace_id": workspace_id},
    )
    return result


# ──────────────────────────────────────────
# audit_logs (T-021/T-023/T-004-05 共通)
# ──────────────────────────────────────────
async def _emit_audit(event_type: str, *, user_id: Optional[str] = None, detail: Optional[dict] = None) -> None:
    """audit_logs に event を流す。失敗してもアプリは止めない。"""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:
        # logger ではなく print (この service が logging を未 import のため)
        print(f"[workspace_service] audit emit failed: {event_type} -- {e}")


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
    await _emit_audit(
        "workspace.member.added",
        user_id=invited_by,
        detail={
            "workspace_id": workspace_id,
            "target_user_id": user_id,
            "role": role,
            "has_custom_permissions": bool(custom_permissions),
        },
    )
    return await get_member(workspace_id, user_id) or {}


class SelfStripError(ValueError):
    """T-021-05: self-strip block — 自分自身の権限を剥奪することは禁止。"""


class OwnerProtectedError(ValueError):
    """T-021-05: owner ロールは降格/削除できない (最後の 1 人は特に)。"""


class TargetNotMemberError(ValueError):
    """T-004-05 AC-UNWANTED: owner 移譲先がメンバーでない。"""


class NotOwnerError(ValueError):
    """T-004-05 AC-STATE: owner ではないユーザーが移譲しようとした。"""


# T-004-04: invitation accept 用例外
class InvitationNotFoundError(ValueError):
    """invitation token が見つからない."""


class InvitationExpiredError(ValueError):
    """invitation が期限切れ."""


class InvitationAlreadyUsedError(ValueError):
    """invitation が既に accepted (再利用)."""


# ──────────────────────────────────────────
# T-004-05: owner 移譲 (atomic)
# ──────────────────────────────────────────
async def transfer_ownership(
    workspace_id: int,
    *,
    current_owner_id: str,
    new_owner_id: str,
) -> dict:
    """Owner を current → new に atomic に移譲する。

    AC (T-004-05):
      - UBIQUITOUS: 既存メンバーへ移譲できる
      - EVENT: current_owner を ws_admin に降格、 new_owner を owner に昇格 (atomic)
      - STATE: current_owner_id が actually owner でない場合 NotOwnerError
      - UNWANTED: new_owner_id が member でない場合 TargetNotMemberError

    実装方針: 同一トランザクション内で 2 行 UPDATE。
    """
    if current_owner_id == new_owner_id:
        raise ValueError("current_owner_id and new_owner_id are the same")

    # 1. current_owner が実際に owner か確認
    current = await get_member(workspace_id, current_owner_id)
    if not current or current.get("role") != "owner":
        raise NotOwnerError(f"{current_owner_id} is not the current owner of workspace {workspace_id}")

    # 2. new_owner_id が既存メンバーか確認
    target = await get_member(workspace_id, new_owner_id)
    if not target:
        raise TargetNotMemberError(
            f"target user {new_owner_id} is not a member of workspace {workspace_id}"
        )

    # 3. atomic な UPDATE 2 件 (同一 connection)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE workspace_members SET role = 'ws_admin' "
            "WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, current_owner_id),
        )
        await db.execute(
            "UPDATE workspace_members SET role = 'owner' "
            "WHERE workspace_id = ? AND user_id = ?",
            (workspace_id, new_owner_id),
        )
        await db.commit()

    await _emit_audit(
        "workspace.ownership_transferred",
        user_id=current_owner_id,
        detail={
            "workspace_id": workspace_id,
            "from_user_id": current_owner_id,
            "to_user_id": new_owner_id,
        },
    )
    return {
        "ok": True,
        "workspace_id": workspace_id,
        "from_user_id": current_owner_id,
        "to_user_id": new_owner_id,
    }


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
    await _emit_audit(
        "workspace.member.updated",
        user_id=actor_user_id,
        detail={
            "workspace_id": workspace_id,
            "target_user_id": user_id,
            "new_role": role,
            "custom_permissions_changed": custom_permissions is not None,
        },
    )
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
        removed = (cur.rowcount or 0) > 0
    if removed:
        await _emit_audit(
            "workspace.member.removed",
            user_id=actor_user_id,
            detail={"workspace_id": workspace_id, "target_user_id": user_id},
        )
    return removed


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
            "SELECT * FROM workspace_invitations WHERE token = ?",
            (token,),
        )
        inv = await cur.fetchone()
        if not inv:
            raise InvitationNotFoundError(f"invitation not found: token=...")
        d = dict(inv)
        status = d.get("status") or "pending"
        if status == "accepted":
            raise InvitationAlreadyUsedError(
                f"invitation already accepted (workspace_id={d['workspace_id']})"
            )
        if status == "expired":
            raise InvitationExpiredError("invitation already expired")
        if status != "pending":
            raise InvitationNotFoundError(f"invitation in invalid state: {status}")
        # 期限チェック
        if d.get("expires_at"):
            try:
                if datetime.fromisoformat(d["expires_at"]) < datetime.now():
                    await db.execute(
                        "UPDATE workspace_invitations SET status='expired' WHERE id=?", (d["id"],)
                    )
                    await db.commit()
                    raise InvitationExpiredError("invitation expired")
            except (InvitationExpiredError, InvitationAlreadyUsedError):
                raise
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


# ──────────────────────────────────────────────────────────────────────────
# T-004-04: lookup_invitation (signup 前のプレビュー)
# ──────────────────────────────────────────────────────────────────────────


async def lookup_invitation(token: str) -> Optional[dict]:
    """token から invitation メタを返す (signup 前のプレビュー). mutate しない."""
    if not token or not token.strip():
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, workspace_id, email, role, status, expires_at, invited_by "
            "FROM workspace_invitations WHERE token = ?",
            (token,),
        )
        if not rows:
            return None
        d = dict(rows[0])
    # 期限切れチェック (read-only なので state mutate しない)
    if d.get("expires_at"):
        try:
            d["is_expired"] = datetime.fromisoformat(d["expires_at"]) < datetime.now()
        except Exception:
            d["is_expired"] = False
    else:
        d["is_expired"] = False
    return d
