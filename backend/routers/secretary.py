"""
secretary.py — 秘書チャット API
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from services.secretary_chat import chat, get_history

router = APIRouter(prefix="/api/secretary", tags=["secretary"])


class ChatBody(BaseModel):
    message:    str
    session_id: Optional[str] = None


@router.post("/chat")
async def secretary_chat(body: ChatBody):
    """秘書AIと対話する。会話履歴を保持・タスク自動分解・社員割当も実行。"""
    return await chat(body.message, body.session_id)


@router.get("/history")
async def secretary_history(limit: int = 50):
    """秘書との会話履歴を取得する。"""
    return await get_history(limit=limit)


@router.delete("/history")
async def clear_history():
    """会話履歴をクリアする。"""
    import aiosqlite
    from pathlib import Path
    DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM conversation_log WHERE channel='web_secretary' AND with_employee=1"
        )
        await db.commit()
    return {"status": "cleared"}
