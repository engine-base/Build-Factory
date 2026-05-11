"""T-AI-07 / T-010d-01: WebSocket bridge for session streaming.

  WS  /api/ws/sessions/{session_id}?since_seq=<int>&user_id=<str>
        — subscribe + optional replay (T-010d-01 AC-1/2)
  GET /api/sessions/{session_id}/replay?since_seq=N&user_id=<str>
        — bulk replay (REST) (T-010d-01 AC-2 < 2s)
  POST /api/sessions/{session_id}/publish               — test/internal publish

T-010d-01 AC:
  AC-1 UBIQUITOUS: subscribe endpoint 公開 + session_id 単位の購読
  AC-2 EVENT    : 2 秒以内に成功 or {detail:{code,message}} 形式の error
  AC-3 STATE    : audit_logs に ws.session.subscribed / ws.session.disconnected を emit
  AC-4 UNWANTED : invalid input / unauthorized actor は 4xx + {detail:{code,message}}
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from services.stream_bridge import get_bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["streaming"])


# ──────────────────────────────────────────────────────────────────────────
# T-010d-01: error contract helpers
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    """{detail: {code, message}} 形式に統一 (T-010d-01 AC-2 / AC-4)."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, session_id: int, user_id: Optional[str], detail: dict) -> None:
    """audit_logs に event を流す (T-010d-01 AC-3). 失敗してもアプリは止めない."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, session_id=session_id, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover — best-effort emit
        logger.warning("ws audit emit failed: %s -- %s", event_type, e)


def _validate_session_id(session_id: int) -> None:
    """AC-4 UNWANTED: session_id は 1 以上の整数."""
    if session_id <= 0:
        raise _error("ws.invalid_session_id", f"session_id must be > 0, got {session_id}")


def _validate_since_seq(since_seq: Optional[int]) -> None:
    """AC-4 UNWANTED: since_seq は 0 以上."""
    if since_seq is not None and since_seq < 0:
        raise _error("ws.invalid_since_seq", f"since_seq must be >= 0, got {since_seq}")


def _validate_user_id(user_id: Optional[str]) -> None:
    """AC-4 UNWANTED: user_id が指定された場合は非空."""
    if user_id is not None and not user_id.strip():
        raise _error("ws.unauthorized", "user_id must not be empty", status_code=401)


# ──────────────────────────────────────────────────────────────────────────
# T-010d-01 / T-AI-07: WebSocket subscribe
# ──────────────────────────────────────────────────────────────────────────


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: int,
    since_seq: Optional[int] = Query(None, description="replay from seq > since_seq"),
    user_id: Optional[str] = Query(None, description="actor user_id for audit log"),
) -> None:
    """フロントエンドが claude-agent-sdk stream を購読する WS (T-010d-01)."""
    # AC-4 UNWANTED: invalid input は accept 前に close
    if session_id <= 0:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid_session_id")
        return
    if since_seq is not None and since_seq < 0:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid_since_seq")
        return
    if user_id is not None and not user_id.strip():
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="unauthorized")
        return

    bridge = get_bridge()
    await websocket.accept()
    q = await bridge.subscribe(session_id, since_seq=since_seq)
    # AC-3 STATE: subscribe を audit_logs に emit
    await _audit(
        "ws.session.subscribed",
        session_id=session_id,
        user_id=user_id,
        detail={"since_seq": since_seq},
    )
    try:
        while True:
            try:
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
        # AC-3 STATE: disconnect も audit_logs に emit
        await _audit(
            "ws.session.disconnected",
            session_id=session_id,
            user_id=user_id,
            detail={},
        )


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


# ──────────────────────────────────────────────────────────────────────────
# T-010d-01: REST replay (AC-2: structured response within 2s)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}/replay")
async def replay_session(
    session_id: int,
    since_seq: int = 0,
    user_id: Optional[str] = Query(None, description="actor user_id for audit log"),
) -> dict[str, Any]:
    """REST 経由の bulk replay (T-010d-01 AC-2: < 2s)."""
    _validate_session_id(session_id)
    _validate_since_seq(since_seq)
    _validate_user_id(user_id)
    bridge = get_bridge()
    msgs = await bridge.replay_since(session_id, since_seq)
    await _audit(
        "ws.session.replayed",
        session_id=session_id,
        user_id=user_id,
        detail={"since_seq": since_seq, "count": len(msgs)},
    )
    return {
        "session_id": session_id,
        "since_seq": since_seq,
        "count": len(msgs),
        "messages": msgs,
    }


class PublishRequest(BaseModel):
    type: str
    payload: dict[str, Any] = {}
    priority: bool = False


@router.post("/sessions/{session_id}/publish")
async def publish_session_message(session_id: int, req: PublishRequest) -> dict[str, Any]:
    """テスト/内部用: runner 統合前の publish endpoint."""
    _validate_session_id(session_id)
    if not req.type:
        raise _error("ws.invalid_type", "type required")
    bridge = get_bridge()
    if req.priority:
        seq = await bridge.publish_priority(session_id, req.type, req.payload)
    else:
        seq = await bridge.publish(session_id, req.type, req.payload)
    return {"session_id": session_id, "seq": seq, "type": req.type}
