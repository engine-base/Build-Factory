"""T-M30-02 / M-30: 短期 layer REST endpoint.

既存 chat_thread_store.py は無改変 (REUSE). 統一インターフェースを
`/api/short-term` として提供する (read-only GET only).

Endpoint:
  GET  /api/short-term/{thread_id}/recent   FIFO 直近 N 件 (chronological)
  GET  /api/short-term/{thread_id}/stats    短期 layer 統計

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 短期 layer 統一 API (REUSE chat_thread_store)
  AC-2 EVENT-DRIVEN  : 2 秒以内 / chronological oldest-first / mid summary default exclude
  AC-3 STATE-DRIVEN  : 既存 chat_thread_store 無改変 / read-only (no add/delete)
  AC-4 UNWANTED      : invalid input → 4xx structured / 不明 thread → 404 /
                       内部 ChatThreadError leak しない
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
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "short_term_layer.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


def _map_service_error(e: stl.ShortTermLayerError) -> HTTPException:
    msg = str(e)
    if "not found" in msg:
        return _error("short_term_layer.not_found", msg, status_code=404)
    return _error("short_term_layer.invalid_input", msg, status_code=400)


@router.get("/{thread_id}/recent")
async def recent(
    thread_id: int,
    n: int = Query(stl.DEFAULT_FIFO_N, ge=stl.MIN_FIFO_N, le=stl.MAX_FIFO_N),
    role: Optional[list[str]] = Query(None),
    exclude_summaries: bool = Query(True),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    actor = _check_actor(actor_user_id)
    try:
        return stl.recent_messages(
            thread_id,
            n=n,
            role_filter=role,
            exclude_summaries=exclude_summaries,
            actor_user_id=actor,
        )
    except stl.ShortTermLayerError as e:
        raise _map_service_error(e)


@router.get("/{thread_id}/stats")
async def stats(
    thread_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    actor = _check_actor(actor_user_id)
    try:
        return stl.short_tier_stats(thread_id, actor_user_id=actor)
    except stl.ShortTermLayerError as e:
        raise _map_service_error(e)
