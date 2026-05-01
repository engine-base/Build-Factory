"""
approval.py — approval_queue CRUD API

承認フローの基盤となるエンドポイント。
どのチャンネル（Slack / Chatwork / ダッシュボード）から操作しても同一キューを更新する SSoT。
"""

import json
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
from fastapi import APIRouter, HTTPException
from pathlib import Path
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

router = APIRouter(prefix="/api/approval", tags=["approval"])


def _row_to_dict(row) -> dict:
    """aiosqlite.Row を辞書に変換し、フロントエンドが期待するフィールド名に統一する。"""
    d = dict(row)
    # フロント互換エイリアス
    d.setdefault("skill_name", d.get("source_skill") or "")
    d.setdefault("requested_at", d.get("created_at") or "")
    # metadata を payload として JSON デコード
    raw_meta = d.get("metadata")
    if raw_meta:
        try:
            d["payload"] = json.loads(raw_meta)
        except Exception:
            d["payload"] = {"raw": raw_meta}
    else:
        d["payload"] = {}
    # notes は revision_memo を優先
    d.setdefault("notes", d.get("revision_memo") or "")
    return d


class ApprovalCreate(BaseModel):
    action_type: str
    title: str
    content: str
    metadata: Optional[dict] = None
    source_skill: Optional[str] = None
    source_execution_id: Optional[int] = None


class ApprovalUpdate(BaseModel):
    status: str          # "approved" | "rejected" | "revision_requested" | "revision"
    notes: Optional[str] = None
    revision_memo: Optional[str] = None   # 後方互換


@router.post("", summary="承認待ちキューに追加")
async def create_approval(body: ApprovalCreate):
    expires_at = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """INSERT INTO approval_queue
               (action_type, title, content, metadata,
                source_skill, source_execution_id, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                body.action_type,
                body.title,
                body.content,
                json.dumps(body.metadata, ensure_ascii=False) if body.metadata else None,
                body.source_skill,
                body.source_execution_id,
                expires_at,
            ),
        )
        await db.commit()
        rows = await db.execute_fetchall(
            "SELECT * FROM approval_queue WHERE id=?", (cursor.lastrowid,)
        )
        item = _row_to_dict(rows[0])

    # Slack / Chatwork に承認リクエスト通知（非同期・失敗しても継続）
    import asyncio
    asyncio.create_task(_notify_new_approval(item))

    return item


@router.get("", summary="承認待ちキュー一覧取得")
async def list_approvals(status: Optional[str] = None, limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            rows = await db.execute_fetchall(
                "SELECT * FROM approval_queue WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            rows = await db.execute_fetchall(
                "SELECT * FROM approval_queue ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [_row_to_dict(r) for r in rows]


@router.get("/{approval_id}", summary="承認待ちキュー単件取得")
async def get_approval(approval_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM approval_queue WHERE id=?", (approval_id,)
        )
    if not rows:
        raise HTTPException(404, "approval not found")
    return _row_to_dict(rows[0])


@router.patch("/{approval_id}", summary="承認 / 却下 / 修正依頼")
async def update_approval(approval_id: int, body: ApprovalUpdate):
    # "revision_requested" → "revision" に正規化
    status = body.status.replace("_requested", "")
    allowed = {"approved", "rejected", "revision"}
    if status not in allowed:
        raise HTTPException(400, f"status は {allowed} のいずれかである必要があります")

    memo = body.notes or body.revision_memo or None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM approval_queue WHERE id=?", (approval_id,)
        )
        if not rows:
            raise HTTPException(404, "approval not found")

        current = dict(rows[0])
        if current["status"] in ("approved", "rejected", "done"):
            raise HTTPException(409, f"既に処理済みです: {current['status']}")

        await db.execute(
            """UPDATE approval_queue
               SET status=?, revision_memo=?,
                   resolved_at=datetime('now','localtime')
               WHERE id=?""",
            (status, memo, approval_id),
        )
        await db.commit()

        rows = await db.execute_fetchall(
            "SELECT * FROM approval_queue WHERE id=?", (approval_id,)
        )
        return _row_to_dict(rows[0])


@router.delete("/{approval_id}", summary="期限切れ処理")
async def delete_approval(approval_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT id FROM approval_queue WHERE id=?", (approval_id,)
        )
        if not rows:
            raise HTTPException(404, "approval not found")
        await db.execute(
            "UPDATE approval_queue SET status='expired' WHERE id=?", (approval_id,)
        )
        await db.commit()
    return {"id": approval_id, "status": "expired"}


async def _notify_new_approval(item: dict) -> None:
    """新規承認リクエストを Slack と Chatwork に通知する（任意）。"""
    approval_id = item["id"]
    title = item.get("title", "")
    skill_name = item.get("skill_name", "")
    action_type = item.get("action_type", "")

    # Slack
    try:
        from integrations.slack_client import send_approval_notification as slack_notify
        await slack_notify(approval_id, title, skill_name, action_type)
    except Exception as e:
        print(f"[approval] Slack通知失敗: {e}")

    # Chatwork
    try:
        from integrations.chatwork_client import send_approval_notification as cw_notify
        await cw_notify(approval_id, title, skill_name, action_type)
    except Exception as e:
        print(f"[approval] Chatwork通知失敗: {e}")
