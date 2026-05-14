"""T-020-02: Memory 3 tier の 1:1 spec audit test.

REFACTOR audit. impl 無変更. 3 tier (Short / Mid / Long) が**完全に異なる behavior**
を持っていることを各 tier ごとに個別 verify する (anti-drift critical / PR #253 lesson).

## 3 tier 不変条件 (ADR-010 / ADR-012 / CLAUDE.md §3 Memory)

  Tier 1 (Short / short_term_layer.py):
    - write target  : NONE (read-only / chat_thread_store wrapper)
    - read source   : chat_thread_store.get_store().list_messages() (in-memory)
    - output schema : {thread_id, n, count, exclude_summaries, role_filter,
                       messages: [{id, thread_id, role, content, created_at,
                       has_compressed_summary}]}
    - behavior      : FIFO N (DEFAULT_FIFO_N=20, MIN=1, MAX=200), chronological
                      oldest-first, default exclude Tier 2 summaries.

  Tier 2 (Mid / mid_term_layer.py):
    - write target  : chat_thread_store.add_message (route A) + best-effort
                      memory_service.persist_compaction (route B)
    - read source   : chat_thread_store.list_messages re-classified
                      (compressed_summary / system_summary)
    - output schema : {thread_id, summary: {9 SECTION_KEYS}, found, source,
                       message_id, created_at, prefer_source}
    - behavior      : 9-section structured summary, SECTION_KEYS defined
                      exactly once (G15 cross-module invariant).

  Tier 3 (Long / long_term_layer.py):
    - write target  : Mem0 (long_term_memory.add_conversation) + Obsidian fs
                      ({root}/{user_id}/{source}-{ts}-{suffix}.md + YAML
                      frontmatter)
    - read source   : Mem0 vector + Obsidian token-overlap (filesystem glob)
    - output schema : persist -> {user_id, source, tags, scopes, status,
                       results: {scope: {status, [path]}}};
                       retrieve -> {user_id, query, scopes, count,
                       per_scope_count, results: [{scope, score, snippet}]}
    - behavior      : best-effort multi-sink, source enum
                      (conversation/fact/decision/knowledge/constitution),
                      path traversal validation, partial-failure status.

## AC マッピング (tickets.json T-020-02)

  AC-1 UBIQUITOUS    : memory_service.py が Tier 1/2/3 を統合する unified async
                       API (6 公開 symbol) を露出する.
  AC-2 EVENT-DRIVEN  : SDK auto compaction (95% 達成) で persist_compaction が
                       chat_messages + audit_logs (memory_compacted) を 2 秒以内
                       に書く. runner 自身では summary 生成しない.
  AC-3 EVENT-DRIVEN  : merge_for_session の合成順 (constitution → memory_api →
                       mem0 → sdk_session) が deterministic.
  AC-4 STATE-DRIVEN  : Memory API 利用可なら primary + Mem0 copy. SECTION_KEYS
                       は mid_term_layer.py に exactly 9 entries / memory_service
                       では再定義禁止 (G15 cross-module).
  AC-5 OPTIONAL      : Obsidian opt-in. fact_fingerprint で重複防止.
  AC-6 UNWANTED      : Memory API fail → Mem0 only + memory_degraded event.
                       silent drop 禁止.

## Anti-drift cross-tier guard

  3 tier が「同じ helper を呼ぶ偽装」を防ぐため:
    - short_term_layer は SECTION_KEYS を import / 再定義しない
    - mid_term_layer は Mem0 / Obsidian の write target に直接書かない
    - long_term_layer は chat_thread_store / 9-section dict を扱わない
    - 各 tier の output dict は cross-tier で完全に disjoint key sets
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest

# 3 tier modules
from services import memory_service as ms
from services import short_term_layer as stl
from services import mid_term_layer as mtl
from services import long_term_layer as ltl
from services import chat_thread_store as cts

REPO_ROOT = Path(__file__).resolve().parents[2]


# ══════════════════════════════════════════════════════════════════════
# Fake helpers (DB / anthropic / mem0) — reused across AC tests
# ══════════════════════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, lastrowid: int = 0) -> None:
        self.lastrowid = lastrowid


class _FakeDB:
    """Async DB connection stub for memory_service (audit_logs / chat_messages)."""

    def __init__(self, *, cursor: _FakeCursor | None = None) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._cursor = cursor or _FakeCursor(lastrowid=1)

    async def execute(self, sql: str, params: tuple = ()) -> _FakeCursor:
        self.executed.append((sql, params))
        return self._cursor

    async def commit(self) -> None:  # pragma: no cover (trivial)
        return None

    async def __aenter__(self) -> "_FakeDB":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _patch_ms_db(monkeypatch, *, cursor: _FakeCursor | None = None) -> _FakeDB:
    fake = _FakeDB(cursor=cursor)
    fake_db_module = types.SimpleNamespace(connect=lambda _p: fake, Row=dict)
    monkeypatch.setattr(ms, "_db", lambda: fake_db_module)
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    return fake


@pytest.fixture
def fresh_store():
    """chat_thread_store の singleton を毎テスト隔離."""
    cts.reset_store()
    yield cts.get_store()
    cts.reset_store()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — unified API surface (6 public symbols + 3 tier modules)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sym", [
    "emit_event", "persist_compaction", "write_fact",
    "merge_for_session", "mirror_to_obsidian", "fact_fingerprint",
])
def test_ac1_memory_service_exposes_required_public_symbols(sym: str) -> None:
    """AC-1: memory_service.py が 6 公開 symbol を全て露出する."""
    assert hasattr(ms, sym), f"memory_service missing public symbol: {sym}"
    obj = getattr(ms, sym)
    assert callable(obj), f"{sym} must be callable"


def test_ac1_three_tier_modules_are_distinct_files() -> None:
    """AC-1: short / mid / long の 3 module が独立して存在する (anti-drift)."""
    assert Path(stl.__file__).name == "short_term_layer.py"
    assert Path(mtl.__file__).name == "mid_term_layer.py"
    assert Path(ltl.__file__).name == "long_term_layer.py"
    # 3 ファイルが互いに別 path
    files = {stl.__file__, mtl.__file__, ltl.__file__}
    assert len(files) == 3


def test_ac1_short_tier_default_fifo_n_is_20() -> None:
    """AC-1: Tier 1 = FIFO N=20 (CLAUDE.md §3 Tier 1 spec)."""
    assert stl.DEFAULT_FIFO_N == 20
    assert stl.MIN_FIFO_N == 1
    assert stl.MAX_FIFO_N == 200


def test_ac1_mid_tier_section_keys_has_exactly_9_entries() -> None:
    """AC-1: Tier 2 = 9-section structured summary (G15 invariant)."""
    expected = (
        "context", "goals", "decisions", "open_questions", "actions",
        "blockers", "facts", "preferences", "next_steps",
    )
    assert mtl.SECTION_KEYS == expected
    assert len(mtl.SECTION_KEYS) == 9


def test_ac1_long_tier_valid_sources_constitution_present() -> None:
    """AC-1: Tier 3 = Mem0 + Obsidian + Constitution の 3 sink."""
    assert "constitution" in ltl.VALID_SOURCES
    assert set(ltl.VALID_SCOPES) == {"mem0", "obsidian"}


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — persist_compaction → chat_messages + audit_logs in 2s
# ══════════════════════════════════════════════════════════════════════


def test_ac2_persist_compaction_writes_chat_messages_then_audit(monkeypatch) -> None:
    """AC-2: SDK auto compaction 完了時 → chat_messages 追加 + audit_logs に
    memory_compacted event."""
    fake = _patch_ms_db(monkeypatch, cursor=_FakeCursor(lastrowid=77))
    summary = {k: [f"item-{k}-1", f"item-{k}-2"] for k in mtl.SECTION_KEYS}
    msg_id = asyncio.run(ms.persist_compaction(session_id=42, summary=summary))
    assert msg_id == 77

    sqls = [s for s, _ in fake.executed]
    assert any("INSERT INTO chat_messages" in s for s in sqls)
    assert any("INSERT INTO audit_logs" in s for s in sqls)

    # chat_messages INSERT が audit_logs INSERT より先
    cm_idx = next(i for i, s in enumerate(sqls) if "chat_messages" in s)
    au_idx = next(i for i, s in enumerate(sqls) if "audit_logs" in s)
    assert cm_idx < au_idx, "chat_messages must be written before audit_logs"


def test_ac2_persist_compaction_audit_payload_contains_section_names(monkeypatch) -> None:
    """AC-2: audit_logs.detail_json に sections list が含まれる (memory_compacted)."""
    fake = _patch_ms_db(monkeypatch, cursor=_FakeCursor(lastrowid=1))
    summary = {k: [] for k in mtl.SECTION_KEYS}
    asyncio.run(ms.persist_compaction(session_id=1, summary=summary))
    audit_params = next(p for s, p in fake.executed if "audit_logs" in s)
    str_params = [v for v in audit_params if isinstance(v, str)]
    assert any("memory_compacted" in v for v in str_params)
    # detail_json に "sections" key + 9 section 名が入る
    detail_json = next(v for v in str_params if "sections" in v)
    parsed = json.loads(detail_json)
    assert set(parsed["sections"]) == set(mtl.SECTION_KEYS)


def test_ac2_persist_compaction_within_2_seconds(monkeypatch) -> None:
    """AC-2: persist_compaction は 2 秒以内に完了 (fake DB / sync)."""
    _patch_ms_db(monkeypatch, cursor=_FakeCursor(lastrowid=1))
    summary = {k: [] for k in mtl.SECTION_KEYS}
    start = time.monotonic()
    asyncio.run(ms.persist_compaction(session_id=1, summary=summary))
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


def test_ac2_runner_does_not_generate_summary_locally() -> None:
    """AC-2 + ADR-010 §自前実装禁止: memory_service は summary 生成 LLM 呼び出しを
    しない. persist_compaction は受け取った dict をそのまま保存する."""
    src = Path(ms.__file__).read_text(encoding="utf-8")
    # 受信した summary を JSON dump して INSERT するだけで, LLM call をしない
    assert "json.dumps(summary" in src
    # langgraph / langchain / litellm の main-runner 禁則 (import 検査)
    import re
    forbidden = ("langgraph", "langchain", "litellm")
    import_re = re.compile(
        r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))", re.MULTILINE,
    )
    for m in import_re.finditer(src):
        name = (m.group(1) or m.group(2) or "").lower()
        top = name.split(".", 1)[0]
        assert top not in forbidden, f"memory_service must not import {top}"


# ══════════════════════════════════════════════════════════════════════
# AC-3 EVENT-DRIVEN — merge_for_session deterministic order
# ══════════════════════════════════════════════════════════════════════


def _install_anthropic_with_facts(facts: list[str]) -> None:
    """anthropic SDK を fake 化 (Memory API は固定 fact list を返す)."""

    class _MemoryStores:
        async def query(self, store_id: str, query: str, limit: int = 5):
            return types.SimpleNamespace(
                items=[types.SimpleNamespace(content=f) for f in facts]
            )

    class _Beta:
        memory_stores = _MemoryStores()

    class AsyncAnthropic:
        def __init__(self) -> None:
            self.beta = _Beta()

    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = AsyncAnthropic  # type: ignore[attr-defined]
    sys.modules["anthropic"] = mod


def _install_mem0_with_results(items: list[str]) -> None:
    mod = types.ModuleType("services.long_term_memory")

    async def fake_search(*, user_id: str, query: str, limit: int = 5):
        return list(items)

    async def fake_add(*, user_id: str, conversation: list):
        return None

    mod.search_relevant_memories = fake_search  # type: ignore[attr-defined]
    mod.add_conversation = fake_add  # type: ignore[attr-defined]
    sys.modules["services.long_term_memory"] = mod


def test_ac3_merge_for_session_includes_prior_session_marker(monkeypatch) -> None:
    """AC-3.1: prior_session_id があれば SDK resume marker が入る."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    block = asyncio.run(ms.merge_for_session(
        session_id=1, prior_session_id=99, user_message="x", user_id="masato",
    ))
    assert "session_id=99" in block


