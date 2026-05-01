"""
knowledge_actions.py — タスク完了後のナレッジ化・承認アクション API
"""

from typing import Optional

from db import async_db as aiosqlite
from fastapi import APIRouter, HTTPException
from pathlib import Path
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

router = APIRouter(prefix="/api/knowledge-actions", tags=["knowledge-actions"])


class CurateBody(BaseModel):
    content: str
    masato_memo: Optional[str] = None
    full_content: bool = True
    source_skill: Optional[str] = None
    source: str = "manual"
    source_id: Optional[int] = None


@router.post("/curate")
async def curate_knowledge(body: CurateBody):
    """
    コンテンツをナレッジ化する。秘書AIが分類・部分抽出を行う。

    Args:
        content:      ナレッジにしたいコンテンツ全文
        masato_memo:  まさとの指示（部分抽出する場合）
        full_content: True=全部、False=一部だけ抽出
    """
    from services.knowledge_curator import classify_and_save
    result = await classify_and_save(
        content=body.content,
        masato_memo=body.masato_memo,
        source_skill=body.source_skill,
        source=body.source,
        source_id=body.source_id,
        full_content=body.full_content,
    )
    return result


class TaskActionBody(BaseModel):
    task_id: int
    action: str  # "approve" | "revise" | "reject" | "curate"
    notes: Optional[str] = None
    masato_memo: Optional[str] = None     # ナレッジ化時の指示
    full_content: bool = True              # 全部 or 一部


@router.post("/task-action")
async def handle_task_action(body: TaskActionBody):
    """
    タスク完了カードからのアクション処理。
    Web画面の「✅承認 / ✏️修正 / ❌却下 / 💾ナレッジ化」ボタンから呼ばれる。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM tasks WHERE id=?", (body.task_id,)
        )
        if not rows:
            raise HTTPException(404, "task not found")
        task = dict(rows[0])

    # アクション処理
    if body.action == "approve":
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE tasks SET status='completed', completed_at=datetime('now','localtime') WHERE id=?",
                (body.task_id,)
            )
            # 承認キューにある場合も承認
            await db.execute(
                "UPDATE approval_queue SET status='approved', resolved_at=datetime('now','localtime') WHERE source_execution_id=?",
                (body.task_id,)
            )
            await db.commit()
        return {"status": "approved"}

    elif body.action == "revise":
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE tasks SET status='pending', last_error=? WHERE id=?",
                (f"修正依頼: {body.notes or ''}", body.task_id)
            )
            await db.commit()
        return {"status": "revising", "notes": body.notes}

    elif body.action == "reject":
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE tasks SET status='cancelled' WHERE id=?",
                (body.task_id,)
            )
            await db.execute(
                "UPDATE approval_queue SET status='rejected', resolved_at=datetime('now','localtime') WHERE source_execution_id=?",
                (body.task_id,)
            )
            await db.commit()
        return {"status": "rejected"}

    elif body.action == "curate":
        # 部分または全部をナレッジ化
        from services.knowledge_curator import classify_and_save
        result = await classify_and_save(
            content=task.get("result", "") or task.get("description", ""),
            masato_memo=body.masato_memo,
            source_skill=task.get("skill_name"),
            source="task_curate",
            source_id=body.task_id,
            full_content=body.full_content,
        )
        return {"status": "curated", **result}

    raise HTTPException(400, f"unknown action: {body.action}")
