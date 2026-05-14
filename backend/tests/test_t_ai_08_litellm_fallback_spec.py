"""T-AI-08 spec audit — circuit breaker thresholds + Claude→GPT-4o + Claude→Gemini 1:1.

NEW audit per Wave 5: Anthropic 障害時 LiteLLM フォールバック の 5 AC を 1:1 で
literal 検証する独立 audit suite.

## 防衛ライン (Anti-drift)

本 audit が防ぐ偽装パターン:

  1. `if anthropic_down: use_litellm` の 1 行で「動いている」装い
     → provider 切替先 (gpt-4o vs gemini-2.5-pro) を **別々の test** で検証する
  2. circuit breaker の閾値を spec 文 (3 fail / 60s, 3 success / 5 min) と
     一致しない値で実装する
     → 定数 ID 検証 + 動作検証を **個別** に書く
  3. LiteLLM をメイン経路で import (ADR-010 違反)
     → lint check (check_no_litellm_in_runner) と test 両面で検出
  4. untested provider (xai / cohere / meta) に silent route
     → ALLOWED_PROVIDERS / VALID_OVERRIDE_PROVIDERS 列挙制約を test

## AC × test 件数

  AC-EVENT-1 (3 fail / 60s → openai + notify) : 7 tests
  AC-STATE   (degraded mode capabilities)     : 5 tests
  AC-EVENT-2 (3 success / 5 min → recover)    : 5 tests
  AC-OPTIONAL (manual /admin/fallback gemini) : 5 tests
  AC-UNWANTED (both fail → paused + alert)    : 5 tests
  Provider routing (gpt-4o / gemini-2.5-pro)  : 6 tests (個別検証)
  Lint (no litellm in main runner)            : 4 tests
  Cross-ref (ADR-010 / ADR-012 / tickets)     : 3 tests

  total = 40 tests

## Source-of-truth

  - ticket: docs/task-decomposition/2026-05-09_v1/tickets.json#T-AI-08
  - ADR-010 (AI stack 3 層): docs/decisions/ADR-010-ai-stack-anthropic-native.md
  - ADR-012 (Memory Tool / provider-adapter): docs/decisions/ADR-012-anthropic-memory-tool-adoption.md
  - 自前実装必須 8 項目 #8 = T-AI-08 (CLAUDE.md §3)
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

from services import fallback_router as fb
from services import litellm_router as ll
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
BACKEND_ROOT = REPO_ROOT / "backend"


@pytest.fixture(autouse=True)
def _reset():
    """各 test 前後で fallback_router state を初期化."""
    reset_state()
    yield
    reset_state()


def _install_audit_recorder() -> list[dict]:
    """services.memory_service.emit_event を捕獲する fake."""
    captured: list[dict] = []
    mod = types.ModuleType("services.memory_service")

    async def emit_event(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event": event_type, "detail": detail or {}})
        return len(captured)

    mod.emit_event = emit_event
    sys.modules["services.memory_service"] = mod
    return captured


def _cleanup_audit_recorder() -> None:
    sys.modules.pop("services.memory_service", None)


# ══════════════════════════════════════════════════════════════════════
# AC-EVENT-1: "When Anthropic API health-check fails 3 times within 60 seconds,
#             the system shall switch the main route to LiteLLM → GPT-4o
#             (primary fallback) and notify masato."
# ══════════════════════════════════════════════════════════════════════


def test_ac_event1_threshold_constant_exactly_3():
    """Spec literal: '3 times'."""
    assert FAILURE_THRESHOLD == 3, (
        f"AC-EVENT-1 spec '3 times' but FAILURE_THRESHOLD={FAILURE_THRESHOLD}"
    )


def test_ac_event1_window_constant_exactly_60_sec():
    """Spec literal: 'within 60 seconds'."""
    assert FAILURE_WINDOW_SEC == 60, (
        f"AC-EVENT-1 spec '60 seconds' but FAILURE_WINDOW_SEC={FAILURE_WINDOW_SEC}"
    )


def test_ac_event1_two_failures_does_not_trigger_fallback():
    """Spec '3 times': 2 回 fail では fallback しない (boundary 下)."""
    asyncio.run(record_health_check("anthropic", False))
    asyncio.run(record_health_check("anthropic", False))
    assert current_route() == "anthropic"
    assert is_degraded() is False


def test_ac_event1_third_failure_triggers_fallback_to_openai():
    """Spec literal: 3 連続 fail → 'GPT-4o (primary fallback)'.
    primary fallback = openai (gemini ではない)."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    assert current_route() == "openai", (
        f"AC-EVENT-1 primary fallback must be 'openai' (GPT-4o), got {current_route()!r}"
    )
    assert is_degraded() is True


