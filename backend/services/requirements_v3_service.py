"""requirements_v3_service.py — T-V3-B-10 / F-006 backend service.

Phase 1 v3 Wave 1 で新規実装する F-006 要件 CRUD / versions / task comments.

公開関数:
  * list_requirements(workspace_id) -> dict  (GET /api/workspaces/{id}/requirements)
  * upsert_requirements(workspace_id, items, *, actor_user_id) -> dict  (PUT)
  * create_version(workspace_id, message, *, actor_user_id) -> dict  (POST /versions)
  * add_task_comment(task_id, body, *, actor_user_id) -> dict  (POST /api/tasks/{id}/comments)
  * list_task_comments(task_id) -> list[dict]

EARS form validator:
  * validate_ears_items(items) -> list[int]  (offending indices, [] なら全件 OK)

3-tier AC:
  Tier 2 functional (T-V3-B-10):
    AC-F1  EVENT-DRIVEN PUT requirements persist + return version+1
    AC-F2  UNWANTED      PUT items が EARS 違反 → 422 + offending indices
    AC-F3  EVENT-DRIVEN POST versions snapshot + return version_id
    AC-F13 EVENT-DRIVEN POST /api/tasks/{id}/comments → 2xx + comment_id
  Tier 3 regression: RLS / pyright / ruff / pytest coverage

SQLite (build.db) 上の互換層を持つ. Supabase Postgres migration
`supabase/migrations/20260516000000_bf_requirements_versions_comments.sql` と
1:1 構造で, RLS は Postgres 側で enforce する.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH


# ──────────────────────────────────────────────────────────────────────────
# EARS form validation
#
# EARS notation 5 形式 (CLAUDE.md §3 / docs/api-design ears-ac-seed と整合):
#   1. UBIQUITOUS    : The system shall ...
#   2. EVENT-DRIVEN  : When [event], the system shall ...
#   3. STATE-DRIVEN  : While [state], the system shall ...
#   4. OPTIONAL      : Where [feature is enabled], the system shall ...
#   5. UNWANTED      : If [unwanted condition], the system shall not ...
#
# Validator は (1) ears_type が enum (2) text が ears_type 接頭辞と整合 (3)
# "the system shall" を含む の 3 点を機械検証する.
# ──────────────────────────────────────────────────────────────────────────

VALID_EARS_TYPES: tuple[str, ...] = (
    "UBIQUITOUS",
    "EVENT-DRIVEN",
    "STATE-DRIVEN",
    "OPTIONAL",
    "UNWANTED",
)

# ears_type → text 接頭辞 (lower-case 比較). UBIQUITOUS は接頭辞なし.
_EARS_PREFIX: dict[str, tuple[str, ...]] = {
    "EVENT-DRIVEN": ("when ",),
    "STATE-DRIVEN": ("while ",),
    "OPTIONAL": ("where ",),
    "UNWANTED": ("if ",),
    "UBIQUITOUS": (),  # 接頭辞無し
}

_SHALL_RE = re.compile(r"\bthe system shall(?:\s+not)?\b", re.IGNORECASE)


class EarsValidationError(ValueError):
    """EARS form validation で 1 件以上の違反があることを示す.

    `offending_indices` には items 配列での 0-based index を入れる.
    `field_errors` は 422 レスポンス body 用の field-level error map.
    """

    def __init__(
        self,
        offending_indices: list[int],
        field_errors: list[dict[str, Any]],
    ) -> None:
        super().__init__(
            f"EARS validation failed for items: {offending_indices}"
        )
        self.offending_indices = offending_indices
        self.field_errors = field_errors


def validate_ears_items(items: list[dict[str, Any]]) -> list[int]:
    """items の各要素が EARS 形式に適合しているかを検査.

    Returns:
        offending_indices: EARS 違反の index list (空なら全件 OK)

    Side-effects: なし (pure function)
    """
    offending: list[int] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            offending.append(i)
            continue
        ears_type = it.get("ears_type")
        text = it.get("text")
        if not isinstance(ears_type, str) or ears_type not in VALID_EARS_TYPES:
            offending.append(i)
            continue
        if not isinstance(text, str) or not text.strip():
            offending.append(i)
            continue
        low = text.strip().lower()
        prefixes = _EARS_PREFIX.get(ears_type, ())
        if prefixes and not any(low.startswith(p) for p in prefixes):
            offending.append(i)
            continue
        if not _SHALL_RE.search(low):
            offending.append(i)
            continue
    return offending


def _build_field_errors(offending: list[int]) -> list[dict[str, Any]]:
    """422 response body 用の field-level error map を生成."""
    return [
        {
            "loc": ["items", i],
            "code": "ears_validation_failed",
            "message": (
                "item does not conform to EARS notation "
                f"(index={i}). Must be one of UBIQUITOUS/EVENT-DRIVEN/"
                "STATE-DRIVEN/OPTIONAL/UNWANTED with matching prefix and "
                "'the system shall' clause."
            ),
        }
        for i in offending
    ]


# ──────────────────────────────────────────────────────────────────────────
# SQLite schema bootstrap (Supabase 環境では Postgres migration が source)
# ──────────────────────────────────────────────────────────────────────────


_BOOTSTRAP_SQL = [
    """CREATE TABLE IF NOT EXISTS bf_requirements (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id    INTEGER NOT NULL,
        item_index      INTEGER NOT NULL,
        ears_type       TEXT NOT NULL,
        text            TEXT NOT NULL,
        title           TEXT,
        category        TEXT,
        version         INTEGER NOT NULL DEFAULT 1,
        created_by      TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now')),
        UNIQUE (workspace_id, item_index)
    )""",
    """CREATE INDEX IF NOT EXISTS ix_bf_requirements_ws
        ON bf_requirements(workspace_id)""",
    """CREATE TABLE IF NOT EXISTS bf_requirement_versions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id    INTEGER NOT NULL,
        version_number  INTEGER NOT NULL,
        message         TEXT,
        snapshot        TEXT NOT NULL,
        created_by      TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        UNIQUE (workspace_id, version_number)
    )""",
    """CREATE INDEX IF NOT EXISTS ix_bf_req_versions_ws
        ON bf_requirement_versions(workspace_id)""",
    """CREATE TABLE IF NOT EXISTS bf_task_comments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id         INTEGER NOT NULL,
        body            TEXT NOT NULL,
        author_user_id  TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE INDEX IF NOT EXISTS ix_bf_task_comments_task
        ON bf_task_comments(task_id)""",
]


async def _ensure_schema(db: Any) -> None:
    """SQLite shadow schema を初期化 (idempotent).

    Supabase 環境では migration が source-of-truth で, SQLite 側は dev/test 用 shim.
    `CREATE TABLE IF NOT EXISTS` なので何度呼んでも安全.
    """
    for stmt in _BOOTSTRAP_SQL:
        await db.execute(stmt)


def _row(r: Any) -> dict:
    return dict(r) if r else {}


# ──────────────────────────────────────────────────────────────────────────
# Public API: requirements CRUD
# ──────────────────────────────────────────────────────────────────────────


async def get_current_version(workspace_id: int) -> int:
    """現在の (最新) version 番号を返す. 未存在なら 0."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        cur = await db.execute(
            "SELECT MAX(version) AS v FROM bf_requirements WHERE workspace_id = ?",
            (workspace_id,),
        )
        row = await cur.fetchone()
        v = row[0] if row else None
        return int(v) if v else 0


