"""T-008-01: phases (bf_phases) CRUD service.

architecture-v1 §4 / T-001-04 で定義された bf_phases テーブルへの CRUD ラッパ.

公開 API:
  list_phases(project_id) -> list[dict]
  get_phase(phase_id) -> dict | None
  create_phase(project_id, phase_no, name, ...) -> dict
  update_phase(phase_id, **fields) -> dict
  delete_phase(phase_id) -> bool   (実態は status='skipped' soft-delete)
  start_phase(phase_id) -> dict    (status='in_progress' + started_at)
  complete_phase(phase_id) -> dict (status='completed' + completed_at)

AC:
  - phase_no は 1-10 (CHECK 制約と整合)
  - status enum: pending / in_progress / completed / blocked / skipped
  - 同 project 内で phase_no 一意 (uq_bf_phase)
"""
from __future__ import annotations

import json
from typing import Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH


VALID_PHASE_STATUSES = ("pending", "in_progress", "completed", "blocked", "skipped")
PHASE_NO_MIN = 1
PHASE_NO_MAX = 10


class InvalidPhaseInput(ValueError):
    """phase_no / status / project_id の入力 invalid."""


class PhaseNotFound(ValueError):
    """指定 phase_id が DB に存在しない."""


def _row(r) -> dict:
    return dict(r) if r else {}


def _validate_phase_no(phase_no: int) -> None:
    if not isinstance(phase_no, int) or phase_no < PHASE_NO_MIN or phase_no > PHASE_NO_MAX:
        raise InvalidPhaseInput(
            f"phase_no must be {PHASE_NO_MIN}-{PHASE_NO_MAX}, got {phase_no!r}"
        )


def _validate_status(status: str) -> None:
    if status not in VALID_PHASE_STATUSES:
        raise InvalidPhaseInput(
            f"status must be one of {VALID_PHASE_STATUSES}, got {status!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────


async def list_phases(project_id: int) -> list[dict]:
    """project の全 phase を phase_no 順で返す."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM bf_phases WHERE project_id = ? ORDER BY phase_no ASC",
            (project_id,),
        )
    return [_row(r) for r in rows]


async def get_phase(phase_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bf_phases WHERE id = ?", (phase_id,))
        row = await cur.fetchone()
    return _row(row) if row else None


async def create_phase(
    *,
    project_id: int,
    phase_no: int,
    name: str,
    artifacts_dir: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """新規 phase を作成. phase_no が duplicate なら ValueError."""
    _validate_phase_no(phase_no)
    if not name or not name.strip():
        raise InvalidPhaseInput("name must not be empty")
    name = name.strip()

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """INSERT INTO bf_phases (project_id, phase_no, name, artifacts_dir, notes)
                   VALUES (?, ?, ?, ?, ?) RETURNING id""",
                (project_id, phase_no, name, artifacts_dir, notes),
            )
            row = await cur.fetchone()
            phase_id = dict(row)["id"] if row else None
            await db.commit()
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "uq_bf_phase" in msg or "duplicate" in msg:
            raise InvalidPhaseInput(
                f"phase_no {phase_no} already exists for project {project_id}"
            ) from e
        raise
    if phase_id is None:
        raise PhaseNotFound("INSERT returned no id")
    return await get_phase(phase_id) or {}


async def update_phase(phase_id: int, **fields) -> dict:
    """phase の更新. unknown phase_id → PhaseNotFound. invalid → InvalidPhaseInput."""
    existing = await get_phase(phase_id)
    if existing is None:
        raise PhaseNotFound(f"phase not found: {phase_id}")

    if "phase_no" in fields:
        _validate_phase_no(fields["phase_no"])
    if "status" in fields:
        _validate_status(fields["status"])
    if "name" in fields and not (fields["name"] or "").strip():
        raise InvalidPhaseInput("name must not be empty")

    cols, vals = [], []
    for k in ("phase_no", "name", "status", "artifacts_dir", "notes"):
        if k in fields:
            cols.append(f"{k} = ?")
            vals.append(fields[k])
    if not cols:
        return existing
    cols.append("updated_at = datetime('now','localtime')")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE bf_phases SET {', '.join(cols)} WHERE id = ?",
                [*vals, phase_id],
            )
            await db.commit()
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "uq_bf_phase" in msg:
            raise InvalidPhaseInput(
                f"phase_no {fields.get('phase_no')} conflicts with existing"
            ) from e
        raise
    return await get_phase(phase_id) or {}


async def start_phase(phase_id: int) -> dict:
    """phase を in_progress に + started_at を NOW でセット."""
    existing = await get_phase(phase_id)
    if existing is None:
        raise PhaseNotFound(f"phase not found: {phase_id}")
    if existing.get("status") == "in_progress":
        return existing  # idempotent
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE bf_phases
                  SET status = 'in_progress',
                      started_at = COALESCE(started_at, datetime('now','localtime')),
                      updated_at = datetime('now','localtime')
                WHERE id = ?""",
            (phase_id,),
        )
        await db.commit()
    return await get_phase(phase_id) or {}


async def complete_phase(phase_id: int) -> dict:
    """phase を completed + completed_at セット."""
    existing = await get_phase(phase_id)
    if existing is None:
        raise PhaseNotFound(f"phase not found: {phase_id}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE bf_phases
                  SET status = 'completed',
                      completed_at = datetime('now','localtime'),
                      updated_at = datetime('now','localtime')
                WHERE id = ?""",
            (phase_id,),
        )
        await db.commit()
    return await get_phase(phase_id) or {}


async def delete_phase(phase_id: int) -> bool:
    """phase を soft-delete (status='skipped'). 既存 dependency を壊さない."""
    existing = await get_phase(phase_id)
    if existing is None:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """UPDATE bf_phases
                  SET status = 'skipped',
                      updated_at = datetime('now','localtime')
                WHERE id = ?""",
            (phase_id,),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0