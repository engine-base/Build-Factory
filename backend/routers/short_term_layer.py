"""T-M30-02 / M-30: 短期 layer (FIFO 直近 N=20) REST endpoint.

既存 chat_thread_store / chat_threads router は不変. 統一インターフェースを
/api/short-term として提供する (read-only view).

Endpoint:
  GET /api/short-term/window        直近 N 件 ChatMessage (FIFO 順)
  GET /api/short-term/context       LLM ready {role, content} list
  GET /api/short-term/stats         window 容量状況

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 短期 layer FIFO N=20 (REUSE chat_thread_store)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 chat_thread_store / chat_threads router 不変
                       (read-only — 永続状態を mutate しない)
  AC-4 UNWANTED      : invalid input (thread_id<=0, limit<1/>200, 不正 role) は
                       4xx + structured / state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from services import short_term_layer as stl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/short-term", tags=["short-term"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_error(e: stl.ShortTermLayerError) -> HTTPException:
    msg = str(e)
    if "not found" in msg:
        return _error("short_term.not_found", msg, status_code=404)
    return _error("short_term.invalid", msg)


def _parse_role_filter(role_filter: Optional[str]) -> Optional[list[str]]:
    if role_filter is None:
        return None
    role_filter = role_filter.strip()
    if not role_filter:
        raise _error("short_term.invalid",
                     "role_filter must not be empty when provided")
    return [r.strip() for r in role_filter.split(",") if r.strip()]


@router.get("/window")
async def window(
    thread_id: int = Query(..., gt=0),
    limit: int = Query(stl.DEFAULT_WINDOW, ge=stl.MIN_WINDOW, le=stl.MAX_WINDOW),
    role_filter: Optional[str] = Query(None),
) -> dict[str, Any]:
    roles = _parse_role_filter(role_filter)
    try:
        items = stl.recent_window(thread_id, limit=limit, role_filter=roles)
    except stl.ShortTermLayerError as e:
        raise _map_error(e)
    return {
        "thread_id": thread_id,
        "limit": limit,
        "role_filter": roles,
        "count": len(items),
        "messages": [m.to_dict() for m in items],
    }


@router.get("/context")
async def context(
    thread_id: int = Query(..., gt=0),
    limit: int = Query(stl.DEFAULT_WINDOW, ge=stl.MIN_WINDOW, le=stl.MAX_WINDOW),
    role_filter: Optional[str] = Query(None),
) -> dict[str, Any]:
    roles = _parse_role_filter(role_filter)
    try:
        ctx = stl.assemble_context(thread_id, limit=limit, role_filter=roles)
    except stl.ShortTermLayerError as e:
        raise _map_error(e)
    return {
        "thread_id": thread_id,
        "limit": limit,
        "role_filter": roles,
        "count": len(ctx),
        "context": ctx,
    }


@router.get("/stats")
async def stats(thread_id: int = Query(..., gt=0)) -> dict[str, Any]:
    try:
        return stl.window_stats(thread_id)
    except stl.ShortTermLayerError as e:
        raise _map_error(e)