def test_ac_event1_primary_fallback_is_openai_not_gemini():
    """AC-EVENT-1 'primary fallback' は GPT-4o = openai. gemini ではない.
    drift guard: spec を gemini に flip した実装の早期検出."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    assert current_route() == "openai"
    assert current_route() != "gemini"


def test_ac_event1_audit_event_emit_on_fallback():
    """Spec literal: 'notify masato'. audit emit でこれを表現."""
    captured = _install_audit_recorder()
    try:
        for _ in range(3):
            asyncio.run(record_health_check("anthropic", False))
        events = [e["event"] for e in captured]
        assert "anthropic_fallback_engaged" in events
        engaged = next(e for e in captured if e["event"] == "anthropic_fallback_engaged")
        assert engaged["detail"]["new_route"] == "openai"
        assert engaged["detail"]["failure_count_60s"] >= 3
    finally:
        _cleanup_audit_recorder()


def test_ac_event1_failure_window_excludes_old_history(monkeypatch):
    """'within 60 seconds' = window 外の fail はカウントしない.
    例: 70 秒前の fail 1 + 直近の fail 2 → fallback しない."""
    s = fb._ProviderState()
    t = [1000.0]

    def fake_monotonic():
        return t[0]

    monkeypatch.setattr(fb.time, "monotonic", fake_monotonic)
    s.record(False)  # t=1000
    t[0] = 1070.0  # 70 秒経過, window 外
    s.record(False)  # t=1070
    s.record(False)  # t=1070
    # window 内 (60 秒) の failure は 2 のみ (t=1000 は除外)
    assert s.failures_in_window(60) == 2


# ══════════════════════════════════════════════════════════════════════
# AC-STATE: "While in fallback mode, the system shall disable Memory API writes
#           and Subagent (Task tool), and shall mark every session with
#           degraded_mode=true."
# ══════════════════════════════════════════════════════════════════════


def test_ac_state_memory_api_writes_disabled_in_fallback():
    """Spec literal: 'disable Memory API writes'."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    assert memory_api_writes_enabled() is False


def test_ac_state_subagent_disabled_in_fallback():
    """Spec literal: 'disable ... Subagent (Task tool)'."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    assert subagent_enabled() is False


def test_ac_state_session_degraded_mode_true_in_fallback():
    """Spec literal: 'mark every session with degraded_mode=true'."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    assert session_degraded_mode_flag() is True


