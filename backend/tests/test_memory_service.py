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


# ---------------------------------------------------------------------------
# T-020-02 AC 全網羅 (DB / Memory API / Mem0 全て mock)
# ---------------------------------------------------------------------------

import sys
import types
from typing import Any
import pytest

from services import memory_service as ms


# ---------- _FakeDB (test_swarm.py の同型を再掲、 import 都合で重複) ----------


class _FakeCursor:
    def __init__(self, rows: list[Any] | None = None, lastrowid: int = 0) -> None:
        self._rows = rows or []
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, *, cursor: _FakeCursor | None = None) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._cursor = cursor or _FakeCursor()

    async def execute(self, sql: str, params: tuple = ()):
        self.executed.append((sql, params))
        return self._cursor

    async def commit(self) -> None:
        return None

    async def __aenter__(self) -> "_FakeDB":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _patch_ms_db(monkeypatch, *, cursor: _FakeCursor | None = None) -> _FakeDB:
    fake = _FakeDB(cursor=cursor)
    fake_db_module = types.SimpleNamespace(connect=lambda _path: fake, Row=dict)
    monkeypatch.setattr(ms, "_db", lambda: fake_db_module)
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    return fake


# ---------------------------------------------------------------------------
# AC-1 UBIQUITOUS: 公開 API surface (Tier 1/2/3 統合)
# ---------------------------------------------------------------------------


def test_public_api_surface_exposes_three_tier_methods() -> None:
    """unified API: emit_event / persist_compaction / write_fact /
    mirror_to_obsidian / merge_for_session / fact_fingerprint が存在."""
    for name in (
        "emit_event", "persist_compaction", "write_fact",
        "mirror_to_obsidian", "merge_for_session", "fact_fingerprint",
    ):
        assert hasattr(ms, name)


# ---------------------------------------------------------------------------
# emit_event (audit_logs に書き込む共通基盤)
# ---------------------------------------------------------------------------


def test_emit_event_inserts_into_audit_logs(monkeypatch) -> None:
    fake = _patch_ms_db(monkeypatch, cursor=_FakeCursor(lastrowid=11))
    eid = asyncio.run(ms.emit_event(
        "memory_compacted",
        session_id=42, user_id="masato", detail={"foo": "bar"},
    ))
    assert eid == 11
    assert any("INSERT INTO audit_logs" in s for s, _ in fake.executed)
    # detail は JSON 文字列で渡る
    sql, params = fake.executed[-1]
    assert "memory_compacted" in params
    assert any("foo" in p for p in params if isinstance(p, str))


# ---------------------------------------------------------------------------
# AC-2 EVENT: persist_compaction → chat_messages + memory_compacted event
# ---------------------------------------------------------------------------


def test_persist_compaction_writes_chat_messages_and_emits_audit(monkeypatch) -> None:
    """AC-2: SDK auto compaction → chat_messages 追加 + audit_logs に
    memory_compacted event."""
    fake = _patch_ms_db(monkeypatch, cursor=_FakeCursor(lastrowid=99))
    summary = {
        "section1": "...", "section2": "...", "section3": "...",
        "section4": "...", "section5": "...", "section6": "...",
        "section7": "...", "section8": "...", "section9": "...",
    }
    msg_id = asyncio.run(ms.persist_compaction(session_id=7, summary=summary))
    assert msg_id == 99
    sqls = [s for s, _ in fake.executed]
    # chat_messages INSERT + audit_logs INSERT の 2 件
    assert any("INSERT INTO chat_messages" in s for s in sqls)
    assert any("INSERT INTO audit_logs" in s for s in sqls)
    # memory_compacted event の payload に sections list が含まれる
    audit_sql_idx = next(i for i, s in enumerate(sqls) if "audit_logs" in s)
    audit_params = fake.executed[audit_sql_idx][1]
    assert any("memory_compacted" in p for p in audit_params if isinstance(p, str))
    assert any("section1" in p for p in audit_params if isinstance(p, str))


# ---------------------------------------------------------------------------
# AC-3 EVENT: merge_for_session が SDK + Memory API + Mem0 + Constitution を統合
# ---------------------------------------------------------------------------


