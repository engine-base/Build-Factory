"""T-010b-01: claude-agent-sdk 統合 (existing task_executor + skill_runner 拡張)
REFACTOR audit spec — 4 AC × claude-agent-sdk Subagent / Memory Tool /
Context Editing / provider precedence / drift guard / REFACTOR invariants.

Spec literal expansion (源泉 cited):

  tickets.json#T-010b-01:
    "title": "claude-agent-sdk 統合 (existing task_executor + skill_runner 拡張)"
    "sprint": 5  "feature": "F-010b"  "layer": "BE+WK"  "label": "REFACTOR"
    "existing_files": [
      "backend/workers/task_executor.py",
      "backend/integrations/skill_runner.py",
      "backend/services/orchestrator_graph.py"
    ]
    AC-1 UBIQUITOUS    : F-010b spec を満たす (Claude Code session spawner /
                         OAuth claude-agent-sdk 起動 / Plan-Gen-Eval / WS stream).
    AC-2 EVENT-DRIVEN  : invocation 2 秒以内に structured response
                         (success or {detail:{code,message}}).
    AC-3 STATE-DRIVEN  : REFACTOR 進行中も既存 API contract / public function
                         signature を維持し coverage は baseline 以上.
    AC-4 UNWANTED      : invalid input / unauthorized → 4xx {detail:{code,message}}
                         で state mutate しない.

  features.json#F-010b "Claude Code セッション・スポナー (play button)":
    happy_path: "play-click -> backend POST /sessions/spawn -> OAuth で claude-agent-sdk
      起動→初期プロンプト構築（spec + AC + Constitution + 知識）→Plan/Gen/Eval→
      WebSocket stream→user_interaction_log 記録（opt-in）"
    policies: startup_to_first_output_sec=10, median_target_sec=5

  ADR-010 §Decision (3 層 + マルチプロバイダ二刀流):
    Layer 3 = claude-agent-sdk + Subagent (Anthropic 公式) ← 中核
    禁則: メイン経路 (claude-runner) で LangGraph / LangChain / LiteLLM を
          使ってはならない (lint で fail).

  ADR-012 §Decision 1: Memory Tool memory_20250818 を一級市民として採用.
  ADR-012 §Decision 2: Context Editing clear_tool_uses_20250919 + compact_20260112
                       を SDK config で明示有効化. exclude_tools=["memory"] で保護.
  ADR-012 §Decision 3: Subagent Memory を handoff の引継ぎ知識保管に活用.
  ADR-012 §Decision 5 precedence (provider-adapter):
    1. per-request header (X-LLM-Provider)
    2. per-session active_route
    3. per-workspace preferred_provider
    4. per-user BYOK key availability
    5. ADR-010 default (Anthropic main)
    6. T-AI-08 circuit-breaker fallback

  IMPLEMENTATION_PROTOCOL.md §1 Step 7 (REFACTOR タスクは v2.1 適合 9 項目).

REFACTOR invariant (PR #253 anti-drift lesson):
  既存 task_executor / skill_runner / orchestrator_graph の公開関数シグネチャを
  破壊しない. SDK 統合は claude_agent_runner.py (T-S0-08) 経由で行う追加経路.
"""
from __future__ import annotations

import inspect
import pathlib
import re
import time

import pytest

# Modules under audit (REFACTOR existing_files)
from workers import task_executor
from integrations import skill_runner
from services import orchestrator_graph

# Modules providing SDK integration surface (ADR-010 / ADR-012)
from integrations import claude_agent_runner as car
from services import anthropic_memory_tool as amt
from services import anthropic_context_editing as ce
from services import handoff_service as hs
from services import provider_adapter_memory as pam


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TASK_EXECUTOR_PATH = REPO_ROOT / "backend" / "workers" / "task_executor.py"
SKILL_RUNNER_PATH = REPO_ROOT / "backend" / "integrations" / "skill_runner.py"
ORCH_GRAPH_PATH = REPO_ROOT / "backend" / "services" / "orchestrator_graph.py"
CLAUDE_RUNNER_PATH = REPO_ROOT / "backend" / "integrations" / "claude_agent_runner.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — F-010b spec satisfied via SDK integration surface
# ══════════════════════════════════════════════════════════════════════


