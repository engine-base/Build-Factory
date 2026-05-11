"""T-M30-01 / M-30: ChatThread / ChatMessage CRUD REST endpoint.

既存の legacy /api/threads (company-os pattern) は不変. M-30 schema
(chat_threads / chat_messages) に対応する CRUD endpoint を /api/chat-threads
として追加する.

Endpoint:
  POST   /api/chat-threads                         thread 作成
  GET    /api/chat-threads                         一覧 (workspace_id filter)
  GET    /api/chat-threads/{id}                    1 件取得
  PATCH  /api/chat-threads/{id}                    title/persona/is_archived 更新
  DELETE /api/chat-threads/{id}                    削除
  POST   /api/chat-threads/{id}/messages           message 追加
  GET    /api/chat-threads/{id}/messages           message 一覧 (limit/offset)
  DELETE /api/chat-threads/{id}/messages/{mid}     message 削除

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 chat thread/message CRUD (REFACTOR threads.py 拡張)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 routers/threads.py / chat.py の API は不変 +
                       audit emit (thread.created/updated/deleted, message.added/deleted)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import chat_thread_store as cts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat-threads", tags=["chat-threads"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("chat-threads audit emit failed: %s -- %s", event_type, e)


class ThreadCreate(BaseModel):
    workspace_id: Optional[int] = Field(None, gt=0)
    session_id: Optional[int] = Field(None, gt=0)
    title: Optional[str] = None
    persona: Optional[str] = None
    actor_user_id: Optional[str] = None


class ThreadUpdate(BaseModel):
    title: Optional[str] = None
    persona: Optional[str] = None
    is_archived: Optional[bool] = None
    actor_user_id: Optional[str] = None


class MessageCreate(BaseModel):
    role: str
    content: str
    compressed_summary: Optional[dict] = None
    token_count: Optional[int] = Field(None, ge=0)
    actor_user_id: Optional[str] = None


def _check_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("chat_thread.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)


def _map_error(e: cts.ChatThreadError) -> HTTPException:
    msg = str(e)
    if "not found" in msg:
        return _error("chat_thread.not_found", msg, status_code=404)
    if "max " in msg:
        return _error("chat_thread.quota_exceeded", msg, status_code=409)
    return _error("chat_thread.invalid", msg)


@router.post("")
async def create_thread(body: ThreadCreate) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    try:
        t = cts.get_store().create_thread(
            workspace_id=body.workspace_id,
            session_id=body.session_id,
            title=body.title,
            persona=body.persona,
        )
    except cts.ChatThreadError as e:
        raise _map_error(e)
    await _audit(
        "chat_thread.created",
        user_id=body.actor_user_id,
        detail={
            "thread_id": t.id,
            "workspace_id": t.workspace_id,
            "session_id": t.session_id,
        },
    )
    return t.to_dict()


@router.get("")
async def list_threads(
    workspace_id: Optional[int] = Query(None, gt=0),
    include_archived: bool = Query(False),
    limit: int = Query(100, gt=0, le=10_000),
) -> dict[str, Any]:
    try:
        threads = cts.get_store().list_threads(
            workspace_id=workspace_id,
            include_archived=include_archived,
            limit=limit,
        )
    except cts.ChatThreadError as e:
        raise _map_error(e)
    return {
        "count": len(threads),
        "threads": [t.to_dict() for t in threads],
    }


@router.get("/{thread_id}")
async def get_thread(thread_id: int) -> dict[str, Any]:
    if thread_id <= 0:
        raise _error("chat_thread.invalid", "thread_id must be > 0")
    t = cts.get_store().get_thread(thread_id)
    if t is None:
        raise _error("chat_thread.not_found",
                     f"thread not found: {thread_id}", status_code=404)
    return t.to_dict()


@router.patch("/{thread_id}")
async def update_thread(thread_id: int, body: ThreadUpdate) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    if thread_id <= 0:
        raise _error("chat_thread.invalid", "thread_id must be > 0")
    try:
        t = cts.get_store().update_thread(
            thread_id,
            title=body.title,
            persona=body.persona,
            is_archived=body.is_archived,
        )
    except cts.ChatThreadError as e:
        raise _map_error(e)
    await _audit(
        "chat_thread.updated",
        user_id=body.actor_user_id,
        detail={
            "thread_id": t.id,
            "fields": [
                k for k, v in {
                    "title": body.title,
                    "persona": body.persona,
                    "is_archived": body.is_archived,
                }.items() if v is not None
            ],
        },
    )
    return t.to_dict()


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    _check_actor(actor_user_id)
    if thread_id <= 0:
        raise _error("chat_thread.invalid", "thread_id must be > 0")
    ok = cts.get_store().delete_thread(thread_id)
    if not ok:
        raise _error("chat_thread.not_found",
                     f"thread not found: {thread_id}", status_code=404)
    await _audit(
        "chat_thread.deleted",
        user_id=actor_user_id,
        detail={"thread_id": thread_id},
    )
    return {"deleted": True, "thread_id": thread_id}


@router.post("/{thread_id}/messages")
async def add_message(thread_id: int, body: MessageCreate) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    if thread_id <= 0:
        raise _error("chat_thread.invalid", "thread_id must be > 0")
    try:
        m = cts.get_store().add_message(
            thread_id, body.role, body.content,
            compressed_summary=body.compressed_summary,
            token_count=body.token_count,
        )
    except cts.ChatThreadError as e:
        raise _map_error(e)
    await _audit(
        "chat_message.added",
        user_id=body.actor_user_id,
        detail={
            "thread_id": thread_id,
            "message_id": m.id,
            "role": m.role,
            "token_count": m.token_count,
        },
    )
    return m.to_dict()


@router.get("/{thread_id}/messages")
async def list_messages(
    thread_id: int,
    limit: int = Query(200, gt=0, le=10_000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    if thread_id <= 0:
        raise _error("chat_thread.invalid", "thread_id must be > 0")
    try:
        items = cts.get_store().list_messages(
            thread_id, limit=limit, offset=offset,
        )
    except cts.ChatThreadError as e:
        raise _map_error(e)
    return {
        "thread_id": thread_id,
        "count": len(items),
        "messages": [m.to_dict() for m in items],
    }


@router.delete("/{thread_id}/messages/{message_id}")
async def delete_message(
    thread_id: int,
    message_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    _check_actor(actor_user_id)
    if thread_id <= 0 or message_id <= 0:
        raise _error("chat_thread.invalid", "ids must be > 0")
    store = cts.get_store()
    m = store.get_message(message_id)
    if m is None or m.thread_id != thread_id:
        raise _error("chat_thread.not_found",
                     f"message not found: thread={thread_id}, message={message_id}",
                     status_code=404)
    ok = store.delete_message(message_id)
    if not ok:  # pragma: no cover - race only
        raise _error("chat_thread.not_found",
                     f"message not found: {message_id}", status_code=404)
    await _audit(
        "chat_message.deleted",
        user_id=actor_user_id,
        detail={"thread_id": thread_id, "message_id": message_id},
    )
    return {"deleted": True, "thread_id": thread_id, "message_id": message_id}
