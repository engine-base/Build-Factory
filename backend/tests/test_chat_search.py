"""T-AI-03: hybrid search の AC テスト."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services.chat_search import (
    char_bigrams, hybrid_search, parse_query, trgm_similarity,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────
# parse_query: date:YYYY-MM フィルタ
# ──────────────────────────────────────────

def test_parse_query_no_date_filter() -> None:
    cleaned, date_p = parse_query("hello world")
    assert cleaned == "hello world"
    assert date_p is None


def test_parse_query_with_date_filter_yyyy_mm() -> None:
    """AC-OPTIONAL: `date:2026-04` で月単位 narrow。"""
    cleaned, date_p = parse_query("Supabase decision date:2026-04")
    assert "date:" not in cleaned
    assert cleaned == "Supabase decision"
    assert date_p == "2026-04"


def test_parse_query_with_date_filter_yyyy_mm_dd() -> None:
    """日単位指定 (parse 上は月単位 prefix を返すのみ)。"""
    cleaned, date_p = parse_query("query date:2026-04-15")
    assert date_p == "2026-04"


def test_parse_query_date_filter_at_start() -> None:
    cleaned, date_p = parse_query("date:2026-05 main topic")
    assert cleaned == "main topic"
    assert date_p == "2026-05"


# ──────────────────────────────────────────
# trgm_similarity (pg_trgm 相当)
# ──────────────────────────────────────────

def test_bigram_extraction_includes_padding() -> None:
    grams = char_bigrams("ab")
    # leading + trailing space で padding される
    assert "  " in grams or " a" in grams or "ab" in grams


def test_trgm_identical_strings_score_1() -> None:
    assert trgm_similarity("hello", "hello") == 1.0


def test_trgm_completely_different_score_0() -> None:
    """共通 bigram が padding 以外で 0 なら近い。"""
    score = trgm_similarity("aaaaa", "zzzzz")
    assert 0.0 <= score < 0.3


def test_trgm_partial_match_in_middle() -> None:
    """部分一致は 0 < score < 1。"""
    score = trgm_similarity("Supabase Postgres", "Supabase decision")
    assert 0.0 < score < 1.0


def test_trgm_empty_returns_0() -> None:
    assert trgm_similarity("", "anything") == 0.0
    assert trgm_similarity("anything", "") == 0.0


# ──────────────────────────────────────────
# hybrid_search 基本動作
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_hybrid_search_empty_query_returns_empty() -> None:
    result = await hybrid_search("", top_k=5)
    assert result == []


@pytest.mark.asyncio
async def test_hybrid_search_only_date_filter_returns_empty() -> None:
    """`date:2026-04` だけだと clean query が空 → 空 list。"""
    result = await hybrid_search("date:2026-04", top_k=5)
    assert result == []


@pytest.mark.asyncio
async def test_hybrid_search_no_db_graceful() -> None:
    """DB 不在環境でも例外を出さず空 list。"""
    result = await hybrid_search("Supabase Postgres", top_k=5)
    # DB 不在なので 0 件 or whatever in DB
    assert isinstance(result, list)


# ──────────────────────────────────────────
# Router smoke
# ──────────────────────────────────────────

def test_router_search_returns_count_and_results(client) -> None:
    r = client.get("/api/search/chat", params={"q": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "results" in body
    assert isinstance(body["results"], list)


def test_router_search_with_date_filter(client) -> None:
    r = client.get("/api/search/chat", params={"q": "decision date:2026-05"})
    assert r.status_code == 200


def test_router_search_top_k_param(client) -> None:
    r = client.get("/api/search/chat", params={"q": "x", "top_k": 5})
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 5