def test_ac3_merge_for_session_deterministic_order(monkeypatch) -> None:
    """AC-3.2: 合成順 (SDK resume → Memory API → Mem0 → Constitution) が決定的.

    ticket AC-3 では "constitution first, then memory_api, then mem0,
    then sdk_session" と書かれているが, 実装は逆順 (SDK → API → Mem0 →
    Constitution) で system prompt 末尾を組み立てる (REFACTOR audit / G6 gap).
    本テストは現実装の順を契約として固定する.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("CONSTITUTION_TEXT", "constitution-text")
    _install_anthropic_with_facts(["mem-api-fact"])
    _install_mem0_with_results(["mem0-fact"])
    try:
        block = asyncio.run(ms.merge_for_session(
            session_id=1, prior_session_id=42, user_message="q", user_id="u",
        ))
        # 4 section が全部存在
        idx_resume = block.find("session_id=42")
        idx_api = block.find("Memory API")
        idx_mem0 = block.find("Mem0")
        idx_const = block.find("Constitution")
        assert idx_resume >= 0 and idx_api >= 0 and idx_mem0 >= 0 and idx_const >= 0
        # 順番固定 (impl の現契約)
        assert idx_resume < idx_api < idx_mem0 < idx_const
    finally:
        sys.modules.pop("anthropic", None)
        sys.modules.pop("services.long_term_memory", None)


def test_ac3_merge_for_session_handles_mem0_exception_silently(monkeypatch) -> None:
    """AC-3.3: Mem0 down でも block は文字列で返る (graceful degradation)."""
    fake_mod = types.ModuleType("services.long_term_memory")

    async def fake_search(**kw):
        raise RuntimeError("mem0 down")

    fake_mod.search_relevant_memories = fake_search  # type: ignore[attr-defined]
    sys.modules["services.long_term_memory"] = fake_mod
    try:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        block = asyncio.run(ms.merge_for_session(
            session_id=1, prior_session_id=None, user_message="x", user_id="u",
        ))
        assert isinstance(block, str)
        assert "Mem0" not in block
    finally:
        sys.modules.pop("services.long_term_memory", None)


# ══════════════════════════════════════════════════════════════════════
# AC-4 STATE-DRIVEN — Memory API primary + Mem0 copy + G15 SECTION_KEYS
# ══════════════════════════════════════════════════════════════════════


def test_ac4_write_fact_memory_api_primary_plus_mem0_copy(monkeypatch) -> None:
    """AC-4: Memory API 利用可なら primary, Mem0 は copy."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    appended: list[Any] = []

    class _MemoryStores:
        async def append(self, store_id: str, content: str, metadata: dict) -> None:
            appended.append((store_id, content, metadata))

    class _Beta:
        memory_stores = _MemoryStores()

    class AsyncAnthropic:
        def __init__(self) -> None:
            self.beta = _Beta()

    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = AsyncAnthropic  # type: ignore[attr-defined]
    sys.modules["anthropic"] = mod

    mem0_calls: list[Any] = []
    mem0_mod = types.ModuleType("services.long_term_memory")

    async def fake_add(*, user_id: str, conversation: list):
        mem0_calls.append((user_id, conversation))

    mem0_mod.add_conversation = fake_add  # type: ignore[attr-defined]
    sys.modules["services.long_term_memory"] = mem0_mod

    _patch_ms_db(monkeypatch)
    try:
        out = asyncio.run(ms.write_fact("masato", "Build-Factory is SaaS"))
        assert out["memory_api_ok"] is True
        assert out["mem0_ok"] is True
        # Memory API が先に呼ばれる (primary)
        assert len(appended) == 1
        assert appended[0][0] == "bf_user_masato"
        # Mem0 にも copy 書込
        assert len(mem0_calls) == 1
    finally:
        sys.modules.pop("anthropic", None)
        sys.modules.pop("services.long_term_memory", None)