async def list_requirements(workspace_id: int) -> dict:
    """GET /api/workspaces/{id}/requirements の戻り値を構築.

    Response shape (features.json#F-006):
        {"requirements": [Requirement, ...], "version": int}

    AC-F4: 認可済み呼び出し → 2xx + 上記 contract.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, workspace_id, item_index, ears_type, text,
                       title, category, version, created_at, updated_at
                 FROM bf_requirements
                WHERE workspace_id = ?
                ORDER BY item_index ASC""",
            (workspace_id,),
        )
        items = [_row(r) for r in rows]
    version = max((it["version"] for it in items), default=0)
    return {"requirements": items, "version": version}


async def upsert_requirements(
    workspace_id: int,
    items: list[dict[str, Any]],
    *,
    actor_user_id: Optional[str] = None,
) -> dict:
    """PUT /api/workspaces/{id}/requirements (AC-F1 + AC-F2).

    AC-F1 (EVENT-DRIVEN): EARS-conformant items を persist し version+1 を返す.
    AC-F2 (UNWANTED):     EARS form 違反があれば EarsValidationError raise
                          (caller が 422 + offending indices に変換).

    実装方針:
      1. items を validate. NG なら EarsValidationError.
      2. 現在の version を取得し +1 する.
      3. workspace の既存 requirements を全削除 → 新 items を INSERT.
      4. {"id": str(workspace_id), "version": new_version} を返す
         (openapi.yaml 4828- にある PUT response contract).
    """
    if not isinstance(items, list):
        raise EarsValidationError(
            offending_indices=[-1],
            field_errors=[{
                "loc": ["items"],
                "code": "ears_validation_failed",
                "message": "items must be an array",
            }],
        )

    offending = validate_ears_items(items)
    if offending:
        raise EarsValidationError(
            offending_indices=offending,
            field_errors=_build_field_errors(offending),
        )

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        cur = await db.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM bf_requirements "
            "WHERE workspace_id = ?",
            (workspace_id,),
        )
        row = await cur.fetchone()
        current = int(row[0] or 0)
        new_version = current + 1

        await db.execute(
            "DELETE FROM bf_requirements WHERE workspace_id = ?",
            (workspace_id,),
        )
        for i, it in enumerate(items):
            await db.execute(
                """INSERT INTO bf_requirements
                   (workspace_id, item_index, ears_type, text,
                    title, category, version, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    workspace_id, i,
                    it.get("ears_type"), it.get("text"),
                    it.get("title"), it.get("category"),
                    new_version, actor_user_id,
                ),
            )
        await db.commit()

    return {"id": str(workspace_id), "version": new_version}


# ──────────────────────────────────────────────────────────────────────────
# Public API: requirement versions (snapshot)
# ──────────────────────────────────────────────────────────────────────────


async def create_version(
    workspace_id: int,
    message: str,
    *,
    actor_user_id: Optional[str] = None,
) -> dict:
    """POST /api/workspaces/{id}/requirements/versions (AC-F3 / AC-F10).

    現在の bf_requirements を snapshot として bf_requirement_versions に保存.

    Returns: {"version_id": str, "version_number": int}
    """
    snapshot_data = await list_requirements(workspace_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        cur = await db.execute(
            "SELECT COALESCE(MAX(version_number), 0) AS v "
            "FROM bf_requirement_versions WHERE workspace_id = ?",
            (workspace_id,),
        )
        row = await cur.fetchone()
        next_version = int(row[0] or 0) + 1

        ins = await db.execute(
            """INSERT INTO bf_requirement_versions
               (workspace_id, version_number, message, snapshot, created_by)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (
                workspace_id, next_version, message,
                json.dumps(snapshot_data, ensure_ascii=False),
                actor_user_id,
            ),
        )
        ver_row = await ins.fetchone()
        await db.commit()
        version_pk = ver_row[0] if ver_row else None
    return {
        "version_id": str(version_pk) if version_pk is not None else None,
        "version_number": next_version,
    }


