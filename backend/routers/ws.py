"""T-AI-07: WebSocket bridge for session streaming.

  WS  /api/ws/sessions/{session_id}?since_seq=<int>   subscribe + optional replay
  GET /api/sessions/{session_id}/replay?since_seq=N   bulk replay (REST)
  POST /api/sessions/{session_id}/publish             test/internal publish
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.stream_bridge import get_bridge


router = APIRouter(prefix="/api", tags=["streaming"])


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: int,
    since_seq: Optional[int] = Query(None, description="replay from seq > since_seq"),
) -> None:
    """フロントエンドが claude-agent-sdk stream を購読する WS."""
    bridge = get_bridge()
    await websocket.accept()
    q = await bridge.subscribe(session_id, since_seq=since_seq)
    try:
        while True:
            try:
                # 0.1s ごとに client → server をチェック (close 検出)
                receive_task = asyncio.create_task(websocket.receive_text())
                send_task = asyncio.create_task(q.get())
                done, pending = await asyncio.wait(
                    {receive_task, send_task}, return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                if receive_task in done:
                    text = receive_task.result()
                    await _handle_client_message(session_id, websocket, text)
                if send_task in done:
                    msg = send_task.result()
                    await websocket.send_json(msg)
            except WebSocketDisconnect:
                break
    finally:
        await bridge.unsubscribe(session_id, q)


async def _handle_client_message(session_id: int, websocket: WebSocket, text: str) -> None:
    """client → server: {action: 'ping' | 'replay', since_seq?: int}"""
    try:
        payload = json.loads(text)
    except Exception:
        return
    action = (payload or {}).get("action")
    if action == "ping":
        await websocket.send_json({"type": "pong", "seq": 0})
    elif action == "replay":
        since = int(payload.get("since_seq") or 0)
        bridge = get_bridge()
        msgs = await bridge.replay_since(session_id, since)
        for m in msgs:
            await websocket.send_json(m)


@router.get("/sessions/{session_id}/replay")
async def replay_session(session_id: int, since_seq: int = 0) -> dict[str, Any]:
    """AC-OPTIONAL: REST 経由の bulk replay。 since_seq より後の全 message を返す."""
    bridge = get_bridge()
    msgs = await bridge.replay_since(session_id, since_seq)
    return {"session_id": session_id, "since_seq": since_seq, "count": len(msgs), "messages": msgs}


class PublishRequest(BaseModel):
    type: str
    payload: dict[str, Any] = {}
    priority: bool = False


@router.post("/sessions/{session_id}/publish")
async def publish_session_message(session_id: int, req: PublishRequest) -> dict[str, Any]:
    """テスト/内部用: runner 統合前の publish endpoint."""
    if not req.type:
        raise HTTPException(400, "type required")
    bridge = get_bridge()
    if req.priority:
        seq = await bridge.publish_priority(session_id, req.type, req.payload)
    else:
        seq = await bridge.publish(session_id, req.type, req.payload)
    return {"session_id": session_id, "seq": seq, "type": req.type}
