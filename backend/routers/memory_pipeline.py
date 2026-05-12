"""T-M30-05 / M-30: Memory pipeline REST endpoint.

3 層 (短期 chat_thread_store / 中期 mid_term_layer / 長期 long_term_layer) を
1 つの context block に組み立てる pipeline の HTTP entry.

Endpoint:
  POST /api/memory/context        3 tier 並列収集 + 1 つの assembled_text 生成
  GET  /api/memory/health         tier 単独で利用可能か診断 (read-only)

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 3-tier pipeline 統合 + chat_search/semantic_retrieval 互換
  AC-2 EVENT-DRIVEN  : context endpoint は audit emit (action + timestamp) /
                       2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 layer modules (4 個) 不変 / RLS は Phase 2 (in-memory store
                       境界を docstring に明示) / audit emit は context のみ
  AC-4 UNWANTED      : invalid input / unauthorized actor / 不明 thread → 4xx /
                       全 tier 失敗 → 502 / state mutate なし
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import memory_pipeline as mp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory-pipeline"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    """memory_service.emit_event 経由 audit. 失敗は warning 握り潰し."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover (sqlite 未配備環境向け)
        logger.warning("memory pipeline audit emit failed: %s -- %s", event_type, e)


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "memory.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


def _map_service_error(e: mp.MemoryPipelineError) -> HTTPException:
    """service 例外を 400 / 404 / 502 にマップ."""
    msg = str(e)
    if "not found" in msg:
        return _error("memory.not_found", msg, status_code=404)
    if "all requested tiers failed" in msg:
        return _error("memory.all_tiers_failed", msg, status_code=502)
    return _error("memory.invalid", msg, status_code=400)


# ──────────────────────────────────────────────────────────────────────
# POST /api/memory/context
# ──────────────────────────────────────────────────────────────────────


class ContextRequest(BaseModel):
    thread_id: int = Field(..., gt=0)
    user_id: str
    query: str
    recent_n: int = Field(
        mp.DEFAULT_RECENT_N, ge=mp.MIN_RECENT_N, le=mp.MAX_RECENT_N,
    )
    long_top_k: int = Field(
        mp.DEFAULT_LONG_TOP_K, ge=mp.MIN_LONG_TOP_K, le=mp.MAX_LONG_TOP_K,
    )
    long_min_score: float = Field(
        mp.DEFAULT_LONG_MIN_SCORE,
        ge=mp.MIN_LONG_MIN_SCORE, le=mp.MAX_LONG_MIN_SCORE,
    )
    tiers: Optional[list[str]] = None
    use_chat_search: bool = False
    use_semantic: bool = False
    actor_user_id: Optional[str] = None


@router.post("/context")
async def context(req: ContextRequest) -> dict[str, Any]:
    actor = _check_actor(req.actor_user_id)
    try:
        result = await mp.build_full_context(
            req.thread_id,
            req.user_id,
            req.query,
            recent_n=req.recent_n,
            long_top_k=req.long_top_k,
            long_min_score=req.long_min_score,
            tiers=req.tiers,
            use_chat_search=req.use_chat_search,
            use_semantic=req.use_semantic,
            actor_user_id=actor,
        )
    except mp.MemoryPipelineError as e:
        raise _map_service_error(e)
    await _audit(
        "memory.context_built",
        user_id=actor or req.user_id,
        detail={
            "thread_id": result["thread_id"],
            "user_id": result["user_id"],
            "tiers_requested": result["tiers_requested"],
            "degraded_mode": result["degraded_mode"],
            "errors": result["errors"],
            "stats": result["stats"],
        },
    )
    return result


# ──────────────────────────────────────────────────────────────────────
# GET /api/memory/health
# ──────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict[str, Any]:
    return mp.tier_health()