async def list_versions(workspace_id: int) -> list[dict]:
    """workspace の version history を返す (内部用 / debug)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, workspace_id, version_number, message,
                       created_by, created_at
                 FROM bf_requirement_versions
                WHERE workspace_id = ?
                ORDER BY version_number DESC""",
            (workspace_id,),
        )
    return [_row(r) for r in rows]


# ──────────────────────────────────────────────────────────────────────────
# Public API: task comments
# ──────────────────────────────────────────────────────────────────────────


class TaskNotFoundError(ValueError):
    """指定 task_id が bf_tasks に無い (router が 404 に変換)."""


async def _task_exists(db: Any, task_id: int) -> bool:
    """bf_tasks が無い test 環境では存在しないと扱う代わりに常に True とみなす.

    (T-V3-B-10 では comment 投稿の bf_tasks FK は Supabase 側で enforce.
     SQLite shadow では bf_tasks の存否を optional check に留める.)
    """
    try:
        cur = await db.execute(
            "SELECT 1 FROM bf_tasks WHERE id = ? LIMIT 1", (task_id,),
        )
        row = await cur.fetchone()
        return row is not None
    except Exception:
        # bf_tasks table が無い test 環境では check を skip
        return True


async def add_task_comment(
    task_id: int,
    body: str,
    *,
    actor_user_id: Optional[str] = None,
    enforce_task_exists: bool = False,
) -> dict:
    """POST /api/tasks/{id}/comments (AC-F13).

    Args:
      task_id: bf_tasks.id (BIGINT).
      body: comment 本文 (空文字列は router 側で 422 にする).
      actor_user_id: comment 作成者.
      enforce_task_exists: True なら bf_tasks に該当 row が無い場合
        TaskNotFoundError を raise (router 層で 404).

    Returns: {"comment_id": str}
    """
    if not isinstance(body, str) or not body.strip():
        raise ValueError("body must be a non-empty string")
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        if enforce_task_exists:
            exists = await _task_exists(db, task_id)
            if not exists:
                raise TaskNotFoundError(
                    f"task not found: id={task_id}"
                )
        cur = await db.execute(
            """INSERT INTO bf_task_comments (task_id, body, author_user_id)
               VALUES (?, ?, ?) RETURNING id""",
            (task_id, body, actor_user_id),
        )
        row = await cur.fetchone()
        await db.commit()
        comment_pk = row[0] if row else None
    return {"comment_id": str(comment_pk) if comment_pk is not None else None}


async def list_task_comments(task_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, task_id, body, author_user_id, created_at, updated_at
                 FROM bf_task_comments
                WHERE task_id = ?
                ORDER BY created_at ASC, id ASC""",
            (task_id,),
        )
    return [_row(r) for r in rows]
