"""T-M30-03 / M-30: 中期 layer REST endpoint (gap closure G3-G4).

既存の conversation_summarizer.py / conversation_memory.py / chat_thread_store.py /
memory_service.py の API は不変. 統一インターフェースを /api/mid-term として
提供する (read-only GET 中心 + Phase 2 dual-write hook の record).

Endpoint:
  GET  /api/mid-term/summary      最新 9-section structured summary
  GET  /api/mid-term/compressed   圧縮済 entries 一覧 (newest-first)
  GET  /api/mid-term/list         同上 (list_summaries spec alias)
  GET  /api/mid-term/stats        圧縮率 / section coverage
  POST /api/mid-term/record       G8 dual-write helper (Phase 2 hook)

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : M-30 中期 layer 統一 API (latest_summary / list_summaries
                       / record_summary).
  AC-2 EVENT-DRIVEN  : 2 秒以内 + record で 'mid_term.recorded' audit emit.
                       Read endpoints は emit しない (spec 明文).
                       audit detail の source は 'chat_thread_store' /
                       'memory_service' (G3 normalization).
  AC-3 STATE-DRIVEN  : 既存 conversation_summarizer / conversation_memory /
                       chat_thread_store / memory_service module 不変.
                       record_summary は dual-write (G4 spec dual-write).
  AC-4 UNWANTED      : 全 4xx は {detail:{code,message}} 形式統一 (pydantic 422
                       排除). invalid input -> 400 / unknown thread -> 404 /
                       unauthorized actor -> 401. 失敗時 persistent state
                       mutate なし.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from services import mid_term_layer as mtl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mid-term", tags=["mid-term"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is None:
        return None
    if not isinstance(actor, str) or not actor.strip():
        raise _error(
            "mid_term.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip()


def _map_service_error(e: mtl.MidTermLayerError) -> HTTPException:
    msg = str(e)
    if "not found" in msg:
        return _error("mid_term.not_found", msg, status_code=404)
    return _error("mid_term.invalid", msg, status_code=400)


def _parse_int(value: Any, *, field: str) -> int:
    """文字列から int 変換. 失敗時 400. 範囲 check は service 層が担う."""
    if value is None:
        raise _error("mid_term.invalid", f"{field} is required")
    if isinstance(value, bool):
        raise _error("mid_term.invalid", f"{field} must be int")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            raise _error("mid_term.invalid", f"{field} must be int")
    raise _error("mid_term.invalid", f"{field} must be int")


# ──────────────────────────────────────────────────────────────────────
# GET /api/mid-term/summary
# ──────────────────────────────────────────────────────────────────────


@router.get("/summary")
async def summary(request: Request) -> dict[str, Any]:
    """AC-4: 全 4xx を {detail:{code,message}} に統一するため Query 制約を排し
    service 層に validation を委譲."""
    q = request.query_params
    thread_id = _parse_int(q.get("thread_id"), field="thread_id")
    prefer_source = q.get("prefer_source", mtl.DEFAULT_PREFER_SOURCE)
    actor = _check_actor(q.get("actor_user_id"))
    try:
        # AC-2 "Read endpoints shall not emit audit events" → emit_audit=False
        return mtl.latest_summary(
            thread_id,
            prefer_source=prefer_source,
            actor_user_id=actor,
        )
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)


# ──────────────────────────────────────────────────────────────────────
# GET /api/mid-term/compressed (and /list alias)
# ──────────────────────────────────────────────────────────────────────


async def _compressed_impl(request: Request) -> dict[str, Any]:
    q = request.query_params
    thread_id = _parse_int(q.get("thread_id"), field="thread_id")
    limit_raw = q.get("limit")
    limit = (
        _parse_int(limit_raw, field="limit")
        if limit_raw is not None
        else mtl.DEFAULT_HISTORY_LIMIT
    )
    actor = _check_actor(q.get("actor_user_id"))
    try:
        return mtl.compressed_history(
            thread_id,
            limit=limit,
            actor_user_id=actor,
        )
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)


@router.get("/compressed")
async def compressed(request: Request) -> dict[str, Any]:
    return await _compressed_impl(request)


@router.get("/list")
async def list_view(request: Request) -> dict[str, Any]:
    """G1 spec alias: list_summaries の HTTP 入口 (compressed と同等)."""
    return await _compressed_impl(request)


# ──────────────────────────────────────────────────────────────────────
# GET /api/mid-term/stats
# ──────────────────────────────────────────────────────────────────────


@router.get("/stats")
async def stats(request: Request) -> dict[str, Any]:
    q = request.query_params
    thread_id = _parse_int(q.get("thread_id"), field="thread_id")
    actor = _check_actor(q.get("actor_user_id"))
    try:
        return mtl.mid_tier_stats(thread_id, actor_user_id=actor)
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)


# ──────────────────────────────────────────────────────────────────────
# POST /api/mid-term/record (G8 dual-write helper)
# ──────────────────────────────────────────────────────────────────────


@router.post("/record")
async def record(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise _error("mid_term.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("mid_term.invalid", "request body must be a JSON object")

    if "thread_id" not in body:
        raise _error("mid_term.invalid", "thread_id is required")
    if "summary" not in body:
        raise _error("mid_term.invalid", "summary is required")

    thread_id = _parse_int(body.get("thread_id"), field="thread_id")
    summary = body.get("summary")
    if not isinstance(summary, dict):
        raise _error("mid_term.invalid", "summary must be a dict")
    persist_legacy = body.get("persist_legacy", True)
    use_backend = body.get("use_backend", True)
    if not isinstance(persist_legacy, bool):
        raise _error("mid_term.invalid", "persist_legacy must be bool")
    if not isinstance(use_backend, bool):
        raise _error("mid_term.invalid", "use_backend must be bool")
    actor = _check_actor(body.get("actor_user_id"))

    try:
        # AC-2: record は emit_audit=True で 'mid_term.recorded' を emit.
        # source は service 内で 'chat_thread_store' / 'memory_service' に
        # 正規化済 (G3).
        return await mtl.record_summary(
            thread_id,
            summary,
            persist_legacy=persist_legacy,
            use_backend=use_backend,
            actor_user_id=actor,
            emit_audit=True,
        )
    except mtl.MidTermLayerError as e:
        raise _map_service_error(e)
