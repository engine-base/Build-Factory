"""
browser_queue.py — ブラウザuseタスクのキュー管理

基本的に「あとでまとめて実行する」前提。即時実行はしない。
実行は Claude Desktop（claude-in-chrome MCP経由）か、明示的な run-now コマンドで。
"""

import json
from datetime import datetime
from typing import Optional

from db import async_db as aiosqlite

from db.queries import DB_PATH


async def add_task(
    task: str,
    service: Optional[str] = None,
    priority: int = 3,
    max_steps: int = 20,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    requested_by: Optional[str] = None,
    requested_via_thread: Optional[int] = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO browser_task_queue
               (task, service, priority, max_steps, provider, model,
                requested_by, requested_via_thread, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending') RETURNING id""",
            (task, service, priority, max_steps, provider, model,
             requested_by, requested_via_thread),
        )
        _row = await cur.fetchone()
        await db.commit()
        return _row["id"]


async def list_tasks(status: Optional[str] = None, limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            cur = await db.execute(
                "SELECT * FROM browser_task_queue WHERE status = ? "
                "ORDER BY priority ASC, created_at ASC LIMIT ?",
                (status, limit),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM browser_task_queue "
                "ORDER BY status = 'pending' DESC, created_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_task(task_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM browser_task_queue WHERE id = ?", (task_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_running(task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE browser_task_queue "
            "SET status = 'running', started_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (datetime.now(), task_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def mark_done(
    task_id: int,
    result: str,
    screenshot_path: Optional[str] = None,
    steps_summary: Optional[list] = None,
) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE browser_task_queue "
            "SET status = 'done', finished_at = ?, result = ?, "
            "    screenshot_path = ?, steps_summary = ? "
            "WHERE id = ?",
            (datetime.now(), result, screenshot_path,
             json.dumps(steps_summary) if steps_summary else None, task_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def mark_failed(task_id: int, error: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE browser_task_queue "
            "SET status = 'failed', finished_at = ?, error = ? "
            "WHERE id = ?",
            (datetime.now(), error, task_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def cancel(task_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE browser_task_queue "
            "SET status = 'cancelled', finished_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (datetime.now(), task_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status, COUNT(*) as cnt FROM browser_task_queue GROUP BY status"
        )
        rows = await cur.fetchall()
        return {r["status"]: r["cnt"] for r in rows}