def test_ac_state_capabilities_re_enabled_after_reset():
    """fallback mode 解除後は normal route に戻る (reset_state)."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    assert memory_api_writes_enabled() is False
    reset_state()
    assert current_route() == "anthropic"
    assert memory_api_writes_enabled() is True
    assert subagent_enabled() is True
    assert session_degraded_mode_flag() is False


def test_ac_state_emergency_chat_response_marks_writes_disabled():
    """litellm_router.emergency_chat の response が memory_api_writes_disabled=True
    を返す (AC-STATE Memory API write 禁止シグナル)."""
    # response shape のみ検証 (実際 LLM 呼び出しは行わない)
    assert hasattr(ll, "memory_api_writes_allowed_in_fallback")
    fake_response = {"provider": "fallback", "memory_api_writes_disabled": True}
    assert ll.memory_api_writes_allowed_in_fallback(fake_response) is False
    normal_response = {"provider": "anthropic"}
    assert ll.memory_api_writes_allowed_in_fallback(normal_response) is True


# ══════════════════════════════════════════════════════════════════════
# AC-EVENT-2: "When Anthropic recovers (3 consecutive successful health-checks
#             in 5 min), the system shall switch back to claude-agent-sdk
#             automatically."
# ══════════════════════════════════════════════════════════════════════


def test_ac_event2_recovery_streak_constant_exactly_3():
    """Spec literal: '3 consecutive successful health-checks'."""
    assert RECOVERY_SUCCESS_STREAK == 3, (
        f"AC-EVENT-2 spec '3 consecutive' but RECOVERY_SUCCESS_STREAK={RECOVERY_SUCCESS_STREAK}"
    )


def test_ac_event2_recovery_window_constant_exactly_5_min():
    """Spec literal: 'in 5 min' = 300 秒."""
    assert RECOVERY_WINDOW_SEC == 300, (
        f"AC-EVENT-2 spec '5 min' but RECOVERY_WINDOW_SEC={RECOVERY_WINDOW_SEC}"
    )


def test_ac_event2_recovery_emits_anthropic_recovered_audit():
    """fallback 中に 3 連続 success → 'anthropic_recovered' audit emit."""
    captured = _install_audit_recorder()
    try:
        for _ in range(3):
            asyncio.run(record_health_check("anthropic", False))
        assert current_route() == "openai"
        for _ in range(3):
            asyncio.run(record_health_check("anthropic", True))
        events = [e["event"] for e in captured]
        assert "anthropic_recovered" in events
    finally:
        _cleanup_audit_recorder()


def test_ac_event2_consecutive_successes_state_tracking():
    """_ProviderState.consecutive_successes() が末尾連続 success を返す."""
    s = fb._ProviderState()
    for ok in (False, True, True, True):
        s.record(ok)
    assert s.consecutive_successes() == 3


def test_ac_event2_consecutive_resets_on_failure():
    """末尾以前に failure があれば streak は中断."""
    s = fb._ProviderState()
    for ok in (True, True, False, True):
        s.record(ok)
    assert s.consecutive_successes() == 1


# ══════════════════════════════════════════════════════════════════════
# AC-OPTIONAL: "Where masato manually overrides via /admin/fallback
#              {provider:gemini}, the system shall route to Gemini 2.5 Pro
#              instead of GPT-4o."
# ══════════════════════════════════════════════════════════════════════


def test_ac_optional_manual_override_to_gemini():
    """Spec literal: 'manually overrides ... {provider:gemini}' → gemini route."""
    asyncio.run(manual_override("gemini"))
    assert current_route() == "gemini"
    assert is_degraded() is True


def test_ac_optional_manual_override_to_openai():
    """OPTIONAL 同じく openai 手動 override も可能."""
    asyncio.run(manual_override("openai"))
    assert current_route() == "openai"


def test_ac_optional_manual_override_back_to_auto_clears():
    """None で manual override 解除 → auto に戻る (normal route = anthropic)."""
    asyncio.run(manual_override("gemini"))
    assert current_route() == "gemini"
    asyncio.run(manual_override(None))
    assert current_route() == "anthropic"


def test_ac_optional_manual_override_audit_emit():
    """Spec 'overrides' = audit 'fallback_manual_override' emit."""
    captured = _install_audit_recorder()
    try:
        asyncio.run(manual_override("gemini"))
        events = [e["event"] for e in captured]
        assert "fallback_manual_override" in events
        ev = next(e for e in captured if e["event"] == "fallback_manual_override")
        assert ev["detail"]["new"] == "gemini"
    finally:
        _cleanup_audit_recorder()


def test_ac_optional_valid_override_providers_constant():
    """Spec '{provider:gemini}' = VALID_OVERRIDE_PROVIDERS に gemini 含む."""
    assert "gemini" in VALID_OVERRIDE_PROVIDERS
    assert "openai" in VALID_OVERRIDE_PROVIDERS
    assert "anthropic" not in VALID_OVERRIDE_PROVIDERS  # 既定は手動切替不要


# ══════════════════════════════════════════════════════════════════════
# AC-UNWANTED: "If both Anthropic AND OpenAI fail simultaneously, the system
#              shall pause new sessions, allow only emergency read-only access,
#              and alert masato + Slack — it shall not silently route to an
#              untested provider."
# ══════════════════════════════════════════════════════════════════════


def test_ac_unwanted_both_fail_triggers_pause():
    """Spec literal: 'both Anthropic AND OpenAI fail' → 'pause'."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    for _ in range(3):
        asyncio.run(record_health_check("openai", False))
    assert should_pause() is True
    assert current_route() == "paused"


def test_ac_unwanted_pause_disables_memory_api_writes():
    """Spec 'emergency read-only' = Memory API write 不可."""
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    for _ in range(3):
        asyncio.run(record_health_check("openai", False))
    assert memory_api_writes_enabled() is False
    assert subagent_enabled() is False


def test_ac_unwanted_pause_alerts_audit_event():
    """Spec 'alert masato' = audit 'fallback_paused_both_down' emit."""
    captured = _install_audit_recorder()
    try:
        for _ in range(3):
            asyncio.run(record_health_check("anthropic", False))
        for _ in range(3):
            asyncio.run(record_health_check("openai", False))
        events = [e["event"] for e in captured]
        assert "fallback_paused_both_down" in events
    finally:
        _cleanup_audit_recorder()


