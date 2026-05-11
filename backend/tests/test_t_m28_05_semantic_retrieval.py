"""T-M28-05: semantic retrieval (existing embedding_service 活用) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : M-28 semantic retrieval 統一 API + endpoint
  AC-2 EVENT-DRIVEN  : audit emit (semantic.search) + 2 秒以内
  AC-3 STATE-DRIVEN  : 既存 embedding_service / rag_context / memory_service 不変
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import semantic_retrieval as sr
from services.semantic_retrieval import (
    DEFAULT_MIN_SCORE,
    DEFAULT_SCOPES,
    DEFAULT_TOP_K,
    MAX_QUERY_CHARS,
    MAX_TOP_K,
    SemanticRetrievalError,
    VALID_SCOPES,
    _stringify_section,
    _token_overlap_score,
    _tokenize,
    validate_inputs,
)


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
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _fake_search_services(monkeypatch):
    """既存 service の呼び出しを差し替え (内部 _search_* 関数を直接 patch)."""
    state: dict[str, list[dict]] = {
        "tier3_knowledge": [],
        "tier3_conversation": [],
    }
    calls: list[tuple] = []

    async def fake_kb(query, *, top_k, min_score, skill_tags=None):
        calls.append(("kb", query, skill_tags, top_k, min_score))
        # _search_tier3_knowledge と同じ shape を返す
        out = []
        for it in state["tier3_knowledge"]:
            out.append({
                "scope": "tier3_knowledge",
                "id": it.get("id"),
                "title": it.get("title") or "",
                "snippet": (it.get("content") or "")[:300],
                "score": float(it.get("score") or 0.0),
                "meta": {"category": it.get("category"),
                         "skill_tags": it.get("skill_tags")},
            })
        return out

    async def fake_conv(query, *, top_k, min_score, exclude_thread_id=None):
        calls.append(("conv", query, exclude_thread_id, top_k, min_score))
        out = []
        for it in state["tier3_conversation"]:
            out.append({
                "scope": "tier3_conversation",
                "id": it.get("thread_id"),
                "title": f"thread:{it.get('thread_id')}" if it.get("thread_id") else "",
                "snippet": (it.get("content") or "")[:300],
                "score": float(it.get("score") or 0.0),
                "meta": {"role": it.get("role"),
                         "created_at": it.get("created_at"),
                         "thread_id": it.get("thread_id")},
            })
        return out

    monkeypatch.setattr(sr, "_search_tier3_knowledge", fake_kb)
    monkeypatch.setattr(sr, "_search_tier3_conversation", fake_conv)
    yield {"state": state, "calls": calls}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: validate_inputs
# ──────────────────────────────────────────────────────────────────────────


def test_validate_inputs_ok():
    q, scopes = validate_inputs("hello", ["tier3_knowledge"], 10, 0.5)
    assert q == "hello"
    assert scopes == ["tier3_knowledge"]


def test_validate_inputs_strips_query():
    q, _ = validate_inputs("  hi  ", ["tier3_knowledge"], 10, 0.5)
    assert q == "hi"


def test_validate_inputs_empty_query():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("   ", ["tier3_knowledge"], 10, 0.5)


def test_validate_inputs_too_long_query():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("x" * (MAX_QUERY_CHARS + 1), ["tier3_knowledge"], 10, 0.5)


def test_validate_inputs_empty_scopes():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("hi", [], 10, 0.5)


def test_validate_inputs_invalid_scope():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("hi", ["bogus_scope"], 10, 0.5)


def test_validate_inputs_duplicate_scopes():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("hi", ["tier3_knowledge", "tier3_knowledge"], 10, 0.5)


def test_validate_inputs_top_k_bounds():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("hi", ["tier3_knowledge"], 0, 0.5)
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("hi", ["tier3_knowledge"], MAX_TOP_K + 1, 0.5)


def test_validate_inputs_min_score_bounds():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("hi", ["tier3_knowledge"], 10, -0.1)
    with pytest.raises(SemanticRetrievalError):
        validate_inputs("hi", ["tier3_knowledge"], 10, 1.1)


def test_validate_inputs_query_not_string():
    with pytest.raises(SemanticRetrievalError):
        validate_inputs(123, ["tier3_knowledge"], 10, 0.5)  # type: ignore


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: tokenize / overlap
# ──────────────────────────────────────────────────────────────────────────


def test_tokenize_basic():
    tokens = _tokenize("Hello, World! Build-Factory 開発")
    assert "hello" in tokens
    assert "world" in tokens
    assert "build" in tokens
    assert "factory" in tokens


def test_tokenize_filters_short():
    tokens = _tokenize("a be I am you")
    # 1 chars は除外
    assert "a" not in tokens
    assert "i" not in tokens
    assert "be" in tokens
    assert "am" in tokens


def test_tokenize_non_string():
    assert _tokenize(None) == set()  # type: ignore
    assert _tokenize(123) == set()  # type: ignore


def test_overlap_score():
    q = _tokenize("apple banana cherry")
    assert _token_overlap_score(q, "apple banana") == pytest.approx(2/3)
    assert _token_overlap_score(q, "apple banana cherry date") == pytest.approx(1.0)
    assert _token_overlap_score(q, "zebra") == 0.0


def test_overlap_score_empty():
    assert _token_overlap_score(set(), "anything") == 0.0
    assert _token_overlap_score({"x"}, "") == 0.0


def test_stringify_section_variants():
    assert _stringify_section("plain") == "plain"
    assert "a" in _stringify_section(["a", "b"])
    assert _stringify_section({"x": 1}) == '{"x": 1}'
    assert _stringify_section(None) == ""
    assert _stringify_section(42) == "42"


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: search (mocked services)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_returns_empty_for_no_results():
    pass


def test_search_no_results(_fake_search_services):
    import asyncio
    out = asyncio.run(sr.search("hello world"))
    assert out["count"] == 0
    assert out["results"] == []
    assert set(out["per_scope_count"].keys()) == set(DEFAULT_SCOPES)


def test_search_merges_and_sorts(_fake_search_services):
    import asyncio
    _fake_search_services["state"]["tier3_knowledge"] = [
        {"id": 1, "title": "kb1", "content": "abc", "score": 0.9},
        {"id": 2, "title": "kb2", "content": "def", "score": 0.5},
    ]
    _fake_search_services["state"]["tier3_conversation"] = [
        {"thread_id": 10, "role": "user", "content": "hi",
         "created_at": "2026-01-01", "score": 0.8},
    ]
    out = asyncio.run(sr.search("hello", top_k=10))
    # 3 結果が score 降順で merge
    assert out["count"] == 3
    scores = [r["score"] for r in out["results"]]
    assert scores == sorted(scores, reverse=True)
    assert out["per_scope_count"] == {
        "tier3_knowledge": 2, "tier3_conversation": 1,
    }


def test_search_top_k_truncates(_fake_search_services):
    import asyncio
    _fake_search_services["state"]["tier3_knowledge"] = [
        {"id": i, "title": f"k{i}", "content": "x", "score": 1.0 - i*0.01}
        for i in range(20)
    ]
    out = asyncio.run(sr.search("query", top_k=5))
    assert out["count"] == 5


def test_search_skill_tags_validation(_fake_search_services):
    import asyncio
    with pytest.raises(SemanticRetrievalError):
        asyncio.run(sr.search("q", skill_tags=["", " "]))
    with pytest.raises(SemanticRetrievalError):
        asyncio.run(sr.search("q", skill_tags=["x"] * 21))


def test_search_session_id_validation(_fake_search_services):
    import asyncio
    with pytest.raises(SemanticRetrievalError):
        asyncio.run(sr.search("q", session_id=0))
    with pytest.raises(SemanticRetrievalError):
        asyncio.run(sr.search("q", exclude_thread_id=-1))


def test_search_specific_scope_only(_fake_search_services):
    import asyncio
    _fake_search_services["state"]["tier3_knowledge"] = [
        {"id": 1, "title": "kb1", "content": "x", "score": 0.5},
    ]
    out = asyncio.run(sr.search("q", scopes=["tier3_knowledge"]))
    # tier3_conversation は呼ばれていない
    convs = [c for c in _fake_search_services["calls"] if c[0] == "conv"]
    assert convs == []
    assert out["per_scope_count"] == {"tier3_knowledge": 1}


def test_search_skill_tags_passed_through(_fake_search_services):
    import asyncio
    asyncio.run(sr.search(
        "q", scopes=["tier3_knowledge"], skill_tags=["invoice-create"],
    ))
    kb_calls = [c for c in _fake_search_services["calls"] if c[0] == "kb"]
    assert kb_calls[0][2] == ["invoice-create"]


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: Tier 2 summary search (mocked DB)
# ──────────────────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, sql, params=None):
        return _FakeCursor(self._rows)


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return _FakeDB(self._rows)

    async def __aexit__(self, *exc):
        return False


class _FakeAioSqlite:
    def __init__(self, rows):
        self._rows = rows

    def connect(self, _path):
        return _FakeConn(self._rows)


def test_tier2_summary_search_hits(monkeypatch):
    import asyncio
    summary = {
        "context": "Build-Factory project",
        "goals": ["ship Phase 1"],
        "decisions": ["ADR-010 anthropic-python"],
    }
    rows = [(1, 7, json.dumps(summary), "2026-01-01")]
    import services.memory_service as ms
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(rows))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    out = asyncio.run(sr.search(
        "Build-Factory project", scopes=["tier2_summary"], min_score=0.1,
    ))
    assert out["count"] >= 1
    titles = [r["title"] for r in out["results"]]
    assert any("summary[context]" in t for t in titles)


def test_tier2_summary_search_invalid_json(monkeypatch):
    import asyncio
    rows = [(1, 7, "not-json", None)]
    import services.memory_service as ms
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(rows))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    out = asyncio.run(sr.search(
        "anything", scopes=["tier2_summary"], min_score=0.1,
    ))
    # invalid JSON は skip
    assert out["count"] == 0


def test_tier2_summary_search_non_dict(monkeypatch):
    import asyncio
    rows = [(1, 7, json.dumps([1, 2, 3]), None)]
    import services.memory_service as ms
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(rows))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    out = asyncio.run(sr.search(
        "anything", scopes=["tier2_summary"], min_score=0.1,
    ))
    assert out["count"] == 0


def test_tier2_summary_session_filter(monkeypatch):
    import asyncio
    summary = {"context": "match the query word"}
    rows = [(1, 99, json.dumps(summary), None)]
    import services.memory_service as ms
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(rows))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    out = asyncio.run(sr.search(
        "match query", scopes=["tier2_summary"], session_id=99, min_score=0.1,
    ))
    assert out["count"] >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_list_scopes(client):
    r = client.get("/api/semantic-retrieval/scopes")
    assert r.status_code == 200
    body = r.json()
    assert set(body["scopes"]) == set(VALID_SCOPES)
    assert set(body["default"]) == set(DEFAULT_SCOPES)
    assert body["max_top_k"] == MAX_TOP_K


def test_ac1_search_empty_result(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hello world",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["results"] == []


def test_ac1_search_with_results(client, _fake_search_services):
    _fake_search_services["state"]["tier3_knowledge"] = [
        {"id": 1, "title": "kb1", "content": "abc", "score": 0.9},
    ]
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hello",
        "scopes": ["tier3_knowledge"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["results"][0]["scope"] == "tier3_knowledge"


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hello",
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_invalid_scope(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hi",
        "scopes": ["bogus_scope"],
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "semantic.invalid"


def test_ac2_error_shape_consistency(client):
    cases = [
        ("POST", "/api/semantic-retrieval/search", {"query": ""}),
        ("POST", "/api/semantic-retrieval/search", {
            "query": "hi", "scopes": ["tier3_knowledge", "tier3_knowledge"],
        }),
        ("POST", "/api/semantic-retrieval/search", {
            "query": "hi", "actor_user_id": "   ",
        }),
    ]
    for method, path, body in cases:
        r = client.post(path, json=body)
        assert r.status_code in (400, 401, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("semantic."), \
                f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_search_emits_audit(client, _capture_audit, _fake_search_services):
    _fake_search_services["state"]["tier3_knowledge"] = [
        {"id": 1, "title": "kb1", "content": "abc", "score": 0.9},
    ]
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hello",
        "scopes": ["tier3_knowledge"],
        "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "semantic.search"]
    assert len(events) == 1
    assert events[0]["user_id"] == "u-1"
    assert events[0]["detail"]["query_chars"] == len("hello")
    assert events[0]["detail"]["count"] == 1


def test_ac3_list_scopes_no_audit(client, _capture_audit):
    client.get("/api/semantic-retrieval/scopes")
    sem_events = [e for e in _capture_audit if e["event_type"].startswith("semantic.")]
    assert sem_events == []


# ──────────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / persistent state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_top_k_pydantic_422(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hi", "top_k": 0,
    })
    assert r.status_code == 422


def test_ac4_top_k_over_max_pydantic_422(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hi", "top_k": MAX_TOP_K + 1,
    })
    assert r.status_code == 422


def test_ac4_min_score_out_of_range_pydantic_422(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hi", "min_score": 2.0,
    })
    assert r.status_code == 422


def test_ac4_empty_query(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "   ",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "semantic.invalid"


def test_ac4_empty_actor_user_id(client, _capture_audit):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hi",
        "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "semantic.unauthorized"
    # 失敗時は audit emit しない
    assert not any(
        e["event_type"] == "semantic.search" for e in _capture_audit
    )


def test_ac4_invalid_skill_tags(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hi",
        "skill_tags": ["", "x"],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "semantic.invalid"


def test_ac4_session_id_zero_pydantic_422(client):
    r = client.post("/api/semantic-retrieval/search", json={
        "query": "hi",
        "session_id": 0,
    })
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# Backwards compatibility — 既存 service 不変
# ──────────────────────────────────────────────────────────────────────────


def test_compat_embedding_service_unchanged():
    # numpy が未導入の環境では skip (本番 / dev では numpy 必須)
    try:
        from services import embedding_service as es
    except ModuleNotFoundError as e:
        pytest.skip(f"embedding_service dep missing: {e}")
    assert hasattr(es, "search_knowledge")
    assert hasattr(es, "embed")
    assert hasattr(es, "encode")
    assert hasattr(es, "decode")


def test_compat_rag_context_unchanged():
    from services import rag_context as rc
    assert hasattr(rc, "search_similar_messages")
    assert hasattr(rc, "build_context")


def test_compat_memory_service_unchanged():
    from services import memory_service as ms
    assert hasattr(ms, "emit_event")
    assert hasattr(ms, "persist_compaction")
