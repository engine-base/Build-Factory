"""T-M12-01 gap closure — LiteLLM Router (サブ用途のみ) の追補 test (G1-G3).

既存 test_t_m12_01_litellm_router.py (38 件) に対する補完:
  G1 (AC-1/3 連携): T-AI-MEM-04 provider_adapter_memory と litellm_router /
                    fallback_router の整合.
  G2 (AC-3 audit統合): emergency_chat 発火時に provider.fallback (T-AI-MEM-04
                    event_type) を emit する経路の存在保証.
  G3 (AC-3 spec文): FAILURE_WINDOW_SEC = 60 / FAILURE_THRESHOLD = 3 の定数固定
                    (3 consecutive 5xx within 60s).
"""
from __future__ import annotations

import asyncio
import time

import pytest

from services import litellm_router as ll
from services import fallback_router as fb
from services import provider_adapter_memory as pam


# ──────────────────────────────────────────────────────────────────────
# G3: AC-3 spec 文 "3 consecutive 5xx within 60s" の定数固定
# ──────────────────────────────────────────────────────────────────────


def test_g3_failure_threshold_is_3():
    """AC-3 EVENT spec 文を定数で固定: 3 consecutive 5xx を発動条件とする."""
    assert fb.FAILURE_THRESHOLD == 3


def test_g3_failure_window_is_60_seconds():
    """AC-3 EVENT spec 文: within 60 seconds の window."""
    assert fb.FAILURE_WINDOW_SEC == 60


def test_g3_3_consecutive_5xx_in_60s_triggers_fallback():
    """3 連続失敗 within 60s で fallback mode に遷移 (AC-3 EVENT 統合検証)."""
    fb.reset_state()
    assert fb.current_route() == "anthropic"
    # 3 連続失敗 (within 60s)
    for _ in range(3):
        asyncio.run(fb.record_health_check("anthropic", False))
    assert fb.is_degraded() is True
    # current_route が openai or gemini に切替されている
    assert fb.current_route() in ("openai", "gemini")
    fb.reset_state()


def test_g3_2_failures_do_not_trigger_fallback():
    """2 連続失敗では fallback しない (閾値 3 の確認)."""
    fb.reset_state()
    for _ in range(2):
        asyncio.run(fb.record_health_check("anthropic", False))
    assert fb.is_degraded() is False
    assert fb.current_route() == "anthropic"
    fb.reset_state()


# ──────────────────────────────────────────────────────────────────────
# G2: emergency_chat audit が T-AI-MEM-04 と同じ event_type で emit
# ──────────────────────────────────────────────────────────────────────


def test_g2_emit_emergency_fallback_audit_uses_provider_fallback_event(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)

    audit_id = asyncio.run(ll.emit_emergency_fallback_audit(
        from_provider="anthropic", to_provider="openai",
    ))
    assert audit_id == 1
    assert captured[0]["event_type"] == pam.EVENT_PROVIDER_FALLBACK
    detail = captured[0]["detail"]
    assert detail["from"] == "anthropic"
    assert detail["to"] == "openai"
    assert detail["reason"] == "circuit_breaker"
    assert detail["scope"] == "per-request"


def test_g2_emit_emergency_fallback_audit_to_gemini(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event_type": event_type, "detail": detail or {}})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)

    asyncio.run(ll.emit_emergency_fallback_audit(
        from_provider="anthropic", to_provider="gemini",
        actor_user_id="bob",
        extra_detail={"failure_count_60s": 3},
    ))
    detail = captured[0]["detail"]
    assert detail["to"] == "gemini"
    assert detail["failure_count_60s"] == 3


def test_g2_emit_emergency_fallback_audit_invalid_provider_rejected(monkeypatch):
    """provider_adapter_memory.emit_switch_audit に委譲しているので
    unsupported provider は内部で例外を raise → caller には None が返る
    (best-effort, raise しない)."""
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)

    out = asyncio.run(ll.emit_emergency_fallback_audit(
        from_provider="anthropic", to_provider="unknown",
    ))
    assert out is None
    # audit emit されない (silent suppression: best-effort)
    assert captured == []


