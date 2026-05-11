"""T-AI-05: Cost tracking — 5 AC 全網羅."""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from services import cost_service as cs
from services.cost_service import (
    CostEntry, PRICE_TABLE, RECONCILE_THRESHOLD,
    cached_discount_ratio, compute_display_cost,
    record_cost, monthly_cost, session_cost,
    check_budget_pause, reconcile_session,
)


# ──────────────────────────────────────────────────────────────────────────
# Fake DB
# ──────────────────────────────────────────────────────────────────────────


class _Cur:
    def __init__(self, rows=None, lastrowid=0):
        self._rows = rows or []
        self.lastrowid = lastrowid

    async def fetchall(self): return self._rows
    async def fetchone(self): return self._rows[0] if self._rows else None


class _Conn:
    Row = dict

    def __init__(self, *,
                  monthly_total=0.0, session_total=0.0,
                  workspace_row=None,
                  raise_on_insert=False):
        self._monthly_total = monthly_total
        self._session_total = session_total
        self._workspace_row = workspace_row
        self._raise_on_insert = raise_on_insert
        self.row_factory = None
        self.executed: list[tuple[str, tuple]] = []

    async def execute(self, sql, args=()):
        self.executed.append((sql, args))
        s = sql.lower()
        if "insert into cost_logs" in s:
            if self._raise_on_insert:
                raise RuntimeError("db insert failed")
            return _Cur(lastrowid=42)
        if "sum(cost_usd)" in s and "workspace_id" in s:
            return _Cur(rows=[{"total": self._monthly_total}])
        if "sum(cost_usd)" in s and "session_id" in s:
            return _Cur(rows=[{"total": self._session_total}])
        if "select budget_jpy_monthly" in s:
            return _Cur(rows=[self._workspace_row] if self._workspace_row else [])
        if "update workspaces" in s:
            return _Cur(lastrowid=0)
        return _Cur()

    async def commit(self): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


def _patch_cs_db(monkeypatch, **kwargs) -> _Conn:
    conn = _Conn(**kwargs)
    fake_mod = types.SimpleNamespace(connect=lambda _p: conn, Row=dict)
    monkeypatch.setattr(cs, "_db", lambda: fake_mod)
    monkeypatch.setattr(cs, "_db_path", lambda: ":memory:")
    return conn


def _install_audit_recorder():
    captured: list[dict] = []
    mod = types.ModuleType("services.memory_service")

    async def emit_event(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event": event_type, "session_id": session_id,
            "detail": detail or {},
        })

    mod.emit_event = emit_event
    sys.modules["services.memory_service"] = mod
    return captured


# ──────────────────────────────────────────────────────────────────────────
# AC-UBIQUITOUS: 1 call = 1 cost_logs row
# ──────────────────────────────────────────────────────────────────────────


def test_record_cost_inserts_into_cost_logs(monkeypatch) -> None:
    fake = _patch_cs_db(monkeypatch)
    rid = asyncio.run(record_cost(CostEntry(
        session_id=1, workspace_id=10,
        provider="anthropic", model="claude-sonnet-4-6",
        input_tokens=100, output_tokens=50,
        cache_read_tokens=80, cache_write_tokens=20,
        cost_usd=0.0012345,
        ai_employee_id="mary",
    )))
    assert rid == 42
    # INSERT が呼ばれた + 全 column が含まれる
    inserts = [(s, p) for s, p in fake.executed if "insert into cost_logs" in s.lower()]
    assert len(inserts) == 1
    _, params = inserts[0]
    # 順序: session, workspace, provider, model, in, out, cache_r, cache_w, cost, metadata
    assert params[0] == 1
    assert params[1] == 10
    assert params[2] == "anthropic"
    assert params[3] == "claude-sonnet-4-6"
    assert params[4] == 100
    assert params[5] == 50
    assert params[6] == 80
    assert params[7] == 20
    assert params[8] == 0.0012345
    # ai_employee_id は metadata JSON
    assert "mary" in params[9]


def test_record_cost_skips_completely_empty_entry(monkeypatch) -> None:
    """0 token / 0 USD のエントリは記録しない (誤計測防止)."""
    fake = _patch_cs_db(monkeypatch)
    rid = asyncio.run(record_cost(CostEntry(
        session_id=1, workspace_id=10,
        provider="anthropic", model="claude-sonnet-4-6",
    )))
    assert rid is None
    inserts = [(s, p) for s, p in fake.executed if "insert into cost_logs" in s.lower()]
    assert inserts == []


# ──────────────────────────────────────────────────────────────────────────
# AC-STATE (cache): cache_read >0 で 90% discount 反映
# ──────────────────────────────────────────────────────────────────────────


def test_compute_display_cost_sonnet_pricing() -> None:
    """Sonnet 4.6: input $3 / output $15 / cache_read $0.30 per 1M."""
    cost = compute_display_cost(
        model="claude-sonnet-4-6",
        input_tokens=1_000_000, output_tokens=0,
    )
    assert cost == pytest.approx(3.0, abs=0.001)


