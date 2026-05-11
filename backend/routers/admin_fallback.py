"""T-AI-08: /admin/fallback admin endpoint.

  GET  /api/admin/fallback                    現状を返す
  POST /api/admin/fallback                    {provider: openai|gemini|null}
  POST /api/admin/fallback/health              {provider: anthropic|openai|gemini, success: bool}

POST /health は本来 internal worker から叩く想定 (ヘルスチェッカー)。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.fallback_router import (
    VALID_OVERRIDE_PROVIDERS, ALLOWED_PROVIDERS,
    current_route, get_state, manual_override, record_health_check,
)


router = APIRouter(prefix="/api/admin/fallback", tags=["admin-fallback"])


class OverrideRequest(BaseModel):
    provider: Optional[str] = Field(None, description="openai / gemini / null (auto)")


class HealthRequest(BaseModel):
    provider: str
    success: bool


@router.get("")
async def get_fallback_state() -> dict:
    return get_state()


@router.post("")
async def post_fallback_override(req: OverrideRequest) -> dict:
    if req.provider is not None and req.provider not in VALID_OVERRIDE_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {VALID_OVERRIDE_PROVIDERS} or null")
    await manual_override(req.provider)
    return {"ok": True, "route": current_route()}


@router.post("/health")
async def post_health_check(req: HealthRequest) -> dict:
    if req.provider not in ALLOWED_PROVIDERS:
        raise HTTPException(400, f"provider must be one of {ALLOWED_PROVIDERS}")
    await record_health_check(req.provider, req.success)
    return {"ok": True, "route": current_route()}