# ──────────────────────────────────────────────────────────────────────
# G1: T-AI-MEM-04 provider_adapter_memory と fallback_router の整合
# ──────────────────────────────────────────────────────────────────────


def test_g1_pam_resolve_with_anthropic_unhealthy_returns_fallback():
    """provider_adapter_memory.resolve_active_provider(anthropic_healthy=False)
    で fallback 発火し、provider が openai or gemini になる
    (= litellm_router.EMERGENCY_PROVIDERS と一致)."""
    result = pam.resolve_active_provider(anthropic_healthy=False)
    assert result["provider"] in ll.EMERGENCY_PROVIDERS
    assert result["reason"] == "auto-fallback"


def test_g1_pam_emergency_providers_match_litellm():
    """provider_adapter_memory が fallback で選ぶ provider 集合 (anthropic 以外で
    SUPPORTED_PROVIDERS) と litellm_router.EMERGENCY_PROVIDERS が一致."""
    non_anthropic = set(pam.SUPPORTED_PROVIDERS) - {"anthropic"}
    assert set(ll.EMERGENCY_PROVIDERS) == non_anthropic


def test_g1_fallback_router_and_pam_share_provider_namespace():
    """fallback_router.current_route() の戻り値が provider_adapter_memory.
    SUPPORTED_PROVIDERS の subset であること (LiteLLM サブ用途と整合)."""
    fb.reset_state()
    route = fb.current_route()
    assert route in pam.SUPPORTED_PROVIDERS
    # 3 連続失敗後 fallback route も SUPPORTED_PROVIDERS subset
    for _ in range(3):
        asyncio.run(fb.record_health_check("anthropic", False))
    route2 = fb.current_route()
    assert route2 in pam.SUPPORTED_PROVIDERS
    fb.reset_state()


def test_g1_memory_api_writes_disabled_in_emergency_response():
    """emergency_chat 戻り response が memory_api_writes_disabled=True を持つ
    (T-AI-MEM-04 の Memory Tool が provider 非依存だが Anthropic Memory API 直接
    write は disable). litellm_router.memory_api_writes_allowed_in_fallback()
    がそれを正しく検知する."""
    response_fallback = {
        "provider": "fallback",
        "sub_route": "emergency_fallback",
        "memory_api_writes_disabled": True,
        "content": "fallback content",
    }
    assert ll.memory_api_writes_allowed_in_fallback(response_fallback) is False
    response_normal = {
        "provider": "anthropic",
        "content": "normal content",
    }
    assert ll.memory_api_writes_allowed_in_fallback(response_normal) is True


def test_g1_pam_capability_matrix_aligns_with_litellm_emergency():
    """T-AI-MEM-04 CAPABILITIES の native_compaction / extended_thinking が
    anthropic のみ True (litellm 経由 = OpenAI/Gemini では False)."""
    assert pam.CAPABILITIES["anthropic"]["native_compaction"] is True
    assert pam.CAPABILITIES["openai"]["native_compaction"] is False
    assert pam.CAPABILITIES["gemini"]["native_compaction"] is False
    # = emergency_chat 経路では client-side summarizer 必須 (AC-4 STATE)


# ──────────────────────────────────────────────────────────────────────
# Cross-reference: lint check + ADR
# ──────────────────────────────────────────────────────────────────────


def test_check_no_litellm_in_runner_exists():
    from pathlib import Path
    script = (Path(__file__).resolve().parents[2] / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_no_litellm_in_runner" in script
    assert "--no-litellm-in-runner" in script


def test_check_no_litellm_in_runner_passes_on_clean_code():
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-litellm-in-runner"],
        capture_output=True, text=True, timeout=30, cwd=str(repo),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout} {r.stderr}"
    assert "OK" in r.stdout


def test_litellm_router_documents_sub_purposes():
    doc = ll.__doc__ or ""
    # 4 sub-purpose が docstring に明記
    for keyword in ("image", "speech", "batch", "emergency"):
        assert keyword.lower() in doc.lower(), f"litellm_router docstring must mention {keyword}"