def test_ac_unwanted_pause_overrides_manual_override():
    """両 fail → 'shall not silently route to untested provider'.
    manual override (gemini) 設定中でも paused が優先 (gemini に逃さない)."""
    asyncio.run(manual_override("gemini"))
    assert current_route() == "gemini"
    for _ in range(3):
        asyncio.run(record_health_check("anthropic", False))
    for _ in range(3):
        asyncio.run(record_health_check("openai", False))
    assert current_route() == "paused"


def test_ac_unwanted_untested_provider_rejected():
    """Spec 'shall not silently route to an untested provider'.
    record_health_check / manual_override に未テスト provider を入れたら reject."""
    async def _run():
        for bad in ("xai", "cohere", "meta", "untested", "claude"):
            with pytest.raises(ValueError):
                await record_health_check(bad, False)
        for bad in ("xai", "cohere", "meta", "untested"):
            with pytest.raises(ValueError):
                await manual_override(bad)

    asyncio.run(_run())
    # state mutate されていないこと
    assert current_route() == "anthropic"


# ══════════════════════════════════════════════════════════════════════
# Provider routing — 個別検証 (anti-drift CRITICAL)
# Claude → GPT-4o と Claude → Gemini をそれぞれ別 test で検証
# ══════════════════════════════════════════════════════════════════════


def test_routing_emergency_providers_constant_exact():
    """litellm_router.EMERGENCY_PROVIDERS = (openai, gemini) のみ.
    untested ('xai' / 'meta') は含まない."""
    assert ll.EMERGENCY_PROVIDERS == ("openai", "gemini")
    assert "anthropic" not in ll.EMERGENCY_PROVIDERS  # 自分自身は emergency 先ではない
    assert "xai" not in ll.EMERGENCY_PROVIDERS
    assert "meta" not in ll.EMERGENCY_PROVIDERS


def test_routing_openai_model_is_gpt_4o():
    """Claude → GPT-4o: emergency_chat の openai route 先は 'openai/gpt-4o'.
    drift guard: openai/gpt-4o-mini や openai/gpt-3.5 に劣化しない."""
    src = (BACKEND_ROOT / "services" / "litellm_router.py").read_text(encoding="utf-8")
    # emergency_chat 関数の中で 'openai': 'openai/gpt-4o' mapping が存在
    assert '"openai": "openai/gpt-4o"' in src, (
        "AC-EVENT-1 primary fallback = GPT-4o. 'openai/gpt-4o' mapping not found"
    )


def test_routing_gemini_model_is_gemini_2_5_pro():
    """Claude → Gemini: emergency_chat の gemini route 先は 'gemini/gemini-2.5-pro'.
    drift guard: gemini-flash や gemini-1.5 に劣化しない."""
    src = (BACKEND_ROOT / "services" / "litellm_router.py").read_text(encoding="utf-8")
    assert '"gemini": "gemini/gemini-2.5-pro"' in src, (
        "AC-OPTIONAL fallback = Gemini 2.5 Pro. 'gemini/gemini-2.5-pro' mapping not found"
    )


def test_routing_emergency_chat_rejects_anthropic_route():
    """active_route='anthropic' で emergency_chat 呼ぶと LiteLLMRouterError.
    'Anthropic が動いてる時に LiteLLM を呼ぶな' を runtime guard."""
    async def _run():
        with pytest.raises(ll.LiteLLMRouterError, match="emergency_chat only allowed"):
            await ll.emergency_chat([{"role": "user", "content": "hi"}], fallback_route="anthropic")

    asyncio.run(_run())


def test_routing_emergency_chat_rejects_untested_route():
    """active_route='xai' / 'cohere' で emergency_chat → reject."""
    async def _run():
        for bad in ("xai", "cohere", "meta", "claude"):
            with pytest.raises(ll.LiteLLMRouterError, match="emergency_chat only allowed"):
                await ll.emergency_chat([{"role": "user", "content": "hi"}], fallback_route=bad)

    asyncio.run(_run())


def test_routing_emergency_chat_reads_current_route_from_fallback_router():
    """emergency_chat の fallback_route 省略時は fallback_router.current_route()
    を読む (defense in depth: 2 つの module が cross-ref)."""
    # source 検査: emergency_chat 関数本体で current_route を import
    src = (BACKEND_ROOT / "services" / "litellm_router.py").read_text(encoding="utf-8")
    assert "from services.fallback_router import current_route" in src
    # 実 import が成功
    from services.fallback_router import current_route as _cr  # noqa: F401


