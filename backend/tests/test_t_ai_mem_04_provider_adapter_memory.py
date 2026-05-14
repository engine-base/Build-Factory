"""T-AI-MEM-04: Provider-adapter Memory Tool (任意切替 + 障害時 fallback 両対応).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : tool_spec_for(anthropic/openai/gemini) + resolve_active_provider
                       precedence 6 layers + Vault filesystem 共有 (provider 非依存).
  AC-2 EVENT-DRIVEN  : POST /api/providers/active で 2 秒以内 + audit 'provider.switched'
                       (manual / auto-fallback) emit.
  AC-3 STATE-DRIVEN  : 非 Anthropic では client-side summarizer / clear_thinking skip /
                       truncation_strategy=auto. file ops byte-identical.
  AC-4 UNWANTED      : unsupported provider / policy 衝突 / schema 違反 → 4xx state mutate なし.
                       BYOK 不在 → precedence fallback + audit 'provider.fallback' silent pick 禁止.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import provider_adapter_memory as pam
from services.provider_adapter_memory import (
    CAPABILITIES,
    DEFAULT_PROVIDER,
    EVENT_PROVIDER_FALLBACK,
    EVENT_PROVIDER_SWITCHED,
    ProviderAdapterMemoryError,
    SUPPORTED_PROVIDERS,
    VALID_FALLBACK_REASONS,
    VALID_SWITCH_REASONS,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _reset_byok():
    from services import byok_store
    byok_store.reset_store()
    yield
    byok_store.reset_store()


# ══════════════════════════════════════════════════════════════════════
# Constants & invariants
# ══════════════════════════════════════════════════════════════════════


def test_constants_supported_providers():
    assert SUPPORTED_PROVIDERS == ("anthropic", "openai", "gemini")
    assert DEFAULT_PROVIDER == "anthropic"


def test_constants_audit_events():
    assert EVENT_PROVIDER_SWITCHED == "provider.switched"
    assert EVENT_PROVIDER_FALLBACK == "provider.fallback"


def test_constants_valid_reasons():
    assert "manual" in VALID_SWITCH_REASONS
    assert "auto-fallback" in VALID_SWITCH_REASONS
    assert "byok_missing" in VALID_FALLBACK_REASONS
    assert "circuit_breaker" in VALID_FALLBACK_REASONS


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: tool_spec_for(各 provider)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_tool_spec_anthropic_is_memory_20250818():
    spec = pam.tool_spec_for("anthropic")
    assert spec == {"type": "memory_20250818", "name": "memory"}


def test_ac1_tool_spec_openai_has_6_function_tools():
    specs = pam.tool_spec_for("openai")
    assert isinstance(specs, list)
    assert len(specs) == 6
    names = {s["function"]["name"] for s in specs}
    assert names == {
        "memory_view", "memory_create", "memory_str_replace",
        "memory_insert", "memory_delete", "memory_rename",
    }
    for s in specs:
        assert s["type"] == "function"


def test_ac1_tool_spec_gemini_has_6_function_declarations():
    specs = pam.tool_spec_for("gemini")
    assert isinstance(specs, list)
    assert len(specs) == 6
    names = {s["name"] for s in specs}
    assert names == {
        "memory_view", "memory_create", "memory_str_replace",
        "memory_insert", "memory_delete", "memory_rename",
    }


def test_ac1_tool_spec_unsupported_provider_rejected():
    with pytest.raises(ProviderAdapterMemoryError):
        pam.tool_spec_for("unknown")
    with pytest.raises(ProviderAdapterMemoryError):
        pam.tool_spec_for(None)
    with pytest.raises(ProviderAdapterMemoryError):
        pam.tool_spec_for("")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: resolve_active_provider precedence 6 layers
# ══════════════════════════════════════════════════════════════════════


def test_ac1_precedence_header_wins_over_session():
    out = pam.resolve_active_provider(
        header_provider="openai",
        session_active_route="gemini",
        workspace_preferred="anthropic",
    )
    assert out["provider"] == "openai"
    assert out["reason"] == "header"


def test_ac1_precedence_session_wins_over_workspace():
    out = pam.resolve_active_provider(
        session_active_route="gemini",
        workspace_preferred="anthropic",
    )
    assert out["provider"] == "gemini"
    assert out["reason"] == "session"


def test_ac1_precedence_workspace_wins_over_default():
    out = pam.resolve_active_provider(workspace_preferred="openai")
    assert out["provider"] == "openai"
    assert out["reason"] == "workspace"


def test_ac1_precedence_workspace_auto_falls_through():
    """workspace_preferred='auto' は precedence layer 3 を skip."""
    out = pam.resolve_active_provider(workspace_preferred="auto")
    assert out["provider"] == DEFAULT_PROVIDER
    assert out["reason"] == "default"


def test_ac1_precedence_byok_wins_over_default(monkeypatch):
    """BYOK key を持つ provider は default より優先."""
    from services import byok_store
    store = byok_store.get_store()
    store.set_key("alice", "openai", "sk-test-xxx")
    out = pam.resolve_active_provider(user_id="alice")
    # 既定 anthropic より BYOK openai が優先される (layer 4)
    assert out["provider"] == "openai"
    assert out["reason"] == "byok"


def test_ac1_precedence_default_when_no_signal():
    out = pam.resolve_active_provider()
    assert out["provider"] == DEFAULT_PROVIDER
    assert out["reason"] == "default"


def test_ac1_precedence_circuit_breaker_falls_back(monkeypatch):
    """anthropic_healthy=False で default(anthropic) も skip, OpenAI/Gemini fallback."""
    out = pam.resolve_active_provider(anthropic_healthy=False)
    assert out["provider"] in ("openai", "gemini")
    assert out["reason"] == "auto-fallback"


def test_ac1_precedence_returns_trace_for_observability():
    out = pam.resolve_active_provider(
        header_provider="openai",
        session_active_route="gemini",
    )
    assert "trace" in out
    assert any(t["reason"] == "header" for t in out["trace"])


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: Vault filesystem 共有 (provider 非依存)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_vault_filesystem_shared_across_providers(tmp_path, monkeypatch):
    """全 provider が同じ MemoryToolHandler (filesystem) を経由する."""
    monkeypatch.setenv("MEMORY_TOOL_DIR", str(tmp_path))
    from services.anthropic_memory_tool import MemoryToolHandler
    handler = MemoryToolHandler()
    handler.create("/memories/shared.txt", "shared-content")
    # provider に依らず読める (provider 非依存 read parity)
    for provider in ("anthropic", "openai", "gemini"):
        # tool_spec の形は異なるが backing storage は共通
        spec = pam.tool_spec_for(provider)
        assert spec is not None
        # 同じ handler 経由なので read は byte-identical
        out = handler.view("/memories/shared.txt")
        assert "shared-content" in out


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: context_editing degrade
# ══════════════════════════════════════════════════════════════════════


def test_ac3_context_editing_anthropic_native():
    cm = pam.context_editing_for("anthropic")
    assert cm["mode"] == "native"
    assert cm["use_client_side_summarizer"] is False
    assert "context_management" in cm
    assert "betas" in cm


def test_ac3_context_editing_openai_uses_truncation_auto():
    cm = pam.context_editing_for("openai")
    assert cm["mode"] == "degrade_openai"
    assert cm["truncation_strategy"] == "auto"
    assert cm["use_client_side_summarizer"] is True
    assert cm["skip_clear_thinking"] is True


def test_ac3_context_editing_gemini_uses_client_summarizer():
    cm = pam.context_editing_for("gemini")
    assert cm["mode"] == "degrade_gemini"
    assert cm["use_client_side_summarizer"] is True
    assert cm["skip_clear_thinking"] is True
    assert cm["keep_n_messages"] >= 1


def test_ac3_provider_supports_native_compaction_only_anthropic():
    assert pam.provider_supports("anthropic", "native_compaction") is True
    assert pam.provider_supports("openai", "native_compaction") is False
    assert pam.provider_supports("gemini", "native_compaction") is False


def test_ac3_provider_supports_extended_thinking_only_anthropic():
    assert pam.provider_supports("anthropic", "extended_thinking") is True
    assert pam.provider_supports("openai", "extended_thinking") is False
    assert pam.provider_supports("gemini", "extended_thinking") is False


def test_ac3_provider_supports_unknown_feature_returns_false():
    assert pam.provider_supports("anthropic", "unknown_feature") is False


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: validation + state mutate なし
# ══════════════════════════════════════════════════════════════════════


def test_ac4_validate_provider_rejects_invalid():
    for bad in ("", "  ", "unknown", None, 123):
        with pytest.raises(ProviderAdapterMemoryError):
            pam._validate_provider(bad)


def test_ac4_resolve_rejects_invalid_header_provider():
    with pytest.raises(ProviderAdapterMemoryError):
        pam.resolve_active_provider(header_provider="unknown")


def test_ac4_resolve_rejects_invalid_session_route():
    with pytest.raises(ProviderAdapterMemoryError):
        pam.resolve_active_provider(session_active_route="unknown")


def test_ac4_resolve_rejects_invalid_policy_allow():
    with pytest.raises(ProviderAdapterMemoryError):
        pam.resolve_active_provider(policy_allow=["unknown_provider"])


def test_ac4_resolve_policy_blocks_all_then_no_fallback_raises():
    """policy_allow=[] かつ anthropic_healthy=False で auto-fallback も blocked → raise."""
    with pytest.raises(ProviderAdapterMemoryError, match="no provider available"):
        pam.resolve_active_provider(
            anthropic_healthy=False,
            policy_allow=[],
        )


def test_ac4_resolve_policy_allows_only_anthropic_with_circuit_open_raises():
    """policy_allow=['anthropic'] かつ anthropic_healthy=False → unavailable."""
    with pytest.raises(ProviderAdapterMemoryError):
        pam.resolve_active_provider(
            anthropic_healthy=False,
            policy_allow=["anthropic"],
        )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: audit emit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_audit_event_for_switch_manual():
    assert pam.audit_event_for_switch("manual") == EVENT_PROVIDER_SWITCHED


def test_ac2_audit_event_for_switch_auto_fallback():
    assert pam.audit_event_for_switch("auto-fallback") == EVENT_PROVIDER_SWITCHED


def test_ac2_audit_event_for_fallback_byok_missing():
    assert pam.audit_event_for_switch("byok_missing") == EVENT_PROVIDER_FALLBACK


def test_ac2_audit_event_for_unknown_reason_raises():
    with pytest.raises(ProviderAdapterMemoryError):
        pam.audit_event_for_switch("bogus_reason")


def test_ac2_emit_switch_audit_manual(_capture_audit):
    audit_id = asyncio.run(pam.emit_switch_audit(
        from_provider="anthropic", to_provider="openai",
        reason="manual", scope="per-session",
        actor_user_id="alice",
    ))
    assert audit_id == 1
    ev = _capture_audit[0]
    assert ev["event_type"] == EVENT_PROVIDER_SWITCHED
    assert ev["detail"]["from"] == "anthropic"
    assert ev["detail"]["to"] == "openai"
    assert ev["detail"]["reason"] == "manual"
    assert ev["detail"]["scope"] == "per-session"


def test_ac2_emit_switch_audit_byok_missing_is_fallback_event(_capture_audit):
    asyncio.run(pam.emit_switch_audit(
        from_provider="anthropic", to_provider="openai",
        reason="byok_missing", scope="per-request",
    ))
    assert _capture_audit[0]["event_type"] == EVENT_PROVIDER_FALLBACK


def test_ac2_emit_switch_audit_rejects_invalid_provider():
    with pytest.raises(ProviderAdapterMemoryError):
        asyncio.run(pam.emit_switch_audit(
            from_provider="anthropic", to_provider="unknown",
            reason="manual", scope="per-session",
        ))


def test_ac2_emit_switch_within_2sec(_capture_audit):
    t0 = time.time()
    asyncio.run(pam.emit_switch_audit(
        from_provider="anthropic", to_provider="openai",
        reason="manual", scope="per-session",
    ))
    assert (time.time() - t0) < 2.0


# ══════════════════════════════════════════════════════════════════════
# REST endpoint (AC-1 / AC-2 / AC-4 4xx 統一)
# ══════════════════════════════════════════════════════════════════════


def test_endpoint_get_active_default(client):
    r = client.get("/api/providers/active")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "anthropic"
    assert body["reason"] == "default"


def test_endpoint_get_active_header_override(client):
    r = client.get(
        "/api/providers/active",
        headers={"X-LLM-Provider": "openai"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "openai"
    assert body["reason"] == "header"


def test_endpoint_get_active_session_query(client):
    r = client.get(
        "/api/providers/active",
        params={"session_active_route": "gemini"},
    )
    assert r.status_code == 200
    assert r.json()["provider"] == "gemini"


def test_endpoint_get_active_unsupported_header_400(client):
    r = client.get(
        "/api/providers/active",
        headers={"X-LLM-Provider": "unknown"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "provider.invalid"


def test_endpoint_get_active_tool_spec(client):
    r = client.get(
        "/api/providers/active/tool-spec",
        headers={"X-LLM-Provider": "openai"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "openai"
    assert isinstance(body["tool_spec"], list)
    assert len(body["tool_spec"]) == 6
    assert body["context_editing"]["mode"] == "degrade_openai"


def test_endpoint_post_active_switch_manual(client, _capture_audit):
    r = client.post("/api/providers/active", json={
        "to_provider": "openai",
        "from_provider": "anthropic",
        "scope": "per-session",
        "reason": "manual",
        "actor_user_id": "alice",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["audit_event_type"] == EVENT_PROVIDER_SWITCHED
    assert _capture_audit[-1]["event_type"] == EVENT_PROVIDER_SWITCHED


def test_endpoint_post_active_within_2sec(client, _capture_audit):
    t0 = time.time()
    r = client.post("/api/providers/active", json={
        "to_provider": "openai", "scope": "per-session", "reason": "manual",
    })
    assert r.status_code == 200
    assert (time.time() - t0) < 2.0


def test_endpoint_post_active_invalid_provider_400(client):
    r = client.post("/api/providers/active", json={
        "to_provider": "unknown", "scope": "per-session", "reason": "manual",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"


def test_endpoint_post_active_invalid_scope_400(client):
    r = client.post("/api/providers/active", json={
        "to_provider": "openai", "scope": "global", "reason": "manual",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"


def test_endpoint_post_active_invalid_reason_400(client):
    r = client.post("/api/providers/active", json={
        "to_provider": "openai", "scope": "per-session", "reason": "bogus",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"


def test_endpoint_fallback_trigger_circuit_breaker(client, _capture_audit):
    r = client.post("/api/providers/fallback/trigger", json={
        "from_provider": "anthropic", "to_provider": "openai",
        "reason": "circuit_breaker",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["audit_event_type"] == EVENT_PROVIDER_FALLBACK
    ev = _capture_audit[-1]
    assert ev["event_type"] == EVENT_PROVIDER_FALLBACK
    assert ev["detail"]["reason"] == "circuit_breaker"


def test_endpoint_fallback_trigger_invalid_reason_400(client):
    r = client.post("/api/providers/fallback/trigger", json={
        "from_provider": "anthropic", "to_provider": "openai",
        "reason": "bogus",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"


def test_endpoint_capabilities_for_anthropic(client):
    r = client.get("/api/providers/capabilities/anthropic")
    assert r.status_code == 200
    body = r.json()
    assert body["capabilities"]["memory_tool_native"] is True
    assert body["capabilities"]["native_compaction"] is True
    assert body["context_editing"]["mode"] == "native"


def test_endpoint_capabilities_for_openai(client):
    r = client.get("/api/providers/capabilities/openai")
    assert r.status_code == 200
    body = r.json()
    assert body["capabilities"]["memory_tool_native"] is False
    assert body["context_editing"]["mode"] == "degrade_openai"


def test_endpoint_capabilities_invalid_provider_400(client):
    r = client.get("/api/providers/capabilities/unknown")
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: 4xx response shape 統一
# ══════════════════════════════════════════════════════════════════════


def test_ac4_all_4xx_detail_shape(client):
    cases = [
        ("GET", "/api/providers/active",
         {"headers": {"X-LLM-Provider": "unknown"}}, 400),
        ("GET", "/api/providers/capabilities/unknown", {}, 400),
        ("POST", "/api/providers/active",
         {"json": {"to_provider": "unknown", "scope": "per-session", "reason": "manual"}}, 400),
        ("POST", "/api/providers/active",
         {"json": {"to_provider": "openai", "scope": "global", "reason": "manual"}}, 400),
        ("POST", "/api/providers/fallback/trigger",
         {"json": {"from_provider": "anthropic", "to_provider": "openai", "reason": "bogus"}}, 400),
    ]
    for method, path, kwargs, expected in cases:
        if method == "GET":
            r = client.get(path, **kwargs)
        else:
            r = client.post(path, **kwargs)
        assert r.status_code == expected, f"{path}: {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail.get("code", "").startswith("provider.")
        assert isinstance(detail.get("message", ""), str) and detail["message"]


# ══════════════════════════════════════════════════════════════════════
# Lint cross-ref (T-AI-MEM-04 self-routing 禁止)
# ══════════════════════════════════════════════════════════════════════


def test_lint_no_self_provider_routing_check_exists():
    script = (REPO_ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_no_self_provider_routing" in script
    assert "--no-self-provider-routing" in script


def test_lint_no_self_provider_routing_passes_on_clean_code():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-self-provider-routing"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout} {r.stderr}"
    assert "OK" in r.stdout


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: ADR-012 + tickets.json
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_ai_mem_04_exists():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-MEM-04"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 4
    assert "T-024-03" in t["deps"]


def test_adr_012_decision_5_precedence_documented():
    adr = REPO_ROOT / "docs" / "decisions" / "ADR-012-anthropic-memory-tool-adoption.md"
    text = adr.read_text(encoding="utf-8")
    text_l = text.lower()
    assert "Decision 5" in text
    assert "precedence" in text
    # 6 layers が全て出現 (文言ゆれ吸収: circuit-breaker / circuit_breaker)
    for layer in ("header", "session", "workspace", "byok", "default", "circuit"):
        assert layer in text_l, f"ADR-012 missing precedence layer: {layer}"


def test_module_docstring_documents_t_ai_mem_04():
    doc = pam.__doc__ or ""
    assert "T-AI-MEM-04" in doc
    assert "ADR-012 Decision 5" in doc
    assert "precedence" in doc
