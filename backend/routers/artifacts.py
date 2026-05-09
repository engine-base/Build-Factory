"""
artifacts.py — Artifact API + WebSocket

GET    /api/artifacts                       一覧（フィルタ可）
GET    /api/artifacts/{id}                  詳細
POST   /api/artifacts                        新規（user 主導）
PATCH  /api/artifacts/{id}                   更新
POST   /api/artifacts/{id}/pin                ピン
POST   /api/artifacts/{id}/unpin              ピン解除
POST   /api/artifacts/{id}/archive             アーカイブ
DELETE /api/artifacts/{id}                   削除
GET    /api/artifacts/{id}/events             変更履歴
GET    /api/artifacts/categories/summary       カテゴリ別件数

WS     /api/artifacts/ws?user_id=masato       live push
"""

from typing import Any, Optional

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services import artifact_service as art

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


# ── 型定義 ──────────────────────────────────────

class ArtifactCreate(BaseModel):
    type: str
    title: str = ""
    data: dict = {}
    category_tags: Optional[list[str]] = None
    thread_id: Optional[int] = None
    employee_id: Optional[int] = None
    task_id: Optional[int] = None
    workspace_id: Optional[int] = None


class ArtifactUpdate(BaseModel):
    title: Optional[str] = None
    data: Optional[dict] = None
    data_patch: Optional[dict] = None
    category_tags: Optional[list[str]] = None
    note: str = ""


# ── REST ────────────────────────────────────────

@router.get("/categories/summary")
async def categories_summary(user_id: str = "masato"):
    return {"categories": await art.categories_summary(user_id)}


@router.get("")
async def list_artifacts(
    category: Optional[str] = None,
    type: Optional[str] = None,
    pinned_only: bool = False,
    thread_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
    include_archived: bool = False,
    limit: int = 50,
    user_id: str = "masato",
):
    items = await art.list_artifacts(
        user_id=user_id, category=category, type=type,
        pinned_only=pinned_only, thread_id=thread_id,
        include_archived=include_archived, limit=limit,
    )
    if workspace_id is not None:
        items = [a for a in items if a.get("workspace_id") == workspace_id]
    return {"artifacts": items, "total": len(items)}


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    a = await art.get_artifact(artifact_id)
    if not a:
        raise HTTPException(404, f"artifact not found: {artifact_id}")
    return a


@router.post("")
async def create_artifact(body: ArtifactCreate):
    from db import async_db as adb
    from pathlib import Path as _P
    DB = _P(__file__).resolve().parents[2] / "data" / "db" / "build.db"

    actor = "user:masato"
    created_by = "user"

    # task_id 指定時 → workspace_id を解決
    ws_id = body.workspace_id
    if body.task_id and ws_id is None:
        async with adb.connect(DB) as db:
            db.row_factory = adb.Row
            rows = await db.execute_fetchall(
                """SELECT t.project_id, w.id AS workspace_id
                   FROM tasks t
                   LEFT JOIN projects p ON p.id = t.project_id
                   LEFT JOIN workspaces w ON w.name = p.title
                   WHERE t.id = ?""",
                (body.task_id,),
            )
            if rows:
                ws_id = rows[0]["workspace_id"]
        actor = f"claude-code:task_{body.task_id}"
        created_by = f"claude-code:task_{body.task_id}"

    try:
        result = await art.create_artifact(
            type=body.type, title=body.title, data=body.data,
            category_tags=body.category_tags,
            thread_id=body.thread_id, employee_id=body.employee_id,
            created_by=created_by, actor=actor,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # workspace_id を後付け
    if ws_id and result.get("id"):
        async with adb.connect(DB) as db:
            await db.execute(
                "UPDATE artifacts SET workspace_id = ? WHERE id = ?",
                (ws_id, result["id"]),
            )
            await db.commit()
        result["workspace_id"] = ws_id

    return result


@router.patch("/{artifact_id}")
async def update_artifact(artifact_id: str, body: ArtifactUpdate):
    try:
        return await art.update_artifact(
            artifact_id,
            title=body.title, data=body.data, data_patch=body.data_patch,
            category_tags=body.category_tags,
            actor="user:masato", note=body.note,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/{artifact_id}/pin")
async def pin(artifact_id: str, user_id: str = "masato"):
    try:
        return await art.pin_artifact(artifact_id, user_id, pinned=True)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/{artifact_id}/unpin")
async def unpin(artifact_id: str, user_id: str = "masato"):
    try:
        return await art.pin_artifact(artifact_id, user_id, pinned=False)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/{artifact_id}/archive")
async def archive(artifact_id: str):
    try:
        return await art.archive_artifact(artifact_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.delete("/{artifact_id}")
async def delete(artifact_id: str):
    return await art.delete_artifact(artifact_id)


@router.get("/{artifact_id}/events")
async def events(artifact_id: str, limit: int = 50):
    return {"events": await art.get_events(artifact_id, limit)}


# ── Export ──────────────────────────────────

@router.post("/{artifact_id}/export")
async def export(artifact_id: str, format: str = Query(..., description="pdf|xlsx|pptx"),
                 template: str = "minimal"):
    a = await art.get_artifact(artifact_id)
    if not a:
        raise HTTPException(404, f"artifact not found: {artifact_id}")
    try:
        from services.artifact_export import export_artifact
        path = export_artifact(a, format=format, template=template)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"export 失敗: {e}")
    rel = path.name
    return {
        "ok": True,
        "format": format,
        "path": str(path),
        "filename": rel,
        "url": f"/api/artifacts/{artifact_id}/exports/{rel}",
        "size": path.stat().st_size,
    }


@router.get("/{artifact_id}/exports/{filename}")
async def get_export(artifact_id: str, filename: str):
    from services.artifact_export import EXPORT_DIR
    path = EXPORT_DIR / artifact_id / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "file not found")
    # ディレクトリトラバーサル防御
    try:
        path.resolve().relative_to(EXPORT_DIR.resolve())
    except ValueError:
        raise HTTPException(400, "invalid path")
    media = "application/pdf" if path.suffix == ".pdf" else (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if path.suffix == ".xlsx" else
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    return FileResponse(path, media_type=media, filename=filename)


# ── WebSocket（live push）──────────────────────

@router.websocket("/ws")
async def artifact_ws(websocket: WebSocket, user_id: str = "masato"):
    await websocket.accept()
    art.subscribe(user_id, websocket)
    try:
        await websocket.send_json({"event": "connected", "user_id": user_id})
        while True:
            # client → server からの受信は ping 用途のみ
            try:
                msg = await websocket.receive_text()
                if msg == "ping":
                    await websocket.send_json({"event": "pong"})
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        art.unsubscribe(user_id, websocket)
