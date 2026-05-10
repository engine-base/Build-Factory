"""File-level lock (T-021-03 OPTIONAL AC).

同じファイルを複数 cell が触る場合に serialize するための DB ベースの
advisory lock。worktree が独立しているため通常は衝突しないが、commit を
main にマージするタイミングで衝突しうるシナリオ向け。

`async with file_lock(pool_id, cell_id, file_path):` で使う。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


# 排他制御のための in-memory event 群 (プロセス内の優先取得用)
_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def _get_inproc_lock(file_path: str) -> asyncio.Lock:
    async with _locks_guard:
        lock = _locks.get(file_path)
        if lock is None:
            lock = asyncio.Lock()
            _locks[file_path] = lock
        return lock


async def _acquire_db(pool_id: int, cell_id: int, file_path: str) -> int:
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """INSERT INTO swarm_file_locks (pool_id, cell_id, file_path)
               VALUES (?, ?, ?)""",
            (pool_id, cell_id, file_path),
        )
        await db.commit()
        return cur.lastrowid or 0


async def _release_db(lock_id: int) -> None:
    async with _db().connect(_db_path()) as db:
        await db.execute(
            """UPDATE swarm_file_locks
                  SET released_at = datetime('now','localtime')
                WHERE id = ?""",
            (lock_id,),
        )
        await db.commit()


@asynccontextmanager
async def file_lock(pool_id: int, cell_id: int, file_path: str) -> AsyncIterator[int]:
    """ファイルレベル lock を取得・解放。

    Yields:
      lock_id (DB の swarm_file_locks.id)
    """
    inproc = await _get_inproc_lock(file_path)
    await inproc.acquire()
    lock_id = await _acquire_db(pool_id, cell_id, file_path)
    try:
        yield lock_id
    finally:
        await _release_db(lock_id)
        inproc.release()


async def active_locks_for(file_path: str) -> int:
    """指定ファイルに対する未解放 lock 数 (デバッグ用)。"""
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM swarm_file_locks
                WHERE file_path = ? AND released_at IS NULL""",
            (file_path,),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0
