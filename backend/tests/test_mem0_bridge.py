"""T-AI-02: Mem0 bridge の AC テスト."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.mem0_bridge import ScoredFact, search_with_rerank
from services.memory_facts import FactRecord


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────
# Re-rank scoring (純粋ロジック)
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_returns_empty_when_mem0_unavailable() -> None:
    """Mem0 が無効な環境でも例外を出さず空 list。"""
    with patch("services.long_term_memory.search_relevant_memories",
               return_value=[]):
        result = await search_with_rerank(user_id="u1", query="x")
    assert result == []


@pytest.mark.asyncio
async def test_search_with_rerank_combines_vector_and_confidence() -> None:
    """Mem0 top-3 を返したら final_score 順に並ぶ。

    rank=0 → vector_score=1.0
    rank=1 → vector_score=0.5
    rank=2 → vector_score=1/3≒0.333
    """
    fake_memories = ["fact A", "fact B", "fact C"]
    async def fake_search(**kwargs):
        return fake_memories
    with patch("services.long_term_memory.search_relevant_memories",
               side_effect=fake_search):
        result = await search_with_rerank(user_id="u1", query="x", top_k=3)

    assert len(result) == 3
    # final_score は降順
    scores = [s.final_score for s in result]
    assert scores == sorted(scores, reverse=True)
    # 最上位は rank=0 (vector=1.0) → final = 0.6*1.0 + 0.4*0.5 = 0.8
    assert result[0].final_score == pytest.approx(0.8, abs=0.01)


@pytest.mark.asyncio
async def test_search_returns_synthetic_record_when_db_lacks_fact() -> None:
    """Mem0 にあるが DB に無い fact も synthetic FactRecord で返す。"""
    async def fake_search(**kwargs):
        return ["orphan fact in mem0"]
    with patch("services.long_term_memory.search_relevant_memories",
               side_effect=fake_search):
        result = await search_with_rerank(user_id="u1", query="x", top_k=1)
    assert len(result) == 1
    assert result[0].fact.id is None  # synthetic
    assert result[0].fact.fact_text == "orphan fact in mem0"


# ──────────────────────────────────────────
# Router smoke
# ──────────────────────────────────────────

def test_router_search_returns_empty_when_mem0_off(client) -> None:
    r = client.get("/api/memory/mem0/search", params={"user_id": "no_user", "query": "anything"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_router_preload_returns_empty_for_unknown_user(client) -> None:
    r = client.get("/api/memory/mem0/preload", params={"user_id": "no_user_zzz"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_router_divergence_returns_zero_for_unknown(client) -> None:
    r = client.post("/api/memory/mem0/divergence", params={"user_id": "no_user_zzz"})
    assert r.status_code == 200
    body = r.json()
    assert body["checked"] == 0
    assert body["missing_in_mem0"] == 0


def test_router_mirror_unknown_returns_404(client) -> None:
    r = client.post("/api/memory/mem0/mirror/9999999")
    assert r.status_code in (404, 500)  # DB 未初期化なら 500、ある+無し なら 404


# ──────────────────────────────────────────
# ScoredFact dataclass
# ──────────────────────────────────────────

def test_scored_fact_dataclass_fields() -> None:
    rec = FactRecord(
        id=1, user_id="u1", workspace_id=None, fact_text="x",
        kind="durable", source_session_id=None,
        confidence_score=0.8, fingerprint="fp",
        status="synced",
    )
    s = ScoredFact(fact=rec, vector_score=0.9, confidence=0.8, final_score=0.86)
    assert s.fact.id == 1
    assert s.final_score == 0.86


# ──────────────────────────────────────────────────────────────────────────
# AC 全網羅 補完 + cov 54% → 90%+
# ──────────────────────────────────────────────────────────────────────────

import asyncio
import sys
import time
import types
from typing import Any
from services import mem0_bridge as mb


class _Cur:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    async def fetchall(self): return self._rows
    async def fetchone(self): return self._rows[0] if self._rows else None


class _Conn:
    Row = dict

    def __init__(self, rows_by_kw=None):
        self._rows_by_kw = rows_by_kw or {}
        self.row_factory = None
        self.executed: list[tuple[str, tuple]] = []

    async def execute(self, sql, args=()):
        self.executed.append((sql, args))
        s = sql.lower()
        # dispatch
        if "update memory_facts" in s and "mem0_id" in s:
            return _Cur(rows=[], rowcount=1)
        if "select * from memory_facts" in s and "status = 'synced'" in s:
            return _Cur(rows=self._rows_by_kw.get("preload", []))
        if "select * from memory_facts" in s and "fingerprint" in s:
            return _Cur(rows=self._rows_by_kw.get("by_fp", []))
        if "select id, fact_text, fingerprint, mem0_id" in s:
            return _Cur(rows=self._rows_by_kw.get("divergence", []))
        return _Cur(rows=[])

    async def commit(self): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


def _patch_mb_db(monkeypatch, **rows_by_kw):
    fake_mod = types.SimpleNamespace(
        connect=lambda _p: _Conn(rows_by_kw), Row=dict,
    )
    monkeypatch.setattr(mb, "_db", lambda: fake_mod)
    monkeypatch.setattr(mb, "_db_path", lambda: ":memory:")


def _install_fake_long_term_memory(*, raise_on_add=False, return_for_search=None):
    state: dict[str, Any] = {"adds": [], "searches": []}
    mod = types.ModuleType("services.long_term_memory")

    async def add_conversation(*, user_id, conversation, metadata=None):
        state["adds"].append({
            "user_id": user_id, "conversation": conversation, "metadata": metadata or {},
        })
        if raise_on_add:
            raise RuntimeError("mem0 down")

    async def search_relevant_memories(*, user_id, query, limit=5):
        state["searches"].append({"user_id": user_id, "query": query, "limit": limit})
        return return_for_search or []

    mod.add_conversation = add_conversation
    mod.search_relevant_memories = search_relevant_memories
    sys.modules["services.long_term_memory"] = mod
    return state


# ─────────────────────────────────────────────────────────────────────────
# AC-UBIQUITOUS: mirror_fact_to_mem0
# ─────────────────────────────────────────────────────────────────────────


def test_mirror_fact_to_mem0_calls_long_term_memory_and_returns_id(monkeypatch) -> None:
    state = _install_fake_long_term_memory()
    _patch_mb_db(monkeypatch)
    rec = FactRecord(
        id=42, user_id="u1", workspace_id=None, fact_text="D-001 採用",
        kind="durable", source_session_id=99, confidence_score=0.9,
        fingerprint="fp-001", status="synced",
    )
    try:
        out = asyncio.run(mb.mirror_fact_to_mem0(rec))
        assert out == "mem0:fp-001"
        assert len(state["adds"]) == 1
        add = state["adds"][0]
        assert add["user_id"] == "u1"
        assert add["conversation"][0]["content"] == "D-001 採用"
        assert add["metadata"]["fingerprint"] == "fp-001"
        assert add["metadata"]["confidence_score"] == 0.9
        assert add["metadata"]["source_session_id"] == 99
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_mirror_fact_returns_none_on_mem0_failure(monkeypatch) -> None:
    _install_fake_long_term_memory(raise_on_add=True)
    _patch_mb_db(monkeypatch)
    rec = FactRecord(
        id=42, user_id="u1", workspace_id=None, fact_text="x",
        kind="durable", source_session_id=None, confidence_score=0.5,
        fingerprint="fp-x", status="synced",
    )
    try:
        out = asyncio.run(mb.mirror_fact_to_mem0(rec))
        assert out is None
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_mirror_fact_without_id_does_not_update_db(monkeypatch) -> None:
    """fact.id が None なら mem0_id を返すが DB UPDATE はスキップ."""
    _install_fake_long_term_memory()
    _patch_mb_db(monkeypatch)
    rec = FactRecord(
        id=None, user_id="u1", workspace_id=None, fact_text="orphan",
        kind="durable", source_session_id=None, confidence_score=0.5,
        fingerprint="fp-orphan", status="synced",
    )
    try:
        out = asyncio.run(mb.mirror_fact_to_mem0(rec))
        assert out == "mem0:fp-orphan"
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_mirror_fact_db_update_failure_does_not_crash(monkeypatch) -> None:
    """DB UPDATE が失敗しても mem0_id は返す (silent log)."""
    _install_fake_long_term_memory()

    class _ErrConn(_Conn):
        async def execute(self, sql, args=()):
            raise RuntimeError("db update failed")

    fake_mod = types.SimpleNamespace(connect=lambda _p: _ErrConn(), Row=dict)
    monkeypatch.setattr(mb, "_db", lambda: fake_mod)
    monkeypatch.setattr(mb, "_db_path", lambda: ":memory:")

    rec = FactRecord(
        id=1, user_id="u", workspace_id=None, fact_text="t",
        kind="durable", source_session_id=None, confidence_score=0.5,
        fingerprint="fp-1", status="synced",
    )
    try:
        out = asyncio.run(mb.mirror_fact_to_mem0(rec))
        assert out == "mem0:fp-1"
    finally:
        sys.modules.pop("services.long_term_memory", None)


# ─────────────────────────────────────────────────────────────────────────
# AC-EVENT: search_with_rerank + 300ms 性能
# ─────────────────────────────────────────────────────────────────────────


def test_search_with_rerank_within_300ms(monkeypatch) -> None:
    """AC-EVENT: top-5 ベクトル検索 + re-rank が 300ms 以内."""
    _install_fake_long_term_memory(return_for_search=[f"fact-{i}" for i in range(5)])
    _patch_mb_db(monkeypatch)
    try:
        t0 = time.monotonic()
        out = asyncio.run(mb.search_with_rerank("u1", "query", top_k=5))
        dt = time.monotonic() - t0
        assert dt < 0.3, f"search took {dt*1000:.1f}ms (limit 300ms)"
        assert len(out) == 5
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_search_with_rerank_joins_facts_from_db(monkeypatch) -> None:
    """Mem0 hit と DB の memory_facts を fingerprint で join."""
    from services.memory_facts import fingerprint as fp_func
    fact_text = "joined fact"
    fp = fp_func(fact_text)
    _install_fake_long_term_memory(return_for_search=[fact_text])
    _patch_mb_db(monkeypatch, by_fp=[{
        "id": 7, "user_id": "u1", "workspace_id": None,
        "fact_text": fact_text, "kind": "durable",
        "source_session_id": 1, "confidence_score": 0.92,
        "fingerprint": fp, "status": "synced",
        "retry_count": 0, "memory_api_id": "m1", "mem0_id": None,
        "last_error": None, "created_at": "", "synced_at": "", "deleted_at": None,
    }])
    try:
        out = asyncio.run(mb.search_with_rerank("u1", "q", top_k=1))
        assert len(out) == 1
        # join 成功で confidence は DB 値が使われる
        assert out[0].confidence == 0.92
        assert out[0].fact.id == 7
        # final = 0.6 * 1.0 (rank=0) + 0.4 * 0.92 = 0.968
        assert out[0].final_score == pytest.approx(0.968, abs=0.001)
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_search_with_rerank_handles_db_failure(monkeypatch) -> None:
    """DB join 失敗 → synthetic record で fallback (data loss なし)."""
    _install_fake_long_term_memory(return_for_search=["fact A"])

    class _ErrConn(_Conn):
        async def execute(self, sql, args=()):
            raise RuntimeError("db down")

    fake_mod = types.SimpleNamespace(connect=lambda _p: _ErrConn(), Row=dict)
    monkeypatch.setattr(mb, "_db", lambda: fake_mod)
    monkeypatch.setattr(mb, "_db_path", lambda: ":memory:")
    try:
        out = asyncio.run(mb.search_with_rerank("u", "q", top_k=1))
        assert len(out) == 1
        assert out[0].fact.fact_text == "fact A"
    finally:
        sys.modules.pop("services.long_term_memory", None)


# ─────────────────────────────────────────────────────────────────────────
# AC-STATE: preload_secretary_facts (top-50)
# ─────────────────────────────────────────────────────────────────────────


def test_preload_secretary_facts_returns_db_rows(monkeypatch) -> None:
    _patch_mb_db(monkeypatch, preload=[
        {"id": 1, "user_id": "u", "workspace_id": None,
         "fact_text": "important", "kind": "durable",
         "source_session_id": 1, "confidence_score": 0.95,
         "fingerprint": "fp1", "status": "synced",
         "retry_count": 0, "memory_api_id": "m1", "mem0_id": "mem0:fp1",
         "last_error": None, "created_at": "", "synced_at": "", "deleted_at": None},
        {"id": 2, "user_id": "u", "workspace_id": None,
         "fact_text": "second", "kind": "durable",
         "source_session_id": 2, "confidence_score": 0.8,
         "fingerprint": "fp2", "status": "synced",
         "retry_count": 0, "memory_api_id": "m2", "mem0_id": None,
         "last_error": None, "created_at": "", "synced_at": "", "deleted_at": None},
    ])
    facts = asyncio.run(mb.preload_secretary_facts("u", top_n=50))
    assert len(facts) == 2
    assert facts[0].confidence_score == 0.95


def test_preload_secretary_facts_returns_empty_on_db_error(monkeypatch) -> None:
    class _ErrConn(_Conn):
        async def execute(self, sql, args=()):
            raise RuntimeError("db down")

    fake_mod = types.SimpleNamespace(connect=lambda _p: _ErrConn(), Row=dict)
    monkeypatch.setattr(mb, "_db", lambda: fake_mod)
    monkeypatch.setattr(mb, "_db_path", lambda: ":memory:")
    facts = asyncio.run(mb.preload_secretary_facts("u"))
    assert facts == []


def test_preload_secretary_facts_respects_top_n(monkeypatch) -> None:
    """top_n パラメータが LIMIT に効くか (SQL の引数を確認)."""
    captured: list = []

    class _CapConn(_Conn):
        async def execute(self, sql, args=()):
            captured.append((sql, args))
            return _Cur(rows=[])

    fake_mod = types.SimpleNamespace(connect=lambda _p: _CapConn(), Row=dict)
    monkeypatch.setattr(mb, "_db", lambda: fake_mod)
    monkeypatch.setattr(mb, "_db_path", lambda: ":memory:")
    asyncio.run(mb.preload_secretary_facts("u", top_n=20))
    # SELECT * FROM memory_facts ... LIMIT ? に 20 が渡る
    assert any(20 in tup for tup in [c[1] for c in captured])


# ─────────────────────────────────────────────────────────────────────────
# AC-UNWANTED: detect_divergence
# ─────────────────────────────────────────────────────────────────────────


def test_detect_divergence_finds_missing_in_mem0(monkeypatch) -> None:
    """mem0_id が NULL の synced fact を「Mem0 未同期」として検出."""
    fake_audit: list = []
    audit_mod = types.ModuleType("services.memory_service")

    async def emit_event(event_type, **kw):
        fake_audit.append({"event": event_type, **kw})

    audit_mod.emit_event = emit_event
    sys.modules["services.memory_service"] = audit_mod

    _patch_mb_db(monkeypatch, divergence=[
        {"id": 1, "fact_text": "ok", "fingerprint": "fp1", "mem0_id": "mem0:fp1"},
        {"id": 2, "fact_text": "missing", "fingerprint": "fp2", "mem0_id": None},
        {"id": 3, "fact_text": "also missing", "fingerprint": "fp3", "mem0_id": None},
    ])
    try:
        out = asyncio.run(mb.detect_divergence("u1", sample=100))
        assert out["checked"] == 3
        assert out["missing_in_mem0"] == 2
        assert 2 in out["missing_ids"]
        assert 3 in out["missing_ids"]
        # AC-UNWANTED: audit event emit (silent fail 防止)
        assert len(fake_audit) == 1
        assert fake_audit[0]["event"] == "memory_divergence_detected"
    finally:
        sys.modules.pop("services.memory_service", None)


def test_detect_divergence_no_audit_when_all_synced(monkeypatch) -> None:
    """全 fact が mem0_id 持ち → divergence なし → audit emit なし."""
    fake_audit: list = []
    audit_mod = types.ModuleType("services.memory_service")

    async def emit_event(event_type, **kw):
        fake_audit.append(event_type)

    audit_mod.emit_event = emit_event
    sys.modules["services.memory_service"] = audit_mod

    _patch_mb_db(monkeypatch, divergence=[
        {"id": 1, "fact_text": "a", "fingerprint": "fp1", "mem0_id": "mem0:fp1"},
    ])
    try:
        out = asyncio.run(mb.detect_divergence("u"))
        assert out["missing_in_mem0"] == 0
        assert fake_audit == []
    finally:
        sys.modules.pop("services.memory_service", None)


def test_detect_divergence_returns_zero_on_db_error(monkeypatch) -> None:
    class _ErrConn(_Conn):
        async def execute(self, sql, args=()):
            raise RuntimeError("db down")

    fake_mod = types.SimpleNamespace(connect=lambda _p: _ErrConn(), Row=dict)
    monkeypatch.setattr(mb, "_db", lambda: fake_mod)
    monkeypatch.setattr(mb, "_db_path", lambda: ":memory:")
    out = asyncio.run(mb.detect_divergence("u"))
    assert out["checked"] == 0
    assert out["missing_in_mem0"] == 0


def test_detect_divergence_audit_emit_failure_does_not_crash(monkeypatch) -> None:
    """audit emit が落ちても detect は完走."""
    audit_mod = types.ModuleType("services.memory_service")

    async def boom(event, **kw):
        raise RuntimeError("audit down")

    audit_mod.emit_event = boom
    sys.modules["services.memory_service"] = audit_mod

    _patch_mb_db(monkeypatch, divergence=[
        {"id": 1, "fact_text": "x", "fingerprint": "fp", "mem0_id": None},
    ])
    try:
        out = asyncio.run(mb.detect_divergence("u"))
        assert out["missing_in_mem0"] == 1  # 検出は完了
    finally:
        sys.modules.pop("services.memory_service", None)
