"""Swarm DB models + DB ops (T-021-03)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional


ALLOWED_SIZES: tuple[int, ...] = (4, 9, 16, 64)


# DB import は遅延 (テスト環境で psycopg 未導入時にロード失敗を避けるため)
def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


@dataclass
class SwarmPool:
    id: Optional[int]
    name: str
    size: int
    status: str  # queued / running / done / failed / cancelled
    base_branch: str = "main"
    task_prompt: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    stats_json: Optional[str] = None

    def stats(self) -> dict:
        if not self.stats_json:
            return {}
        try:
            return json.loads(self.stats_json)
        except json.JSONDecodeError:
            return {}


@dataclass
class SwarmCell:
    id: Optional[int]
    pool_id: int
    cell_index: int
    worktree_path: str
    branch_name: str
    status: str  # queued / running / done / failed / crashed / killed
    session_id: Optional[int] = None
    exit_code: Optional[int] = None
    error_msg: Optional[str] = None
    log_path: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class RedlineEvent:
    id: Optional[int]
    pool_id: int
    cell_id: int
    event_type: str  # sandbox_escape / cross_cell_access / timeout / oom
    detail: Optional[str] = None
    detected_at: Optional[str] = None


# ──────────────────────────────────────────
# Pool ops
# ──────────────────────────────────────────

async def insert_pool(pool: SwarmPool) -> int:
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """INSERT INTO swarm_pools (name, size, status, base_branch, task_prompt, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pool.name, pool.size, pool.status, pool.base_branch,
             pool.task_prompt, pool.created_by),
        )
        await db.commit()
        return cur.lastrowid or 0


async def update_pool_status(pool_id: int, status: str,
                             started: bool = False, completed: bool = False,
                             stats: Optional[dict] = None) -> None:
    async with _db().connect(_db_path()) as db:
        sets = ["status = ?"]
        args: list = [status]
        if started:
            sets.append("started_at = datetime('now','localtime')")
        if completed:
            sets.append("completed_at = datetime('now','localtime')")
        if stats is not None:
            sets.append("stats_json = ?")
            args.append(json.dumps(stats, ensure_ascii=False))
        args.append(pool_id)
        await db.execute(
            f"UPDATE swarm_pools SET {', '.join(sets)} WHERE id = ?", tuple(args),
        )
        await db.commit()


async def fetch_pool(pool_id: int) -> Optional[SwarmPool]:
    async with _db().connect(_db_path()) as db:
        db.row_factory = _db().Row
        cur = await db.execute(
            "SELECT * FROM swarm_pools WHERE id = ?", (pool_id,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    return SwarmPool(**d)


# ──────────────────────────────────────────
# Cell ops
# ──────────────────────────────────────────

async def insert_cell(cell: SwarmCell) -> int:
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """INSERT INTO swarm_cells (pool_id, cell_index, worktree_path, branch_name, status)
               VALUES (?, ?, ?, ?, ?)""",
            (cell.pool_id, cell.cell_index, cell.worktree_path, cell.branch_name, cell.status),
        )
        await db.commit()
        return cur.lastrowid or 0


async def update_cell_status(cell_id: int, status: str, *,
                             started: bool = False, completed: bool = False,
                             session_id: Optional[int] = None,
                             exit_code: Optional[int] = None,
                             error_msg: Optional[str] = None,
                             log_path: Optional[str] = None) -> None:
    async with _db().connect(_db_path()) as db:
        sets = ["status = ?"]
        args: list = [status]
        if started:
            sets.append("started_at = datetime('now','localtime')")
        if completed:
            sets.append("completed_at = datetime('now','localtime')")
        if session_id is not None:
            sets.append("session_id = ?")
            args.append(session_id)
        if exit_code is not None:
            sets.append("exit_code = ?")
            args.append(exit_code)
        if error_msg is not None:
            sets.append("error_msg = ?")
            args.append(error_msg)
        if log_path is not None:
            sets.append("log_path = ?")
            args.append(log_path)
        args.append(cell_id)
        await db.execute(
            f"UPDATE swarm_cells SET {', '.join(sets)} WHERE id = ?", tuple(args),
        )
        await db.commit()


async def fetch_cells(pool_id: int) -> list[SwarmCell]:
    async with _db().connect(_db_path()) as db:
        db.row_factory = _db().Row
        cur = await db.execute(
            "SELECT * FROM swarm_cells WHERE pool_id = ? ORDER BY cell_index ASC",
            (pool_id,),
        )
        rows = await cur.fetchall()
    return [SwarmCell(**dict(r)) for r in rows]


# ──────────────────────────────────────────
# Redline events (UNWANTED AC)
# ──────────────────────────────────────────

async def emit_redline(pool_id: int, cell_id: int, event_type: str,
                       detail: Optional[str] = None) -> int:
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """INSERT INTO swarm_redline_events (pool_id, cell_id, event_type, detail)
               VALUES (?, ?, ?, ?)""",
            (pool_id, cell_id, event_type, detail),
        )
        await db.commit()
        return cur.lastrowid or 0


async def fetch_redlines(pool_id: int) -> list[RedlineEvent]:
    async with _db().connect(_db_path()) as db:
        db.row_factory = _db().Row
        cur = await db.execute(
            "SELECT * FROM swarm_redline_events WHERE pool_id = ? ORDER BY detected_at DESC",
            (pool_id,),
        )
        rows = await cur.fetchall()
    return [RedlineEvent(**dict(r)) for r in rows]
