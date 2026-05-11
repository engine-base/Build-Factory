"""T-M28-03 / M-28: Tier 2 prompt cache friendly REST endpoint.

Endpoint:
  POST /api/tier2-cache/compose                Tier 2 cached payload を組み立て
  GET  /api/tier2-cache/summary/{session_id}   summary stats (no payload)

AC マッピング:
  AC-1 UBIQUITOUS    : M-28 Tier 2 prompt cache friendly (cache_control: ephemeral 5min)
  AC-2 EVENT-DRIVEN  : audit emit (tier2.cache.compose) + 2 秒以内
  AC-3 STATE-DRIVEN  : RLS / audit_logs を CLAUDE.md §5.3 に従って維持
  AC-4 UNWANTED      : invalid input / unauthorized actor は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import tier2_cache as t2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tier2-cache", tags=["tier2-cache"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, session_id: Optional[int],
                 user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, session_id=session_id,
                         user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("tier2-cache audit emit failed: %s -- %s", event_type, e)


class ComposeRequest(BaseModel):
    session_id: int = Field(..., gt=0)
    model: str
    user_messages: list[dict]
    constitution_text: Optional[str] = None
    max_tokens: int = Field(4096, gt=0)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    cache_summary: bool = True
    cache_constitution: bool = True
    override_summary: Optional[dict] = None
    actor_user_id: Optional[str] = None


@router.post("/compose")
async def compose(req: ComposeRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("tier2.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    # 1. summary 解決: override が指定されればそれを優先、なければ DB ロード
    if req.override_summary is not None:
        try:
            summary_text = t2.format_summary_text(req.override_summary)
            loaded_message_id: Optional[int] = None
        except t2.Tier2CacheError as e:
            raise _error("tier2.invalid", str(e))
    else:
        try:
            loaded = await t2.load_latest_summary(req.session_id)
        except t2.Tier2CacheError as e:
            raise _error("tier2.invalid", str(e))
        if loaded is None:
            summary_text = None
            loaded_message_id = None
        else:
            try:
                summary_text = t2.format_summary_text(loaded["summary"])
            except t2.Tier2CacheError as e:
                raise _error("tier2.invalid", str(e))
            loaded_message_id = loaded.get("message_id")
    # 2. composer
    try:
        result = t2.compose_cached_payload(
            model=req.model,
            summary_text=summary_text,
            user_messages=req.user_messages,
            constitution_text=req.constitution_text,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            cache_summary=req.cache_summary,
            cache_constitution=req.cache_constitution,
        )
    except t2.Tier2CacheError as e:
        raise _error("tier2.invalid", str(e))
    # 3. audit emit
    await _audit(
        "tier2.cache.compose",
        session_id=req.session_id,
        user_id=req.actor_user_id,
        detail={
            "model": req.model,
            "summary_cached": result["cache_meta"]["summary_cached"],
            "constitution_cached": result["cache_meta"]["constitution_cached"],
            "breakpoints": result["cache_meta"]["breakpoints"],
            "summary_message_id": loaded_message_id,
        },
    )
    result["summary_message_id"] = loaded_message_id
    return result


@router.get("/summary/{session_id}")
async def get_summary_stats(session_id: int) -> dict[str, Any]:
    if session_id <= 0:
        raise _error("tier2.invalid_session_id", "session_id must be > 0")
    try:
        loaded = await t2.load_latest_summary(session_id)
    except t2.Tier2CacheError as e:
        raise _error("tier2.invalid", str(e))
    stats = t2.summary_stats(loaded)
    stats["session_id"] = session_id
    return stats
