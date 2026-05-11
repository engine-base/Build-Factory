"""T-020-04 / F-020: BYOK (Bring-Your-Own-Key) + Anthropic prompt cache REST endpoint.

Endpoint:
  POST   /api/byok/keys                       set / update per-user/provider key
  GET    /api/byok/keys                       list (masked preview のみ)
  DELETE /api/byok/keys/{provider}            delete
  POST   /api/byok/prompt-cache/compose       Anthropic cached payload を組み立て

AC マッピング:
  AC-1 UBIQUITOUS    : F-020 BYOK + prompt cache (cache_control: ephemeral)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 provider_adapter / cost_service / encrypted_credentials
                       schema は不変 + audit emit (byok.key.set/deleted)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       平文 API key は API response に含めない /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import byok_store as bs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/byok", tags=["byok"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("byok audit emit failed: %s -- %s", event_type, e)


class SetKeyRequest(BaseModel):
    user_id: str
    provider: str
    api_key: str
    actor_user_id: Optional[str] = None
    detail: dict = Field(default_factory=dict)


class CachedComposeRequest(BaseModel):
    model: str
    messages: list[dict]
    max_tokens: int = Field(4096, gt=0)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    system_cache: bool = True
    message_cache_indices: Optional[list[int]] = None
    actor_user_id: Optional[str] = None


@router.post("/keys")
async def set_key(req: SetKeyRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("byok.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        rec = bs.get_store().set_key(
            req.user_id, req.provider, req.api_key,
            detail=req.detail or {},
        )
    except bs.BYOKError as e:
        msg = str(e)
        if "max keys" in msg:
            raise _error("byok.quota_exceeded", msg, status_code=409)
        raise _error("byok.invalid", msg)
    await _audit(
        "byok.key.set",
        user_id=req.actor_user_id or req.user_id,
        detail={
            "user_id": req.user_id,
            "provider": req.provider,
            "key_version": rec.key_version,
        },
    )
    # 平文を返さない
    return rec.to_dict()


@router.get("/keys")
async def list_keys(user_id: str = Query(...)) -> dict[str, Any]:
    if not user_id or not user_id.strip():
        raise _error("byok.invalid_user_id", "user_id must not be empty")
    try:
        records = bs.get_store().list_for_user(user_id)
    except bs.BYOKError as e:
        raise _error("byok.invalid", str(e))
    return {
        "user_id": user_id,
        "count": len(records),
        "keys": [r.to_dict() for r in records],
    }


@router.delete("/keys/{provider}")
async def delete_key(
    provider: str,
    user_id: str = Query(...),
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    if not user_id or not user_id.strip():
        raise _error("byok.invalid_user_id", "user_id must not be empty")
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error("byok.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        ok = bs.get_store().delete_key(user_id, provider)
    except bs.BYOKError as e:
        raise _error("byok.invalid", str(e))
    if not ok:
        raise _error("byok.not_found",
                     f"key not found for user={user_id}, provider={provider}",
                     status_code=404)
    await _audit(
        "byok.key.deleted",
        user_id=actor_user_id or user_id,
        detail={"user_id": user_id, "provider": provider},
    )
    return {"deleted": True, "user_id": user_id, "provider": provider}


@router.post("/prompt-cache/compose")
async def cached_compose(req: CachedComposeRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("byok.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        payload = bs.build_anthropic_cached_payload(
            req.model,
            req.messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            system_cache=req.system_cache,
            message_cache_indices=req.message_cache_indices,
        )
    except bs.BYOKError as e:
        raise _error("byok.invalid", str(e))
    return {
        "provider": "anthropic",
        "route": "main",
        "payload": payload,
    }
