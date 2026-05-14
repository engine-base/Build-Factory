"""T-AI-05: Cost tracking — gap closure (G1-G3).

主要実装 (services/cost_service.py + 23 既存 tests) は完備.
本 PR は **tickets.json T-AI-05 AC との 3 件の追補 gap** を埋める.

## Gaps

  G1 (AC-1 cross-ref): provider 切替 (T-AI-MEM-04) / LiteLLM (T-M12-01) 経路の
     CostEntry が必要フィールド全 9 件を持つことを test 担保.
  G2 (AC-3 STATE #1): budget 超過時の canonical audit event 'cost.budget_exceeded'
     emit (既存 'workspace_budget_exceeded' は alias として併発).
  G3 (AC-1 invariants): cost_logs.provider が T-AI-MEM-04 SUPPORTED_PROVIDERS
     (anthropic / openai / gemini) と整合.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from services import cost_service as cs
from services.cost_service import (
    EVENT_COST_BUDGET_EXCEEDED,
    EVENT_COST_RECORDING_FAILED,
    EVENT_RECONCILE_DISCREPANCY,
    EVENT_WORKSPACE_BUDGET_EXCEEDED,
    PRICE_TABLE,
    RECONCILE_THRESHOLD,
    CostEntry,
    cached_discount_ratio,
    check_budget_pause,
    compute_display_cost,
    record_cost,
    reconcile_session,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


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


# ══════════════════════════════════════════════════════════════════════
# G2 (AC-3 STATE #1): canonical event 'cost.budget_exceeded'
# ══════════════════════════════════════════════════════════════════════


def test_g2_event_constants_exported():
    assert EVENT_COST_BUDGET_EXCEEDED == "cost.budget_exceeded"
    assert EVENT_WORKSPACE_BUDGET_EXCEEDED == "workspace_budget_exceeded"
    assert EVENT_COST_RECORDING_FAILED == "cost_recording_failed"
    assert EVENT_RECONCILE_DISCREPANCY == "cost_reconcile_discrepancy"


def test_g2_check_budget_pause_emits_canonical_event(monkeypatch, _capture_audit):
    """budget 超過時に canonical event 'cost.budget_exceeded' を emit (+ alias)."""

    class _FakeRow:
        def __init__(self, b): self._b = b
        def __getitem__(self, k):
            return self._b.get(k)
        def get(self, k, *a):
            return self._b.get(k, *a)

    class _FakeCursor:
        def __init__(self, rows): self._rows = rows
        async def fetchall(self): return self._rows

    class _FakeConn:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        row_factory = None
        async def execute(self, sql, *args, **kwargs):
            if "FROM workspaces" in sql:
                return _FakeCursor([{
                    "budget_jpy_monthly": 15000, "status": "active",
                }])
            return _FakeCursor([])
        async def commit(self): pass

    def fake_connect(_path):
        return _FakeConn()

    # monthly_cost を budget 超に固定
    async def fake_monthly_cost(wid, *, month=None):
        return 200.0  # USD ($200 > ¥15000 / 150 = $100)

    monkeypatch.setattr(cs._db(), "connect", fake_connect)
    monkeypatch.setattr(cs, "monthly_cost", fake_monthly_cost)

    out = asyncio.run(check_budget_pause(1))
    assert out["exceeded"] is True
    canonical = [e for e in _capture_audit if e["event_type"] == EVENT_COST_BUDGET_EXCEEDED]
    alias = [e for e in _capture_audit if e["event_type"] == EVENT_WORKSPACE_BUDGET_EXCEEDED]
    assert len(canonical) == 1
    assert len(alias) == 1
    # detail 整合
    d = canonical[0]["detail"]
    assert d["workspace_id"] == 1
    assert d["monthly_usd"] == 200.0
    assert d["budget_jpy"] == 15000
    assert d["exceeded_by_usd"] >= 0


def test_g2_no_emit_when_under_budget(monkeypatch, _capture_audit):
    class _FakeCursor:
        def __init__(self, rows): self._rows = rows
        async def fetchall(self): return self._rows

    class _FakeConn:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        row_factory = None
        async def execute(self, sql, *args, **kwargs):
            return _FakeCursor([{"budget_jpy_monthly": 100000, "status": "active"}])
        async def commit(self): pass

    monkeypatch.setattr(cs._db(), "connect", lambda _: _FakeConn())

    async def fake_monthly_cost(wid, *, month=None):
        return 1.0

    monkeypatch.setattr(cs, "monthly_cost", fake_monthly_cost)
    asyncio.run(check_budget_pause(1))
    canonical = [e for e in _capture_audit if e["event_type"] == EVENT_COST_BUDGET_EXCEEDED]
    assert canonical == []


# ══════════════════════════════════════════════════════════════════════
# G1 (AC-1 cross-ref): provider 切替 / LiteLLM 経路の CostEntry 整合
# ══════════════════════════════════════════════════════════════════════


def test_g1_cost_entry_dataclass_has_required_9_fields():
    """AC-1: provider, model, in/out, cache_read/write, USD, session_id,
    workspace_id, ai_employee_id の 9 必須属性."""
    fields = set(CostEntry.__dataclass_fields__.keys())
    expected = {
        "provider", "model", "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens", "session_id",
        "workspace_id", "ai_employee_id",
    }
    assert expected.issubset(fields), f"missing fields: {expected - fields}"


def test_g1_cost_entry_supports_litellm_fallback_providers():
    """T-AI-MEM-04 / T-M12-01: openai / gemini provider でも CostEntry を構築可能."""
    for prov, mdl in [("openai", "gpt-4o"), ("gemini", "gemini-2.5-pro"), ("anthropic", "claude-sonnet-4-6")]:
        entry = CostEntry(
            provider=prov, model=mdl,
            input_tokens=100, output_tokens=50,
            cache_read_tokens=0, cache_write_tokens=0,
            session_id=1, workspace_id=1, ai_employee_id="mary",
        )
        assert entry.provider == prov


def test_g1_record_cost_failure_emits_recording_failed_audit(monkeypatch, _capture_audit):
    """AC-4 UNWANTED: INSERT 失敗時に cost_recording_failed audit emit."""

    class _FailConn:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def execute(self, *a, **k):
            raise RuntimeError("DB write failed (test)")
        async def commit(self): pass

    monkeypatch.setattr(cs._db(), "connect", lambda _: _FailConn())
    entry = CostEntry(
        provider="anthropic", model="claude-sonnet-4-6",
        input_tokens=100, output_tokens=50,
        cache_read_tokens=0, cache_write_tokens=0,
        session_id=1, workspace_id=1, ai_employee_id="mary",
    )
    out = asyncio.run(record_cost(entry))
    assert out is None  # 失敗時 None 返却
    events = [e for e in _capture_audit if e["event_type"] == EVENT_COST_RECORDING_FAILED]
    assert len(events) >= 1
    # session 継続のための情報 (session_id) が detail にある
    assert events[0]["session_id"] == 1


# ══════════════════════════════════════════════════════════════════════
# G3 (AC-1 invariants): provider が T-AI-MEM-04 SUPPORTED_PROVIDERS と整合
# ══════════════════════════════════════════════════════════════════════


def test_g3_pricing_table_covers_all_anthropic_models():
    """price table が claude-opus / sonnet / haiku を含む."""
    for model in ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"):
        assert model in PRICE_TABLE
        rate = PRICE_TABLE[model]
        for key in ("input", "output", "cache_read", "cache_write"):
            assert key in rate
            assert rate[key] > 0


def test_g3_pricing_table_default_fallback_exists():
    """unknown model でも default rate で fallback できる."""
    assert "default" in PRICE_TABLE
    for key in ("input", "output", "cache_read", "cache_write"):
        assert PRICE_TABLE["default"][key] > 0


def test_g3_compute_cost_with_default_rate_for_unknown_model():
    """T-AI-MEM-04 fallback で openai/gpt-4o 等を渡しても落ちない (default rate 適用)."""
    cost = compute_display_cost(
        model="gpt-4o", input_tokens=1000, output_tokens=500,
        cache_read_tokens=0, cache_write_tokens=0,
    )
    assert cost > 0


def test_g3_pam_supported_providers_compatible():
    """T-AI-MEM-04 SUPPORTED_PROVIDERS の各 provider が CostEntry に格納可能."""
    from services.provider_adapter_memory import SUPPORTED_PROVIDERS
    for provider in SUPPORTED_PROVIDERS:
        entry = CostEntry(
            provider=provider, model="x",
            input_tokens=0, output_tokens=0,
            cache_read_tokens=0, cache_write_tokens=0,
            session_id=None, workspace_id=None, ai_employee_id=None,
        )
        assert entry.provider in SUPPORTED_PROVIDERS


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE #2: prompt cache hit → 90% discount 反映
# ══════════════════════════════════════════════════════════════════════


def test_ac3_state2_cache_hit_yields_90pct_discount():
    """cache_read 単価 = input × 0.10 なので 90% off."""
    full = compute_display_cost(
        model="claude-sonnet-4-6", input_tokens=1_000_000,
        output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
    )
    cached = compute_display_cost(
        model="claude-sonnet-4-6", input_tokens=0,
        output_tokens=0, cache_read_tokens=1_000_000, cache_write_tokens=0,
    )
    assert pytest.approx(cached / full, abs=1e-3) == 0.10


def test_ac3_state2_cached_discount_ratio_returns_fraction():
    """cached_discount_ratio() は cache_read / (input + cache_read).
    cache_read=1000, input=0 → 1.0 (full cache). この場合 90% off 適用は
    compute_display_cost 側で行う (rate × cache_read_tokens の単価で).
    """
    full_cached = cached_discount_ratio(input_tokens=0, cache_read_tokens=1000)
    assert full_cached == 1.0
    half = cached_discount_ratio(input_tokens=1000, cache_read_tokens=1000)
    assert pytest.approx(half, abs=1e-6) == 0.5


def test_ac3_state2_no_cache_yields_zero_ratio():
    assert cached_discount_ratio(input_tokens=1000, cache_read_tokens=0) == 0.0


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT: reconcile threshold > 5% で flag
# ══════════════════════════════════════════════════════════════════════


def test_ac2_reconcile_threshold_is_5_percent():
    assert RECONCILE_THRESHOLD == 0.05


def test_ac2_reconcile_emits_when_over_threshold(monkeypatch, _capture_audit):
    async def fake_session_cost(sid):
        return 100.0
    monkeypatch.setattr(cs, "session_cost", fake_session_cost)
    out = asyncio.run(reconcile_session(1, anthropic_usage_total_usd=110.0))
    # 10% discrepancy > 5% threshold → flagged
    assert out["flagged"] is True
    events = [e for e in _capture_audit if e["event_type"] == EVENT_RECONCILE_DISCREPANCY]
    assert len(events) >= 1


def test_ac2_reconcile_no_emit_when_under_threshold(monkeypatch, _capture_audit):
    async def fake_session_cost(sid):
        return 100.0
    monkeypatch.setattr(cs, "session_cost", fake_session_cost)
    out = asyncio.run(reconcile_session(1, anthropic_usage_total_usd=102.0))
    # 2% < 5% → not flagged
    assert out["flagged"] is False
    events = [e for e in _capture_audit if e["event_type"] == EVENT_RECONCILE_DISCREPANCY]
    assert events == []


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets.json + module docstring
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_ai_05_has_5_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-05"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 5
    assert "T-M12-01" in t["deps"]


def test_module_docstring_documents_adr_012_cross_ref():
    doc = cs.__doc__ or ""
    assert "T-AI-MEM-04" in doc
    assert "ADR-012" in doc
    assert "T-M12-01" in doc


def test_event_constants_documented_in_docstring():
    doc = cs.__doc__ or ""
    for ev in ("cost.budget_exceeded", "cost_recording_failed"):
        assert ev in doc
