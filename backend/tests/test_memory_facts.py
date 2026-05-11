"""T-AI-01: memory_facts の AC テスト.

DB 不在環境では graceful (None / [] / {processed: 0}) を返す前提で、
本テストは fingerprint / extract_facts_from_text の純粋関数 + router smoke。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.memory_facts import (
    extract_facts_from_text, fingerprint,
)


# ──────────────────────────────────────────
# fingerprint
# ──────────────────────────────────────────

def test_fingerprint_is_16_hex_chars() -> None:
    fp = fingerprint("hello world")
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_normalizes_whitespace_and_case() -> None:
    """空白の差・大小は同一 fingerprint。"""
    a = fingerprint("Hello   World")
    b = fingerprint("hello world")
    c = fingerprint("HELLO\tWORLD\n")
    assert a == b == c


def test_fingerprint_differs_for_different_content() -> None:
    assert fingerprint("a") != fingerprint("b")


# ──────────────────────────────────────────
# fact extraction (D-XXX / P-XXX / C-XXX)
# ──────────────────────────────────────────

def test_extract_d_prefix_decision() -> None:
    text = "D-001: 主要 DB は Supabase Postgres"
    facts = extract_facts_from_text(text)
    assert len(facts) == 1
    assert facts[0][0] == "D-001"
    assert "Supabase" in facts[0][1]


def test_extract_p_prefix_preference() -> None:
    text = "P-002: Lucide Icons を絶対遵守"
    facts = extract_facts_from_text(text)
    assert facts[0][0] == "P-002"


def test_extract_c_prefix_context() -> None:
    text = "C-100: Phase 1 は ¥0/月 構成"
    facts = extract_facts_from_text(text)
    assert facts[0][0] == "C-100"


def test_extract_with_markdown_heading() -> None:
    """## D-001 形式も拾う。"""
    text = "## D-005: Anthropic Memory API を 永続記憶の primary"
    facts = extract_facts_from_text(text)
    assert len(facts) == 1
    assert facts[0][0] == "D-005"


def test_extract_with_bold_markup() -> None:
    text = "**D-007** AI 社員は BMAD 10 ペルソナで運用"
    facts = extract_facts_from_text(text)
    assert len(facts) == 1
    assert facts[0][0] == "D-007"


def test_extract_multiple_facts_from_block() -> None:
    text = """\
## 決定事項
D-001: 主要 DB は Supabase Postgres
D-002: AI スタックは 3 層 (claude-agent-sdk + anthropic + LiteLLM)
P-001: 絵文字禁止 (Lucide Icons のみ)
"""
    facts = extract_facts_from_text(text)
    assert len(facts) == 3
    ids = [f[0] for f in facts]
    assert ids == ["D-001", "D-002", "P-001"]


def test_extract_ignores_horizontal_rules() -> None:
    """`D-001: ===` のような区切り線は拾わない。"""
    text = "D-001: ====================="
    facts = extract_facts_from_text(text)
    assert facts == []


def test_extract_returns_empty_for_no_match() -> None:
    text = "ただのメモです。決定事項なし。"
    assert extract_facts_from_text(text) == []


# ──────────────────────────────────────────
# Router smoke (DB 不在でも 200 を返すべき endpoint のみ)
# ──────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def test_router_recall_returns_empty_for_unknown_user(client) -> None:
    r = client.get("/api/memory/facts/recall", params={"user_id": "no_such_user_zzz", "query": "anything"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_router_process_retry_queue_returns_dict(client) -> None:
    r = client.post("/api/memory/facts/process-retry-queue")
    assert r.status_code == 200
    body = r.json()
    assert "processed" in body or "success" in body


def test_router_process_deletions_dry_run(client) -> None:
    r = client.post("/api/memory/facts/process-deletions", params={"dry_run": "true"})
    assert r.status_code == 200
    body = r.json()
    assert "would_delete" in body or "deleted" in body or "processed" in body


def test_router_delete_unknown_returns_404(client) -> None:
    r = client.delete("/api/memory/facts/9999999", params={"user_id": "no_user"})
    assert r.status_code == 404
