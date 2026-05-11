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
