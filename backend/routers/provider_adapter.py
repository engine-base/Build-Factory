"""T-020-03 / F-020: provider adapter 3 個 (Anthropic/OpenAI/Gemini) REST endpoint.

Endpoint:
  GET  /api/providers                          supported provider list
  GET  /api/providers/{provider}/models        known models
  POST /api/providers/cost-estimate            cost USD 推定
  POST /api/providers/compose                  request payload を組み立て (実呼び出しなし)
  POST /api/providers/validate                 messages の事前 validation

AC マッピング:
  AC-1 UBIQUITOUS    : F-020 で 3 provider 統一 adapter + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 anthropic_retry / litellm_router / fallback_router /
                       cost_service の API は不変 (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import provider_adapter as pa

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["provider-adapter"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("provider-adapter audit emit failed: %s -- %s", event_type, e)


class CostEstimateRequest(BaseModel):
    provider: str
    model: str
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    cache_read_tokens: int = Field(0, ge=0)


class Message(BaseModel):
    role: str
    content: str


class ComposeRequest(BaseModel):
    provider: str
    model: str
    messages: list[dict]
    max_tokens: int = Field(4096, gt=0)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    cache_control: bool = False
    actor_user_id: Optional[str] = None


class ValidateRequest(BaseModel):
    provider: str
    model: str
    messages: list[dict]
    max_tokens: int = Field(4096, gt=0)


@router.get("")
async def list_providers() -> dict[str, Any]:
    return {
        "providers": list(pa.SUPPORTED_PROVIDERS),
        "main_route": list(pa.MAIN_ROUTE_PROVIDERS),
        "sub_route": list(pa.SUB_ROUTE_PROVIDERS),
    }


@router.get("/{provider}/models")
async def list_models(provider: str) -> dict[str, Any]:
    if provider not in pa.SUPPORTED_PROVIDERS:
        raise _error(
            "provider.invalid_provider",
            f"provider must be one of {pa.SUPPORTED_PROVIDERS}",
        )
    return {
        "provider": provider,
        "models": list(pa.KNOWN_MODELS.get(provider, ())),
    }


@router.post("/cost-estimate")
async def cost_estimate(req: CostEstimateRequest) -> dict[str, Any]:
    if req.provider not in pa.SUPPORTED_PROVIDERS:
        raise _error(
            "provider.invalid_provider",
            f"provider must be one of {pa.SUPPORTED_PROVIDERS}",
        )
    if not req.model or not req.model.strip():
        raise _error("provider.invalid_model", "model must not be empty")
    if req.cache_read_tokens > req.input_tokens:
        raise _error(
            "provider.invalid_cache_read",
            "cache_read_tokens must be <= input_tokens",
        )
    try:
        usd = pa.estimate_cost_usd(
            req.provider, req.model,
            req.input_tokens, req.output_tokens,
            cache_read_tokens=req.cache_read_tokens,
        )
    except pa.ProviderAdapterError as e:
        raise _error("provider.invalid", str(e))
    return {
        "provider": req.provider,
        "model": req.model,
        "input_tokens": req.input_tokens,
        "output_tokens": req.output_tokens,
        "cache_read_tokens": req.cache_read_tokens,
        "cost_usd": usd,
        "is_known_model": pa.is_known_model(req.provider, req.model),
    }


@router.post("/compose")
async def compose(req: ComposeRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("provider.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        result = pa.compose_request(
            req.provider, req.model, req.messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            cache_control=req.cache_control,
        )
    except pa.ProviderAdapterError as e:
        raise _error("provider.invalid", str(e))
    await _audit(
        "provider.compose",
        user_id=req.actor_user_id,
        detail={
            "provider": req.provider,
            "model": req.model,
            "route": result["route"],
            "messages_count": len(req.messages),
        },
    )
    return result


@router.post("/validate")
async def validate(req: ValidateRequest) -> dict[str, Any]:
    try:
        pa.validate_request(
            req.provider, req.model, req.messages,
            max_tokens=req.max_tokens,
        )
    except pa.ProviderAdapterError as e:
        raise _error("provider.invalid", str(e))
    return {"valid": True, "provider": req.provider, "model": req.model}