def test_compute_display_cost_cache_read_is_90_percent_off() -> None:
    """1M cache_read = $0.30 ≒ 1M input ($3.0) の 10% (90% 引き)."""
    cached = compute_display_cost(
        model="claude-sonnet-4-6",
        input_tokens=0, output_tokens=0,
        cache_read_tokens=1_000_000,
    )
    uncached = compute_display_cost(
        model="claude-sonnet-4-6",
        input_tokens=1_000_000, output_tokens=0,
    )
    assert cached == pytest.approx(uncached * 0.10, abs=0.001)


def test_compute_display_cost_cache_write_premium() -> None:
    """cache_write は input の 1.25× (cache 書き込みプレミアム)."""
    cache_w = compute_display_cost(
        model="claude-sonnet-4-6",
        input_tokens=0, output_tokens=0,
        cache_write_tokens=1_000_000,
    )
    input_only = compute_display_cost(
        model="claude-sonnet-4-6",
        input_tokens=1_000_000, output_tokens=0,
    )
    assert cache_w == pytest.approx(input_only * 1.25, abs=0.001)


def test_compute_display_cost_unknown_model_uses_default() -> None:
    """未知 model は default 価格に fallback."""
    cost = compute_display_cost(
        model="some-future-model",
        input_tokens=1_000_000, output_tokens=0,
    )
    # default = sonnet 価格
    assert cost == pytest.approx(3.0, abs=0.001)


def test_compute_display_cost_opus_more_expensive_than_haiku() -> None:
    same_tokens = dict(input_tokens=1_000_000, output_tokens=1_000_000)
    opus = compute_display_cost(model="claude-opus-4-7", **same_tokens)
    haiku = compute_display_cost(model="claude-haiku-4-5", **same_tokens)
    assert opus > haiku


def test_cached_discount_ratio_calculation() -> None:
    """cache_read / (input + cache_read) で 0-1 の比率."""
    assert cached_discount_ratio(input_tokens=100, cache_read_tokens=400) == 0.8
    assert cached_discount_ratio(input_tokens=0, cache_read_tokens=0) == 0.0
    assert cached_discount_ratio(input_tokens=1000, cache_read_tokens=0) == 0.0
    assert cached_discount_ratio(input_tokens=0, cache_read_tokens=100) == 1.0


def test_price_table_has_required_models() -> None:
    """全 4 model + default が定義されている."""
    for model in ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5", "default"):
        assert model in PRICE_TABLE
        rate = PRICE_TABLE[model]
        for key in ("input", "output", "cache_read", "cache_write"):
            assert key in rate
            assert rate[key] > 0


# ──────────────────────────────────────────────────────────────────────────
# AC-EVENT: reconcile with Anthropic Usage API
# ──────────────────────────────────────────────────────────────────────────


def test_reconcile_session_within_threshold_not_flagged(monkeypatch) -> None:
    """internal $1.00 vs anthropic $1.03 → 3% 差 (<5%) で flag false."""
    _patch_cs_db(monkeypatch, session_total=1.00)
    out = asyncio.run(reconcile_session(session_id=1, anthropic_usage_total_usd=1.03))
    assert out["discrepancy_ratio"] < RECONCILE_THRESHOLD
    assert out["flagged"] is False


def test_reconcile_session_over_threshold_flagged_and_audit(monkeypatch) -> None:
    """internal $1.00 vs anthropic $1.20 → 16.7% 差 (>5%) で flagged + audit emit."""
    _patch_cs_db(monkeypatch, session_total=1.00)
    captured = _install_audit_recorder()
    try:
        out = asyncio.run(reconcile_session(session_id=5, anthropic_usage_total_usd=1.20))
        assert out["flagged"] is True
        assert out["discrepancy_ratio"] > 0.05
        assert any(e["event"] == "cost_reconcile_discrepancy" for e in captured)
    finally:
        sys.modules.pop("services.memory_service", None)


def test_reconcile_zero_anthropic_usage_returns_zero_ratio(monkeypatch) -> None:
    _patch_cs_db(monkeypatch, session_total=1.00)
    out = asyncio.run(reconcile_session(session_id=1, anthropic_usage_total_usd=0.0))
    assert out["discrepancy_ratio"] == 0.0
    assert out["flagged"] is False


# ──────────────────────────────────────────────────────────────────────────
# AC-STATE: monthly budget exceed → pause + notify
# ──────────────────────────────────────────────────────────────────────────


def test_check_budget_pause_triggers_when_over_budget(monkeypatch) -> None:
    """budget = ¥30,000 ($200) / 月次 = $300 → exceeded + pause."""
    captured = _install_audit_recorder()
    fake = _patch_cs_db(
        monkeypatch,
        monthly_total=300.0,
        workspace_row={"budget_jpy_monthly": 30000, "status": "active"},
    )
    try:
        out = asyncio.run(check_budget_pause(workspace_id=1))
        assert out["exceeded"] is True
        assert out["pause_triggered"] is True
        # workspace UPDATE が走った
        assert any("update workspaces" in s.lower() for s, _ in fake.executed)
        # audit event
        assert any(e["event"] == "workspace_budget_exceeded" for e in captured)
    finally:
        sys.modules.pop("services.memory_service", None)


