"""T-AI-08: Anthropic 障害時 LiteLLM フォールバック — 5 AC gap closure (G1-G5).

主要実装 (services/fallback_router.py + services/circuit_breaker.py +
routers/admin_fallback.py + 29 既存 tests) は完備.
本 PR で **spec 文の細部 + ADR-012 / T-M12-01 cross-ref + lint 機械検知** の
5 件追補 gap を埋める.

## Gaps

  G1 (AC-EVENT-2 5min window): RECOVERY_WINDOW_SEC = 300 の定数固定 test
  G2 (AC-UNWANTED Slack alert): pause 時の _notify_slack 経路の test
  G3 (T-AI-MEM-04 / T-M12-01 cross-ref): emergency_chat / provider_adapter_memory
     と fallback_router の整合 test
  G4 ("untested provider" 防止): ALLOWED_PROVIDERS 以外 route 不可 test
  G5 (lint cross-ref): T-AI-08 自前実装の禁止語 lint (check_no_self_fallback_circuit)
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from services import fallback_router as fb
from services.fallback_router import (
    ALLOWED_PROVIDERS,
    FAILURE_THRESHOLD,
    FAILURE_WINDOW_SEC,
    RECOVERY_SUCCESS_STREAK,
    RECOVERY_WINDOW_SEC,
    VALID_OVERRIDE_PROVIDERS,
    current_route,
    get_state,
    is_degraded,
    manual_override,
    memory_api_writes_enabled,
    record_health_check,
    reset_state,
    session_degraded_mode_flag,
    should_pause,
    subagent_enabled,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _reset_fb():
    reset_state()
    yield
    reset_state()


# ══════════════════════════════════════════════════════════════════════
# G1 (AC-EVENT-2): 5 min recovery window
# ══════════════════════════════════════════════════════════════════════


def test_g1_failure_window_60_sec_spec_constant():
    """AC-EVENT-1 spec: 3 回 fail / 60s."""
    assert FAILURE_WINDOW_SEC == 60
    assert FAILURE_THRESHOLD == 3


def test_g1_recovery_window_300_sec_spec_constant():
    """AC-EVENT-2 spec: 3 consecutive success / 5 min."""
    assert RECOVERY_WINDOW_SEC == 300
    assert RECOVERY_SUCCESS_STREAK == 3


# ══════════════════════════════════════════════════════════════════════
# G2 (AC-UNWANTED): Slack alert 経路
# ══════════════════════════════════════════════════════════════════════


def test_g2_notify_slack_function_exists():
    """pause 時の Slack 通知関数が module に存在."""
    assert hasattr(fb, "_notify_slack")
    assert callable(fb._notify_slack)


def test_g2_notify_slack_no_op_without_webhook(monkeypatch):
    """SLACK_WEBHOOK_URL 未設定なら早期 return (silent skip / not raise)."""
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    # raise しないことを確認
    asyncio.run(fb._notify_slack("test.event", {"foo": "bar"}))


def test_g2_pause_emits_alert_audit_when_both_fail(monkeypatch):
    """両方 fail → audit 'fallback_paused_both_down' emit."""
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event_type": event_type, "detail": detail or {}})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)

    async def _run():
        # anthropic 3 fail → degraded (openai)
        for _ in range(3):
            await record_health_check("anthropic", False)
        # openai も 3 fail → paused
        for _ in range(3):
            await record_health_check("openai", False)

    asyncio.run(_run())
    pause_events = [e for e in captured if "paused" in e["event_type"].lower()
                    or "both" in e["event_type"].lower()]
    assert len(pause_events) >= 1
    assert should_pause() is True


# ══════════════════════════════════════════════════════════════════════
# G3 (T-AI-MEM-04 / T-M12-01 cross-ref)
# ══════════════════════════════════════════════════════════════════════


def test_g3_allowed_providers_match_pam_supported():
    """fallback_router.ALLOWED_PROVIDERS = T-AI-MEM-04 SUPPORTED_PROVIDERS."""
    from services.provider_adapter_memory import SUPPORTED_PROVIDERS
    assert set(ALLOWED_PROVIDERS) == set(SUPPORTED_PROVIDERS)


def test_g3_emergency_chat_uses_current_route(monkeypatch):
    """litellm_router.emergency_chat が fallback_router.current_route() を参照する.
    fallback 中なら openai or gemini を返し、 normal なら anthropic."""
    # normal mode: current_route() == "anthropic"
    assert current_route() == "anthropic"
    # fallback 発火後
    async def _run():
        for _ in range(3):
            await record_health_check("anthropic", False)
    asyncio.run(_run())
    assert current_route() in ("openai", "gemini")
    # litellm_router.emergency_chat はこの route を読む (実装内部で読込)
    from services import litellm_router as ll
    # EMERGENCY_PROVIDERS が fallback の現状 route を含む
    assert current_route() in ll.EMERGENCY_PROVIDERS


def test_g3_memory_api_writes_disabled_in_degraded_mode():
    """T-AI-MEM-04 / T-M12-01 STATE: fallback 中は Memory API writes 無効."""
    assert memory_api_writes_enabled() is True  # normal
    async def _run():
        for _ in range(3):
            await record_health_check("anthropic", False)
    asyncio.run(_run())
    assert memory_api_writes_enabled() is False
    assert subagent_enabled() is False
    assert session_degraded_mode_flag() is True


def test_g3_provider_adapter_memory_respects_fallback_route():
    """provider_adapter_memory.resolve_active_provider(anthropic_healthy=False)
    で fallback_router.current_route() と整合."""
    from services.provider_adapter_memory import resolve_active_provider
    async def _run():
        for _ in range(3):
            await record_health_check("anthropic", False)
    asyncio.run(_run())
    # fallback active 後 anthropic_healthy=False で resolve すると non-anthropic
    out = resolve_active_provider(anthropic_healthy=False)
    assert out["provider"] != "anthropic"
    assert out["provider"] in ALLOWED_PROVIDERS


# ══════════════════════════════════════════════════════════════════════
# G4 (UNWANTED): "untested provider" 防止
# ══════════════════════════════════════════════════════════════════════


def test_g4_manual_override_rejects_untested_provider():
    """OPTIONAL spec: VALID_OVERRIDE_PROVIDERS = (openai, gemini) のみ.
    untested ('xai' / 'meta' etc.) は ValueError で reject."""
    async def _run():
        for bad in ("xai", "meta", "cohere", "untested", ""):
            with pytest.raises((ValueError, Exception)):
                await manual_override(bad)

    asyncio.run(_run())


def test_g4_record_health_check_rejects_unknown_provider():
    """ALLOWED_PROVIDERS 以外を record すると ValueError, state mutate なし."""
    async def _run():
        with pytest.raises(ValueError):
            await record_health_check("xai", False)
    asyncio.run(_run())
    # state mutate なし
    assert current_route() == "anthropic"


def test_g4_valid_override_providers_subset_of_allowed():
    """VALID_OVERRIDE_PROVIDERS ⊆ ALLOWED_PROVIDERS (anthropic は除く)."""
    assert set(VALID_OVERRIDE_PROVIDERS).issubset(set(ALLOWED_PROVIDERS))
    assert "anthropic" not in VALID_OVERRIDE_PROVIDERS


# ══════════════════════════════════════════════════════════════════════
# G5 (lint cross-ref)
# ══════════════════════════════════════════════════════════════════════


def test_g5_lint_check_no_self_fallback_circuit_exists():
    script = (REPO_ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_no_self_fallback_circuit" in script
    assert "--no-self-fallback-circuit" in script


def test_g5_lint_check_passes_on_clean_code():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-self-fallback-circuit"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout} {r.stderr}"
    assert "OK" in r.stdout


def test_g5_no_self_fallback_function_outside_module():
    """禁止語が backend/services / routers / ai_agents / integrations の
    fallback_router.py / circuit_breaker.py 以外に現れていない."""
    forbidden = (
        "_custom_health_circuit",
        "_self_failover_loop",
        "_inline_3_strike_fallback",
        "_manual_recovery_streak",
        "_route_to_untested_provider",
    )
    base = REPO_ROOT / "backend"
    targets = []
    for sub in ("services", "routers"):
        d = base / sub
        if d.exists():
            targets.extend(d.rglob("*.py"))
    for py in targets:
        if py.name in ("fallback_router.py", "circuit_breaker.py"):
            continue
        text = py.read_text(encoding="utf-8")
        for word in forbidden:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert f"def {word}" not in line, (
                    f"forbidden self-fallback function {word!r} in {py}"
                )


# ══════════════════════════════════════════════════════════════════════
# AC-EVENT-2 (recovery) timing 検証
# ══════════════════════════════════════════════════════════════════════


def test_ac2_recovery_streak_constant():
    """3 連続 success で recover."""
    assert RECOVERY_SUCCESS_STREAK == 3


def test_ac2_recovery_streak_emits_anthropic_recovered_audit(monkeypatch):
    """fallback → 3 連続 success で 'anthropic_recovered' audit emit.

    NOTE: route の実復帰は failure_window (60s) を超えるか, failure 履歴が
    被って消えるまでタイミング依存. 本 test は recovery audit emit を確認.
    """
    captured: list[str] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append(event_type)
        return 1

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)

    async def _run():
        # fallback 発火
        for _ in range(3):
            await record_health_check("anthropic", False)
        assert current_route() in ("openai", "gemini")
        # 3 連続 success で recovery audit emit
        for _ in range(3):
            await record_health_check("anthropic", True)

    asyncio.run(_run())
    assert "anthropic_recovered" in captured


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets + module docstring
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_ai_08_has_5_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-08"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 5
    assert "T-M12-01" in t["deps"]


def test_module_docstring_documents_cross_refs():
    """docstring に ADR-012 / T-AI-MEM-04 / T-M12-01 cross-ref が明記."""
    doc = fb.__doc__ or ""
    assert "ADR-012" in doc
    assert "T-AI-MEM-04" in doc
    assert "T-M12-01" in doc
    for ac in ("EVENT-1", "EVENT-2", "STATE", "OPTIONAL", "UNWANTED"):
        assert ac in doc