def test_ac1_claude_agent_runner_module_exists():
    """AC-1.1: claude-agent-sdk wrapper module (ClaudeAgentRunner) is present."""
    assert CLAUDE_RUNNER_PATH.exists()
    assert hasattr(car, "ClaudeAgentRunner")
    assert hasattr(car, "SessionRecord")


def test_ac1_runner_run_task_uses_sdk_options():
    """AC-1.2: ClaudeAgentRunner.run_task imports claude_agent_sdk
    (ClaudeAgentOptions / ClaudeSDKClient / AssistantMessage / ResultMessage)
    inside the function body (lazy import allowed)."""
    src = CLAUDE_RUNNER_PATH.read_text(encoding="utf-8")
    assert "from claude_agent_sdk import" in src
    for sym in ("ClaudeAgentOptions", "ClaudeSDKClient", "ResultMessage"):
        assert sym in src, f"{sym} symbol not referenced in claude_agent_runner"


def test_ac1_memory_tool_registered_in_sdk_path():
    """AC-1.3: ADR-012 Decision 1 — Memory Tool spec exposed for SDK
    tools list activation (memory_20250818)."""
    spec = amt.memory_tool_spec()
    assert spec["type"] == "memory_20250818"
    assert spec["name"] == "memory"
    # symbol is exported for SDK callers
    assert amt.MEMORY_TOOL_TYPE == "memory_20250818"


def test_ac1_context_editing_default_config_present():
    """AC-1.4: ADR-012 Decision 2 — Context Editing default config exposes
    clear_tool_uses_20250919 and compact_20260112 strategies."""
    cfg = ce.default_context_management_config()
    edits = cfg["edits"]
    strategy_types = {e["type"] for e in edits}
    assert "clear_tool_uses_20250919" in strategy_types
    assert "compact_20260112" in strategy_types


def test_ac1_subagent_handoff_pattern_available():
    """AC-1.5: ADR-012 Decision 3 — handoff_service exposes request_handoff
    + register_handoff_backend for SDK Task tool delegation."""
    assert callable(hs.request_handoff)
    assert callable(hs.register_handoff_backend)
    assert callable(hs.get_handoff_backend)


def test_ac1_resume_choices_match_session_spec():
    """AC-1.6: F-010b session resume choices = (from_checkpoint, rerun_full,
    manual_fix, cancel) — 4-choice contract surfaced from runner."""
    assert set(car.VALID_RESUME_CHOICES) == {
        "from_checkpoint", "rerun_full", "manual_fix", "cancel",
    }


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — invocation returns within 2s (structured)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_memory_tool_spec_returns_within_2s():
    t0 = time.time()
    spec = amt.memory_tool_spec()
    assert (time.time() - t0) < 2.0
    assert isinstance(spec, dict)


def test_ac2_context_editing_config_returns_within_2s():
    t0 = time.time()
    cfg = ce.default_context_management_config()
    assert (time.time() - t0) < 2.0
    assert isinstance(cfg, dict)


def test_ac2_provider_resolve_returns_within_2s():
    t0 = time.time()
    out = pam.resolve_active_provider()
    assert (time.time() - t0) < 2.0
    assert out["provider"] == "anthropic"  # ADR-010 default


def test_ac2_runner_emits_structured_session_record():
    """AC-2: SessionRecord has structured fields used by both success and
    error path (status / crash_reason / completed_at)."""
    rec = car.SessionRecord(prompt="x")
    for field in ("status", "sdk_session_id", "prompt", "crash_reason"):
        assert hasattr(rec, field)


def test_ac2_handoff_error_carries_structured_detail():
    """AC-2: HandoffError raised on invalid input is convertible to
    {detail:{code,message}} by router."""
    with pytest.raises(hs.HandoffError) as exc:
        hs._validate_persona_key("", field_name="source_persona")
    assert "must not be empty" in str(exc.value)


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — REFACTOR backwards compat (existing signatures intact)
# ══════════════════════════════════════════════════════════════════════


