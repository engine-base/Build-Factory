"""llm domain — public barrel (T-001-01b AC-2).

責務: Anthropic retry / LiteLLM サブルート / fallback router / constitution.

ADR-010: claude-agent-sdk + anthropic-python がメイン経路.
       LiteLLM はサブ用途 (image/speech/batch/emergency) のみ.
"""
from __future__ import annotations

from services.anthropic_retry import (
    with_retry,
    is_retryable,
    RetryExhaustedError,
)
from services.litellm_router import (
    generate_image,
    transcribe_audio,
    batch_complete,
    emergency_chat,
    LiteLLMRouterError,
    ProviderUnavailable,
    MainEngineRoutingDenied,
)
from services.fallback_router import (
    record_health_check,
    current_route,
    is_degraded,
    should_pause,
    manual_override,
    get_state,
)
from services.constitution_engine import (
    Constitution,
    ConstitutionError,
    CorruptConstitution,
    MissingConstitution,
)

__all__ = [
    "with_retry",
    "is_retryable",
    "RetryExhaustedError",
    "generate_image",
    "transcribe_audio",
    "batch_complete",
    "emergency_chat",
    "LiteLLMRouterError",
    "ProviderUnavailable",
    "MainEngineRoutingDenied",
    "record_health_check",
    "current_route",
    "is_degraded",
    "should_pause",
    "manual_override",
    "get_state",
    "Constitution",
    "ConstitutionError",
    "CorruptConstitution",
    "MissingConstitution",
]