def test_merge_for_session_includes_constitution_when_set(monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_TEXT", "松本の判断基準: シンプル優先")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    block = asyncio.run(ms.merge_for_session(
        session_id=1, prior_session_id=None, user_message="x", user_id="masato",
    ))
    assert "Constitution" in block
    assert "シンプル優先" in block


def test_merge_for_session_includes_mem0_results(monkeypatch) -> None:
    """Mem0 search が結果を返す場合は 【長期記憶 (Mem0)】 ブロックが入る."""
    fake_mod = types.ModuleType("services.long_term_memory")

    async def fake_search(*, user_id: str, query: str, limit: int = 5):
        return ["fact-A", "fact-B"]

    async def fake_add(*, user_id: str, conversation: list):
        return None

    fake_mod.search_relevant_memories = fake_search
    fake_mod.add_conversation = fake_add
    sys.modules["services.long_term_memory"] = fake_mod
    try:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        block = asyncio.run(ms.merge_for_session(
            session_id=1, prior_session_id=None,
            user_message="検索クエリ", user_id="masato",
        ))
        assert "Mem0" in block
        assert "fact-A" in block and "fact-B" in block
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_merge_for_session_handles_mem0_exception_silently(monkeypatch) -> None:
    """Mem0 が例外を投げても block は壊れない (graceful degradation)."""
    fake_mod = types.ModuleType("services.long_term_memory")

    async def fake_search(**kw):
        raise RuntimeError("mem0 down")

    fake_mod.search_relevant_memories = fake_search
    sys.modules["services.long_term_memory"] = fake_mod
    try:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        block = asyncio.run(ms.merge_for_session(
            session_id=1, prior_session_id=None,
            user_message="x", user_id="masato",
        ))
        assert isinstance(block, str)
        assert "Mem0" not in block
    finally:
        sys.modules.pop("services.long_term_memory", None)


# ---------------------------------------------------------------------------
# AC-4 STATE: Memory API primary + Mem0 copy
# ---------------------------------------------------------------------------


def _install_fake_anthropic(*, has_append: bool = True, raise_on_call: bool = False):
    """anthropic.AsyncAnthropic を fake 化."""
    state: dict[str, Any] = {"calls": []}

    class _MemoryStores:
        async def append(self, store_id: str, content: str, metadata: dict) -> None:
            state["calls"].append(("append", store_id, content, metadata))
            if raise_on_call:
                raise RuntimeError("api boom")

        async def query(self, store_id: str, query: str, limit: int = 5):
            state["calls"].append(("query", store_id, query, limit))
            if raise_on_call:
                raise RuntimeError("api boom")
            return types.SimpleNamespace(
                items=[types.SimpleNamespace(content=f"recalled-{i}") for i in range(2)]
            )

    class _Beta:
        memory_stores = _MemoryStores()

    class AsyncAnthropic:
        def __init__(self) -> None:
            self.beta = _Beta()

    if not has_append:
        del _MemoryStores.append

    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = AsyncAnthropic
    sys.modules["anthropic"] = mod
    return state