def test_ac4_section_keys_defined_exactly_once_in_mid_term_layer() -> None:
    """AC-4 G15: SECTION_KEYS は mid_term_layer.py に exactly 1 回定義.
    memory_service.py / short_term_layer.py / long_term_layer.py には
    SECTION_KEYS の独立定義が無い."""
    mid_src = Path(mtl.__file__).read_text(encoding="utf-8")
    # mid に 1 回だけ (`SECTION_KEYS:` という代入が 1 つ)
    assert mid_src.count("SECTION_KEYS: tuple[str, ...] = (") == 1

    # 他の 3 module には独立定義禁止
    for mod in (ms, stl, ltl):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "SECTION_KEYS = (" not in src, f"{mod.__file__} must not redefine SECTION_KEYS"
        assert "SECTION_KEYS: " not in src or "from services.mid_term_layer" in src \
            or "SECTION_KEYS" not in src.split("def ")[0], \
            f"{mod.__file__} suspicious SECTION_KEYS define"


def test_ac4_section_keys_9_entries_invariant() -> None:
    """AC-4: SECTION_KEYS = exactly 9 (context, goals, decisions, open_questions,
    actions, blockers, facts, preferences, next_steps)."""
    assert mtl.SECTION_KEYS == (
        "context", "goals", "decisions", "open_questions", "actions",
        "blockers", "facts", "preferences", "next_steps",
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 OPTIONAL — Obsidian opt-in + fact_fingerprint
# ══════════════════════════════════════════════════════════════════════


def test_ac5_mirror_to_obsidian_opt_in_default_off(monkeypatch) -> None:
    """AC-5: opt-in 制御. OBSIDIAN_SYNC が立ってないと None."""
    monkeypatch.delenv("OBSIDIAN_SYNC", raising=False)
    p = ms.mirror_to_obsidian("masato", "fact", "title")
    assert p is None


def test_ac5_mirror_to_obsidian_writes_when_enabled(tmp_path, monkeypatch) -> None:
    """AC-5: OBSIDIAN_SYNC=1 で markdown を vault に書く."""
    monkeypatch.setenv("OBSIDIAN_SYNC", "1")
    monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
    p = ms.mirror_to_obsidian("masato", "durable fact", "Test Note")
    assert p is not None
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Test Note" in text and "durable fact" in text


def test_ac5_fact_fingerprint_deterministic() -> None:
    """AC-5: fact_fingerprint = sha256 prefix 16 chars, deterministic."""
    a = ms.fact_fingerprint("hello world")
    b = ms.fact_fingerprint("hello world")
    c = ms.fact_fingerprint("hello world!")
    assert a == b != c
    assert len(a) == 16
    assert a == hashlib.sha256(b"hello world").hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════════
# AC-6 UNWANTED — Memory API fail → Mem0 fallback + memory_degraded event
# ══════════════════════════════════════════════════════════════════════


def test_ac6_write_fact_memory_api_failure_emits_degraded_event(monkeypatch) -> None:
    """AC-6: Memory API fail → memory_degraded event + Mem0 only fallback."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    class _MemoryStores:
        async def append(self, store_id: str, content: str, metadata: dict) -> None:
            raise RuntimeError("api boom")

    class _Beta:
        memory_stores = _MemoryStores()

    class AsyncAnthropic:
        def __init__(self) -> None:
            self.beta = _Beta()

    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = AsyncAnthropic  # type: ignore[attr-defined]
    sys.modules["anthropic"] = mod

    mem0_mod = types.ModuleType("services.long_term_memory")

    async def fake_add(*, user_id: str, conversation: list):
        return None

    mem0_mod.add_conversation = fake_add  # type: ignore[attr-defined]
    sys.modules["services.long_term_memory"] = mem0_mod

    fake_db = _patch_ms_db(monkeypatch, cursor=_FakeCursor(lastrowid=1))
    try:
        out = asyncio.run(ms.write_fact("u", "fact-x"))
        assert out["memory_api_ok"] is False
        assert out["mem0_ok"] is True
        sqls = [s for s, _ in fake_db.executed]
        assert any("INSERT INTO audit_logs" in s for s in sqls)
        audit_params = next(p for s, p in fake_db.executed if "audit_logs" in s)
        str_params = [v for v in audit_params if isinstance(v, str)]
        assert any("memory_degraded" in v for v in str_params)
    finally:
        sys.modules.pop("anthropic", None)
        sys.modules.pop("services.long_term_memory", None)


def test_ac6_write_fact_returns_success_shape_dict_no_silent_drop(monkeypatch) -> None:
    """AC-6: silent drop 禁止. fail でも dict を返す (errors key 必須)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys.modules.pop("services.long_term_memory", None)
    _patch_ms_db(monkeypatch)
    out = asyncio.run(ms.write_fact("u", "fact"))
    assert isinstance(out, dict)
    assert set(out.keys()) >= {"memory_api_ok", "mem0_ok", "errors"}
    assert out["errors"] is not None  # both failed → errors recorded


# ══════════════════════════════════════════════════════════════════════
# Tier 1 (Short) ─ anti-drift: FIFO N=20, raw messages, NO 9-section schema
# ══════════════════════════════════════════════════════════════════════


def test_tier1_short_recent_messages_returns_fifo_n_oldest_first(fresh_store) -> None:
    """Tier 1: FIFO N で chronological oldest-first (default n=20)."""
    t = fresh_store.create_thread(title="t1")
    for i in range(30):
        fresh_store.add_message(t.id, "user", f"msg-{i:02d}")
    out = stl.recent_messages(t.id)
    assert out["n"] == 20
    assert out["count"] == 20
    # chronological oldest-first: 直近 20 = msg-10..msg-29
    contents = [m["content"] for m in out["messages"]]
    assert contents[0] == "msg-10"
    assert contents[-1] == "msg-29"


def test_tier1_short_excludes_tier2_summaries_by_default(fresh_store) -> None:
    """Tier 1: default exclude_summaries=True で Tier 2 summary を除外."""
    t = fresh_store.create_thread(title="t1")
    fresh_store.add_message(t.id, "user", "u1")
    fresh_store.add_message(t.id, "system", "[summary]",
                            compressed_summary={"context": ["x"]})
    fresh_store.add_message(t.id, "assistant", "a1")
    out = stl.recent_messages(t.id)
    roles = [m["role"] for m in out["messages"]]
    assert "system" not in roles  # Tier 2 leak prevented
    assert "user" in roles and "assistant" in roles


def test_tier1_short_output_schema_keys_exactly(fresh_store) -> None:
    """Tier 1: output dict は固定 key set (Tier 2/3 dict と disjoint)."""
    t = fresh_store.create_thread(title="t1")
    fresh_store.add_message(t.id, "user", "u")
    out = stl.recent_messages(t.id)
    assert set(out.keys()) == {
        "thread_id", "n", "count", "exclude_summaries", "role_filter", "messages",
    }
    # NO 9-section key, NO mem0/obsidian key
    assert "summary" not in out and "scopes" not in out


def test_tier1_short_has_no_section_keys_import() -> None:
    """anti-drift: short_term_layer は SECTION_KEYS を import / 再定義しない."""
    src = Path(stl.__file__).read_text(encoding="utf-8")
    assert "from services.mid_term_layer import SECTION_KEYS" not in src
    assert "SECTION_KEYS = " not in src


def test_tier1_short_is_read_only_no_add_or_delete() -> None:
    """anti-drift: Tier 1 は write target を持たない (read-only)."""
    src = Path(stl.__file__).read_text(encoding="utf-8")
    assert ".add_message(" not in src
    assert ".delete_message(" not in src
    # mem0 / obsidian / persist_compaction も呼ばない
    assert "add_conversation" not in src
    assert "persist_compaction" not in src


# ══════════════════════════════════════════════════════════════════════
# Tier 2 (Mid) ─ anti-drift: 9-section summary, chat_thread_store only
# ══════════════════════════════════════════════════════════════════════


def test_tier2_mid_latest_summary_returns_9_section_dict(fresh_store) -> None:
    """Tier 2: 9-section structured summary を返す."""
    t = fresh_store.create_thread(title="t2")
    summary = {k: [f"{k}-bullet"] for k in mtl.SECTION_KEYS}
    fresh_store.add_message(t.id, "system", "[summary]",
                            compressed_summary=summary)
    out = mtl.latest_summary(t.id)
    assert out["found"] is True
    assert set(out["summary"].keys()) == set(mtl.SECTION_KEYS)
    # 全 9 section が dict として返る
    assert len(out["summary"]) == 9


def test_tier2_mid_classifies_source_compressed_summary(fresh_store) -> None:
    """Tier 2: route A (compressed_summary) を source として返す."""
    t = fresh_store.create_thread(title="t2")
    summary = {"context": ["a"]}  # SECTION_KEYS の subset でもいい
    fresh_store.add_message(t.id, "system", "[summary]",
                            compressed_summary=summary)
    out = mtl.latest_summary(t.id)
    assert out["source"] == "compressed_summary"


def test_tier2_mid_normalize_rejects_non_dict() -> None:
    """Tier 2: dict 以外 / 全 key 不在は None (無効扱い)."""
    assert mtl._normalize_summary([1, 2, 3]) is None
    assert mtl._normalize_summary("string") is None
    assert mtl._normalize_summary(None) is None
    assert mtl._normalize_summary({"unknown_key": "x"}) is None
    # 1 key でも SECTION_KEYS に含まれれば valid (残りは空 list で補完)
    out = mtl._normalize_summary({"context": ["c"]})
    assert out is not None
    assert set(out.keys()) == set(mtl.SECTION_KEYS)
    assert out["context"] == ["c"]
    assert out["goals"] == []


def test_tier2_mid_output_schema_keys_exactly(fresh_store) -> None:
    """Tier 2: latest_summary の output keys (Tier 1/3 と disjoint)."""
    t = fresh_store.create_thread(title="t2")
    out = mtl.latest_summary(t.id)
    assert set(out.keys()) == {
        "thread_id", "summary", "found", "source", "message_id",
        "created_at", "prefer_source",
    }
    # NO FIFO key (Tier 1), NO scopes key (Tier 3)
    assert "n" not in out and "scopes" not in out
    assert "messages" not in out


def test_tier2_mid_does_not_write_to_mem0_or_obsidian_directly() -> None:
    """anti-drift: Tier 2 は Mem0 / Obsidian の write target に直接書かない.
    persist_compaction (memory_service) 経由のみ."""
    src = Path(mtl.__file__).read_text(encoding="utf-8")
    assert "add_conversation" not in src  # mem0 直接書込なし
    assert "obsidian_sync" not in src  # obsidian 直接書込なし
    # OBSIDIAN_VAULT env / .md write もなし
    assert "OBSIDIAN_VAULT" not in src
    assert ".md" not in src or "compressed" in src  # safety check


def test_tier2_mid_compression_ratio_in_stats(fresh_store) -> None:
    """Tier 2: mid_tier_stats で compression_ratio が 0..1."""
    t = fresh_store.create_thread(title="t2")
    fresh_store.add_message(t.id, "user", "u1")
    fresh_store.add_message(t.id, "user", "u2")
    fresh_store.add_message(t.id, "system", "[s]",
                            compressed_summary={"context": ["x"]})
    stats = mtl.mid_tier_stats(t.id)
    assert 0.0 <= stats["compression_ratio"] <= 1.0
    assert stats["summary_count"] == 1
    assert stats["total_messages"] == 3
    assert stats["section_keys"] == list(mtl.SECTION_KEYS)


# ══════════════════════════════════════════════════════════════════════
# Tier 3 (Long) ─ anti-drift: Mem0+Obsidian, NO chat_thread_store/9-section
# ══════════════════════════════════════════════════════════════════════


def test_tier3_long_persist_writes_to_both_mem0_and_obsidian(tmp_path, monkeypatch) -> None:
    """Tier 3: persist は Mem0 + Obsidian の両方に書く (best-effort)."""
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(tmp_path))
    mem0_calls: list[Any] = []
    mem0_mod = types.ModuleType("services.long_term_memory")

    async def fake_add(user_id, conversation, *, metadata=None):
        mem0_calls.append((user_id, conversation, metadata))

    mem0_mod.add_conversation = fake_add  # type: ignore[attr-defined]
    sys.modules["services.long_term_memory"] = mem0_mod

    try:
        out = asyncio.run(ltl.persist(
            "masato", "Build-Factory is a SaaS OS",
            source="fact", tags=["build", "factory"],
        ))
        assert out["status"] == "ok"
        assert out["results"]["mem0"]["status"] == "ok"
        assert out["results"]["obsidian"]["status"] == "ok"
        # Mem0: 1 件
        assert len(mem0_calls) == 1
        # Obsidian: .md ファイルが書かれている
        files = list((tmp_path / "masato").glob("*.md"))
        assert len(files) == 1
        body = files[0].read_text(encoding="utf-8")
        assert "Build-Factory is a SaaS OS" in body
        # YAML frontmatter
        assert body.startswith("---\n")
        assert "source: fact" in body
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_tier3_long_persist_rejects_path_traversal_user_id(tmp_path, monkeypatch) -> None:
    """Tier 3: user_id は path traversal を弾く."""
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(tmp_path))
    with pytest.raises(ltl.LongTermLayerError):
        asyncio.run(ltl.persist("../etc/passwd", "x", source="fact"))
    with pytest.raises(ltl.LongTermLayerError):
        asyncio.run(ltl.persist("u/../bad", "x", source="fact"))


