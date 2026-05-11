"""T-020-03: provider adapter 3 個 (Anthropic / OpenAI / Gemini) 統一 interface.

3 つの LLM provider に対する共通インターフェース.

- Anthropic はメイン経路 (anthropic-python via anthropic_retry + claude-agent-sdk)
- OpenAI / Gemini はサブ経路 (litellm_router 経由)
- ADR-010 準拠: claude-runner 内では litellm を import しない

公開 API:
  - SUPPORTED_PROVIDERS = ('anthropic', 'openai', 'gemini')
  - normalize_model(provider, model) -> str
  - estimate_cost_usd(provider, model, input_tokens, output_tokens, cache_read=0) -> float
  - select_provider(active_route) -> str  (fallback_router 連携)
  - compose_request(provider, model, messages, *, max_tokens) -> dict
  - validate_request(provider, model, messages) -> None
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class ProviderAdapterError(RuntimeError):
    pass


SUPPORTED_PROVIDERS = ("anthropic", "openai", "gemini")

# サブ経路 (fallback / batch / image / speech 用) として LiteLLM 経由で行く provider
SUB_ROUTE_PROVIDERS = frozenset({"openai", "gemini"})
# メイン経路は Anthropic のみ
MAIN_ROUTE_PROVIDERS = frozenset({"anthropic"})

# 各 provider の代表モデル (validation 用、 完全リストではない)
KNOWN_MODELS: dict[str, tuple[str, ...]] = {
    "anthropic": (
        "claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
        "claude-sonnet-4-5", "claude-opus-4-5",
    ),
    "openai": ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo"),
    "gemini": ("gemini-2.5-pro", "gemini-2.0-flash-exp", "imagen-3.0"),
}

# USD / 1M tokens (input, output) — 公開価格に基づく概算
PRICING_PER_1M: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-opus-4-7":         (15.00, 75.00),
        "claude-sonnet-4-6":       (3.00, 15.00),
        "claude-haiku-4-5-20251001": (1.00, 5.00),
        "claude-sonnet-4-5":       (3.00, 15.00),
        "claude-opus-4-5":         (15.00, 75.00),
    },
    "openai": {
        "gpt-4o":                  (5.00, 15.00),
        "gpt-4o-mini":             (0.15, 0.60),
        "gpt-4-turbo":             (10.00, 30.00),
    },
    "gemini": {
        "gemini-2.5-pro":          (1.25, 10.00),
        "gemini-2.0-flash-exp":    (0.075, 0.30),
        "imagen-3.0":              (0.0, 0.0),  # image generation 別単価
    },
}

# Anthropic prompt cache の input 割引
ANTHROPIC_CACHE_READ_DISCOUNT = 0.1   # cache hit 時は input price の 10% のみ課金

MAX_MESSAGES = 200
MAX_MESSAGE_CHARS = 50_000
MAX_TOKENS_LIMIT = 200_000


def normalize_model(provider: str, model: str) -> str:
    """provider / model の組み合わせを正規化. invalid は raise."""
    if not isinstance(provider, str) or provider not in SUPPORTED_PROVIDERS:
        raise ProviderAdapterError(
            f"provider must be one of {SUPPORTED_PROVIDERS}, got {provider!r}"
        )
    if not isinstance(model, str) or not model.strip():
        raise ProviderAdapterError("model must not be empty")
    m = model.strip()
    if len(m) > 200:
        raise ProviderAdapterError("model must be <= 200 chars")
    return m


def is_known_model(provider: str, model: str) -> bool:
    if provider not in SUPPORTED_PROVIDERS:
        return False
    return model in KNOWN_MODELS.get(provider, ())


def estimate_cost_usd(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
) -> float:
    """USD 単位の推定コスト. unknown model は 0 を返す."""
    if not isinstance(input_tokens, int) or input_tokens < 0:
        raise ProviderAdapterError("input_tokens must be >= 0")
    if not isinstance(output_tokens, int) or output_tokens < 0:
        raise ProviderAdapterError("output_tokens must be >= 0")
    if not isinstance(cache_read_tokens, int) or cache_read_tokens < 0:
        raise ProviderAdapterError("cache_read_tokens must be >= 0")
    if cache_read_tokens > input_tokens:
        raise ProviderAdapterError(
            "cache_read_tokens must be <= input_tokens"
        )

    pricing = PRICING_PER_1M.get(provider, {}).get(model)
    if pricing is None:
        return 0.0
    input_price, output_price = pricing

    # Anthropic prompt cache の input 割引
    if provider == "anthropic" and cache_read_tokens > 0:
        full_input = input_tokens - cache_read_tokens
        cost_input = (
            full_input * input_price / 1_000_000
            + cache_read_tokens * input_price * ANTHROPIC_CACHE_READ_DISCOUNT / 1_000_000
        )
    else:
        cost_input = input_tokens * input_price / 1_000_000
    cost_output = output_tokens * output_price / 1_000_000
    return round(cost_input + cost_output, 6)


def select_provider(active_route: str) -> str:
    """fallback_router.current_route() の戻り値から provider を選ぶ."""
    if not isinstance(active_route, str) or active_route not in SUPPORTED_PROVIDERS:
        raise ProviderAdapterError(
            f"active_route must be one of {SUPPORTED_PROVIDERS}, got {active_route!r}"
        )
    return active_route


def validate_request(
    provider: str,
    model: str,
    messages: list[dict],
    *,
    max_tokens: int = 4096,
) -> None:
    """request payload の妥当性 (provider / model / messages / max_tokens)."""
    normalize_model(provider, model)
    if not isinstance(messages, list) or not messages:
        raise ProviderAdapterError("messages must be a non-empty list")
    if len(messages) > MAX_MESSAGES:
        raise ProviderAdapterError(f"messages must be <= {MAX_MESSAGES}")
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            raise ProviderAdapterError(f"messages[{i}] must be a dict")
        role = m.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            raise ProviderAdapterError(
                f"messages[{i}].role must be one of system/user/assistant/tool"
            )
        content = m.get("content")
        if not isinstance(content, str):
            raise ProviderAdapterError(
                f"messages[{i}].content must be a string"
            )
        if len(content) > MAX_MESSAGE_CHARS:
            raise ProviderAdapterError(
                f"messages[{i}].content must be <= {MAX_MESSAGE_CHARS} chars"
            )
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ProviderAdapterError("max_tokens must be > 0")
    if max_tokens > MAX_TOKENS_LIMIT:
        raise ProviderAdapterError(
            f"max_tokens must be <= {MAX_TOKENS_LIMIT}"
        )


def compose_request(
    provider: str,
    model: str,
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    cache_control: bool = False,
) -> dict:
    """provider 固有 payload を作る. SDK 呼び出しは呼び出し側責任 (これは payload 生成のみ)."""
    validate_request(provider, model, messages, max_tokens=max_tokens)
    if not isinstance(temperature, (int, float)) or not (0.0 <= temperature <= 2.0):
        raise ProviderAdapterError("temperature must be 0.0..2.0")
    if provider == "anthropic":
        # メイン経路: anthropic-python の messages.create() payload
        sys_msgs = [m["content"] for m in messages if m["role"] == "system"]
        user_msgs = [m for m in messages if m["role"] != "system"]
        payload: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_msgs,
        }
        if sys_msgs:
            if cache_control:
                payload["system"] = [
                    {"type": "text", "text": "\n\n".join(sys_msgs),
                     "cache_control": {"type": "ephemeral"}}
                ]
            else:
                payload["system"] = "\n\n".join(sys_msgs)
        return {
            "provider": "anthropic",
            "route": "main",
            "payload": payload,
        }

    # OpenAI / Gemini → LiteLLM の completion 形式
    return {
        "provider": provider,
        "route": "sub",
        "payload": {
            "model": f"{provider}/{model}" if provider == "gemini" else model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
    }
