"""T-M28-01: Context Builder の smoke test."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.context_builder import (
    build_context, lookup_decision, preload_constitution,
    DECISION_REF_RE, _detect_conflicts,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────
# Decision lookup (EVENT AC)
# ──────────────────────────────────────────

def test_decision_ref_regex_matches_3to5_digits() -> None:
    assert DECISION_REF_RE.fullmatch("D-001")
    assert DECISION_REF_RE.fullmatch("D-1234")
    assert DECISION_REF_RE.fullmatch("D-99999")
    assert not DECISION_REF_RE.fullmatch("D-12")     # 2 桁は弾く
    assert not DECISION_REF_RE.fullmatch("D-")
    assert not DECISION_REF_RE.fullmatch("d-001")    # 大文字のみ


def test_lookup_decision_returns_none_for_invalid_format() -> None:
    assert lookup_decision("X-001") is None
    assert lookup_decision("D-12") is None


def test_lookup_decision_reads_md_when_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    p = tmp_path / "D-042.md"
    p.write_text("# Test Decision 42\n\nThe quick brown fox.\n", encoding="utf-8")
    d = lookup_decision("D-042")
    assert d is not None
    assert d["id"] == "D-042"
    assert d["title"] == "Test Decision 42"
    assert "quick brown fox" in d["content"]


def test_lookup_decision_returns_none_when_file_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    assert lookup_decision("D-999") is None


# ──────────────────────────────────────────
# Constitution preload (STATE AC)
# ──────────────────────────────────────────

def test_preload_constitution_returns_env_text(monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_TEXT", "MASATO IS THE BOSS")
    text = asyncio.run(preload_constitution())
    assert text == "MASATO IS THE BOSS"


def test_preload_constitution_concatenates_md_files(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-001.md").write_text("# A\n\nPolicy A", encoding="utf-8")
    (tmp_path / "D-002.md").write_text("# B\n\nPolicy B", encoding="utf-8")
    text = asyncio.run(preload_constitution())
    assert "Policy A" in text
    assert "Policy B" in text


# ──────────────────────────────────────────
# Conflict detection (UNWANTED AC)
# ──────────────────────────────────────────

def test_detect_conflicts_finds_contradiction() -> None:
    facts = ["この案件は採用", "この案件は不採用"]
    conflicts = _detect_conflicts(facts)
    assert len(conflicts) >= 1
    assert "採用" in conflicts[0]["axis"]


def test_detect_conflicts_empty_for_consistent_facts() -> None:
    facts = ["顧客は田中商事", "金額は 50 万円"]
    conflicts = _detect_conflicts(facts)
    assert conflicts == []


# ──────────────────────────────────────────
# build_context (UBIQUITOUS AC)
# ──────────────────────────────────────────

def test_build_context_returns_unified_dict(monkeypatch) -> None:
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = asyncio.run(build_context(
        user_message="hi",
        session_id=1,
        user_id="masato",
        include_constitution=False,
    ))
    # 不確定 deps が無くても dict 構造は維持される
    for key in ("memory_block", "decisions", "constitution", "mem0_facts", "conflicts"):
        assert key in result


def test_build_context_extracts_decision_refs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-100.md").write_text("# Decision 100\n\nrule X", encoding="utf-8")
    result = asyncio.run(build_context(
        user_message="D-100 についてどう思う?",
        session_id=1, user_id="masato",
        include_constitution=False,
    ))
    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["id"] == "D-100"


# ──────────────────────────────────────────
# E2E: router
# ──────────────────────────────────────────

def test_context_decision_endpoint_404(client) -> None:
    r = client.get("/api/context/decisions/D-99999")
    assert r.status_code == 404


def test_context_decision_endpoint_400_bad_format(client) -> None:
    r = client.get("/api/context/decisions/X-001")
    assert r.status_code == 400


def test_context_build_endpoint_returns_unified_dict(client) -> None:
    r = client.post(
        "/api/context/build",
        json={
            "user_message": "hi",
            "session_id": 1,
            "user_id": "masato",
            "include_constitution": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("memory_block", "decisions", "constitution", "mem0_facts", "conflicts"):
        assert key in body
