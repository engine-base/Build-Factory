"""T-014-02 / F-014: カテゴリ別 push + ダイジェスト REST endpoint.

Endpoint:
  POST /api/notifications/push                       カテゴリ別通知
  GET  /api/notifications/pending/{category}         pending 一覧 (digest 待機)
  POST /api/notifications/digest/flush/{category}    1 カテゴリ flush
  POST /api/notifications/digest/flush-all           全カテゴリ flush
  POST /api/notifications/configure                  channel / digest_window 設定

AC マッピング:
  AC-1 UBIQUITOUS    : F-014 5 カテゴリ push + digest endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 T-014-01 Slack contract 不変 (backwards compat) +
                       audit emit
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import category_push as cp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["category-push"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("category-push audit emit failed: %s -- %s", event_type, e)


class PushRequest(BaseModel):
    category: str
    message: str
    channel: Optional[str] = None
    immediate: bool = False
    actor_user_id: Optional[str] = None


class FlushRequest(BaseModel):
    actor_user_id: Optional[str] = None


class ConfigureRequest(BaseModel):
    category: str
    channel: Optional[str] = None
    digest_window_seconds: Optional[float] = Field(
        None, ge=0, le=cp.MAX_DIGEST_WINDOW_SEC,
    )
    actor_user_id: Optional[str] = None


def _validate_category(category: str) -> str:
    if not category or category not in cp.VALID_CATEGORIES:
        raise _error(
            "notify.invalid_category",
            f"category must be one of {cp.VALID_CATEGORIES}",
        )
    return category


@router.post("/push")
async def push(req: PushRequest) -> dict[str, Any]:
    _validate_category(req.category)
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("notify.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not req.message or not req.message.strip():
        raise _error("notify.invalid_message", "message must not be empty")
    if len(req.message) > cp.MAX_MESSAGE_LEN:
        raise _error("notify.message_too_long",
                     f"message must be <= {cp.MAX_MESSAGE_LEN} chars")
    if req.channel is not None:
        if not req.channel.strip():
            raise _error("notify.invalid_channel",
                         "channel must not be empty when provided")
        if len(req.channel) > cp.MAX_CHANNEL_LEN:
            raise _error("notify.invalid_channel",
                         f"channel must be <= {cp.MAX_CHANNEL_LEN} chars")

    try:
        result = await cp.push_message(
            req.category, req.message,
            channel=req.channel, immediate=req.immediate,
        )
    except cp.CategoryPushError as e:
        msg = str(e)
        if "pending queue full" in msg:
            raise _error("notify.queue_full", msg, status_code=409)
        raise _error("notify.invalid", msg)

    await _audit(
        "notify.pushed",
        user_id=req.actor_user_id,
        detail={
            "id": result["id"],
            "category": req.category,
            "immediate": result["immediate"],
            "delivered": result["delivered"],
        },
    )
    return result


@router.get("/pending/{category}")
async def get_pending(category: str) -> dict[str, Any]:
    _validate_category(category)
    items = cp.get_store().get_pending(category)
    return {
        "category": category,
        "count": len(items),
        "items": [i.to_dict() for i in items],
    }


@router.post("/digest/flush/{category}")
async def flush_one(category: str, body: FlushRequest) -> dict[str, Any]:
    _validate_category(category)
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("notify.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    result = await cp.flush_digest(category)
    await _audit(
        "notify.digest.flushed",
        user_id=body.actor_user_id,
        detail={
            "category": category,
            "flushed": result["flushed"],
            "delivered": result["delivered"],
        },
    )
    return result


@router.post("/digest/flush-all")
async def flush_all(body: FlushRequest) -> dict[str, Any]:
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("notify.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    result = await cp.flush_all_digests()
    await _audit(
        "notify.digest.flush_all",
        user_id=body.actor_user_id,
        detail={"flushed": result["flushed"]},
    )
    return result


@router.post("/configure")
async def configure(req: ConfigureRequest) -> dict[str, Any]:
    _validate_category(req.category)
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("notify.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if req.channel is not None and not req.channel.strip():
        raise _error("notify.invalid_channel",
                     "channel must not be empty when provided")
    try:
        cfg = cp.get_store().configure(
            req.category,
            channel=req.channel,
            digest_window_seconds=req.digest_window_seconds,
        )
    except cp.CategoryPushError as e:
        raise _error("notify.invalid_config", str(e))
    await _audit(
        "notify.configured",
        user_id=req.actor_user_id,
        detail={
            "category": req.category,
            "channel": cfg.channel,
            "digest_window_seconds": cfg.digest_window_seconds,
        },
    )
    return {
        "category": cfg.category,
        "channel": cfg.channel,
        "digest_window_seconds": cfg.digest_window_seconds,
    }
