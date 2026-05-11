"""T-M28-05 / M-28: semantic retrieval REST endpoint.

Endpoint:
  POST /api/semantic-retrieval/search       3-tier 横断 semantic search
  GET  /api/semantic-retrieval/scopes       supported scopes 一覧

AC マッピング:
  AC-1 UBIQUITOUS    : M-28 semantic retrieval (existing embedding_service 活用)
  AC-2 EVENT-DRIVEN  : audit emit (semantic.search) + 2 秒以内
  AC-3 STATE-DRIVEN  : embedding_service / rag_context / memory_service 既存 API 不変
                       + audit_logs 保持
  AC-4 UNWANTED      : invalid scope / query / top_k / unauthorized actor は
                       4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import semantic_retrieval as sr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/semantic-retrieval", tags=["semantic-retrieval"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("semantic-retrieval audit emit failed: %s -- %s", event_type, e)


class SearchRequest(BaseModel):
    query: str
    scopes: list[str] = Field(default_factory=lambda: list(sr.DEFAULT_SCOPES))
    top_k: int = Field(sr.DEFAULT_TOP_K, gt=0, le=sr.MAX_TOP_K)
    min_score: float = Field(sr.DEFAULT_MIN_SCORE, ge=0.0, le=1.0)
    skill_tags: Optional[list[str]] = None
    session_id: Optional[int] = Field(None, gt=0)
    exclude_thread_id: Optional[int] = Field(None, gt=0)
    actor_user_id: Optional[str] = None


@router.get("/scopes")
async def list_scopes() -> dict[str, Any]:
    return {
        "scopes": list(sr.VALID_SCOPES),
        "default": list(sr.DEFAULT_SCOPES),
        "max_top_k": sr.MAX_TOP_K,
        "max_query_chars": sr.MAX_QUERY_CHARS,
    }


@router.post("/search")
async def search(req: SearchRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("semantic.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        result = await sr.search(
            req.query,
            scopes=req.scopes,
            top_k=req.top_k,
            min_score=req.min_score,
            skill_tags=req.skill_tags,
            session_id=req.session_id,
            exclude_thread_id=req.exclude_thread_id,
        )
    except sr.SemanticRetrievalError as e:
        raise _error("semantic.invalid", str(e))
    await _audit(
        "semantic.search",
        user_id=req.actor_user_id,
        detail={
            "query_chars": len(req.query),
            "scopes": req.scopes,
            "top_k": req.top_k,
            "count": result["count"],
            "per_scope_count": result["per_scope_count"],
        },
    )
    return result
