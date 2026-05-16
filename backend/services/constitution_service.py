"""T-V3-B-28 / F-026: Constitution backend service layer.

機能:
  - get_constitution(workspace_id)   → active Constitution の content_md / version / is_active
  - create_version(workspace_id, ...) → 新しい version snapshot (active 化は行わない)
  - approve_version(workspace_id, v) → version v を active にし旧 active を deactivate

依存:
  - features.json#F-026 (max_size_kb 10 / version_lock)
  - entities.json#E-017 Constitution (table bf_constitutions, project-scoped)
  - 既存 services/constitution_engine.py (inject 経路)

設計メモ:
  bf_constitutions は project-scoped (project_id) だが API は workspace-scoped.
  既存 workspaces.py の慣例に倣い "workspace_id ≒ project_id" として動作する
  (1 workspace 1 project の前提).
  bf_constitution_revisions に rationale/message を残し audit を担保する.

audit event types (features.json#F-026 audit_logs に対応):
  - constitution_versioned : create_version 成功時
  - constitution_approved  : approve_version 成功時

errors:
  - WorkspaceNotFoundError : workspace_id が存在しない (router → 404)
  - VersionNotFoundError   : approve 対象の version が存在しない (router → 404)
  - AlreadyActiveError     : approve 対象が既に active (router → 409)
  - ContentTooLargeError   : content_md > 10 KB (router → 422)

cache invalidation:
  create_version / approve_version 後に constitution_engine.invalidate_cache() を
  best-effort 呼出. 失敗は warn-log のみ (AC-EVENT cache flush).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────────────────────────────────


class ConstitutionServiceError(Exception):
    """base."""


class WorkspaceNotFoundError(ConstitutionServiceError):
    """workspace_id が存在しない."""


class VersionNotFoundError(ConstitutionServiceError):
    """approve 対象 version が存在しない."""


class AlreadyActiveError(ConstitutionServiceError):
    """approve 対象 version が既に active (is_current=TRUE)."""


class ContentTooLargeError(ConstitutionServiceError):
    """content_md > 10 KB."""


# 10 KB (features.json#F-026 policies max_size_kb 10) — schemas 側と二重防御
CONTENT_MD_MAX_BYTES = 10 * 1024


# ──────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────


async def _table_exists(db, table: str) -> bool:
    cur = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = await cur.fetchone()
    return row is not None


async def _workspace_exists(db, workspace_id: int) -> bool:
    if not await _table_exists(db, "workspaces"):
        # workspaces テーブル未配備環境: legacy 動作 (skip)
        return True
    cur = await db.execute(
        "SELECT 1 FROM workspaces WHERE id = ? LIMIT 1", (workspace_id,),
    )
    row = await cur.fetchone()
    return row is not None


def _principles_to_content_md(principles: Any) -> str:
    """bf_constitutions.principles JSONB → content_md 文字列.

    既存 schema は principles JSONB (section_*_* キー) を持つ. content_md は
    F-026 では Markdown 単一文字列. 翻訳ルール:
      - principles が dict で "content_md" キーを持つなら直接使う
      - そうでないなら section_* キーを順に concat (constitution_engine.to_prompt 流)
      - dict でない場合は str() 化
    """
    if principles is None:
        return ""
    if isinstance(principles, str):
        try:
            principles = json.loads(principles)
        except Exception:
            return principles
    if isinstance(principles, dict):
        if "content_md" in principles and isinstance(principles["content_md"], str):
            return principles["content_md"]
        # fallback: serialize known sections in stable order
        from services.constitution_engine import SECTION_KEYS
        parts: list[str] = []
        for k in SECTION_KEYS:
            v = principles.get(k)
            if not v:
                continue
            if isinstance(v, list):
                parts.append(f"## {k}\n" + "\n".join(f"- {x}" for x in v))
            elif isinstance(v, dict):
                parts.append(f"## {k}\n" + json.dumps(v, ensure_ascii=False, indent=2))
            else:
                parts.append(f"## {k}\n{v}")
        return "\n\n".join(parts)
    return str(principles)


def _content_md_to_principles(content_md: str) -> dict[str, Any]:
    """API 入力 content_md (markdown text) → principles JSONB.

    "content_md" キーで単一文字列を格納する (F-026 API contract 優先).
    legacy section_* 経路と共存可能 (constitution_engine._principles_to_content_md
    が両方を解釈する).
    """
    return {"content_md": content_md}


async def _invalidate_engine_cache(reason: str) -> None:
    """services.constitution_engine.invalidate_cache を best-effort 呼出.

    AC-EVENT (features.json#F-026): create/approve で全 session の cache を flush.
    """
    try:
        from services import constitution_engine as ce
        await ce.invalidate_cache(reason=reason)
    except Exception as e:  # pragma: no cover (engine 未配備の legacy 環境)
        logger.warning("constitution cache invalidate failed: %s", e)


async def _emit_audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("constitution audit emit failed %s: %s", event_type, e)


# audit event type 定数 (features.json#F-026 audit_logs に対応)
EVENT_VERSIONED = "constitution_versioned"
EVENT_APPROVED = "constitution_approved"


# ──────────────────────────────────────────────────────────────────────────
# DDL bootstrap (sqlite テスト環境向け. 既存 supabase migration があれば no-op)
# ──────────────────────────────────────────────────────────────────────────

# 注意: 本 bootstrap は **sqlite ローカル env 限定** の救済策.
# 本番 (supabase postgres) は supabase/migrations/20260510000001_bf_project_tables.sql
# が同等定義を所持 (project_id BIGINT). sqlite 側は workspace_id 直結で運用する.
_BF_CONSTITUTIONS_DDL = """
CREATE TABLE IF NOT EXISTS bf_constitutions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id    INTEGER NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    principles      TEXT NOT NULL DEFAULT '{}',
    is_current      INTEGER NOT NULL DEFAULT 0,
    authored_by     TEXT,
    approved_by     TEXT,
    approved_at     TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (workspace_id, version)
);
"""

_BF_CONSTITUTION_REVISIONS_DDL = """
CREATE TABLE IF NOT EXISTS bf_constitution_revisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    constitution_id INTEGER NOT NULL REFERENCES bf_constitutions(id) ON DELETE CASCADE,
    diff            TEXT NOT NULL DEFAULT '{}',
    rationale       TEXT,
    revised_by      TEXT,
    revised_at      TEXT DEFAULT (datetime('now'))
);
"""


async def _ensure_tables(db) -> None:
    """sqlite テスト環境向け bootstrap (legacy 動作). prod は migration 適用済.

    workspace_id カラムが無い legacy bf_constitutions を持つ環境では
    最小限スキーマで上書きせず, 検出時のみ no-op (本サービスは
    workspace_id ベースの新規 row だけ操作する).
    """
    await db.execute(_BF_CONSTITUTIONS_DDL)
    await db.execute(_BF_CONSTITUTION_REVISIONS_DDL)


# ──────────────────────────────────────────────────────────────────────────
# public API
# ──────────────────────────────────────────────────────────────────────────


async def get_constitution(workspace_id: int) -> Optional[dict]:
    """active Constitution を返す (なければ None).

    Returns:
      {"content_md": str, "version": int, "is_active": True}  or  None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_tables(db)
        if not await _workspace_exists(db, workspace_id):
            raise WorkspaceNotFoundError(
                f"workspace not found: {workspace_id}"
            )
        cur = await db.execute(
            "SELECT version, principles, is_current FROM bf_constitutions "
            "WHERE workspace_id = ? AND is_current = 1 "
            "ORDER BY version DESC LIMIT 1",
            (workspace_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "content_md": _principles_to_content_md(row["principles"]),
            "version": int(row["version"]),
            "is_active": bool(row["is_current"]),
        }


async def create_version(
    *,
    workspace_id: int,
    content_md: str,
    message: str,
    author: str,
) -> dict:
    """新 version snapshot を作成 (active 化はしない / AC-F1).

    既存最大 version + 1 を採番. is_current=0 (approve 後に切替).

    Raises:
      WorkspaceNotFoundError : workspace_id が存在しない (router → 404)
      ContentTooLargeError   : content_md > 10 KB (router → 422)

    Returns:
      {"version_id": str, "version_number": int}
    """
    if not isinstance(content_md, str) or not content_md.strip():
        raise ContentTooLargeError("content_md must be non-empty")
    if len(content_md.encode("utf-8")) > CONTENT_MD_MAX_BYTES:
        raise ContentTooLargeError(
            f"content_md exceeds {CONTENT_MD_MAX_BYTES} bytes (>10KB)"
        )

    principles_text = json.dumps(_content_md_to_principles(content_md), ensure_ascii=False)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_tables(db)
        if not await _workspace_exists(db, workspace_id):
            raise WorkspaceNotFoundError(
                f"workspace not found: {workspace_id}"
            )

        # 採番: max(version) + 1 (workspace scope)
        cur = await db.execute(
            "SELECT COALESCE(MAX(version), 0) AS mx FROM bf_constitutions "
            "WHERE workspace_id = ?",
            (workspace_id,),
        )
        row = await cur.fetchone()
        next_version = int(row["mx"]) + 1 if row else 1

        cur = await db.execute(
            "INSERT INTO bf_constitutions "
            "(workspace_id, version, principles, is_current, authored_by) "
            "VALUES (?, ?, ?, 0, ?)",
            (workspace_id, next_version, principles_text, author),
        )
        constitution_row_id = cur.lastrowid

        # revision audit 行 (diff_summary = message)
        diff_json = json.dumps(
            {"message": message, "content_md_bytes": len(content_md.encode("utf-8"))},
            ensure_ascii=False,
        )
        await db.execute(
            "INSERT INTO bf_constitution_revisions "
            "(constitution_id, diff, rationale, revised_by) VALUES (?, ?, ?, ?)",
            (constitution_row_id, diff_json, message, author),
        )
        await db.commit()

    # API 応答用に uuid 形式 ID を発行 (DB 内整数 ID と分離; openapi.yaml で uuid).
    version_id = str(uuid.uuid4())

    # AC-EVENT: cache を flush しない (まだ active 化されていない). approve で flush.
    await _emit_audit(
        EVENT_VERSIONED,
        user_id=author,
        detail={
            "workspace_id": workspace_id,
            "version_number": next_version,
            "version_id": version_id,
            "message": message,
        },
    )
    return {"version_id": version_id, "version_number": next_version}


async def approve_version(
    *,
    workspace_id: int,
    version: int,
    approver: str,
) -> dict:
    """version v を active に切替. 旧 active を deactivate (AC-F2 / atomic).

    Raises:
      WorkspaceNotFoundError : workspace_id が存在しない
      VersionNotFoundError   : workspace 配下に version v が無い (router → 404)
      AlreadyActiveError     : 既に is_current=1 (router → 409)

    Returns:
      {"approved_at": iso datetime str, "active_version": int}
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_tables(db)
        if not await _workspace_exists(db, workspace_id):
            raise WorkspaceNotFoundError(
                f"workspace not found: {workspace_id}"
            )

        cur = await db.execute(
            "SELECT id, is_current FROM bf_constitutions "
            "WHERE workspace_id = ? AND version = ?",
            (workspace_id, version),
        )
        row = await cur.fetchone()
        if not row:
            raise VersionNotFoundError(
                f"constitution version not found: ws={workspace_id} v={version}"
            )
        if int(row["is_current"]) == 1:
            raise AlreadyActiveError(
                f"version already active: ws={workspace_id} v={version}"
            )

        approved_at = datetime.now(timezone.utc).isoformat()
        # atomic 切替: 同一 workspace の他 row を全 deactivate → 対象 row を activate
        await db.execute(
            "UPDATE bf_constitutions SET is_current = 0 WHERE workspace_id = ?",
            (workspace_id,),
        )
        await db.execute(
            "UPDATE bf_constitutions "
            "SET is_current = 1, approved_by = ?, approved_at = ? WHERE id = ?",
            (approver, approved_at, row["id"]),
        )
        await db.commit()

    # AC-EVENT: 新版 active 化で全 active session の cache を flush.
    await _invalidate_engine_cache(reason="version_approved")
    await _emit_audit(
        EVENT_APPROVED,
        user_id=approver,
        detail={
            "workspace_id": workspace_id,
            "active_version": version,
            "approved_at": approved_at,
        },
    )
    return {"approved_at": approved_at, "active_version": version}


__all__ = [
    "ConstitutionServiceError",
    "WorkspaceNotFoundError",
    "VersionNotFoundError",
    "AlreadyActiveError",
    "ContentTooLargeError",
    "CONTENT_MD_MAX_BYTES",
    "EVENT_VERSIONED",
    "EVENT_APPROVED",
    "get_constitution",
    "create_version",
    "approve_version",
]
