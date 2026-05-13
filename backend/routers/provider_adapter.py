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


# ──────────────────────────────────────────────────────────────────────
# T-AI-MEM-04 (ADR-012 Decision 5): provider 任意切替 + 障害時 fallback
# ──────────────────────────────────────────────────────────────────────


from fastapi import Header, Request  # noqa: E402

from services import provider_adapter_memory as pam  # noqa: E402


def _map_pam_error(e: pam.ProviderAdapterMemoryError) -> HTTPException:
    msg = str(e)
    if "no provider available" in msg:
        return _error("provider.unavailable", msg, status_code=503)
    return _error("provider.invalid", msg, status_code=400)


@router.get("/active")
async def get_active_provider(
    request: Request,
    x_llm_provider: Optional[str] = Header(None, alias="X-LLM-Provider"),
) -> dict[str, Any]:
    """resolve_active_provider の現在値を返す.

    Query / Header:
      X-LLM-Provider           per-request override
      session_active_route     per-session (query string)
      workspace_preferred      per-workspace (query string)
      user_id                  byok lookup key (query string)
    """
    q = request.query_params
    user_id = q.get("user_id")
    # policy_allow は明示的に query で渡された時のみ tuple 化. 未指定なら None
    # (= 全 provider 許可) を渡して全 provider blocked を避ける.
    policy_keys = (
        q.getlist("policy_allow")
        if hasattr(q, "getlist") and "policy_allow" in q
        else None
    )
    try:
        result = pam.resolve_active_provider(
            header_provider=x_llm_provider,
            session_active_route=q.get("session_active_route"),
            workspace_preferred=q.get("workspace_preferred"),
            user_id=user_id,
            anthropic_healthy=q.get("anthropic_healthy", "true").lower() != "false",
            policy_allow=policy_keys,
        )
    except pam.ProviderAdapterMemoryError as e:
        raise _map_pam_error(e)
    # GET = read endpoint なので audit emit しない (ADR-012 Decision 2 等の精神)
    return result


@router.get("/active/tool-spec")
async def get_tool_spec_for_active(
    request: Request,
    x_llm_provider: Optional[str] = Header(None, alias="X-LLM-Provider"),
) -> dict[str, Any]:
    """active provider の Memory Tool tool_spec を返す (provider 非依存 caller 向け)."""
    q = request.query_params
    try:
        resolved = pam.resolve_active_provider(
            header_provider=x_llm_provider,
            session_active_route=q.get("session_active_route"),
            workspace_preferred=q.get("workspace_preferred"),
            user_id=q.get("user_id"),
        )
        spec = pam.tool_spec_for(resolved["provider"])
        cm = pam.context_editing_for(resolved["provider"])
    except pam.ProviderAdapterMemoryError as e:
        raise _map_pam_error(e)
    return {
        "provider": resolved["provider"],
        "reason": resolved["reason"],
        "tool_spec": spec,
        "context_editing": cm,
    }


class SwitchProviderRequest(BaseModel):
    to_provider: str
    from_provider: Optional[str] = None
    scope: str = "per-session"  # per-session / per-workspace / per-request
    reason: str = "manual"
    actor_user_id: Optional[str] = None
    detail: Optional[dict] = None


@router.post("/active")
async def switch_active_provider(req: SwitchProviderRequest) -> dict[str, Any]:
    """AC-2: 任意切替 (manual). audit 'provider.switched' emit.

    AC-4: unsupported provider / unknown reason は 4xx state mutate なし.
    """
    if req.scope not in ("per-session", "per-workspace", "per-request"):
        raise _error("provider.invalid", f"scope must be per-session / per-workspace / per-request, got {req.scope!r}")
    if req.reason not in pam.VALID_SWITCH_REASONS:
        raise _error(
            "provider.invalid",
            f"reason must be one of {pam.VALID_SWITCH_REASONS}, got {req.reason!r}",
        )
    try:
        pam._validate_provider(req.to_provider, field="to_provider")
        if req.from_provider:
            pam._validate_provider(req.from_provider, field="from_provider")
    except pam.ProviderAdapterMemoryError as e:
        raise _map_pam_error(e)
    audit_id = await pam.emit_switch_audit(
        from_provider=req.from_provider,
        to_provider=req.to_provider,
        reason=req.reason,
        scope=req.scope,
        actor_user_id=req.actor_user_id,
        extra_detail=req.detail,
    )
    return {
        "to_provider": req.to_provider,
        "from_provider": req.from_provider,
        "scope": req.scope,
        "reason": req.reason,
        "audit_event_id": audit_id,
        "audit_event_type": pam.audit_event_for_switch(req.reason),
    }


class FallbackTriggerRequest(BaseModel):
    from_provider: str = "anthropic"
    to_provider: str
    reason: str = "circuit_breaker"
    actor_user_id: Optional[str] = "system"
    detail: Optional[dict] = None


@router.post("/fallback/trigger")
async def trigger_provider_fallback(req: FallbackTriggerRequest) -> dict[str, Any]:
    """T-AI-08 circuit-breaker / policy_blocked / byok_missing 発火時の自動 fallback.

    audit 'provider.fallback' emit (silent pick 禁止 = AC-4).
    """
    if req.reason not in pam.VALID_FALLBACK_REASONS:
        raise _error(
            "provider.invalid",
            f"reason must be one of {pam.VALID_FALLBACK_REASONS}, got {req.reason!r}",
        )
    try:
        pam._validate_provider(req.from_provider, field="from_provider")
        pam._validate_provider(req.to_provider, field="to_provider")
    except pam.ProviderAdapterMemoryError as e:
        raise _map_pam_error(e)
    audit_id = await pam.emit_switch_audit(
        from_provider=req.from_provider,
        to_provider=req.to_provider,
        reason=req.reason,
        scope="per-request",
        actor_user_id=req.actor_user_id,
        extra_detail=req.detail,
    )
    return {
        "from_provider": req.from_provider,
        "to_provider": req.to_provider,
        "reason": req.reason,
        "audit_event_id": audit_id,
        "audit_event_type": pam.audit_event_for_switch(req.reason),
    }


@router.get("/capabilities/{provider}")
async def get_provider_capabilities(provider: str) -> dict[str, Any]:
    """provider ごとの capability matrix (memory tool native / native compaction
    等). degrade 経路の判定用."""
    try:
        pam._validate_provider(provider)
    except pam.ProviderAdapterMemoryError as e:
        raise _map_pam_error(e)
    return {
        "provider": provider,
        "capabilities": pam.CAPABILITIES.get(provider, {}),
        "context_editing": pam.context_editing_for(provider),
    }
