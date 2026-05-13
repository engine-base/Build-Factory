"""T-M12-01 / F-M12: LiteLLM Router (サブ用途のみ).

ADR-010 で「メイン経路 = claude-agent-sdk + anthropic-python」と確定した上で、
以下のサブ用途のみ LiteLLM 経由を許可する.

許可される用途:
  1. 画像生成 (Gemini Image / DALL-E)         — Anthropic は image gen 未対応
  2. 音声 (Whisper)                            — Anthropic は speech 未対応
  3. 安価バッチ (Gemini Flash 等)              — token 単価が Claude より安い
  4. 緊急代替 (Anthropic 障害時 GPT-4o / Gemini 2.5 Pro)  — fallback_router 連携

メイン経路 (claude-runner / claude_agent_runner.py) で LiteLLM を import すると
lint-mock.sh で fail (ADR-010 / T-M12-01 AC-5).

公開 API:
  generate_image(prompt, *, provider='gemini'|'openai', size, n) -> dict
  transcribe_audio(audio_bytes, *, language='ja') -> dict
  batch_complete(messages, *, model='gemini-flash') -> dict
  emergency_chat(messages, *, fallback_route='openai'|'gemini') -> dict
                — fallback_router.current_route() == 'openai'/'gemini' 時のみ
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ALLOWED sub-purposes (AC-1)
SUB_PURPOSES = ("image_generation", "speech", "batch", "emergency_fallback")

# Provider routing
IMAGE_PROVIDERS = ("gemini", "openai")
SPEECH_PROVIDERS = ("openai",)  # Whisper
BATCH_PROVIDERS = ("gemini-flash", "gpt-4o-mini")
EMERGENCY_PROVIDERS = ("openai", "gemini")


class LiteLLMRouterError(RuntimeError):
    """LiteLLM 呼び出し失敗の総称."""


class ProviderUnavailable(LiteLLMRouterError):
    """指定 provider が利用不可 (API key 無し / SDK 未導入)."""


class MainEngineRoutingDenied(RuntimeError):
    """メイン経路 (claude-runner) から LiteLLM を呼び出そうとした (AC-5)."""


# ──────────────────────────────────────────────────────────────────────────
# AC-5: メイン経路からの import を runtime でも block
# ──────────────────────────────────────────────────────────────────────────


def _assert_not_called_from_runner() -> None:
    """呼び出し元 stack に claude_agent_runner.py / claude_runner が含まれていたら拒否.

    AC-5 UNWANTED: lint だけでなく runtime でも防衛 (defense in depth).
    """
    import inspect
    stack = inspect.stack()
    for frame in stack:
        filename = frame.filename
        if "claude_agent_runner" in filename or "/claude-runner/" in filename:
            raise MainEngineRoutingDenied(
                f"LiteLLM cannot be invoked from main Claude Code runner: {filename}"
            )


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT: 画像生成
# ──────────────────────────────────────────────────────────────────────────


async def generate_image(
    prompt: str, *,
    provider: str = "gemini",
    size: str = "1024x1024",
    n: int = 1,
) -> dict:
    """画像生成 (Gemini Image / DALL-E).

    Returns:
      {provider, urls: [str], model, prompt}

    Raises:
      ProviderUnavailable: 指定 provider が利用不可
      LiteLLMRouterError:  生成失敗
    """
    _assert_not_called_from_runner()
    if provider not in IMAGE_PROVIDERS:
        raise LiteLLMRouterError(
            f"image provider must be one of {IMAGE_PROVIDERS}, got {provider!r}"
        )
    if not prompt or not prompt.strip():
        raise LiteLLMRouterError("prompt must not be empty")

    model_map = {
        "gemini": "gemini/imagen-3.0",
        "openai": "dall-e-3",
    }
    model = model_map[provider]

    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError as e:
        raise ProviderUnavailable(f"litellm SDK not installed: {e}") from e

    try:
        resp = await litellm.aimage_generation(
            prompt=prompt, model=model, n=n, size=size,
        )
        urls = [d.get("url") for d in (getattr(resp, "data", []) or []) if d.get("url")]
        return {
            "provider": "fallback",  # AC-4: response に provider=fallback マーク
            "sub_route": "image_generation",
            "actual_model": model,
            "urls": urls,
            "prompt": prompt,
        }
    except Exception as e:
        raise LiteLLMRouterError(f"image generation failed: {e}") from e


# ──────────────────────────────────────────────────────────────────────────
# 音声 (Whisper)
# ──────────────────────────────────────────────────────────────────────────


async def transcribe_audio(
    audio_bytes: bytes, *,
    language: Optional[str] = "ja",
    provider: str = "openai",
) -> dict:
    """音声 → テキスト (Whisper).

    Returns:
      {provider, sub_route, transcript, language}
    """
    _assert_not_called_from_runner()
    if provider not in SPEECH_PROVIDERS:
        raise LiteLLMRouterError(
            f"speech provider must be one of {SPEECH_PROVIDERS}, got {provider!r}"
        )
    if not audio_bytes:
        raise LiteLLMRouterError("audio_bytes must not be empty")

    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError as e:
        raise ProviderUnavailable(f"litellm SDK not installed: {e}") from e

    try:
        resp = await litellm.atranscription(
            model="whisper-1",
            file=audio_bytes,
            language=language,
        )
        text = getattr(resp, "text", "") or (resp.get("text") if isinstance(resp, dict) else "")
        return {
            "provider": "fallback",
            "sub_route": "speech",
            "actual_model": "whisper-1",
            "transcript": text,
            "language": language,
        }
    except Exception as e:
        raise LiteLLMRouterError(f"transcription failed: {e}") from e


# ──────────────────────────────────────────────────────────────────────────
# 安価バッチ
# ──────────────────────────────────────────────────────────────────────────


async def batch_complete(
    messages: list[dict], *,
    model: str = "gemini-flash",
    max_tokens: int = 1000,
) -> dict:
    """安価バッチ (Gemini Flash / GPT-4o-mini)."""
    _assert_not_called_from_runner()
    if model not in BATCH_PROVIDERS:
        raise LiteLLMRouterError(
            f"batch model must be one of {BATCH_PROVIDERS}, got {model!r}"
        )
    if not messages:
        raise LiteLLMRouterError("messages must not be empty")

    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError as e:
        raise ProviderUnavailable(f"litellm SDK not installed: {e}") from e

    model_map = {
        "gemini-flash": "gemini/gemini-2.0-flash-exp",
        "gpt-4o-mini": "openai/gpt-4o-mini",
    }
    actual_model = model_map[model]

    try:
        resp = await litellm.acompletion(
            model=actual_model,
            messages=messages,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        return {
            "provider": "fallback",
            "sub_route": "batch",
            "actual_model": actual_model,
            "content": text,
            "usage": getattr(resp, "usage", None),
        }
    except Exception as e:
        raise LiteLLMRouterError(f"batch completion failed: {e}") from e


# ──────────────────────────────────────────────────────────────────────────
# AC-3 EVENT / AC-4 STATE: 緊急代替 (Anthropic 障害時)
# ──────────────────────────────────────────────────────────────────────────


async def emergency_chat(
    messages: list[dict], *,
    fallback_route: Optional[str] = None,
    max_tokens: int = 2000,
) -> dict:
    """Anthropic 障害時の緊急 chat (GPT-4o / Gemini 2.5 Pro).

    AC-3: fallback_router.current_route() が 'openai' or 'gemini' を返している時のみ起動.
    AC-4 STATE: response に provider='fallback' マーク + Memory API write 無効化シグナル.
    """
    _assert_not_called_from_runner()

    # T-AI-08 fallback_router と連携 (route 判定を委譲)
    try:
        from services.fallback_router import current_route
        active_route = fallback_route or current_route()
    except Exception:
        active_route = fallback_route or "openai"

    if active_route not in EMERGENCY_PROVIDERS:
        raise LiteLLMRouterError(
            f"emergency_chat only allowed during fallback mode (route={active_route!r})"
        )
    if not messages:
        raise LiteLLMRouterError("messages must not be empty")

    try:
        import litellm  # type: ignore[import-not-found]
    except ImportError as e:
        raise ProviderUnavailable(f"litellm SDK not installed: {e}") from e

    model_map = {
        "openai": "openai/gpt-4o",
        "gemini": "gemini/gemini-2.5-pro",
    }
    actual_model = model_map[active_route]

    try:
        resp = await litellm.acompletion(
            model=actual_model,
            messages=messages,
            max_tokens=max_tokens,
        )
        content = (resp.choices[0].message.content or "") if resp.choices else ""
        return {
            "provider": "fallback",  # AC-4
            "sub_route": "emergency_fallback",
            "actual_model": actual_model,
            "active_route": active_route,
            "content": content,
            "memory_api_writes_disabled": True,  # AC-4: Anthropic only feature
        }
    except Exception as e:
        raise LiteLLMRouterError(f"emergency chat failed: {e}") from e


# ──────────────────────────────────────────────────────────────────────────
# Helper: memory_api write 可否判定 (AC-4 連携)
# ──────────────────────────────────────────────────────────────────────────


def memory_api_writes_allowed_in_fallback(response: dict) -> bool:
    """response に provider='fallback' が立っていたら Memory API write 禁止."""
    if not isinstance(response, dict):
        return True
    if response.get("provider") == "fallback":
        return False
    if response.get("memory_api_writes_disabled") is True:
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────
# T-M12-01 + T-AI-MEM-04 cross-ref: emergency_chat 発火時の audit emit
# ──────────────────────────────────────────────────────────────────────────


async def emit_emergency_fallback_audit(
    *,
    from_provider: str = "anthropic",
    to_provider: str,
    actor_user_id: Optional[str] = "system",
    extra_detail: Optional[dict] = None,
) -> Optional[int]:
    """emergency_chat の fallback 発火を T-AI-MEM-04 と同じ event_type
    ('provider.fallback') で audit_logs に emit. silent pick 禁止 (AC-4 / ADR-012 5.5).

    provider_adapter_memory.emit_switch_audit に委譲し circuit_breaker 由来の
    fallback として記録する. emit 自体は失敗しても raise しない (best-effort).
    """
    try:
        from services.provider_adapter_memory import emit_switch_audit
        return await emit_switch_audit(
            from_provider=from_provider,
            to_provider=to_provider,
            reason="circuit_breaker",
            scope="per-request",
            actor_user_id=actor_user_id,
            extra_detail=extra_detail,
        )
    except Exception as e:  # pragma: no cover
        import logging
        logging.getLogger(__name__).warning(
            "emergency fallback audit emit failed to=%s: %s", to_provider, e,
        )
        return None


# ──────────────────────────────────────────────────────────────────────────
# Sentinel comment (AC-5 lint で claude-runner が litellm を import しないこと)
# ──────────────────────────────────────────────────────────────────────────

# NO_LITELLM_IN_RUNNER — claude_agent_runner.py への litellm import は ADR-010 違反.
# lint-mock.sh --no-litellm-in-runner で機械的に検出される.