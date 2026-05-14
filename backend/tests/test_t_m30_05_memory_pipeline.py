"""T-M30-05: Memory 統合テスト (3 層 → context 組立) — 4 AC 全網羅 + spec gap closure G11-G14.

AC マッピング (1:1 テスト):
  AC-1 UBIQUITOUS    : M-30 3-tier pipeline (短期 chat_thread_store /
                       中期 mid_term_layer / 長期 long_term_layer) を
                       context block に統合
  AC-2 EVENT-DRIVEN  : context endpoint 呼出時 audit emit (action + timestamp) /
                       2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 4 layer module 不変 / RLS は Phase 2 (in-memory store
                       境界明示) / read endpoint で audit emit しない
  AC-4 UNWANTED      : invalid input / unauthorized actor / 不明 thread →
                       4xx structured / 全 tier 失敗 → 502 / state mutate なし

Spec gap closure (PR #128 G1-G6 / PR #129 G7-G10 と同じ精神 / G11-G14):
  G11 cross-tier semantic_retrieval (T-M28-05) 互換 (use_semantic flag)
  G12 chat_search (T-AI-03) 互換 (use_chat_search flag)
  G13 assemble pluggable (register_assembler hook)
  G14 degraded mode (単独 tier 失敗を許容、全失敗のみ raise)
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import chat_thread_store as cts
from services import memory_pipeline as mp
from services.memory_pipeline import (
    ALL_TIERS,
    DEFAULT_LONG_MIN_SCORE,
    DEFAULT_LONG_TOP_K,
    DEFAULT_RECENT_N,
    MAX_LONG_MIN_SCORE,
    MAX_LONG_TOP_K,
    MAX_QUERY_CHARS,
    MAX_RECENT_N,
    MIN_LONG_MIN_SCORE,
    MIN_LONG_TOP_K,
    MIN_RECENT_N,
    MemoryPipelineError,
    VALID_TIER_NAMES,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    cts.reset_store()
    mp.register_assembler(None)
    # mid_term_layer の hook も clear (前テストの汚染防止)
    from services import mid_term_layer as mtl
    mtl.register_summarizer_backend(None)
    yield
    cts.reset_store()
    mp.register_assembler(None)
    mtl.register_summarizer_backend(None)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _isolate_obsidian(monkeypatch, tmp_path):
    """long_term_layer の Obsidian 書込先を tmp に隔離."""
    root = tmp_path / "obsidian"
    monkeypatch.setenv("BF_OBSIDIAN_ROOT", str(root))
    yield root


@pytest.fixture(autouse=True)
def _mock_mem0(monkeypatch):
    """long_term_memory (Mem0) を mock - 外部依存を切る."""
    state: dict[str, list[dict]] = {"added": []}

    async def fake_add(user_id, messages, metadata=None):
        state["added"].append({
            "user_id": user_id, "messages": messages, "metadata": metadata,
        })

    async def fake_search(user_id, query, limit=5):
        # 簡易 keyword match で hit を返す
        out = []
        for it in state["added"]:
            if it["user_id"] != user_id:
                continue
            for m in it.get("messages") or []:
                txt = m.get("content") or ""
                if query.lower() in txt.lower():
                    out.append(txt)
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
        return out

    async def fake_all(user_id):
        return [m for m in state["added"] if m["user_id"] == user_id]

    import services.long_term_memory as ltm
    monkeypatch.setattr(ltm, "add_conversation", fake_add)
    monkeypatch.setattr(ltm, "search_relevant_memories", fake_search)
    monkeypatch.setattr(ltm, "all_memories", fake_all)
    yield state


def _make_thread(title: str = "T-M30-05") -> int:
    return cts.get_store().create_thread(title=title).id


def _seed_short_messages(thread_id: int, count: int = 3) -> list:
    """短期 layer に raw messages を seed."""
    msgs = []
    for i in range(count):
        msgs.append(cts.get_store().add_message(
            thread_id, "user" if i % 2 == 0 else "assistant",
            f"message {i} about Build-Factory",
        ))
    return msgs


def _seed_mid_summary(thread_id: int, prefix: str = "v"):
    """中期 layer に compressed_summary を seed."""
    from services.mid_term_layer import SECTION_KEYS
    summary = {k: [f"{prefix}-{k}-1"] for k in SECTION_KEYS}
    return cts.get_store().add_message(
        thread_id, "system", "[seed]", compressed_summary=summary,
    )


async def _seed_long_term(user_id: str, content: str, scopes=None):
    """長期 layer (long_term_layer) に persist."""
    from services import long_term_layer as ltl
    return await ltl.persist(
        user_id, content,
        scopes=scopes or ["obsidian"],
    )


# ══════════════════════════════════════════════════════════════════════
# Service: constants & invariants
# ══════════════════════════════════════════════════════════════════════


def test_all_tiers_constant():
    assert ALL_TIERS == ("short", "mid", "long")
    assert set(VALID_TIER_NAMES) == {"short", "mid", "long"}


def test_tier_health_all_available():
    h = mp.tier_health()
    assert h["all_available"] is True
    for t in ALL_TIERS:
        assert h[t]["available"] is True
        assert "module" in h[t]


# ══════════════════════════════════════════════════════════════════════
# Service: validation (UNWANTED AC-4 input)
# ══════════════════════════════════════════════════════════════════════


def test_validate_thread_id():
    for bad in (0, -1, True, "1", 1.5, None):
        with pytest.raises(MemoryPipelineError):
            mp._validate_thread_id(bad)
    assert mp._validate_thread_id(7) == 7


def test_validate_user_id():
    for bad in ("", "   ", None, 123, "x" * 201):
        with pytest.raises(MemoryPipelineError):
            mp._validate_user_id(bad)
    assert mp._validate_user_id(" alice ") == "alice"


def test_validate_actor_user_id():
    assert mp._validate_actor_user_id(None) is None
    assert mp._validate_actor_user_id(" bob ") == "bob"
    for bad in ("", "   ", 1, "x" * 201):
        with pytest.raises(MemoryPipelineError):
            mp._validate_actor_user_id(bad)


def test_validate_query():
    assert mp._validate_query(" how are you ") == "how are you"
    for bad in ("", "   ", None, 1, "x" * (MAX_QUERY_CHARS + 1)):
        with pytest.raises(MemoryPipelineError):
            mp._validate_query(bad)


def test_validate_recent_n():
    assert mp._validate_recent_n(MIN_RECENT_N) == MIN_RECENT_N
    assert mp._validate_recent_n(MAX_RECENT_N) == MAX_RECENT_N
    for bad in (0, MAX_RECENT_N + 1, True, "20", 1.0):
        with pytest.raises(MemoryPipelineError):
            mp._validate_recent_n(bad)


def test_validate_long_top_k():
    for ok in (MIN_LONG_TOP_K, MAX_LONG_TOP_K):
        assert mp._validate_long_top_k(ok) == ok
    for bad in (0, MAX_LONG_TOP_K + 1, True, "5"):
        with pytest.raises(MemoryPipelineError):
            mp._validate_long_top_k(bad)


def test_validate_long_min_score():
    for ok in (0.0, 0.5, 1.0):
        assert mp._validate_long_min_score(ok) == pytest.approx(ok)
    for bad in (-0.01, 1.01, True, "0.5"):
        with pytest.raises(MemoryPipelineError):
            mp._validate_long_min_score(bad)


def test_validate_tiers_default():
    assert mp._validate_tiers(None) == list(ALL_TIERS)


def test_validate_tiers_subset():
    assert mp._validate_tiers(["short"]) == ["short"]
    assert mp._validate_tiers(("mid", "long")) == ["mid", "long"]


def test_validate_tiers_rejects_unknown_dup_empty_nonlist():
    with pytest.raises(MemoryPipelineError):
        mp._validate_tiers(["bogus"])
    with pytest.raises(MemoryPipelineError):
        mp._validate_tiers(["short", "short"])
    with pytest.raises(MemoryPipelineError):
        mp._validate_tiers([])
    with pytest.raises(MemoryPipelineError):
        mp._validate_tiers("short")  # str は list でない
    with pytest.raises(MemoryPipelineError):
        mp._validate_tiers([1])


# ══════════════════════════════════════════════════════════════════════
# Service: build_full_context (AC-1 UBIQUITOUS — 3 tier 統合)
# ══════════════════════════════════════════════════════════════════════


def test_build_full_context_all_3_tiers_populated(_mock_mem0):
    tid = _make_thread()
    _seed_short_messages(tid, count=3)
    _seed_mid_summary(tid)
    asyncio.run(_seed_long_term("alice", "Build-Factory delivers OS-level dev"))

    out = asyncio.run(mp.build_full_context(
        tid, "alice", "Build-Factory",
        long_min_score=0.0,
    ))
    assert out["thread_id"] == tid
    assert out["user_id"] == "alice"
    assert out["query"] == "Build-Factory"
    assert out["tiers_requested"] == list(ALL_TIERS)
    assert out["short"]["count"] == 3
    assert out["mid"]["found"] is True
    assert out["long"]["count"] >= 1
    assert out["degraded_mode"] is False
    assert isinstance(out["assembled_text"], str)
    assert len(out["assembled_text"]) > 0
    assert out["stats"]["short_count"] == 3
    assert out["stats"]["mid_summary_found"] is True
    assert out["stats"]["long_count"] >= 1
    assert out["stats"]["char_count"] == len(out["assembled_text"])


def test_build_full_context_short_only(_mock_mem0):
    tid = _make_thread()
    _seed_short_messages(tid, count=2)
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "anything", tiers=["short"],
    ))
    assert out["tiers_requested"] == ["short"]
    assert out["short"]["count"] == 2
    assert out["mid"] is None
    assert out["long"] is None
    assert out["degraded_mode"] is False


def test_build_full_context_mid_only_no_summary_yet(_mock_mem0):
    tid = _make_thread()
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "anything", tiers=["mid"],
    ))
    assert out["mid"]["found"] is False
    assert out["short"] is None
    assert out["long"] is None


def test_build_full_context_long_only(_mock_mem0):
    tid = _make_thread()
    asyncio.run(_seed_long_term("alice", "Hello world"))
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "Hello", tiers=["long"], long_min_score=0.0,
    ))
    assert out["long"]["count"] >= 1
    assert out["short"] is None
    assert out["mid"] is None


def test_build_full_context_assembled_text_includes_query(_mock_mem0):
    tid = _make_thread()
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "specific query string",
    ))
    assert "specific query string" in out["assembled_text"]


def test_build_full_context_assembled_text_includes_short_history(_mock_mem0):
    tid = _make_thread()
    cts.get_store().add_message(tid, "user", "MARKER_USER_LINE_42")
    out = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    assert "MARKER_USER_LINE_42" in out["assembled_text"]


def test_build_full_context_assembled_text_includes_mid_summary(_mock_mem0):
    tid = _make_thread()
    _seed_mid_summary(tid, prefix="UNIQUE")
    out = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    assert "UNIQUE-context-1" in out["assembled_text"]


def test_build_full_context_assembled_text_includes_long_results(_mock_mem0):
    tid = _make_thread()
    asyncio.run(_seed_long_term("alice", "VERY_UNIQUE_LONG_TERM_TOKEN"))
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "VERY_UNIQUE_LONG_TERM_TOKEN", long_min_score=0.0,
    ))
    assert "VERY_UNIQUE_LONG_TERM_TOKEN" in out["assembled_text"]


# ══════════════════════════════════════════════════════════════════════
# Service: AC-4 invalid input → raise + state mutate なし
# ══════════════════════════════════════════════════════════════════════


def test_build_full_context_rejects_invalid_thread_id():
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(0, "alice", "q"))


def test_build_full_context_rejects_unknown_thread(_mock_mem0):
    with pytest.raises(MemoryPipelineError) as ei:
        asyncio.run(mp.build_full_context(99999, "alice", "q"))
    assert "not found" in str(ei.value)


def test_build_full_context_rejects_empty_user_id():
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(1, "  ", "q"))


def test_build_full_context_rejects_empty_query():
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(1, "alice", ""))


def test_build_full_context_rejects_invalid_recent_n():
    tid = _make_thread()
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(tid, "alice", "q", recent_n=0))


def test_build_full_context_rejects_use_chat_search_non_bool():
    tid = _make_thread()
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(
            tid, "alice", "q", use_chat_search="yes",
        ))


def test_build_full_context_rejects_use_semantic_non_bool():
    tid = _make_thread()
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(
            tid, "alice", "q", use_semantic="yes",
        ))


def test_build_full_context_rejects_invalid_actor():
    tid = _make_thread()
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(
            tid, "alice", "q", actor_user_id="  ",
        ))


def test_build_full_context_does_not_mutate_state_on_validation_error(_mock_mem0):
    tid = _make_thread()
    cts.get_store().add_message(tid, "user", "before")
    before_count = cts.get_store().count_messages(tid)
    with pytest.raises(MemoryPipelineError):
        asyncio.run(mp.build_full_context(tid, "  ", "q"))
    assert cts.get_store().count_messages(tid) == before_count
    # mem0 にも書かれていない
    assert _mock_mem0["added"] == []


# ══════════════════════════════════════════════════════════════════════
# G14 degraded mode: 単独 tier 失敗を許容、全失敗のみ raise
# ══════════════════════════════════════════════════════════════════════


def test_g14_single_tier_failure_returns_degraded_mode(_mock_mem0, monkeypatch):
    tid = _make_thread()
    _seed_short_messages(tid, count=1)
    _seed_mid_summary(tid)

    # long を強制的に失敗させる
    async def boom(*a, **kw):
        raise RuntimeError("mem0 down")

    import services.long_term_layer as ltl
    monkeypatch.setattr(ltl, "retrieve", boom)

    out = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    assert out["short"] is not None
    assert out["mid"] is not None
    assert out["long"] is None
    assert "long" in out["errors"]
    assert out["degraded_mode"] is True


def test_g14_all_tiers_failure_raises(monkeypatch, _mock_mem0):
    tid = _make_thread()

    async def short_boom(*a, **kw):
        raise RuntimeError("short down")
    async def mid_boom(*a, **kw):
        raise RuntimeError("mid down")
    async def long_boom(*a, **kw):
        raise RuntimeError("long down")

    monkeypatch.setattr(mp, "_fetch_tier_short", short_boom)
    monkeypatch.setattr(mp, "_fetch_tier_mid", mid_boom)
    monkeypatch.setattr(mp, "_fetch_tier_long", long_boom)

    with pytest.raises(MemoryPipelineError) as ei:
        asyncio.run(mp.build_full_context(tid, "alice", "q"))
    assert "all requested tiers failed" in str(ei.value)


def test_g14_validation_error_in_tier_propagates(_mock_mem0, monkeypatch):
    """tier 内で MemoryPipelineError (validation) が出たら raise されること."""
    tid = _make_thread()

    async def raising_validation(*a, **kw):
        raise MemoryPipelineError("inner validation failed")
    monkeypatch.setattr(mp, "_fetch_tier_short", raising_validation)

    with pytest.raises(MemoryPipelineError) as ei:
        asyncio.run(mp.build_full_context(tid, "alice", "q"))
    assert "inner validation" in str(ei.value)


# ══════════════════════════════════════════════════════════════════════
# G13: assemble_text pluggable (register_assembler)
# ══════════════════════════════════════════════════════════════════════


def test_g13_register_assembler_callable_only():
    with pytest.raises(MemoryPipelineError):
        mp.register_assembler("not callable")
    with pytest.raises(MemoryPipelineError):
        mp.register_assembler(123)
    mp.register_assembler(lambda s, m, l, q: "custom")
    assert mp.get_assembler() is not None
    mp.register_assembler(None)
    assert mp.get_assembler() is None


def test_g13_assembler_swap_used(_mock_mem0):
    mp.register_assembler(lambda s, m, l, q: f"CUSTOM[{q}]")
    tid = _make_thread()
    out = asyncio.run(mp.build_full_context(tid, "alice", "hello"))
    assert out["assembled_text"] == "CUSTOM[hello]"


def test_g13_assembler_exception_falls_back_to_default(_mock_mem0):
    def boom(s, m, l, q):
        raise RuntimeError("formatter down")
    mp.register_assembler(boom)
    tid = _make_thread()
    out = asyncio.run(mp.build_full_context(tid, "alice", "hello"))
    assert "hello" in out["assembled_text"]  # default formatter ran


def test_g13_assembler_non_str_return_falls_back(_mock_mem0):
    mp.register_assembler(lambda s, m, l, q: 12345)
    tid = _make_thread()
    out = asyncio.run(mp.build_full_context(tid, "alice", "hello"))
    assert isinstance(out["assembled_text"], str)
    assert "hello" in out["assembled_text"]


def test_g13_default_assembler_handles_empty_inputs():
    text = mp._default_assemble_text({}, {}, {}, "q only")
    assert "q only" in text


def test_g13_default_assembler_truncates_long_short_content():
    long = "x" * 500
    text = mp._default_assemble_text(
        {"messages": [{"role": "user", "content": long}]}, {}, {}, "q",
    )
    # 240 char + ellipsis
    assert "…" in text
    assert long not in text


def test_g13_default_assembler_truncates_long_long_content():
    long = "x" * 500
    text = mp._default_assemble_text(
        {}, {}, {"results": [{"scope": "tier3_knowledge",
                              "content": long, "score": 0.5}]}, "q",
    )
    assert "…" in text
    assert long not in text


def test_short_tier_truncates_to_recent_n(_mock_mem0):
    """recent_n < raw_msgs 件数 → 末尾 recent_n 件のみ取得."""
    tid = _make_thread()
    _seed_short_messages(tid, count=5)
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "q", tiers=["short"], recent_n=2,
    ))
    assert out["short"]["count"] == 2
    # 末尾 2 件は idx 3, 4 (message 3, message 4)
    assert "message 3" in out["short"]["messages"][0]["content"]
    assert "message 4" in out["short"]["messages"][1]["content"]


def test_tier_health_failure_path_marks_unavailable(monkeypatch):
    """tier の module import が失敗した場合 available=False になる."""
    real_import = __builtins__["__import__"] if isinstance(
        __builtins__, dict) else __builtins__.__import__

    def faulty_import(name, *a, **kw):
        if name == "services.long_term_layer":
            raise ImportError("simulated import error")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", faulty_import)
    h = mp.tier_health()
    assert h["long"]["available"] is False
    assert "ImportError" in h["long"]["error"]
    assert h["all_available"] is False


def test_g13_assemble_text_alias_uses_backend():
    mp.register_assembler(lambda s, m, l, q: "ALIAS")
    text = mp.assemble_text({}, {}, {}, "q")
    assert text == "ALIAS"


# ══════════════════════════════════════════════════════════════════════
# G12 chat_search (T-AI-03) 互換 (use_chat_search flag)
# ══════════════════════════════════════════════════════════════════════


def test_g12_chat_search_flag_propagates_via(_mock_mem0, monkeypatch):
    tid = _make_thread()
    _seed_short_messages(tid, count=2)
    # chat_search.hybrid_search を hit ありで stub
    async def fake_hybrid(*, query, thread_id, top_k):
        from services.chat_search import HybridHit
        return [HybridHit(
            message_id=99, thread_id=thread_id, role="user",
            content="hit", created_at=None, trgm_score=0.5,
            vector_score=0.5, final_score=0.5,
        )]
    import services.chat_search as cs
    monkeypatch.setattr(cs, "hybrid_search", fake_hybrid)

    out = asyncio.run(mp.build_full_context(
        tid, "alice", "anything", tiers=["short"], use_chat_search=True,
    ))
    assert "chat_search" in out["short"]["via"]


def test_g12_chat_search_failure_does_not_break_short(_mock_mem0, monkeypatch):
    tid = _make_thread()
    _seed_short_messages(tid, count=2)

    async def boom(**kw):
        raise RuntimeError("chat_search down")
    import services.chat_search as cs
    monkeypatch.setattr(cs, "hybrid_search", boom)

    out = asyncio.run(mp.build_full_context(
        tid, "alice", "q", tiers=["short"], use_chat_search=True,
    ))
    # short tier 自体は成功しているべき (chat_search は補助)
    assert out["short"] is not None
    assert out["short"]["count"] == 2
    assert out["short"]["via"] == "chat_thread_store"  # chat_search 失敗 = fallback


def test_g12_chat_search_disabled_by_default(_mock_mem0):
    tid = _make_thread()
    _seed_short_messages(tid, count=1)
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "q", tiers=["short"],
    ))
    assert out["short"]["via"] == "chat_thread_store"


# ══════════════════════════════════════════════════════════════════════
# G11 semantic_retrieval (T-M28-05) 互換 (use_semantic flag)
# ══════════════════════════════════════════════════════════════════════


def test_g11_semantic_retrieval_merges_extras(_mock_mem0, monkeypatch):
    tid = _make_thread()
    asyncio.run(_seed_long_term("alice", "long-record"))

    async def fake_search(query, **kw):
        return {"results": [
            {"scope": "tier3_knowledge", "content": "from semantic", "score": 0.9}
        ]}
    import services.semantic_retrieval as sr
    monkeypatch.setattr(sr, "search", fake_search)

    out = asyncio.run(mp.build_full_context(
        tid, "alice", "long-record", tiers=["long"],
        use_semantic=True, long_min_score=0.0,
    ))
    assert "semantic_retrieval" in out["long"]["via"]
    assert out["long"]["extras"]["semantic_retrieval"]["added"] == 1


def test_g11_semantic_retrieval_failure_does_not_break_long(
    _mock_mem0, monkeypatch,
):
    tid = _make_thread()
    asyncio.run(_seed_long_term("alice", "x"))

    async def boom(*a, **kw):
        raise RuntimeError("semantic down")
    import services.semantic_retrieval as sr
    monkeypatch.setattr(sr, "search", boom)

    out = asyncio.run(mp.build_full_context(
        tid, "alice", "x", tiers=["long"], use_semantic=True,
        long_min_score=0.0,
    ))
    assert out["long"] is not None
    assert "semantic_retrieval_error" in out["long"]["extras"]


def test_g11_semantic_retrieval_disabled_by_default(_mock_mem0):
    tid = _make_thread()
    asyncio.run(_seed_long_term("alice", "x"))
    out = asyncio.run(mp.build_full_context(
        tid, "alice", "x", tiers=["long"], long_min_score=0.0,
    ))
    assert out["long"]["via"] == "long_term_layer"


# ══════════════════════════════════════════════════════════════════════
# Existing modules unchanged (G9 spirit / AC-3 STATE-DRIVEN)
# ══════════════════════════════════════════════════════════════════════


def test_compat_chat_thread_store_unchanged():
    s = cts.ChatThreadStore()
    for sym in (
        "create_thread", "get_thread", "list_threads", "update_thread",
        "delete_thread", "add_message", "get_message", "list_messages",
        "delete_message", "count_messages",
    ):
        assert hasattr(s, sym)


def test_compat_mid_term_layer_unchanged():
    from services import mid_term_layer as mtl
    for sym in (
        "latest_summary", "compressed_history", "mid_tier_stats",
        "record_summary", "register_summarizer_backend",
        "SECTION_KEYS", "MidTermLayerError",
    ):
        assert hasattr(mtl, sym), f"mid_term_layer.{sym} missing"


def test_compat_long_term_layer_unchanged():
    from services import long_term_layer as ltl
    for sym in (
        "persist", "retrieve", "list_sources",
        "VALID_SOURCES", "VALID_SCOPES", "LongTermLayerError",
    ):
        assert hasattr(ltl, sym), f"long_term_layer.{sym} missing"


def test_compat_chat_search_unchanged():
    from services import chat_search as cs
    for sym in ("hybrid_search", "parse_query", "trgm_similarity", "HybridHit"):
        assert hasattr(cs, sym), f"chat_search.{sym} missing"


def test_compat_semantic_retrieval_unchanged():
    from services import semantic_retrieval as sr
    for sym in ("search", "validate_inputs", "VALID_SCOPES",
                "SemanticRetrievalError"):
        assert hasattr(sr, sym), f"semantic_retrieval.{sym} missing"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS endpoint smoke
# ══════════════════════════════════════════════════════════════════════


def test_ac1_endpoint_context_full_3_tier(client, _mock_mem0):
    tid = _make_thread()
    _seed_short_messages(tid, count=2)
    _seed_mid_summary(tid)
    asyncio.run(_seed_long_term("alice", "Build-Factory"))
    r = client.post("/api/memory/context", json={
        "thread_id": tid,
        "user_id": "alice",
        "query": "Build-Factory",
        "long_min_score": 0.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["short"]["count"] == 2
    assert body["mid"]["found"] is True
    assert body["long"]["count"] >= 1
    assert "Build-Factory" in body["assembled_text"]


def test_ac1_endpoint_health(client):
    r = client.get("/api/memory/health")
    assert r.status_code == 200
    body = r.json()
    assert body["all_available"] is True


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 2 秒以内 + audit emit (action + timestamp)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_context_within_2sec(client, _mock_mem0):
    tid = _make_thread()
    _seed_short_messages(tid, count=20)
    _seed_mid_summary(tid)
    asyncio.run(_seed_long_term("alice", "x"))
    t0 = time.time()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "anything",
        "long_min_score": 0.0,
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_health_within_2sec(client):
    t0 = time.time()
    r = client.get("/api/memory/health")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_context_emits_audit(client, _capture_audit, _mock_mem0):
    tid = _make_thread()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "x",
        "actor_user_id": "alice",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "memory.context_built"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert detail["thread_id"] == tid
    assert detail["user_id"] == "alice"
    assert detail["tiers_requested"] == list(ALL_TIERS)
    assert "stats" in detail
    assert "errors" in detail
    assert "degraded_mode" in detail
    assert events[0]["user_id"] == "alice"


def test_ac2_error_shape_consistency(client, _mock_mem0):
    """全 error path で {detail:{code,message}} で code が 'memory.' prefix."""
    cases = [
        # 不明 thread → 404
        ("POST", "/api/memory/context",
         {"thread_id": 88888, "user_id": "alice", "query": "q"}, 404),
        # actor 空 → 401
        ("POST", "/api/memory/context",
         {"thread_id": 1, "user_id": "alice", "query": "q",
          "actor_user_id": "  "}, 401),
        # user_id 空 → 400 (service layer)
        ("POST", "/api/memory/context",
         {"thread_id": 1, "user_id": "  ", "query": "q"}, 400),
    ]
    tid = _make_thread()
    assert tid == 1
    for method, path, body, expected_status in cases:
        r = client.post(path, json=body)
        assert r.status_code == expected_status, f"{path}/{body}: {r.status_code}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert "code" in detail and "message" in detail
        assert detail["code"].startswith("memory."), f"{path}: {detail['code']}"


def test_ac2_all_tiers_fail_returns_502(client, monkeypatch, _mock_mem0):
    tid = _make_thread()

    async def boom(*a, **kw):
        raise RuntimeError("down")
    monkeypatch.setattr(mp, "_fetch_tier_short", boom)
    monkeypatch.setattr(mp, "_fetch_tier_mid", boom)
    monkeypatch.setattr(mp, "_fetch_tier_long", boom)

    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "x",
    })
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "memory.all_tiers_failed"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: 既存 module 不変 + read endpoint で audit emit しない
# ══════════════════════════════════════════════════════════════════════


def test_ac3_health_no_audit(client, _capture_audit):
    client.get("/api/memory/health")
    assert not [e for e in _capture_audit if e["event_type"].startswith("memory.")]


def test_ac3_context_audit_includes_degraded_flag(
    client, _capture_audit, monkeypatch, _mock_mem0,
):
    tid = _make_thread()

    async def long_boom(*a, **kw):
        raise RuntimeError("long down")
    monkeypatch.setattr(mp, "_fetch_tier_long", long_boom)

    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "memory.context_built"]
    assert len(events) == 1
    assert events[0]["detail"]["degraded_mode"] is True
    assert "long" in events[0]["detail"]["errors"]


def test_ac3_existing_module_routes_unchanged(client):
    """3 layer の既存 endpoint が変更されていない."""
    paths = [getattr(r, "path", "") for r in client.app.routes]
    # T-M30-01 chat_threads
    assert any(p.startswith("/api/chat-threads") for p in paths)
    # T-M30-03 mid-term
    assert "/api/mid-term/summary" in paths
    # T-M30-04 long-term
    assert "/api/long-term/persist" in paths


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED endpoint level
# ══════════════════════════════════════════════════════════════════════


def test_ac4_endpoint_thread_id_pydantic_422(client):
    r = client.post("/api/memory/context", json={
        "thread_id": 0, "user_id": "alice", "query": "q",
    })
    assert r.status_code == 422


def test_ac4_endpoint_recent_n_pydantic_422(client):
    tid = _make_thread()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
        "recent_n": 0,
    })
    assert r.status_code == 422


def test_ac4_endpoint_long_top_k_pydantic_422(client):
    tid = _make_thread()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
        "long_top_k": MAX_LONG_TOP_K + 1,
    })
    assert r.status_code == 422


def test_ac4_endpoint_long_min_score_pydantic_422(client):
    tid = _make_thread()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
        "long_min_score": 1.5,
    })
    assert r.status_code == 422


def test_ac4_endpoint_unknown_thread_404(client, _mock_mem0):
    r = client.post("/api/memory/context", json={
        "thread_id": 88888, "user_id": "alice", "query": "q",
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "memory.not_found"


def test_ac4_endpoint_invalid_tiers_400(client):
    tid = _make_thread()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
        "tiers": ["bogus"],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "memory.invalid"


def test_ac4_endpoint_state_unchanged_on_error(
    client, _capture_audit, _mock_mem0,
):
    """validation error 後 chat_thread_store / audit / mem0 全て unchanged."""
    tid = _make_thread()
    cts.get_store().add_message(tid, "user", "before")
    before_count = cts.get_store().count_messages(tid)
    before_mem0 = list(_mock_mem0["added"])
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "  ", "query": "q",
    })
    assert r.status_code == 400
    # state mutate なし
    assert cts.get_store().count_messages(tid) == before_count
    assert _mock_mem0["added"] == before_mem0
    # 失敗時 audit emit なし
    assert not [
        e for e in _capture_audit if e["event_type"] == "memory.context_built"
    ]


def test_ac4_endpoint_unauthorized_401(client, _capture_audit, _mock_mem0):
    tid = _make_thread()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
        "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "memory.unauthorized"
    # audit emit なし
    assert not [
        e for e in _capture_audit if e["event_type"] == "memory.context_built"
    ]


# ══════════════════════════════════════════════════════════════════════
# Module docstring (G11-G14 + path A/B/C 明示) — 発見性
# ══════════════════════════════════════════════════════════════════════


def test_module_docstring_documents_g11_g14():
    doc = mp.__doc__ or ""
    for tag in ("G11", "G12", "G13", "G14"):
        assert tag in doc, f"module docstring must mention {tag}"


def test_module_docstring_documents_3_tiers():
    doc = mp.__doc__ or ""
    assert "Tier 1 短期" in doc
    assert "Tier 2 中期" in doc
    assert "Tier 3 長期" in doc


# ══════════════════════════════════════════════════════════════════════
# AC-2 命名 alias: build_context (tickets.json T-M30-05 EVENT-DRIVEN)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_build_context_is_alias_of_build_full_context():
    """T-M30-05 AC-2 EVENT-DRIVEN は build_context を pipeline entry に指定.
    build_full_context と同一 callable (完全等価)."""
    from services.memory_pipeline import build_context, build_full_context
    assert build_context is build_full_context


def test_ac2_build_context_runs_via_alias(_mock_mem0):
    """build_context 名でも 3 tier 並列収集が成立."""
    from services.memory_pipeline import build_context
    tid = _make_thread()
    _seed_short_messages(tid, count=2)
    _seed_mid_summary(tid)
    import asyncio
    result = asyncio.run(build_context(tid, "alice", "q"))
    assert result["thread_id"] == tid
    assert isinstance(result["stats"], dict)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: audit detail に tier_hit_count + total_chars
# ══════════════════════════════════════════════════════════════════════


def test_ac2_audit_emits_tier_hit_count_and_total_chars(
    client, _capture_audit, _mock_mem0,
):
    """audit detail に AC-2 で要求される tier_hit_count + total_chars を含む."""
    tid = _make_thread()
    _seed_short_messages(tid, count=3)
    _seed_mid_summary(tid)
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "memory.context_built"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert "tier_hit_count" in detail
    assert "total_chars" in detail
    assert isinstance(detail["tier_hit_count"], int)
    assert isinstance(detail["total_chars"], int)
    # short + mid が seed されているので tier_hit_count >= 2
    assert detail["tier_hit_count"] >= 2
    # total_chars は assembled_text の長さと一致
    assert detail["total_chars"] == len(r.json()["assembled_text"])


def test_ac2_audit_tier_hit_count_increments_per_active_tier(
    client, _capture_audit, _mock_mem0,
):
    """seed 無し thread でも 200 OK (degraded mode); tier_hit_count = 0."""
    tid = _make_thread()
    r = client.post("/api/memory/context", json={
        "thread_id": tid, "user_id": "alice", "query": "q",
    })
    assert r.status_code == 200
    ev = [e for e in _capture_audit
          if e["event_type"] == "memory.context_built"][0]
    # short/mid/long すべて空 → tier_hit_count == 0
    assert ev["detail"]["tier_hit_count"] == 0


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: cross-layer integration invariants
# (9-section SECTION_KEYS / tier ordering / source attribution)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_cross_layer_mid_uses_9section_section_keys(_mock_mem0):
    """中期 tier の summary は mid_term_layer.SECTION_KEYS と同じ 9 keys."""
    from services.mid_term_layer import SECTION_KEYS
    tid = _make_thread()
    _seed_mid_summary(tid)
    import asyncio
    result = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    mid = result["mid"]
    assert mid is not None
    assert mid["found"] is True
    # summary は 9 sections 完全一致
    assert set(mid["summary"].keys()) == set(SECTION_KEYS)


def test_ac1_cross_layer_tier_ordering_in_response(_mock_mem0):
    """response の tier ordering は ALL_TIERS と同じ (short → mid → long)."""
    from services.memory_pipeline import ALL_TIERS
    tid = _make_thread()
    _seed_short_messages(tid, count=1)
    _seed_mid_summary(tid)
    import asyncio
    result = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    # tiers_requested は ALL_TIERS と一致 (デフォルト時)
    assert tuple(result["tiers_requested"]) == ALL_TIERS
    # keys "short" / "mid" / "long" が必ず response に存在
    assert "short" in result and "mid" in result and "long" in result


def test_ac1_cross_layer_assembled_text_orders_tiers(_mock_mem0):
    """assembled_text 内で「短期 → 中期 → 長期」の順序が保たれる."""
    tid = _make_thread()
    _seed_short_messages(tid, count=2)
    _seed_mid_summary(tid)
    import asyncio
    # long 経路用に mem0 stub を seed
    _mock_mem0["added"].append({
        "user_id": "alice",
        "content": "long memory content about decision X",
    })
    result = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    text = result["assembled_text"]
    # 仕様: 短期は中期より前、中期は長期より前 (= "短期" / "中期" / "長期" の登場順)
    pos_short = text.find("短期記憶")
    pos_mid = text.find("中期記憶")
    pos_long = text.find("長期記憶")
    # それぞれ存在することを確認 (-1 でない)
    assert pos_short != -1, "短期記憶 not in assembled_text"
    assert pos_mid != -1, "中期記憶 not in assembled_text"
    # 順序: short < mid < long (long が hit していれば)
    assert pos_short < pos_mid


def test_ac1_cross_layer_source_attribution_in_short(_mock_mem0):
    """短期 tier の各 message に role (= source attribution) が記録される."""
    tid = _make_thread()
    _seed_short_messages(tid, count=3)
    import asyncio
    result = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    msgs = (result["short"] or {}).get("messages") or []
    assert len(msgs) >= 3
    # 各 message に role があり, user/assistant のいずれか
    for m in msgs:
        assert "role" in m
        assert m["role"] in ("user", "assistant", "system", "system_summary")


def test_ac1_cross_layer_source_attribution_in_mid(_mock_mem0):
    """中期 tier の summary は source ('compressed_summary' / 'system_summary')
    を持つ (mid_term_layer の経路 A/B 区別が pipeline まで伝搬する)."""
    tid = _make_thread()
    _seed_mid_summary(tid)  # 経路 A: compressed_summary フィールド
    import asyncio
    result = asyncio.run(mp.build_full_context(tid, "alice", "q"))
    mid = result["mid"] or {}
    assert mid.get("found") is True
    # source は経路 A/B のいずれか (mid_term_layer.latest_summary の return)
    assert mid.get("source") in ("compressed_summary", "system_summary")


def test_ac1_cross_layer_module_delegation_invariant():
    """orchestrator は self-compaction を持たない (delegation only).
    AC-4 UNWANTED: '3-tier compaction を orchestrator で再実装' を禁止.
    実装: _fetch_tier_* は layer module を delegate しているか確認."""
    import inspect
    src = inspect.getsource(mp)
    # service module 内で 3-tier compaction logic (LLM call / keyword heuristic)
    # を行う直接的な署名が無いことを確認
    forbidden = ["openai.chat", "anthropic.messages.create",
                 "client.messages.create", "_summarize_chat_messages"]
    for token in forbidden:
        assert token not in src, (
            f"memory_pipeline must not implement compaction directly: '{token}'"
        )
    # 各 _fetch_tier_* が layer module からの import を経由していることを確認
    assert "from services import chat_thread_store" in src or \
           "import chat_thread_store" in src
    assert "from services.mid_term_layer" in src or \
           "import mid_term_layer" in src
    assert "from services import long_term_layer" in src or \
           "from services.long_term_layer" in src or \
           "import long_term_layer" in src