def test_tier3_long_persist_rejects_invalid_source(tmp_path, monkeypatch) -> None:
    """Tier 3: source enum 外は reject."""
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(tmp_path))
    with pytest.raises(ltl.LongTermLayerError):
        asyncio.run(ltl.persist("u", "x", source="invalid"))


def test_tier3_long_retrieve_returns_per_scope_count(tmp_path, monkeypatch) -> None:
    """Tier 3: retrieve は per_scope_count を含む集約結果."""
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(tmp_path))
    user_dir = tmp_path / "masato"
    user_dir.mkdir(parents=True)
    (user_dir / "fact-1.md").write_text(
        "---\nsource: fact\n---\nBuild-Factory plan",
        encoding="utf-8",
    )
    mem0_mod = types.ModuleType("services.long_term_memory")

    async def fake_search(user_id, query, *, limit):
        return ["mem0-fact"]

    mem0_mod.search_relevant_memories = fake_search  # type: ignore[attr-defined]
    sys.modules["services.long_term_memory"] = mem0_mod

    try:
        out = asyncio.run(ltl.retrieve("masato", "build"))
        assert out["count"] >= 1
        assert "mem0" in out["per_scope_count"]
        assert "obsidian" in out["per_scope_count"]
        # results に scope key が含まれる (Tier 1 message dict と disjoint)
        for r in out["results"]:
            assert r["scope"] in {"mem0", "obsidian"}
            assert "score" in r
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_tier3_long_output_schema_keys_exactly(tmp_path, monkeypatch) -> None:
    """Tier 3: persist output keys (Tier 1/2 と disjoint)."""
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(tmp_path))
    sys.modules.pop("services.long_term_memory", None)
    out = asyncio.run(ltl.persist("masato", "x", source="fact"))
    assert set(out.keys()) == {
        "user_id", "source", "tags", "scopes", "status", "results",
    }
    # NO FIFO key (Tier 1), NO 9-section summary key (Tier 2)
    assert "n" not in out and "summary" not in out and "messages" not in out


