"""T-M30-03 / M-30: 中期 layer REST endpoint.

既存の conversation_summarizer.py / conversation_memory.py / chat_thread_store.py /
memory_service.py の API は不変. 統一インターフェースを /api/mid-term として
提供する (read-only GET 中心 + Phase 2 dual-write hook の record).

Endpoint:
  GET  /api/mid-term/summary      最新 9-section structured summary
  GET  /api/mid-term/compressed   圧縮済 entries 一覧 (newest-first)
  GET  /api/mid-term/stats        圧縮率 / section coverage
  POST /api/mid-term/record       G8 dual-write helper (Phase 2 hook)

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 中期 layer 統一 API (REFACTOR REUSE 既存 modules)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}} (in-memory store の
                       sync 実装で典型 ms オーダー)
  AC-3 STATE-DRIVEN  : 既存 conversation_summarizer / conversation_memory /
                       chat_thread_store / memory_service module 不変 +
                       audit emit (record 経路のみ)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       不明 thread → 404 / 失敗時 persistent state mutate なし
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import mid_term_layer as mtl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mid-term", tags=["mid-term"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    """audit emit (memory_service.emit_event 経由). 失敗は warning に握り潰す."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover (sqlite 未配備環境向け)
        logger.warning("mid-term audit emit failed: %s -- %s", event_type, e)


def _check_actor(actor: Optional[str]) -> Optional[str]:
    """actor_user_id の空文字列を 401 に変換 (validate は service 側にも残す)."""
    if actor is not None and not actor.strip():
        raise _error(
            "mid_term.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


def _map_service_error(e: mtl.MidTermLayerError) -> HTTPException:
    """service の MidTermLayerError を 400/404 に振り分ける."""
    msg = str(e)
    if "not found" in msg:
        return _error("mid_term.not_found", msg, status_code=404)
    return _error("mid_term.invalid", msg, status_code=400)


# ──────────────────────────────────────────────────────────────────────
# GET /api/mid-term/summary
# ──────────────────────────────────────────────────────────────────────


@router.get("/summary")
async def summary(
    thread_id: int = Query(..., gt=0),
    prefer_source: str = Query(mtl.DEFAULT_PREFER_SOURCE),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    actor = _check_actor(actor_user_id)
    try:
        return mtl.latest_summary(
            thread_id,
            prefer_source=prefer_source,
            actor_user_id=actor,
        )
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)


# ──────────────────────────────────────────────────────────────────────
# GET /api/mid-term/compressed
# ──────────────────────────────────────────────────────────────────────


@router.get("/compressed")
async def compressed(
    thread_id: int = Query(..., gt=0),
    limit: int = Query(
        mtl.DEFAULT_HISTORY_LIMIT,
        ge=mtl.MIN_HISTORY_LIMIT,
        le=mtl.MAX_HISTORY_LIMIT,
    ),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    actor = _check_actor(actor_user_id)
    try:
        return mtl.compressed_history(
            thread_id,
            limit=limit,
            actor_user_id=actor,
        )
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)


# AC-1 命名 alias: /list は /compressed の等価エンドポイント
# (tickets.json T-M30-03 UBIQUITOUS の "list_summaries" に対応する read view).
@router.get("/list")
async def list_(
    thread_id: int = Query(..., gt=0),
    limit: int = Query(
        mtl.DEFAULT_HISTORY_LIMIT,
        ge=mtl.MIN_HISTORY_LIMIT,
        le=mtl.MAX_HISTORY_LIMIT,
    ),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    actor = _check_actor(actor_user_id)
    try:
        return mtl.list_summaries(
            thread_id,
            limit=limit,
            actor_user_id=actor,
        )
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)


# ──────────────────────────────────────────────────────────────────────
# GET /api/mid-term/stats
# ──────────────────────────────────────────────────────────────────────


@router.get("/stats")
async def stats(
    thread_id: int = Query(..., gt=0),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    actor = _check_actor(actor_user_id)
    try:
        return mtl.mid_tier_stats(thread_id, actor_user_id=actor)
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)


# ──────────────────────────────────────────────────────────────────────
# POST /api/mid-term/record (G8 dual-write helper)
# ──────────────────────────────────────────────────────────────────────


class RecordRequest(BaseModel):
    thread_id: int = Field(..., gt=0)
    summary: dict
    persist_legacy: bool = True
    use_backend: bool = True
    actor_user_id: Optional[str] = None


@router.post("/record")
async def record(req: RecordRequest) -> dict[str, Any]:
    actor = _check_actor(req.actor_user_id)
    try:
        result = await mtl.record_summary(
            req.thread_id,
            req.summary,
            persist_legacy=req.persist_legacy,
            use_backend=req.use_backend,
            actor_user_id=actor,
        )
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)
    await _audit(
        "mid_term.recorded",
        user_id=actor,
        detail={
            "thread_id": result["thread_id"],
            "message_id": result["message_id"],
            "source": result["source"],
            "backend_used": result["backend_used"],
            "persist_legacy": req.persist_legacy,
            "legacy_status": (result.get("legacy_result") or {}).get("status"),
        },
    )
    return result
