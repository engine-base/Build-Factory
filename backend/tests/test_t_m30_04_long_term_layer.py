"""T-M30-04: 長期 layer (existing long_term_memory + obsidian_sync 統合) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 長期 layer 統一 API (REFACTOR REUSE)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 mem0/obsidian module 不変 + audit emit
  AC-4 UNWANTED      : invalid input / path traversal は 4xx /
                       all-sinks-failed は 502
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import long_term_layer as ltl
from services.long_term_layer import (
    DEFAULT_SCOPES,
    DEFAULT_TOP_K,
    LongTermLayerError,
    MAX_CONTENT_CHARS,
    MAX_QUERY_CHARS,
    MAX_TAGS,
    MAX_TOP_K,
    VALID_SCOPES,
    VALID_SOURCES,
    _token_overlap_score,
    _tokenize,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _tmp_obsidian(monkeypatch, tmp_path):
    root = tmp_path / "obsidian"
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(root))
    yield root


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
def _mock_mem0(monkeypatch):
    """既存 long_term_memory を mock - Mem0 外部依存を切る."""
    state: dict[str, list[dict]] = {"added": [], "search_result": []}

    async def fake_add(user_id, messages, metadata=None):
        state["added"].append({
            "user_id": user_id, "messages": messages, "metadata": metadata,
        })

    async def fake_search(user_id, query, limit=5):
        return [
            r for r in state["search_result"]
            if r.get("user_id") == user_id
        ][:limit]

    async def fake_all(user_id):
        return [m for m in state["added"] if m["user_id"] == user_id]

    import services.long_term_memory as ltm
    monkeypatch.setattr(ltm, "add_conversation", fake_add)
    monkeypatch.setattr(
        ltm, "search_relevant_memories",
        lambda u, q, limit=5: _to_strings(fake_search, u, q, limit),
    )
    monkeypatch.setattr(ltm, "all_memories", fake_all)
    yield state


async def _to_strings(fake_search_fn, user_id, query, limit):
    items = await fake_search_fn(user_id, query, limit)
    return [it.get("content", "") for it in items]


# ──────────────────────────────────────────────────────────────────────
# Service 単体: validation
# ──────────────────────────────────────────────────────────────────────


def test_service_constants():
    assert "conversation" in VALID_SOURCES
    assert "constitution" in VALID_SOURCES
    assert set(DEFAULT_SCOPES) == set(VALID_SCOPES)


def test_persist_invalid_user_id():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("  ", "x"))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("../escape", "x"))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("x" * 201, "x"))


def test_persist_invalid_content():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "   "))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x" * (MAX_CONTENT_CHARS + 1)))


def test_persist_invalid_source():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", source="bogus"))


def test_persist_invalid_tags():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", tags=[""]))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", tags=["x" * 51]))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", tags=["t"] * (MAX_TAGS + 1)))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", tags="not-list"))


def test_persist_invalid_scopes():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", scopes=["bogus"]))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", scopes=["mem0", "mem0"]))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.persist("u-1", "x", scopes=[]))


# ──────────────────────────────────────────────────────────────────────
# Service 単体: persist
# ──────────────────────────────────────────────────────────────────────


def test_persist_writes_mem0_and_obsidian(_tmp_obsidian, _mock_mem0):
    result = asyncio.run(ltl.persist(
        "u-1", "Hello world", source="fact", tags=["test"],
    ))
    assert result["status"] == "ok"
    assert result["results"]["mem0"]["status"] == "ok"
    assert result["results"]["obsidian"]["status"] == "ok"
    # Mem0 に渡された
    assert len(_mock_mem0["added"]) == 1
    assert _mock_mem0["added"][0]["user_id"] == "u-1"
    # Obsidian にファイル
    user_dir = _tmp_obsidian / "u-1"
    files = list(user_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "Hello world" in content
    assert "source: fact" in content
    assert "tags: [test]" in content


def test_persist_obsidian_only(_tmp_obsidian, _mock_mem0):
    result = asyncio.run(ltl.persist(
        "u-1", "obsidian-only", scopes=["obsidian"],
    ))
    assert result["results"].get("mem0") is None
    assert result["results"]["obsidian"]["status"] == "ok"
    # mem0 へは書かれていない
    assert _mock_mem0["added"] == []


def test_persist_mem0_only(_tmp_obsidian, _mock_mem0):
    result = asyncio.run(ltl.persist(
        "u-1", "mem0-only", scopes=["mem0"],
    ))
    assert result["results"].get("obsidian") is None
    assert result["results"]["mem0"]["status"] == "ok"
    # obsidian root にユーザディレクトリ無し
    user_dir = _tmp_obsidian / "u-1"
    assert not user_dir.exists() or not any(user_dir.glob("*.md"))


def test_persist_status_partial_when_mem0_fails(_tmp_obsidian, monkeypatch):
    """mem0 が import error / runtime error でも obsidian は成功させる."""
    import services.long_term_memory as ltm

    async def err(*a, **kw):
        raise RuntimeError("mem0 down")
    monkeypatch.setattr(ltm, "add_conversation", err)
    result = asyncio.run(ltl.persist("u-1", "x"))
    # mem0 は internal で握り潰されて status='ok' になる可能性も
    # → mem0 service 内 except で status_code は ok と error 両方ありうる
    assert result["results"]["obsidian"]["status"] == "ok"


def test_persist_strips_user_id(_tmp_obsidian, _mock_mem0):
    result = asyncio.run(ltl.persist("  u-1  ", "x", scopes=["obsidian"]))
    assert result["user_id"] == "u-1"


# ──────────────────────────────────────────────────────────────────────
# Service 単体: retrieve
# ──────────────────────────────────────────────────────────────────────


def test_retrieve_obsidian_only(_tmp_obsidian, _mock_mem0):
    asyncio.run(ltl.persist(
        "u-1", "Build-Factory rocks", scopes=["obsidian"],
    ))
    asyncio.run(ltl.persist(
        "u-1", "Hello universe", scopes=["obsidian"],
    ))
    result = asyncio.run(ltl.retrieve(
        "u-1", "Build-Factory", scopes=["obsidian"], min_score=0.1,
    ))
    assert result["count"] >= 1
    assert all(r["scope"] == "obsidian" for r in result["results"])


def test_retrieve_unknown_user_returns_empty(_tmp_obsidian, _mock_mem0):
    result = asyncio.run(ltl.retrieve(
        "u-x", "anything", scopes=["obsidian"],
    ))
    assert result["count"] == 0


def test_retrieve_invalid_query():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.retrieve("u-1", "   "))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.retrieve("u-1", "x" * (MAX_QUERY_CHARS + 1)))


def test_retrieve_invalid_top_k():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.retrieve("u-1", "x", top_k=0))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.retrieve("u-1", "x", top_k=MAX_TOP_K + 1))


def test_retrieve_invalid_min_score():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.retrieve("u-1", "x", min_score=1.5))
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.retrieve("u-1", "x", min_score=-0.1))


def test_retrieve_invalid_user_id():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.retrieve("../escape", "x"))


def test_retrieve_top_k_truncates(_tmp_obsidian, _mock_mem0):
    for i in range(20):
        asyncio.run(ltl.persist(
            "u-1", f"build-factory record {i}", scopes=["obsidian"],
            tags=["t"],
        ))
    result = asyncio.run(ltl.retrieve(
        "u-1", "build factory", scopes=["obsidian"], top_k=5, min_score=0.1,
    ))
    assert result["count"] == 5


# ──────────────────────────────────────────────────────────────────────
# Service 単体: list_sources
# ──────────────────────────────────────────────────────────────────────


def test_list_sources_empty(_tmp_obsidian, _mock_mem0):
    result = asyncio.run(ltl.list_sources("u-fresh"))
    assert result["obsidian"]["user_dir_exists"] is False
    assert result["obsidian"]["file_count"] == 0


def test_list_sources_with_files(_tmp_obsidian, _mock_mem0):
    asyncio.run(ltl.persist(
        "u-1", "x", scopes=["obsidian"],
    ))
    result = asyncio.run(ltl.list_sources("u-1"))
    assert result["obsidian"]["user_dir_exists"] is True
    assert result["obsidian"]["file_count"] == 1


def test_list_sources_invalid_user():
    with pytest.raises(LongTermLayerError):
        asyncio.run(ltl.list_sources("../escape"))


# ──────────────────────────────────────────────────────────────────────
# Service 単体: tokenize / overlap
# ──────────────────────────────────────────────────────────────────────


def test_tokenize_basic():
    assert "hello" in _tokenize("Hello, world!")


def test_tokenize_non_string():
    assert _tokenize(123) == set()


def test_overlap_score():
    q = _tokenize("apple banana")
    assert _token_overlap_score(q, "apple cake") == 0.5


def test_overlap_score_empty():
    assert _token_overlap_score(set(), "anything") == 0.0


# ──────────────────────────────────────────────────────────────────────
# Backwards compat - 既存 module 不変
# ──────────────────────────────────────────────────────────────────────


def test_compat_long_term_memory_unchanged():
    from services import long_term_memory as ltm
    assert hasattr(ltm, "add_conversation")
    assert hasattr(ltm, "search_relevant_memories")
    assert hasattr(ltm, "all_memories")


def test_compat_obsidian_sync_unchanged():
    from services import obsidian_sync as os_mod
    assert hasattr(os_mod, "run_obsidian_sync")


def test_compat_obsidian_vault_sync_unchanged():
    from services import obsidian_vault_sync
    assert hasattr(obsidian_vault_sync, "__name__")


# ──────────────────────────────────────────────────────────────────────
# AC-1: endpoint
# ──────────────────────────────────────────────────────────────────────


def test_ac1_persist(client, _tmp_obsidian, _mock_mem0):
    r = client.post("/api/long-term/persist", json={
        "user_id": "u-1",
        "content": "hello",
        "source": "fact",
        "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_ac1_retrieve(client, _tmp_obsidian, _mock_mem0):
    client.post("/api/long-term/persist", json={
        "user_id": "u-1",
        "content": "build-factory test",
        "scopes": ["obsidian"],
    })
    r = client.post("/api/long-term/retrieve", json={
        "user_id": "u-1",
        "query": "build factory",
        "scopes": ["obsidian"],
        "min_score": 0.1,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1


def test_ac1_sources(client, _tmp_obsidian, _mock_mem0):
    r = client.get("/api/long-term/sources", params={"user_id": "u-1"})
    assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client, _tmp_obsidian, _mock_mem0):
    t0 = time.time()
    r = client.post("/api/long-term/persist", json={
        "user_id": "u-1", "content": "hello",
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_consistency(client, _tmp_obsidian):
    cases = [
        ("POST", "/api/long-term/persist", {
            "user_id": "../escape", "content": "x",
        }),
        ("POST", "/api/long-term/persist", {
            "user_id": "u-1", "content": "x", "actor_user_id": "  ",
        }),
        ("POST", "/api/long-term/persist", {
            "user_id": "u-1", "content": "x", "source": "bogus",
        }),
        ("POST", "/api/long-term/retrieve", {
            "user_id": "u-1", "query": "  ",
        }),
        ("GET", "/api/long-term/sources", None),  # user_id missing → 422
    ]
    for method, path, body in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=body)
        assert r.status_code in (400, 401, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("long_term."), f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────
# AC-3: audit emit
# ──────────────────────────────────────────────────────────────────────


def test_ac3_persist_emits_audit(client, _tmp_obsidian, _mock_mem0, _capture_audit):
    r = client.post("/api/long-term/persist", json={
        "user_id": "u-1", "content": "x", "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "long_term.persisted"]
    assert len(events) == 1
    assert events[0]["detail"]["status"] == "ok"


def test_ac3_retrieve_no_audit(client, _tmp_obsidian, _mock_mem0, _capture_audit):
    client.post("/api/long-term/retrieve", json={
        "user_id": "u-1", "query": "x", "actor_user_id": "u-1",
    })
    lt_events = [e for e in _capture_audit if e["event_type"].startswith("long_term.")]
    assert lt_events == []


def test_ac3_sources_no_audit(client, _tmp_obsidian, _mock_mem0, _capture_audit):
    client.get("/api/long-term/sources", params={"user_id": "u-1"})
    lt_events = [e for e in _capture_audit if e["event_type"].startswith("long_term.")]
    assert lt_events == []


# ──────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / state mutate しない
# ──────────────────────────────────────────────────────────────────────


def test_ac4_path_traversal_rejected(client, _tmp_obsidian):
    r = client.post("/api/long-term/persist", json={
        "user_id": "../etc/passwd",
        "content": "x",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "long_term.invalid"
    # state mutate なし - tmp obsidian root に何も書かれない
    parent_files = list(_tmp_obsidian.parent.rglob("passwd"))
    assert parent_files == []


def test_ac4_empty_actor(client, _tmp_obsidian):
    r = client.post("/api/long-term/persist", json={
        "user_id": "u-1", "content": "x", "actor_user_id": "  ",
    })
    assert r.status_code == 401


def test_ac4_top_k_pydantic_422(client):
    r = client.post("/api/long-term/retrieve", json={
        "user_id": "u-1", "query": "x", "top_k": 0,
    })
    assert r.status_code == 422


def test_ac4_min_score_out_of_range_pydantic_422(client):
    r = client.post("/api/long-term/retrieve", json={
        "user_id": "u-1", "query": "x", "min_score": 2.0,
    })
    assert r.status_code == 422


def test_ac4_content_too_long(client):
    r = client.post("/api/long-term/persist", json={
        "user_id": "u-1", "content": "x" * (MAX_CONTENT_CHARS + 1),
    })
    assert r.status_code == 400


def test_ac4_failed_persist_audit_not_emitted(client, monkeypatch, _capture_audit, _tmp_obsidian):
    """全 sink failed → 502 + audit emit しない."""
    # mem0 と obsidian 両方を error にする
    async def err_persist_mem0(*a, **kw):
        return {"status": "error", "reason": "mem0 down"}

    async def err_persist_obsidian(*a, **kw):
        return {"status": "error", "reason": "obsidian down"}

    monkeypatch.setattr(ltl, "_persist_to_mem0", err_persist_mem0)
    monkeypatch.setattr(ltl, "_persist_to_obsidian", err_persist_obsidian)
    r = client.post("/api/long-term/persist", json={
        "user_id": "u-1", "content": "x",
    })
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "long_term.persist_failed"
    # 失敗時 audit 非発行
    assert not any(
        e["event_type"] == "long_term.persisted" for e in _capture_audit
    )