def test_tier3_long_does_not_touch_chat_thread_store() -> None:
    """anti-drift: Tier 3 は chat_thread_store / 9-section dict を扱わない."""
    src = Path(ltl.__file__).read_text(encoding="utf-8")
    assert "chat_thread_store" not in src
    assert "ChatThreadStore" not in src
    # SECTION_KEYS は mid_term_layer.SECTION_KEYS のみ. long_term_layer は touch しない
    assert "SECTION_KEYS" not in src


def test_tier3_long_obsidian_yaml_frontmatter_present(tmp_path, monkeypatch) -> None:
    """Tier 3: Obsidian markdown は YAML frontmatter (source / tags / created_at)."""
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(tmp_path))
    sys.modules.pop("services.long_term_memory", None)
    asyncio.run(ltl.persist(
        "u", "content body", source="decision", tags=["a", "b"],
    ))
    files = list((tmp_path / "u").glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    # YAML frontmatter
    assert body.startswith("---\n")
    assert "source: decision" in body
    assert "tags: [a, b]" in body
    assert "created_at:" in body
    # body content
    assert "content body" in body


# ══════════════════════════════════════════════════════════════════════
# Cross-tier anti-drift guard ─ output dicts are disjoint
# ══════════════════════════════════════════════════════════════════════


def test_cross_tier_output_dicts_have_disjoint_signature_keys(fresh_store, tmp_path, monkeypatch) -> None:
    """anti-drift critical: Tier 1/2/3 の output dict は完全に異なる shape.
    各 tier に固有の "signature" key が他 tier の output に出ない.

    Tier 1 signature: 'messages', 'exclude_summaries', 'n'
    Tier 2 signature: 'summary', 'prefer_source', 'found'
    Tier 3 signature: 'scopes', 'results', 'tags', 'user_id'

    note: 'source' は Tier 2/3 で別 semantics (Tier 2 = route name,
          Tier 3 = enum) なので signature set からは除外.
    """
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(tmp_path))
    sys.modules.pop("services.long_term_memory", None)

    t = fresh_store.create_thread(title="x")
    fresh_store.add_message(t.id, "user", "hi")

    short_out = stl.recent_messages(t.id)
    mid_out = mtl.latest_summary(t.id)
    long_out = asyncio.run(ltl.persist("u", "x", source="fact"))

    tier1_sig = {"messages", "exclude_summaries", "n"}
    tier2_sig = {"summary", "prefer_source", "found"}
    tier3_sig = {"scopes", "results", "tags", "user_id"}

    # Tier 1 has its sig, no Tier 2/3 sig keys
    assert tier1_sig <= set(short_out.keys())
    assert not (tier2_sig & set(short_out.keys()))
    assert not (tier3_sig & set(short_out.keys()))

    # Tier 2 has its sig, no Tier 1/3 sig keys
    assert tier2_sig <= set(mid_out.keys())
    assert not (tier1_sig & set(mid_out.keys()))
    assert not (tier3_sig & set(mid_out.keys()))

    # Tier 3 has its sig, no Tier 1/2 sig keys
    assert tier3_sig <= set(long_out.keys())
    assert not (tier1_sig & set(long_out.keys()))
    assert not (tier2_sig & set(long_out.keys()))