def test_ac3_task_executor_public_signatures_intact():
    """AC-3: REFACTOR invariant — task_executor public functions retain
    their signatures (process_pending_tasks() -> None / execute_task_now(int))."""
    sig = inspect.signature(task_executor.process_pending_tasks)
    assert list(sig.parameters.keys()) == []

    sig = inspect.signature(task_executor.execute_task_now)
    params = list(sig.parameters.keys())
    assert params == ["task_id"]
    assert sig.parameters["task_id"].annotation is int


def test_ac3_skill_runner_invoke_skill_signature_intact():
    """AC-3: REFACTOR invariant — skill_runner.invoke_skill signature
    is preserved (skill_name, user_input, provider, model, triggered_by,
    trigger_id)."""
    sig = inspect.signature(skill_runner.invoke_skill)
    params = list(sig.parameters.keys())
    for required in ("skill_name", "user_input", "provider", "model",
                     "triggered_by", "trigger_id"):
        assert required in params, f"invoke_skill missing param {required}"
    # default provider/model preserved for backwards compat
    assert sig.parameters["provider"].default == "ollama"
    assert sig.parameters["triggered_by"].default == "user"


def test_ac3_orchestrator_graph_prepare_state_signature_intact():
    """AC-3: REFACTOR invariant — orchestrator_graph.prepare_state retains
    its async signature shape (entry point for conversation pipeline)."""
    sig = inspect.signature(orchestrator_graph.prepare_state)
    params = list(sig.parameters.keys())
    for required in ("thread_id", "employee_id", "user_message", "history",
                     "provider", "model"):
        assert required in params


def test_ac3_runner_run_task_supports_session_resume():
    """AC-3: ClaudeAgentOptions(resume=sdk_session_id) — session resume
    is plumbed through ClaudeAgentRunner.run_task."""
    sig = inspect.signature(car.ClaudeAgentRunner.run_task)
    assert "sdk_session_id" in sig.parameters
    assert "agent_persona" in sig.parameters
    assert "skill_name" in sig.parameters
    assert "cwd" in sig.parameters  # swarm worktree support


def test_ac3_memory_tool_protected_in_context_editing():
    """AC-3 STATE-DRIVEN: ADR-012 Decision 2 — Memory tool results MUST be
    in exclude_tools for clear_tool_uses (prevents loss of memory state)."""
    cfg = ce.default_context_management_config()
    clear_edit = next(
        e for e in cfg["edits"] if e["type"] == "clear_tool_uses_20250919"
    )
    assert "memory" in clear_edit["exclude_tools"]


def test_ac3_clear_thinking_must_be_first_when_enabled():
    """AC-3: ADR-012 — clear_thinking_20251015 必ず最初に配置."""
    cfg = ce.default_context_management_config(enable_clear_thinking=True)
    assert cfg["edits"][0]["type"] == "clear_thinking_20251015"


# ── Provider precedence (ADR-012 §5.2) — each layer overrides lower ────


def test_ac3_precedence_header_overrides_session():
    """ADR-012 §5.2 layer 1: per-request header beats per-session."""
    out = pam.resolve_active_provider(
        header_provider="gemini",
        session_active_route="openai",
    )
    assert out["provider"] == "gemini"
    assert out["reason"] == "header"


def test_ac3_precedence_session_overrides_workspace():
    """ADR-012 §5.2 layer 2: per-session active_route beats per-workspace."""
    out = pam.resolve_active_provider(
        session_active_route="openai",
        workspace_preferred="gemini",
    )
    assert out["provider"] == "openai"
    assert out["reason"] == "session"


def test_ac3_precedence_workspace_overrides_byok_when_present():
    """ADR-012 §5.2 layer 3: per-workspace beats BYOK key fall-through."""
    out = pam.resolve_active_provider(workspace_preferred="gemini")
    assert out["provider"] == "gemini"
    assert out["reason"] == "workspace"


def test_ac3_precedence_default_when_no_overrides():
    """ADR-012 §5.2 layer 5: ADR-010 default = anthropic."""
    out = pam.resolve_active_provider()
    assert out["provider"] == "anthropic"
    assert out["reason"] == "default"


