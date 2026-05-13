"""T-AI-08: Anthropic 障害時 LiteLLM フォールバック (Claude → GPT-4o / Gemini).

CLAUDE.md §3 必須 8 項目 #8。 ADR-010 で「メイン経路 = claude-agent-sdk +
anthropic-python」と決めた上で、 Anthropic が完全停止した時のみ LiteLLM
経由で GPT-4o / Gemini に逃がす非常用経路。

## AC マッピング

- EVENT-1 (degrade): Anthropic health-check 3 回 fail / 60s → GPT-4o + notify
- STATE   (degraded): fallback 中は Memory API writes / Subagent 無効 + sessions.degraded_mode=true
- EVENT-2 (recover): Anthropic 3 連続 success / 5 min → claude-agent-sdk に戻す
- OPTIONAL (manual): /admin/fallback {provider:gemini} で Gemini 2.5 Pro
- UNWANTED (both fail): Anthropic + OpenAI 両方 fail → pause + read-only + Slack alert

## ADR-012 / T-AI-MEM-04 / T-M12-01 cross-ref

本 module は **provider 切替経路の中核 health-check / failover layer** で,
ADR-012 Decision 5 (provider_adapter_memory) と T-M12-01 (litellm_router) を
以下のように連携する:

  fallback_router.current_route()  ←─ provider_adapter_memory.resolve_active_provider
                                        の "anthropic_healthy" 入力 source
  fallback_router.is_degraded()    ←─ litellm_router.emergency_chat の起動条件
  fallback_router.manual_override() ←─ POST /api/provider/active (T-AI-MEM-04) と
                                        ADR-012 5.2 precedence で連携

## 状態モデル

  Route:
    "anthropic"  ← 正常 (default)
    "openai"     ← fallback (LiteLLM → GPT-4o)
    "gemini"     ← manual override / 次フォールバック
    "paused"    ← 両方失敗、 emergency read-only

## 公開 API

  record_health_check(provider, success) -> None
  current_route() -> str
  is_degraded() -> bool
  should_pause() -> bool
  manual_override(provider: str | None) -> None  # None で auto に戻す
  get_state() -> dict
  reset_state() -> None   # test only
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# AC-EVENT-1: 60 秒窓で 3 回失敗 → fallback
FAILURE_WINDOW_SEC = 60
FAILURE_THRESHOLD = 3

# AC-EVENT-2: 5 分窓で 3 連続成功 → 復帰
RECOVERY_WINDOW_SEC = 300
RECOVERY_SUCCESS_STREAK = 3

# 許可される provider
ALLOWED_PROVIDERS = ("anthropic", "openai", "gemini")
VALID_OVERRIDE_PROVIDERS = ("openai", "gemini")


@dataclass
class _ProviderState:
    """1 provider の health history."""
    # (timestamp, success) のタプルを保持
    history: deque = field(default_factory=lambda: deque(maxlen=50))

    def record(self, success: bool) -> None:
        self.history.append((time.monotonic(), success))

    def failures_in_window(self, window_sec: float) -> int:
        now = time.monotonic()
        return sum(1 for t, ok in self.history if (now - t) <= window_sec and not ok)

    def consecutive_successes(self) -> int:
        """末尾から連続 success の数."""
        count = 0
        for _, ok in reversed(self.history):
            if ok:
                count += 1
            else:
                break
        return count

    def last_success_at(self) -> Optional[float]:
        for t, ok in reversed(self.history):
            if ok:
                return t
        return None


@dataclass
class FallbackState:
    """global fallback router 状態."""
    anthropic: _ProviderState = field(default_factory=_ProviderState)
    openai: _ProviderState = field(default_factory=_ProviderState)
    gemini: _ProviderState = field(default_factory=_ProviderState)
    manual_override_provider: Optional[str] = None
    notified_degraded_at: Optional[float] = None
    notified_paused_at: Optional[float] = None

    def get_provider(self, name: str) -> _ProviderState:
        if name == "anthropic": return self.anthropic
        if name == "openai":    return self.openai
        if name == "gemini":    return self.gemini
        raise ValueError(f"unknown provider: {name}")


_state = FallbackState()
_lock = asyncio.Lock()


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────


async def record_health_check(provider: str, success: bool) -> None:
    """health-check の結果を記録し、 必要なら fallback / 復旧を判定."""
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(f"provider must be one of {ALLOWED_PROVIDERS}")
    async with _lock:
        _state.get_provider(provider).record(success)

    # 副作用 (audit emit) は lock の外で
    if not success and _state.get_provider(provider).failures_in_window(FAILURE_WINDOW_SEC) >= FAILURE_THRESHOLD:
        # 既に notify 済みなら多重発火しない (60s 以内の連続失敗で 1 回だけ)
        now = time.monotonic()
        if _state.notified_degraded_at is None or (now - _state.notified_degraded_at) > 60:
            _state.notified_degraded_at = now
            await _notify("anthropic_fallback_engaged", {
                "trigger_provider": provider,
                "failure_count_60s": _state.get_provider(provider).failures_in_window(FAILURE_WINDOW_SEC),
                "new_route": current_route(),
            })

    # 両方 fail なら pause 通知
    if should_pause():
        now = time.monotonic()
        if _state.notified_paused_at is None or (now - _state.notified_paused_at) > 60:
            _state.notified_paused_at = now
            await _notify("fallback_paused_both_down", {
                "anthropic_failures": _state.anthropic.failures_in_window(FAILURE_WINDOW_SEC),
                "openai_failures": _state.openai.failures_in_window(FAILURE_WINDOW_SEC),
            })

    # Anthropic 復旧 (3 連続成功) → notify
    if (
        provider == "anthropic"
        and success
        and _state.anthropic.consecutive_successes() >= RECOVERY_SUCCESS_STREAK
        and _state.notified_degraded_at is not None
    ):
        _state.notified_degraded_at = None  # 復旧 → reset
        await _notify("anthropic_recovered", {"streak": _state.anthropic.consecutive_successes()})


def current_route() -> str:
    """現在のルートを返す.

    優先順位:
      1. should_pause (Anthropic + OpenAI 両方 fail) → 'paused'
      2. manual_override_provider が set → そのまま
      3. Anthropic が degraded (60s 内 3 回 fail) → 'openai'
      4. それ以外 → 'anthropic'
    """
    if should_pause():
        return "paused"
    if _state.manual_override_provider:
        return _state.manual_override_provider
    if _state.anthropic.failures_in_window(FAILURE_WINDOW_SEC) >= FAILURE_THRESHOLD:
        return "openai"
    return "anthropic"


def is_degraded() -> bool:
    """fallback mode (Memory API writes / Subagent 無効) 中か."""
    return current_route() != "anthropic"


def should_pause() -> bool:
    """Anthropic + OpenAI 両方が直近 fail 多数 → pause すべきか (AC-UNWANTED)."""
    ant_fail = _state.anthropic.failures_in_window(FAILURE_WINDOW_SEC) >= FAILURE_THRESHOLD
    oa_fail = _state.openai.failures_in_window(FAILURE_WINDOW_SEC) >= FAILURE_THRESHOLD
    return ant_fail and oa_fail


async def manual_override(provider: Optional[str]) -> None:
    """AC-OPTIONAL: /admin/fallback で手動切替.

    provider=None で auto に戻す.
    """
    if provider is not None and provider not in VALID_OVERRIDE_PROVIDERS:
        raise ValueError(
            f"override must be one of {VALID_OVERRIDE_PROVIDERS} or None"
        )
    async with _lock:
        prev = _state.manual_override_provider
        _state.manual_override_provider = provider
    await _notify("fallback_manual_override", {
        "previous": prev,
        "new": provider,
        "route": current_route(),
    })


def get_state() -> dict:
    """現在の fallback 状態 (UI / admin endpoint 用)."""
    return {
        "route": current_route(),
        "is_degraded": is_degraded(),
        "should_pause": should_pause(),
        "manual_override": _state.manual_override_provider,
        "anthropic_failures_60s": _state.anthropic.failures_in_window(FAILURE_WINDOW_SEC),
        "openai_failures_60s": _state.openai.failures_in_window(FAILURE_WINDOW_SEC),
        "gemini_failures_60s": _state.gemini.failures_in_window(FAILURE_WINDOW_SEC),
        "anthropic_consecutive_successes": _state.anthropic.consecutive_successes(),
    }


def reset_state() -> None:
    """test 用: 状態を初期化."""
    global _state
    _state = FallbackState()


# ──────────────────────────────────────────────────────────────────────────
# Provider-aware capabilities (AC-STATE)
# ──────────────────────────────────────────────────────────────────────────


def memory_api_writes_enabled() -> bool:
    """AC-STATE: fallback 中は Memory API write 無効."""
    return not is_degraded()


def subagent_enabled() -> bool:
    """AC-STATE: fallback 中は Subagent (Task tool) 無効."""
    return not is_degraded()


def session_degraded_mode_flag() -> bool:
    """sessions.degraded_mode に書く値 (AC-STATE)."""
    return is_degraded()


# ──────────────────────────────────────────────────────────────────────────
# Internal
# ──────────────────────────────────────────────────────────────────────────


async def _notify(event_type: str, detail: dict) -> None:
    """audit_logs + Slack 通知 (best effort)."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, detail=detail)
    except Exception as e:
        logger.warning("fallback audit failed: %s", e)

    # Slack 通知 (env SLACK_WEBHOOK_URL がある時のみ、 失敗は吸収)
    if event_type in ("anthropic_fallback_engaged", "fallback_paused_both_down"):
        try:
            await _notify_slack(event_type, detail)
        except Exception as e:
            logger.warning("slack notify failed: %s", e)


async def _notify_slack(event_type: str, detail: dict) -> None:
    if not os.environ.get("SLACK_WEBHOOK_URL"):
        return
    try:
        from services.slack_client import send_message
    except Exception:
        return
    await send_message(text=f"[{event_type}] {detail}")
