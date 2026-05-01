"""
threads.py — チャットスレッド管理 API

秘書 / 各社員 ごとに複数スレッドを持てる。
"""

from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

router = APIRouter(prefix="/api/threads", tags=["threads"])


class ThreadCreate(BaseModel):
    channel:       str             # "secretary" | "employee"
    with_employee: Optional[int] = None
    title:         Optional[str] = None


class ThreadUpdate(BaseModel):
    title:    Optional[str] = None
    archived: Optional[int] = None


@router.get("")
async def list_threads(
    channel:       Optional[str] = None,
    with_employee: Optional[int] = None,
    archived:      int = 0,
    limit:         int = 100,
):
    """スレッド一覧。社員別 or 秘書ごとに絞り込み可能。"""
    conds, params = ["archived=?"], [archived]
    if channel:        conds.append("channel=?");        params.append(channel)
    if with_employee:  conds.append("with_employee=?");  params.append(with_employee)
    where = "WHERE " + " AND ".join(conds)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""SELECT t.*,
                       (SELECT COUNT(*) FROM conversation_log WHERE thread_id=t.id) as msg_count,
                       (SELECT message FROM conversation_log
                        WHERE thread_id=t.id AND role='user'
                        ORDER BY created_at LIMIT 1) as first_msg
                FROM threads t
                {where}
                ORDER BY t.last_active_at DESC LIMIT ?""",
            (*params, limit)
        )
    return [dict(r) for r in rows]


@router.post("")
async def create_thread(body: ThreadCreate):
    """新規スレッド作成。"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO threads (channel, with_employee, title)
               VALUES (?, ?, ?)""",
            (body.channel, body.with_employee, body.title or "新しいチャット")
        )
        await db.commit()
    return {"id": cursor.lastrowid}


@router.get("/{thread_id}")
async def get_thread(thread_id: int):
    """スレッド情報＋会話履歴を返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        thread_rows = await db.execute_fetchall(
            "SELECT * FROM threads WHERE id=?", (thread_id,)
        )
        if not thread_rows:
            raise HTTPException(404)
        msg_rows = await db.execute_fetchall(
            """SELECT id, role, message, task_id, created_at FROM conversation_log
               WHERE thread_id=? ORDER BY created_at""",
            (thread_id,)
        )
    return {
        "thread":   dict(thread_rows[0]),
        "messages": [dict(m) for m in msg_rows],
    }


@router.patch("/{thread_id}")
async def update_thread(thread_id: int, body: ThreadUpdate):
    """タイトル変更・アーカイブ切替。"""
    sets, params = [], []
    if body.title is not None:
        sets.append("title=?"); params.append(body.title)
    if body.archived is not None:
        sets.append("archived=?"); params.append(body.archived)
    if not sets:
        raise HTTPException(400)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE threads SET {', '.join(sets)}, last_active_at=datetime('now','localtime') WHERE id=?",
            (*params, thread_id)
        )
        await db.commit()
    return {"status": "updated"}


@router.delete("/{thread_id}")
async def delete_thread(thread_id: int):
    """スレッドを削除（メッセージごと）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM conversation_log WHERE thread_id=?", (thread_id,))
        await db.execute("DELETE FROM threads WHERE id=?", (thread_id,))
        await db.commit()
    return {"status": "deleted"}


async def get_or_create_thread(
    channel: str,
    with_employee: Optional[int],
    thread_id: Optional[int],
    force_new: bool = False,
) -> int:
    """thread_id 指定なし → 直近のアクティブを返す or 新規作成。
    force_new=True なら必ず新スレッドを作る（採用フロー等で前のフロー履歴を持ち越さないため）。"""
    if thread_id:
        return thread_id
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if not force_new:
            conds, params = ["archived=0", "channel=?"], [channel]
            if with_employee:
                conds.append("with_employee=?"); params.append(with_employee)
            else:
                conds.append("with_employee IS NULL OR with_employee=1")
            rows = await db.execute_fetchall(
                f"SELECT id FROM threads WHERE {' AND '.join(conds)} ORDER BY last_active_at DESC LIMIT 1",
                params
            )
            if rows:
                return rows[0]["id"]
        cursor = await db.execute(
            "INSERT INTO threads (channel, with_employee) VALUES (?, ?)",
            (channel, with_employee)
        )
        await db.commit()
        return cursor.lastrowid