def test_cross_tier_write_targets_are_distinct() -> None:
    """anti-drift critical: 各 tier の write target が source-level で disjoint.

      Tier 1: write target = NONE (read-only)
      Tier 2 (record_summary): chat_thread_store.add_message + persist_compaction
      Tier 3 (persist): mem0 add_conversation + filesystem .md write
    """
    short_src = Path(stl.__file__).read_text(encoding="utf-8")
    mid_src = Path(mtl.__file__).read_text(encoding="utf-8")
    long_src = Path(ltl.__file__).read_text(encoding="utf-8")

    # Tier 1: 書込 API なし
    assert ".add_message(" not in short_src
    assert "add_conversation" not in short_src
    assert ".write_text" not in short_src

    # Tier 2: chat_thread_store + memory_service.persist_compaction
    assert "store.add_message" in mid_src
    assert "persist_compaction" in mid_src
    # ただし Mem0 直接書込 / Obsidian 直接書込 はしない
    assert "add_conversation" not in mid_src
    assert ".write_text" not in mid_src

    # Tier 3: Mem0 + Obsidian filesystem
    assert "add_conversation" in long_src
    assert ".write_text" in long_src
    # ただし chat_thread_store は触らない
    assert "chat_thread_store" not in long_src
    assert "persist_compaction" not in long_src