def test_ac3_precedence_fallback_when_anthropic_unhealthy():
    """ADR-012 §5.2 layer 6: T-AI-08 circuit-breaker — when anthropic
    is unhealthy AND no override, auto-fallback to openai/gemini."""
    out = pam.resolve_active_provider(anthropic_healthy=False)
    assert out["provider"] != "anthropic"
    assert out["reason"] == "auto-fallback"


def test_ac3_precedence_workspace_auto_collapses_to_default():
    """workspace_preferred='auto' → ADR-010 default path."""
    out = pam.resolve_active_provider(workspace_preferred="auto")
    assert out["provider"] == "anthropic"
    assert out["reason"] == "default"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input → 4xx-convertible error, no state mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_resume_choice_rejected():
    runner = car.ClaudeAgentRunner()
    import asyncio
    with pytest.raises(ValueError) as exc:
        asyncio.run(runner.handle_resume(session_id=1, choice="bogus"))
    assert "invalid resume choice" in str(exc.value)


def test_ac4_unknown_provider_rejected():
    with pytest.raises(pam.ProviderAdapterMemoryError):
        pam.tool_spec_for("bogus-provider")


def test_ac4_unknown_memory_command_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TOOL_DIR", str(tmp_path))
    h = amt.MemoryToolHandler()
    with pytest.raises(amt.MemoryToolError):
        h.dispatch("evil_command", path="/memories/x")


def test_ac4_handoff_same_source_target_rejected():
    import asyncio
    with pytest.raises(hs.HandoffError) as exc:
        asyncio.run(hs.request_handoff(
            source_persona="mary",
            target_persona="mary",
            message="x",
        ))
    assert "must differ" in str(exc.value)


def test_ac4_context_editing_compact_below_minimum_rejected():
    """ADR-012: compact_20260112 trigger must be >= 50_000 (official)."""
    with pytest.raises(ce.ContextEditingError):
        ce.default_context_management_config(compact_trigger=10_000)


def test_ac4_path_traversal_blocked():
    """ADR-012 Decision 1 — `/memories` 外へのアクセスは MemoryToolError."""
    with pytest.raises(amt.MemoryToolError):
        amt._resolve_virtual_path("/etc/passwd")


# ══════════════════════════════════════════════════════════════════════
# Drift guard — ADR-010 禁則 (LangGraph / LangChain / LiteLLM-in-main-runner)
# ══════════════════════════════════════════════════════════════════════


def _grep_imports(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"^(?:from|import)\s+(\S+)", text, re.MULTILINE)


def test_drift_no_langgraph_in_main_runner():
    """CLAUDE.md §3 禁則: メイン経路 (claude-runner) で LangGraph 禁止."""
    imports = _grep_imports(CLAUDE_RUNNER_PATH)
    forbidden = [i for i in imports if i.startswith(("langgraph", "langchain"))]
    assert forbidden == [], f"forbidden imports in claude_agent_runner: {forbidden}"


def test_drift_no_langchain_in_existing_refactor_files():
    """REFACTOR invariant: 既存 task_executor / skill_runner / orchestrator_graph
    どこにも langgraph / langchain import が無いこと (本 audit の前提)."""
    for p in (TASK_EXECUTOR_PATH, SKILL_RUNNER_PATH, ORCH_GRAPH_PATH):
        imports = _grep_imports(p)
        forbidden = [i for i in imports if i.startswith(("langgraph", "langchain"))]
        assert forbidden == [], f"forbidden imports in {p.name}: {forbidden}"


def test_drift_no_litellm_in_main_runner():
    """ADR-010 禁則: claude-runner は LiteLLM を import しない (サブ用途のみ)."""
    imports = _grep_imports(CLAUDE_RUNNER_PATH)
    forbidden = [i for i in imports if "litellm" in i.lower()]
    assert forbidden == [], f"LiteLLM in main runner: {forbidden}"


def test_drift_runner_has_no_langgraph_sentinel_comment():
    """T-S0-08 AC-7 sentinel marker must remain — lint detection anchor."""
    src = CLAUDE_RUNNER_PATH.read_text(encoding="utf-8")
    assert "NO_LANGGRAPH_IN_RUNNER" in src


