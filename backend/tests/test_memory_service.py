"""T-020-02: Memory 3 tier の smoke test.

minimal scope:
  - fact_fingerprint が決定的 hash を返す
  - mirror_to_obsidian は OBSIDIAN_SYNC=0 のとき None を返す (opt-in 制御)
  - merge_for_session が prior_session_id を含む block を返す (Mem0 / API 無くても)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from services.memory_service import (
    fact_fingerprint, mirror_to_obsidian, merge_for_session,
)


def test_fact_fingerprint_deterministic() -> None:
    a = fact_fingerprint("hello world")
    b = fact_fingerprint("hello world")
    c = fact_fingerprint("hello world!")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_mirror_to_obsidian_opt_in_default_off(monkeypatch) -> None:
    monkeypatch.delenv("OBSIDIAN_SYNC", raising=False)
    p = mirror_to_obsidian("masato", "test fact", "test-note")
    assert p is None


def test_mirror_to_obsidian_writes_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OBSIDIAN_SYNC", "1")
    monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
    p = mirror_to_obsidian("masato", "durable fact", "Test Note")
    assert p is not None
    assert p.exists()
    text = p.read_text()
    assert "Test Note" in text
    assert "durable fact" in text


def test_merge_for_session_includes_prior_marker(monkeypatch) -> None:
    # Mem0 / Memory API が無くても、prior_session_id があれば marker が入る
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    block = asyncio.run(merge_for_session(
        session_id=100, prior_session_id=42,
        user_message="続きから", user_id="masato",
    ))
    assert "session_id=42" in block


def test_merge_for_session_empty_when_nothing_available(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    block = asyncio.run(merge_for_session(
        session_id=100, prior_session_id=None,
        user_message="hi", user_id="masato",
    ))
    # Mem0 が失敗しても空 string が返る (例外を吸収する)
    assert isinstance(block, str)