# ══════════════════════════════════════════════════════════════════════
# Lint — LiteLLM がメイン経路 (claude-runner) で使われない
# ══════════════════════════════════════════════════════════════════════


def test_lint_no_litellm_in_main_runner_source():
    """ADR-010 / T-AI-08: 主経路 (claude_agent_runner.py) で litellm を import
    していない (source grep)."""
    runner = BACKEND_ROOT / "integrations" / "claude_agent_runner.py"
    if not runner.exists():
        pytest.skip("claude_agent_runner.py not present in this branch")
    src = runner.read_text(encoding="utf-8")
    # python source-level に 'import litellm' / 'from litellm' を含まないこと
    assert not re.search(r"^\s*import\s+litellm\b", src, flags=re.MULTILINE), (
        "ADR-010 violation: claude_agent_runner.py imports litellm"
    )
    assert not re.search(r"^\s*from\s+litellm\b", src, flags=re.MULTILINE), (
        "ADR-010 violation: claude_agent_runner.py 'from litellm' import"
    )


def test_lint_no_litellm_in_runner_passes():
    """`bash scripts/lint-mock.sh --no-litellm-in-runner` が PASS."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-litellm-in-runner"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout}\n{r.stderr}"


def test_lint_no_self_fallback_circuit_passes():
    """T-AI-08 AC-UNWANTED: 自前 fallback / circuit-breaker 実装の禁止語 lint."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-self-fallback-circuit"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout}\n{r.stderr}"


def test_lint_emergency_chat_runtime_guard_blocks_main_runner():
    """litellm_router._assert_not_called_from_runner() が claude_agent_runner.py
    の filename を検知して MainEngineRoutingDenied を raise する.

    runtime defense (lint だけでなく call stack check)."""
    # 関数を直接呼び stack に runner.py を疑似挿入
    fake_frame = inspect.FrameInfo(
        frame=inspect.currentframe(),
        filename="/path/to/claude_agent_runner.py",
        lineno=1,
        function="run",
        code_context=None,
        index=None,
    )

    def fake_stack():
        return [fake_frame]

    import services.litellm_router as _ll
    real_stack = inspect.stack
    inspect.stack = fake_stack  # type: ignore[assignment]
    try:
        with pytest.raises(_ll.MainEngineRoutingDenied):
            _ll._assert_not_called_from_runner()
    finally:
        inspect.stack = real_stack  # type: ignore[assignment]


# ══════════════════════════════════════════════════════════════════════
# Cross-ref: ticket / ADR / module docstring
# ══════════════════════════════════════════════════════════════════════


def test_xref_ticket_t_ai_08_has_5_ac_and_deps():
    """tickets.json T-AI-08 の AC 5 件 + deps に T-M12-01 が含まれる."""
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-08"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 5
    assert t["label"] == "NEW"
    assert "T-M12-01" in t["deps"]
    # 5 種 EARS type に必ず触れる
    types_seen = {ac["type"] for ac in t["acceptance_criteria"]}
    assert "EVENT" in types_seen
    assert "STATE" in types_seen
    assert "OPTIONAL" in types_seen
    assert "UNWANTED" in types_seen


def test_xref_adr_010_supersedes_adr_002():
    """ADR-010 が ADR-002 を supersede しており Layer 2b に LiteLLM が
    'emergency fallback' として明記されている (T-AI-08 の依拠)."""
    adr = REPO_ROOT / "docs" / "decisions" / "ADR-010-ai-stack-anthropic-native.md"
    text = adr.read_text(encoding="utf-8")
    assert "supersedes ADR-002" in text
    assert "Anthropic 障害時のフォールバック" in text or "緊急代替" in text
    # 自前 8 項目に T-AI-08 が enumerate
    assert "T-AI-08" in text


def test_xref_fallback_router_docstring_documents_cross_refs():
    """fallback_router docstring に ADR-012 / T-AI-MEM-04 / T-M12-01 と 5 AC を明記."""
    doc = fb.__doc__ or ""
    assert "ADR-012" in doc
    assert "T-AI-MEM-04" in doc
    assert "T-M12-01" in doc
    for ac in ("EVENT-1", "EVENT-2", "STATE", "OPTIONAL", "UNWANTED"):
        assert ac in doc
