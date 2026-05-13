"""T-024-02: 統一 search REST endpoint (T-024-01 Cmd+K modal の dynamic items 供給).

既存 knowledge_search router + embedding_service は無改変 (REUSE).
本 router は複数 source を横断する統一 endpoint.

Endpoint:
  POST /api/search/unified : 並列 search + audit emit
  GET  /api/search/sources : 利用可能 source 一覧 (read-only)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import unified_search as us

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["unified-search"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("unified search audit emit failed: %s -- %s", event_type, e)


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "search.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


# ──────────────────────────────────────────────────────────────────────
# POST /api/search/unified
# ──────────────────────────────────────────────────────────────────────


class UnifiedSearchRequest(BaseModel):
    query: str = Field(..., min_length=us.MIN_QUERY_CHARS, max_length=us.MAX_QUERY_CHARS)
    sources: Optional[list[str]] = None
    account_id: Optional[int] = None
    limit_per_source: int = us.DEFAULT_LIMIT_PER_SOURCE
    actor_user_id: Optional[str] = None


@router.post("/unified")
async def unified(req: UnifiedSearchRequest) -> dict[str, Any]:
    actor = _check_actor(req.actor_user_id)
    if req.account_id is not None and req.account_id <= 0:
        raise _error(
            "search.invalid",
            "account_id must be positive int or null",
        )
    try:
        result = await us.unified_search(
            req.query,
            sources=req.sources,
            account_id=req.account_id,
            limit_per_source=req.limit_per_source,
        )
    except ValueError as e:
        raise _error("search.invalid", str(e))
    await _audit(
        "search.unified",
        user_id=actor,
        detail={
            "query_chars": len(req.query),
            "sources_used": result["sources_used"],
            "total": result["total"],
            "by_kind": result["by_kind"],
        },
    )
    return result


# ──────────────────────────────────────────────────────────────────────
# GET /api/search/sources
# ──────────────────────────────────────────────────────────────────────


@router.get("/sources")
async def sources() -> dict[str, Any]:
    return {
        "valid_sources": us.list_valid_sources(),
        "default_limit": us.DEFAULT_LIMIT_PER_SOURCE,
        "max_limit": us.MAX_LIMIT_PER_SOURCE,
        "max_query_chars": us.MAX_QUERY_CHARS,
    }