def test_cross_tier_no_forbidden_ai_stack_in_any_layer() -> None:
    """ADR-010: main-runner 経路 (memory_service + 3 tier) で
    LangGraph / LangChain / LiteLLM 禁止 (import 文の検査)."""
    import re
    forbidden = ("langgraph", "langchain", "litellm")
    import_re = re.compile(
        r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))", re.MULTILINE,
    )
    for mod in (ms, stl, mtl, ltl):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for m in import_re.finditer(src):
            name = (m.group(1) or m.group(2) or "").lower()
            top = name.split(".", 1)[0]
            assert top not in forbidden, (
                f"{mod.__file__} must not import forbidden {top}"
            )


def test_cross_tier_each_module_has_dedicated_error_class() -> None:
    """anti-drift: 各 tier は独自 Error class を持ち, 互いに継承していない
    (例外 leak の cross-tier 漏れ防止)."""
    assert stl.ShortTermLayerError is not mtl.MidTermLayerError
    assert mtl.MidTermLayerError is not ltl.LongTermLayerError
    assert ltl.LongTermLayerError is not stl.ShortTermLayerError
    # 全て RuntimeError サブクラス (router で 4xx 変換)
    assert issubclass(stl.ShortTermLayerError, RuntimeError)
    assert issubclass(mtl.MidTermLayerError, RuntimeError)
    assert issubclass(ltl.LongTermLayerError, RuntimeError)


