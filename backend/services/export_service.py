"""T-V3-D-10 (F-031, E-020 Artifact): workspace export service.

`POST /api/workspaces/{id}/exports` のバックエンド. spec_pdf / delivery_report
等の export job を非同期 enqueue し job_id を返す.

設計:
    - 実 PDF rendering は Wave 5 以降の Group B-1 (Headless Chromium pipeline) で実装.
      ここでは **job descriptor を export_jobs テーブルに persist** し、status=queued の
      job_id (uuid) を返す.
    - workspace membership check は caller (router) 側で実施する.

DB schema (SQLite fallback):
    export_jobs(
        id           TEXT PRIMARY KEY  -- uuid v4
        workspace_id INTEGER NOT NULL
        kind         TEXT NOT NULL     -- 'spec_pdf' | 'delivery_report'
        options_json TEXT              -- JSON object string (nullable)
        status       TEXT NOT NULL     -- 'queued' | 'running' | 'done' | 'failed'
        requested_by TEXT              -- actor user_id
        requested_at TEXT NOT NULL
        completed_at TEXT
        artifact_url TEXT              -- 完了時のダウンロード URL
    )
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ALLOWED_KINDS = {"spec_pdf", "delivery_report"}


class ExportError(Exception):
    """汎用 service-layer error."""


class ExportValidationError(ExportError):
    """422 validation error."""


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def _ensure_table() -> None:
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS export_jobs (
                       id           TEXT PRIMARY KEY,
                       workspace_id INTEGER NOT NULL,
                       kind         TEXT NOT NULL,
                       options_json TEXT,
                       status       TEXT NOT NULL,
                       requested_by TEXT,
                       requested_at TEXT NOT NULL,
                       completed_at TEXT,
                       artifact_url TEXT
                   )"""
            )
            await db.commit()
    except Exception as e:  # pragma: no cover
        logger.warning("export_service._ensure_table failed: %s", e)


def _validate(kind: str, options: Optional[dict]) -> None:
    errors: dict[str, str] = {}
    if not isinstance(kind, str) or kind not in ALLOWED_KINDS:
        errors["kind"] = f"kind must be one of {sorted(ALLOWED_KINDS)}"
    if options is not None and not isinstance(options, dict):
        errors["options"] = "options must be an object"
    if errors:
        raise ExportValidationError(errors)


async def enqueue_export(
    workspace_id: int,
    *,
    kind: str,
    options: Optional[dict] = None,
    requested_by: Optional[str] = None,
) -> dict[str, Any]:
    """新 export job を enqueue.

    Returns: { job_id, status: 'queued', kind, requested_at, workspace_id }
    Raises : ExportValidationError
    """
    _validate(kind, options)
    await _ensure_table()
    job_id = str(uuid.uuid4())
    requested_at = _iso()
    options_json = json.dumps(options) if options else None

    async with _db().connect(_db_path()) as db:
        await db.execute(
            """INSERT INTO export_jobs
                   (id, workspace_id, kind, options_json, status,
                    requested_by, requested_at, completed_at, artifact_url)
               VALUES (?, ?, ?, ?, 'queued', ?, ?, NULL, NULL)""",
            (
                job_id,
                workspace_id,
                kind,
                options_json,
                requested_by,
                requested_at,
            ),
        )
        await db.commit()

    return {
        "job_id": job_id,
        "status": "queued",
        "kind": kind,
        "workspace_id": workspace_id,
        "requested_at": requested_at,
    }


async def get_job(job_id: str) -> Optional[dict[str, Any]]:
    """test/debug 用. job descriptor を返す (なければ None)."""
    await _ensure_table()
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """SELECT id, workspace_id, kind, options_json, status,
                      requested_by, requested_at, completed_at, artifact_url
                 FROM export_jobs WHERE id = ?""",
            (job_id,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "job_id": row[0],
        "workspace_id": row[1],
        "kind": row[2],
        "options": json.loads(row[3]) if row[3] else None,
        "status": row[4],
        "requested_by": row[5],
        "requested_at": row[6],
        "completed_at": row[7],
        "artifact_url": row[8],
    }