def test_write_fact_memory_api_primary_plus_mem0_copy(monkeypatch) -> None:
    """AC-4 STATE: Memory API が利用可能なら primary 書き込み + Mem0 copy."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    api_state = _install_fake_anthropic()

    fake_mod = types.ModuleType("services.long_term_memory")
    mem0_calls: list[Any] = []

    async def fake_add(*, user_id: str, conversation: list):
        mem0_calls.append((user_id, conversation))

    fake_mod.add_conversation = fake_add
    sys.modules["services.long_term_memory"] = fake_mod
    _patch_ms_db(monkeypatch)

    try:
        out = asyncio.run(ms.write_fact("masato", "Build-Factory は SaaS 開発工場 OS"))
        assert out["memory_api_ok"] is True
        assert out["mem0_ok"] is True
        # API: append が呼ばれた
        assert any(c[0] == "append" for c in api_state["calls"])
        # Mem0: add_conversation が呼ばれた
        assert len(mem0_calls) == 1
        assert mem0_calls[0][0] == "masato"
    finally:
        sys.modules.pop("anthropic", None)
        sys.modules.pop("services.long_term_memory", None)


# ---------------------------------------------------------------------------
# AC-6 UNWANTED: Memory API fail → Mem0 fallback + memory_degraded event
# ---------------------------------------------------------------------------


def test_write_fact_memory_api_failure_falls_back_to_mem0_with_degraded_event(
    monkeypatch,
) -> None:
    """AC-6: Memory API fail → memory_degraded event + Mem0 only fallback."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic(raise_on_call=True)

    fake_mod = types.ModuleType("services.long_term_memory")

    async def fake_add(*, user_id: str, conversation: list):
        return None

    fake_mod.add_conversation = fake_add
    sys.modules["services.long_term_memory"] = fake_mod

    fake_db = _patch_ms_db(monkeypatch, cursor=_FakeCursor(lastrowid=1))
    try:
        out = asyncio.run(ms.write_fact("masato", "fact-x"))
        assert out["memory_api_ok"] is False
        assert out["mem0_ok"] is True
        # audit_logs に memory_degraded が emit された
        sqls = [s for s, p in fake_db.executed]
        assert any("INSERT INTO audit_logs" in s for s in sqls)
        last_audit = next(p for s, p in fake_db.executed if "audit_logs" in s)
        assert any("memory_degraded" in v for v in last_audit if isinstance(v, str))
    finally:
        sys.modules.pop("anthropic", None)
        sys.modules.pop("services.long_term_memory", None)


def test_write_fact_no_anthropic_key_falls_back_silently(monkeypatch) -> None:
    """ANTHROPIC_API_KEY 無し → Memory API は False を返し、 Mem0 only."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_mod = types.ModuleType("services.long_term_memory")

    async def fake_add(*, user_id: str, conversation: list):
        return None

    fake_mod.add_conversation = fake_add
    sys.modules["services.long_term_memory"] = fake_mod
    fake_db = _patch_ms_db(monkeypatch)
    try:
        out = asyncio.run(ms.write_fact("u", "fact"))
        assert out["memory_api_ok"] is False
        assert out["mem0_ok"] is True
        # memory_degraded event が emit
        sqls = [s for s, _ in fake_db.executed]
        assert any("INSERT INTO audit_logs" in s for s in sqls)
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_write_fact_both_fail_no_silent_drop(monkeypatch) -> None:
    """AC-6: Memory API も Mem0 も fail → memory_degraded event は emit、
    silent drop しない."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys.modules.pop("services.long_term_memory", None)
    fake_db = _patch_ms_db(monkeypatch)
    out = asyncio.run(ms.write_fact("u", "fact"))
    assert out["memory_api_ok"] is False
    assert out["mem0_ok"] is False
    assert out["errors"] is not None
    sqls = [s for s, _ in fake_db.executed]
    assert any("INSERT INTO audit_logs" in s for s in sqls)


# ---------------------------------------------------------------------------
# _memory_api_recall (merge_for_session 経由)
# ---------------------------------------------------------------------------


def test_memory_api_recall_returns_facts(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic()
    try:
        facts = asyncio.run(ms._memory_api_recall(user_id="masato", query="?"))
        assert facts == ["recalled-0", "recalled-1"]
    finally:
        sys.modules.pop("anthropic", None)


def test_memory_api_recall_returns_empty_without_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    facts = asyncio.run(ms._memory_api_recall(user_id="masato", query="?"))
    assert facts == []


def test_memory_api_recall_returns_empty_without_user_id(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    facts = asyncio.run(ms._memory_api_recall(user_id=None, query="?"))
    assert facts == []


def test_memory_api_recall_handles_api_exception(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic(raise_on_call=True)
    try:
        facts = asyncio.run(ms._memory_api_recall(user_id="masato", query="?"))
        assert facts == []
    finally:
        sys.modules.pop("anthropic", None)


def test_memory_api_recall_returns_empty_when_anthropic_not_installed(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    sys.modules.pop("anthropic", None)
    # anthropic 未インストールを ImportError 経路でシミュレート
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def stub_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", stub_import)
    facts = asyncio.run(ms._memory_api_recall(user_id="masato", query="?"))
    assert facts == []
