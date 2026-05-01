"""
artifact_service.py — Artifact (出力 view オブジェクト) の CRUD + イベント記録 + Push 配信

責務:
  - artifacts テーブルの CRUD
  - artifact_events テーブルへ変更履歴記録
  - WebSocket 経由で frontend に live 反映を push（user / AI どちらの更新でも）

スキル / AI 社員はこの層を意識しない。
出力プロセッサ (output_processor.py) と routers/artifacts.py からのみ呼ばれる。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from db.queries import DB_PATH

# 15 view 型 + カテゴリマッピング
VIEW_TYPES = {
    "list":        ["task"],
    "table":       ["catalog"],
    "kanban":      ["task"],
    "kpi-card":    ["number"],
    "markdown":    ["document"],
    "gantt":       ["task", "time"],
    "calendar":    ["time"],
    "chart":       ["number"],
    "compare":     ["catalog"],
    "workflow":    ["flow"],
    "gallery":     ["catalog"],
    "matrix":      ["task"],
    "form":        ["flow"],
    "slide":       ["design"],
    "mindmap":     ["flow"],
}

CATEGORIES = {
    "number":   "📊 数字",
    "task":     "✅ タスク",
    "document": "📄 文書",
    "catalog":  "🗂 一覧",
    "design":   "🎨 デザイン",
    "flow":     "🔁 フロー",
    "time":     "📅 時間",
}

DEFAULT_USER_ID = "masato"

# ──────────────────────────────────────────
# WebSocket Pub/Sub
# ──────────────────────────────────────────

# 接続中の WebSocket クライアント（user_id → set of websocket）
_subscribers: dict[str, set] = {}


def subscribe(user_id: str, websocket) -> None:
    _subscribers.setdefault(user_id, set()).add(websocket)


def unsubscribe(user_id: str, websocket) -> None:
    s = _subscribers.get(user_id)
    if s is not None:
        s.discard(websocket)


async def _broadcast(user_id: str, event: dict) -> None:
    s = _subscribers.get(user_id)
    if not s:
        return
    dead = []
    for ws in s:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        s.discard(ws)


# ──────────────────────────────────────────
# 内部ヘルパー
# ──────────────────────────────────────────

def _row_to_dict(row) -> dict:
    d = dict(row)
    for k in ("data", "category_tags", "pinned_by"):
        if isinstance(d.get(k), str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                d[k] = {} if k == "data" else []
    d["is_archived"] = bool(d.get("is_archived", 0))
    return d


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


async def _record_event(db, artifact_id: str, actor: str, action: str,
                         diff: Optional[dict] = None, note: str = "") -> None:
    await db.execute(
        """INSERT INTO artifact_events
           (artifact_id, actor, action, diff, note)
           VALUES (?, ?, ?, ?, ?)""",
        (artifact_id, actor, action,
         json.dumps(diff or {}, ensure_ascii=False), note),
    )


# ──────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────

async def list_artifacts(
    *,
    user_id: str = DEFAULT_USER_ID,
    category: Optional[str] = None,
    type: Optional[str] = None,
    pinned_only: bool = False,
    thread_id: Optional[int] = None,
    include_archived: bool = False,
    limit: int = 50,
) -> list[dict]:
    """フィルタ付き一覧。"""
    conds = []
    params: list = []
    if not include_archived:
        conds.append("is_archived = 0")
    if type:
        conds.append("type = ?"); params.append(type)
    if thread_id:
        conds.append("thread_id = ?"); params.append(thread_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""SELECT * FROM artifacts {where}
                ORDER BY updated_at DESC LIMIT ?""",
            [*params, limit],
        )
    out = [_row_to_dict(r) for r in rows]

    if category:
        out = [a for a in out if category in (a.get("category_tags") or [])]
    if pinned_only:
        out = [a for a in out if user_id in (a.get("pinned_by") or [])]
    return out