def test_check_budget_pause_under_budget(monkeypatch) -> None:
    _patch_cs_db(
        monkeypatch,
        monthly_total=50.0,  # $50
        workspace_row={"budget_jpy_monthly": 30000, "status": "active"},  # ¥30,000 ≒ $200
    )
    out = asyncio.run(check_budget_pause(workspace_id=1))
    assert out["exceeded"] is False
    assert out["pause_triggered"] is False


def test_check_budget_pause_no_budget_set(monkeypatch) -> None:
    """budget_jpy_monthly = 0 (未設定) なら exceeded=False."""
    _patch_cs_db(
        monkeypatch,
        monthly_total=999.0,
        workspace_row={"budget_jpy_monthly": 0, "status": "active"},
    )
    out = asyncio.run(check_budget_pause(workspace_id=1))
    assert out["exceeded"] is False


def test_check_budget_pause_unknown_workspace(monkeypatch) -> None:
    _patch_cs_db(monkeypatch, workspace_row=None)
    out = asyncio.run(check_budget_pause(workspace_id=999))
    assert out["exceeded"] is False
    assert out["pause_triggered"] is False


# ──────────────────────────────────────────────────────────────────────────
# AC-UNWANTED: 記録失敗 → session 継続 + cost_recording_failed audit
# ──────────────────────────────────────────────────────────────────────────


def test_record_cost_failure_emits_audit_and_returns_none(monkeypatch) -> None:
    captured = _install_audit_recorder()
    _patch_cs_db(monkeypatch, raise_on_insert=True)
    try:
        rid = asyncio.run(record_cost(CostEntry(
            session_id=7, workspace_id=10,
            provider="anthropic", model="claude-sonnet-4-6",
            input_tokens=100, cost_usd=0.001,
        )))
        assert rid is None  # 失敗
        # audit event 発火
        assert any(e["event"] == "cost_recording_failed" for e in captured)
        ev = next(e for e in captured if e["event"] == "cost_recording_failed")
        assert ev["session_id"] == 7
        assert "anthropic" in str(ev["detail"])
    finally:
        sys.modules.pop("services.memory_service", None)


def test_record_cost_audit_failure_does_not_crash(monkeypatch) -> None:
    """audit emit が落ちても record_cost が例外を伝播させない."""
    _patch_cs_db(monkeypatch, raise_on_insert=True)
    mod = types.ModuleType("services.memory_service")

    async def boom(*a, **kw):
        raise RuntimeError("audit down")

    mod.emit_event = boom
    sys.modules["services.memory_service"] = mod
    try:
        rid = asyncio.run(record_cost(CostEntry(
            session_id=1, workspace_id=1,
            provider="anthropic", model="claude-sonnet-4-6",
            input_tokens=10, cost_usd=0.001,
        )))
        assert rid is None
    finally:
        sys.modules.pop("services.memory_service", None)


# ──────────────────────────────────────────────────────────────────────────
# Aggregation helpers
# ──────────────────────────────────────────────────────────────────────────


def test_monthly_cost_returns_sum(monkeypatch) -> None:
    _patch_cs_db(monkeypatch, monthly_total=42.5)
    total = asyncio.run(monthly_cost(workspace_id=1))
    assert total == 42.5


def test_monthly_cost_with_explicit_month(monkeypatch) -> None:
    fake = _patch_cs_db(monkeypatch, monthly_total=10.0)
    asyncio.run(monthly_cost(workspace_id=1, month="2026-04"))
    # SELECT 引数に "2026-04" が渡る
    selects = [p for s, p in fake.executed if "sum(cost_usd)" in s.lower() and "substr" in s.lower()]
    assert selects[0][1] == "2026-04"


def test_monthly_cost_returns_zero_on_db_error(monkeypatch) -> None:
    class _ErrConn(_Conn):
        async def execute(self, sql, args=()):
            raise RuntimeError("db down")

    fake_mod = types.SimpleNamespace(connect=lambda _p: _ErrConn(), Row=dict)
    monkeypatch.setattr(cs, "_db", lambda: fake_mod)
    monkeypatch.setattr(cs, "_db_path", lambda: ":memory:")
    total = asyncio.run(monthly_cost(workspace_id=1))
    assert total == 0.0


def test_session_cost_returns_sum(monkeypatch) -> None:
    _patch_cs_db(monkeypatch, session_total=3.14)
    out = asyncio.run(session_cost(session_id=1))
    assert out == 3.14


def test_session_cost_returns_zero_on_db_error(monkeypatch) -> None:
    class _ErrConn(_Conn):
        async def execute(self, sql, args=()):
            raise RuntimeError("db down")

    fake_mod = types.SimpleNamespace(connect=lambda _p: _ErrConn(), Row=dict)
    monkeypatch.setattr(cs, "_db", lambda: fake_mod)
    monkeypatch.setattr(cs, "_db_path", lambda: ":memory:")
    assert asyncio.run(session_cost(1)) == 0.0