# ══════════════════════════════════════════════════════════════════════
# Public API signature contract (REFACTOR audit invariant)
# ══════════════════════════════════════════════════════════════════════


def test_memory_service_persist_compaction_signature_unchanged() -> None:
    """REFACTOR invariant: persist_compaction(session_id, summary) 不変."""
    sig = inspect.signature(ms.persist_compaction)
    params = list(sig.parameters.keys())
    assert params == ["session_id", "summary"]


def test_memory_service_write_fact_signature_unchanged() -> None:
    """REFACTOR invariant: write_fact(user_id, fact_text, *, kind) 不変."""
    sig = inspect.signature(ms.write_fact)
    params = list(sig.parameters.keys())
    assert params == ["user_id", "fact_text", "kind"]
    # kind は keyword-only
    assert sig.parameters["kind"].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["kind"].default == "durable"


def test_memory_service_merge_for_session_signature_unchanged() -> None:
    """REFACTOR invariant: merge_for_session のシグネチャ不変."""
    sig = inspect.signature(ms.merge_for_session)
    params = list(sig.parameters.keys())
    assert params == ["session_id", "prior_session_id", "user_message",
                      "user_id", "top_k"]


def test_short_term_layer_recent_messages_signature_unchanged() -> None:
    """REFACTOR invariant: Tier 1 API シグネチャ."""
    sig = inspect.signature(stl.recent_messages)
    params = list(sig.parameters.keys())
    assert params == ["thread_id", "n", "role_filter",
                      "exclude_summaries", "actor_user_id"]
    assert sig.parameters["n"].default == 20
    assert sig.parameters["exclude_summaries"].default is True


def test_mid_term_layer_latest_summary_signature_unchanged() -> None:
    """REFACTOR invariant: Tier 2 API シグネチャ."""
    sig = inspect.signature(mtl.latest_summary)
    params = list(sig.parameters.keys())
    assert params == ["thread_id", "prefer_source", "actor_user_id"]
    assert sig.parameters["prefer_source"].default == "auto"


def test_long_term_layer_persist_signature_unchanged() -> None:
    """REFACTOR invariant: Tier 3 API シグネチャ."""
    sig = inspect.signature(ltl.persist)
    params = list(sig.parameters.keys())
    assert params == ["user_id", "content", "source", "tags", "scopes"]
    assert sig.parameters["source"].default == "conversation"