async def get_artifact(artifact_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


async def create_artifact(
    *,
    type: str,
    title: str,
    data: dict,
    category_tags: Optional[list[str]] = None,
    thread_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    created_by: str = "ai",
    actor: str = "ai:secretary",
) -> dict:
    if type not in VIEW_TYPES:
        raise ValueError(f"unknown view type: {type}")
    artifact_id = uuid.uuid4().hex
    tags = category_tags or VIEW_TYPES.get(type, [])

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO artifacts
               (id, type, title, data, category_tags, pinned_by,
                thread_id, employee_id, created_by)
               VALUES (?, ?, ?, ?, ?, '[]', ?, ?, ?)""",
            (artifact_id, type, title or type,
             json.dumps(data, ensure_ascii=False),
             json.dumps(tags, ensure_ascii=False),
             thread_id, employee_id, created_by),
        )
        await _record_event(db, artifact_id, actor, "create",
                             {"type": type, "title": title})
        await db.commit()

    art = await get_artifact(artifact_id)
    asyncio.create_task(_broadcast(DEFAULT_USER_ID, {"event": "artifact.created", "artifact": art}))
    return art


async def update_artifact(
    artifact_id: str,
    *,
    title: Optional[str] = None,
    data: Optional[dict] = None,
    data_patch: Optional[dict] = None,    # data の部分更新
    category_tags: Optional[list[str]] = None,
    actor: str = "user:" + DEFAULT_USER_ID,
    note: str = "",
) -> dict:
    """部分更新。data_patch を渡すと既存 data に merge。"""
    cur = await get_artifact(artifact_id)
    if not cur:
        raise FileNotFoundError(artifact_id)

    new_data = cur["data"]
    if data is not None:
        new_data = data
    elif data_patch:
        new_data = {**(cur["data"] or {}), **data_patch}

    new_title = title if title is not None else cur["title"]
    new_tags = category_tags if category_tags is not None else cur["category_tags"]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE artifacts
               SET title=?, data=?, category_tags=?,
                   updated_at=datetime('now','localtime')
               WHERE id=?""",
            (new_title,
             json.dumps(new_data, ensure_ascii=False),
             json.dumps(new_tags, ensure_ascii=False),
             artifact_id),
        )
        diff = {}
        if data is not None or data_patch:
            diff["data"] = data_patch or data
        if title is not None:
            diff["title"] = title
        await _record_event(db, artifact_id, actor, "update", diff, note)
        await db.commit()

    art = await get_artifact(artifact_id)
    asyncio.create_task(_broadcast(DEFAULT_USER_ID, {"event": "artifact.updated", "artifact": art}))
    return art


async def pin_artifact(artifact_id: str, user_id: str = DEFAULT_USER_ID,
                       pinned: bool = True) -> dict:
    cur = await get_artifact(artifact_id)
    if not cur:
        raise FileNotFoundError(artifact_id)
    pins = list(cur.get("pinned_by") or [])
    if pinned and user_id not in pins:
        pins.append(user_id)
    elif not pinned and user_id in pins:
        pins.remove(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE artifacts SET pinned_by=?, updated_at=datetime('now','localtime') WHERE id=?",
            (json.dumps(pins, ensure_ascii=False), artifact_id),
        )
        await _record_event(db, artifact_id, f"user:{user_id}",
                             "pin" if pinned else "unpin", {})
        await db.commit()
    art = await get_artifact(artifact_id)
    asyncio.create_task(_broadcast(user_id, {"event": "artifact.pinned", "artifact": art}))
    return art


async def archive_artifact(artifact_id: str,
                           actor: str = "user:" + DEFAULT_USER_ID) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE artifacts SET is_archived=1, updated_at=datetime('now','localtime') WHERE id=?",
            (artifact_id,),
        )
        await _record_event(db, artifact_id, actor, "archive", {})
        await db.commit()
    art = await get_artifact(artifact_id)
    asyncio.create_task(_broadcast(DEFAULT_USER_ID, {"event": "artifact.archived", "artifact": art}))
    return art


async def delete_artifact(artifact_id: str,
                          actor: str = "user:" + DEFAULT_USER_ID) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM artifacts WHERE id=?", (artifact_id,))
        # 履歴は残す（artifact_id は孤児になるが原因追跡用）
        await db.execute(
            """INSERT INTO artifact_events (artifact_id, actor, action, diff)
               VALUES (?, ?, 'delete', '{}')""",
            (artifact_id, actor),
        )
        await db.commit()
    asyncio.create_task(_broadcast(DEFAULT_USER_ID,
        {"event": "artifact.deleted", "artifact_id": artifact_id}))
    return {"id": artifact_id, "deleted": True}


async def get_events(artifact_id: str, limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM artifact_events WHERE artifact_id=? "
            "ORDER BY ts DESC LIMIT ?",
            (artifact_id, limit),
        )
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["diff"] = json.loads(d.get("diff") or "{}")
        except Exception:
            pass
        out.append(d)
    return out


async def categories_summary(user_id: str = DEFAULT_USER_ID) -> list[dict]:
    """各カテゴリの件数を返す（左バー表示用）。"""
    arts = await list_artifacts(user_id=user_id, limit=500)
    counts: dict[str, int] = {k: 0 for k in CATEGORIES}
    for a in arts:
        for tag in a.get("category_tags") or []:
            if tag in counts:
                counts[tag] += 1
    return [
        {"key": k, "label": CATEGORIES[k], "count": counts[k]}
        for k in CATEGORIES
    ]
