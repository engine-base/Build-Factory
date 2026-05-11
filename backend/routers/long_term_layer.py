"""T-M30-04 / M-30: 長期 layer REST endpoint.

既存の long_term_memory.py (Mem0) + obsidian_sync.py + obsidian_vault_sync.py
の API は不変. 統一インターフェースを /api/long-term として提供する.

Endpoint:
  POST /api/long-term/persist        Mem0 + Obsidian に永続化
  POST /api/long-term/retrieve       横断検索
  GET  /api/long-term/sources        tracked source 一覧

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 長期 layer 統一 API (REFACTOR REUSE 既存 mem0/obsidian)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 mem0/obsidian module 不変 + audit emit (persist のみ)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       path traversal 防止 / persistent state 失敗時非反映
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import long_term_layer as ltl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/long-term", tags=["long-term"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("long-term audit emit failed: %s -- %s", event_type, e)


class PersistRequest(BaseModel):
    user_id: str
    content: str
    source: str = "conversation"
    tags: Optional[list[str]] = None
    scopes: Optional[list[str]] = None
    actor_user_id: Optional[str] = None


class RetrieveRequest(BaseModel):
    user_id: str
    query: str
    top_k: int = Field(ltl.DEFAULT_TOP_K, gt=0, le=ltl.MAX_TOP_K)
    min_score: float = Field(ltl.DEFAULT_MIN_SCORE, ge=0.0, le=1.0)
    scopes: Optional[list[str]] = None
    actor_user_id: Optional[str] = None


def _check_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("long_term.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)


@router.post("/persist")
async def persist(req: PersistRequest) -> dict[str, Any]:
    _check_actor(req.actor_user_id)
    try:
        result = await ltl.persist(
            req.user_id, req.content,
            source=req.source,
            tags=req.tags,
            scopes=req.scopes,
        )
    except ltl.LongTermLayerError as e:
        raise _error("long_term.invalid", str(e))
    if result["status"] == "failed":
        # 全 sink が失敗 → AC-4 4xx
        raise _error(
            "long_term.persist_failed",
            f"all sinks failed: {result['results']}",
            status_code=502,
        )
    await _audit(
        "long_term.persisted",
        user_id=req.actor_user_id or result["user_id"],
        detail={
            "user_id": result["user_id"],
            "source": result["source"],
            "scopes": result["scopes"],
            "status": result["status"],
            "tag_count": len(result["tags"]),
        },
    )
    return result


@router.post("/retrieve")
async def retrieve(req: RetrieveRequest) -> dict[str, Any]:
    _check_actor(req.actor_user_id)
    try:
        result = await ltl.retrieve(
            req.user_id, req.query,
            top_k=req.top_k,
            min_score=req.min_score,
            scopes=req.scopes,
        )
    except ltl.LongTermLayerError as e:
        raise _error("long_term.invalid", str(e))
    return result


@router.get("/sources")
async def sources(user_id: str = Query(...)) -> dict[str, Any]:
    try:
        result = await ltl.list_sources(user_id)
    except ltl.LongTermLayerError as e:
        raise _error("long_term.invalid", str(e))
    return result