# ══════════════════════════════════════════════════════════════════════
# REFACTOR 9-項目 適合チェック (公開シンボル / 構造保護)
# ══════════════════════════════════════════════════════════════════════


def test_refactor_task_executor_module_unchanged_surface():
    """REFACTOR 適合: task_executor の public function 群 (4 件) が module 表面に
    存在 (削除/改名されていない)."""
    for name in ("process_pending_tasks", "execute_task_now"):
        assert hasattr(task_executor, name), (
            f"task_executor.{name} removed — REFACTOR invariant breach"
        )


def test_refactor_skill_runner_module_unchanged_surface():
    """REFACTOR 適合: skill_runner.invoke_skill / WEB_SEARCH_SKILLS /
    KNOWLEDGE_AWARE_SKILLS の公開シンボル維持."""
    for name in ("invoke_skill", "WEB_SEARCH_SKILLS",
                 "KNOWLEDGE_AWARE_SKILLS", "WEB_SEARCH_KEYWORDS"):
        assert hasattr(skill_runner, name)


def test_refactor_orchestrator_node_functions_present():
    """REFACTOR 適合: orchestrator_graph の 7 node 関数が module 表面に存在."""
    for name in ("node_load_employee", "node_update_profile",
                 "node_detect_mode", "node_detect_skill",
                 "node_update_slots", "node_build_rag",
                 "node_long_term_memory"):
        assert hasattr(orchestrator_graph, name)


def test_refactor_runner_dataclass_fields_complete():
    """SessionRecord/CostRecord/AuditEvent dataclass の必須 field が揃っている."""
    rec_fields = {f for f in car.SessionRecord.__dataclass_fields__}
    for required in ("sdk_session_id", "workspace_id", "agent_persona",
                     "status", "crash_reason", "resume_choice"):
        assert required in rec_fields

    cost_fields = {f for f in car.CostRecord.__dataclass_fields__}
    for required in ("cache_read_tokens", "cache_write_tokens", "cost_usd",
                     "input_tokens", "output_tokens"):
        assert required in cost_fields


def test_refactor_provider_capabilities_cover_three_providers():
    """ADR-012 §5.3 capability matrix: anthropic / openai / gemini 全 carry."""
    assert set(pam.SUPPORTED_PROVIDERS) == {"anthropic", "openai", "gemini"}
    assert pam.DEFAULT_PROVIDER == "anthropic"
    for p in pam.SUPPORTED_PROVIDERS:
        caps = pam.CAPABILITIES[p]
        for feat in ("memory_tool_native", "native_compaction",
                     "extended_thinking", "native_tool_clearing"):
            assert feat in caps, f"{p} missing capability {feat}"


def test_refactor_tool_spec_per_provider_shapes_distinct():
    """ADR-012 §5.3: anthropic = 1 server tool dict / openai = 6 function defs /
    gemini = 6 function_declarations."""
    anth = pam.tool_spec_for("anthropic")
    openai = pam.tool_spec_for("openai")
    gemini = pam.tool_spec_for("gemini")
    assert isinstance(anth, dict)
    assert isinstance(openai, list) and len(openai) == 6
    assert isinstance(gemini, list) and len(gemini) == 6


def test_refactor_context_editing_per_provider_modes_distinct():
    """ADR-012 §5.3: anthropic native / openai degrade / gemini degrade."""
    assert pam.context_editing_for("anthropic")["mode"] == "native"
    assert pam.context_editing_for("openai")["mode"] == "degrade_openai"
    assert pam.context_editing_for("gemini")["mode"] == "degrade_gemini"
    # non-anthropic providers must NOT use SDK-native compaction
    assert pam.context_editing_for("openai")["use_client_side_summarizer"] is True
    assert pam.context_editing_for("gemini")["use_client_side_summarizer"] is True


def test_refactor_recommended_beta_headers_present():
    """ADR-012 Decision 2: beta headers context-management-2025-06-27 +
    compact-2026-01-12 must be exposed for SDK callers."""
    headers = ce.recommended_beta_headers()
    assert "context-management-2025-06-27" in headers
    assert "compact-2026-01-12" in headers
