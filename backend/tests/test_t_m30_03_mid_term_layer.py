"""T-M30-03: 中期 layer (existing conversation_summarizer 活用) — 4 AC 全網羅 + spec gap closure.

AC マッピング (1:1 テスト):
  AC-1 UBIQUITOUS    : M-30 中期 layer 統一 read view (REFACTOR REUSE 既存 modules,
                       書き手 経路 A/B を統一 9-section dict として返す)
  AC-2 EVENT-DRIVEN  : 各 endpoint は 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 conversation_summarizer / conversation_memory /
                       chat_thread_store / memory_service module 不変 +
                       record 経由は audit emit / read は audit emit しない
  AC-4 UNWANTED      : invalid input / unauthorized actor / 不明 thread →
                       4xx structured / persistent state mutate しない

Spec gap closure (PR #128 G1-G6 と同じ精神):
  G7  : register_summarizer_backend hook (SDK 差替点)
  G8  : record_summary dual-write (chat_thread_store + memory_service)
  G9  : conversation_summarizer は不変 (補助 LLM 温存ハッチ)
  G10 : SECTION_KEYS は tier3_structured_summary と完全一致 (cross-module)
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import chat_thread_store as cts
from services import mid_term_layer as mtl
from services.mid_term_layer import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_PREFER_SOURCE,
    MAX_ACTOR_USER_ID_LEN,
    MAX_HISTORY_LIMIT,
    MIN_HISTORY_LIMIT,
    MidTermLayerError,
    SECTION_KEYS,
    SUMMARY_ROLE_SYSTEM,
    SUMMARY_ROLE_SYSTEM_SUMMARY,
    VALID_PREFER_SOURCES,
    empty_summary,
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
    """各テストで in-memory store を初期化."""
    cts.reset_store()
    # backend hook も clear (テスト間の状態漏れ防止)
    mtl.register_summarizer_backend(None)
    yield
    cts.reset_store()
    mtl.register_summarizer_backend(None)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    """memory_service.emit_event を mock し event を集める."""
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


@pytest.fixture
def stub_legacy_persist(monkeypatch):
    """memory_service.persist_compaction を stub (sqlite 非依存)."""
    persisted: list[dict] = []

    async def fake_persist_compaction(thread_id, summary):
        persisted.append({"thread_id": thread_id, "summary": dict(summary)})
        return 9999 + len(persisted)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "persist_compaction", fake_persist_compaction)
    return persisted


def _make_thread() -> int:
    """テスト用の thread を作成し id を返す."""
    return cts.get_store().create_thread(title="T-M30-03 test").id


def _add_compressed_message(
    thread_id: int,
    summary: dict[str, Any],
    *,
    role: str = SUMMARY_ROLE_SYSTEM,
    content: str = "[compressed]",
):
    return cts.get_store().add_message(
        thread_id, role, content, compressed_summary=summary,
    )


_NEXT_INJECTED_MSG_ID = [10_000]


def _add_system_summary_message(thread_id: int, summary: dict[str, Any]):
    """memory_service.persist_compaction が書く形式 (role='system_summary' + JSON content).

    chat_thread_store.VALID_ROLES に 'system_summary' は含まれないため
    (memory_service は raw SQL で sqlite chat_messages に書く), in-memory
    store には ChatMessage dataclass を直接挿入して mirror をシミュレート.
    Phase 2 で sqlite ↔ in-memory store の mirror sync が入った時の挙動を
    Phase 1 のテストで先取りする.
    """
    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise ValueError(f"thread not found: {thread_id}")
    _NEXT_INJECTED_MSG_ID[0] += 1
    msg = cts.ChatMessage(
        id=_NEXT_INJECTED_MSG_ID[0],
        thread_id=thread_id,
        role=SUMMARY_ROLE_SYSTEM_SUMMARY,
        content=json.dumps(summary, ensure_ascii=False),
        compressed_summary=None,
        token_count=None,
        created_at=time.time(),
    )
    with store._lock:
        store._messages[msg.id] = msg
        store._by_thread.setdefault(thread_id, []).append(msg.id)
    return msg


def _full_summary(prefix: str = "v") -> dict[str, list[str]]:
    """全 9 section に bullet を 1 件ずつ持つ summary."""
    return {k: [f"{prefix}-{k}-1"] for k in SECTION_KEYS}


# ══════════════════════════════════════════════════════════════════════
# Service: constants & invariants
# ══════════════════════════════════════════════════════════════════════


def test_section_keys_exactly_9():
    assert len(SECTION_KEYS) == 9
    assert len(set(SECTION_KEYS)) == 9


def test_g10_section_keys_match_tier3_module_when_available():
    """G10: tier3_structured_summary が import 可能な環境では SECTION_KEYS が一致."""
    try:
        from services import tier3_structured_summary as t3  # noqa: F401
    except ImportError:
        pytest.skip("tier3_structured_summary not yet merged (PR #128 pending)")
    assert tuple(SECTION_KEYS) == tuple(t3.SECTION_KEYS), (
        "SECTION_KEYS divergence between mid_term_layer and tier3_structured_summary"
    )


def test_empty_summary_is_9_sections_all_lists():
    e = empty_summary()
    assert set(e.keys()) == set(SECTION_KEYS)
    assert all(isinstance(v, list) and v == [] for v in e.values())


def test_valid_prefer_sources_tuple():
    assert "auto" in VALID_PREFER_SOURCES
    assert "compressed_summary" in VALID_PREFER_SOURCES
    assert "system_summary" in VALID_PREFER_SOURCES


# ══════════════════════════════════════════════════════════════════════
# Service: validation (UNWANTED AC-4)
# ══════════════════════════════════════════════════════════════════════


def test_validate_thread_id_rejects_zero_negative_bool_str():
    for bad in (0, -1, True, False, "1", 1.0, None):
        with pytest.raises(MidTermLayerError):
            mtl._validate_thread_id(bad)


def test_validate_thread_id_accepts_positive_int():
    assert mtl._validate_thread_id(7) == 7


def test_validate_limit_bounds():
    with pytest.raises(MidTermLayerError):
        mtl._validate_limit(MIN_HISTORY_LIMIT - 1)
    with pytest.raises(MidTermLayerError):
        mtl._validate_limit(MAX_HISTORY_LIMIT + 1)
    with pytest.raises(MidTermLayerError):
        mtl._validate_limit(True)
    with pytest.raises(MidTermLayerError):
        mtl._validate_limit("20")
    assert mtl._validate_limit(MIN_HISTORY_LIMIT) == MIN_HISTORY_LIMIT
    assert mtl._validate_limit(MAX_HISTORY_LIMIT) == MAX_HISTORY_LIMIT


def test_validate_prefer_source():
    for ok in VALID_PREFER_SOURCES:
        assert mtl._validate_prefer_source(ok) == ok
    for bad in ("foo", "", None, 1, True):
        with pytest.raises(MidTermLayerError):
            mtl._validate_prefer_source(bad)


def test_validate_actor_user_id():
    assert mtl._validate_actor_user_id(None) is None
    assert mtl._validate_actor_user_id(" alice ") == "alice"
    with pytest.raises(MidTermLayerError):
        mtl._validate_actor_user_id("   ")
    with pytest.raises(MidTermLayerError):
        mtl._validate_actor_user_id(123)
    with pytest.raises(MidTermLayerError):
        mtl._validate_actor_user_id("x" * (MAX_ACTOR_USER_ID_LEN + 1))


def test_require_thread_exists_raises_for_unknown():
    with pytest.raises(MidTermLayerError):
        mtl._require_thread_exists(99999)


# ══════════════════════════════════════════════════════════════════════
# Service: _normalize_summary
# ══════════════════════════════════════════════════════════════════════


def test_normalize_summary_returns_none_for_non_dict():
    assert mtl._normalize_summary(None) is None
    assert mtl._normalize_summary("foo") is None
    assert mtl._normalize_summary([1, 2]) is None


def test_normalize_summary_returns_none_when_no_known_key():
    assert mtl._normalize_summary({"unrelated": ["x"]}) is None


def test_normalize_summary_fills_missing_sections():
    out = mtl._normalize_summary({"context": ["c1"]})
    assert out is not None
    assert set(out.keys()) == set(SECTION_KEYS)
    assert out["context"] == ["c1"]
    assert out["goals"] == []


def test_normalize_summary_coerces_non_str_list_items():
    out = mtl._normalize_summary({"context": [1, "two", None, 3.5]})
    assert out is not None
    assert out["context"] == ["1", "two", "3.5"]  # None は除外


def test_normalize_summary_accepts_string_value():
    """defensive: 非 list value も str 化して 1-elem list に."""
    out = mtl._normalize_summary({"context": "single"})
    assert out is not None
    assert out["context"] == ["single"]


def test_normalize_summary_ignores_extra_keys():
    out = mtl._normalize_summary({"context": ["c"], "extra": ["e"]})
    assert out is not None
    assert "extra" not in out


def test_normalize_summary_explicit_none_value_becomes_empty_list():
    out = mtl._normalize_summary({"context": None, "goals": ["g"]})
    assert out is not None
    assert out["context"] == []
    assert out["goals"] == ["g"]


def test_extract_summary_path_b_returns_none_for_non_string_content_after_json():
    """role='system_summary' で content が JSON 数値 (dict でない) → None."""
    tid = _make_thread()
    _inject_system_summary_with_content(tid, "12345")
    out = mtl.latest_summary(tid)
    assert out["found"] is False


def test_extract_summary_no_summary_returns_none_at_end():
    """role='user' / no compressed_summary → _extract_summary_from_message が None."""
    tid = _make_thread()
    cts.get_store().add_message(tid, "user", "plain text")
    out = mtl.latest_summary(tid)
    assert out["found"] is False


# ══════════════════════════════════════════════════════════════════════
# Service: latest_summary (AC-1 UBIQUITOUS)
# ══════════════════════════════════════════════════════════════════════


def test_latest_summary_empty_thread_returns_empty_skeleton():
    tid = _make_thread()
    out = mtl.latest_summary(tid)
    assert out["found"] is False
    assert out["source"] is None
    assert out["summary"] == empty_summary()
    assert set(out["summary"].keys()) == set(SECTION_KEYS)


def test_latest_summary_path_a_compressed_summary():
    tid = _make_thread()
    s = _full_summary("a")
    msg = _add_compressed_message(tid, s)
    out = mtl.latest_summary(tid)
    assert out["found"] is True
    assert out["source"] == "compressed_summary"
    assert out["message_id"] == msg.id
    assert out["summary"] == s


def test_latest_summary_path_b_system_summary_json():
    tid = _make_thread()
    s = _full_summary("b")
    msg = _add_system_summary_message(tid, s)
    out = mtl.latest_summary(tid)
    assert out["found"] is True
    assert out["source"] == "system_summary"
    assert out["message_id"] == msg.id
    assert out["summary"] == s


def test_latest_summary_newest_first_across_paths():
    tid = _make_thread()
    s_old = _full_summary("old")
    s_new = _full_summary("new")
    _add_compressed_message(tid, s_old)
    time.sleep(0.001)  # ensure created_at order
    _add_system_summary_message(tid, s_new)
    out = mtl.latest_summary(tid)
    assert out["source"] == "system_summary"
    assert out["summary"] == s_new


def test_latest_summary_prefer_compressed_only():
    tid = _make_thread()
    s_old = _full_summary("old")
    s_new = _full_summary("new")
    _add_compressed_message(tid, s_old)
    time.sleep(0.001)
    _add_system_summary_message(tid, s_new)
    out = mtl.latest_summary(tid, prefer_source="compressed_summary")
    assert out["source"] == "compressed_summary"
    assert out["summary"] == s_old


def test_latest_summary_prefer_system_summary_only():
    tid = _make_thread()
    s_old = _full_summary("old")
    s_new = _full_summary("new")
    _add_system_summary_message(tid, s_old)
    time.sleep(0.001)
    _add_compressed_message(tid, s_new)
    out = mtl.latest_summary(tid, prefer_source="system_summary")
    assert out["source"] == "system_summary"
    assert out["summary"] == s_old


def test_latest_summary_skips_non_summary_messages():
    tid = _make_thread()
    cts.get_store().add_message(tid, "user", "hello")
    cts.get_store().add_message(tid, "assistant", "hi")
    out = mtl.latest_summary(tid)
    assert out["found"] is False


def _inject_system_summary_with_content(thread_id: int, content: str):
    """role='system_summary' のメッセージを raw content で in-memory store に注入."""
    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise ValueError(f"thread not found: {thread_id}")
    _NEXT_INJECTED_MSG_ID[0] += 1
    msg = cts.ChatMessage(
        id=_NEXT_INJECTED_MSG_ID[0],
        thread_id=thread_id,
        role=SUMMARY_ROLE_SYSTEM_SUMMARY,
        content=content,
        compressed_summary=None,
        token_count=None,
        created_at=time.time(),
    )
    with store._lock:
        store._messages[msg.id] = msg
        store._by_thread.setdefault(thread_id, []).append(msg.id)
    return msg


def test_latest_summary_system_summary_with_invalid_json_skipped():
    tid = _make_thread()
    _inject_system_summary_with_content(tid, "not json")
    out = mtl.latest_summary(tid)
    assert out["found"] is False


def test_latest_summary_system_summary_with_unknown_keys_skipped():
    tid = _make_thread()
    _inject_system_summary_with_content(tid, json.dumps({"foo": ["bar"]}))
    out = mtl.latest_summary(tid)
    assert out["found"] is False


def test_latest_summary_actor_validated():
    tid = _make_thread()
    with pytest.raises(MidTermLayerError):
        mtl.latest_summary(tid, actor_user_id="   ")


def test_latest_summary_thread_id_validated():
    with pytest.raises(MidTermLayerError):
        mtl.latest_summary(0)
    with pytest.raises(MidTermLayerError):
        mtl.latest_summary(True)


def test_latest_summary_prefer_source_validated():
    tid = _make_thread()
    with pytest.raises(MidTermLayerError):
        mtl.latest_summary(tid, prefer_source="bogus")


def test_latest_summary_unknown_thread_404():
    with pytest.raises(MidTermLayerError) as ei:
        mtl.latest_summary(99999)
    assert "not found" in str(ei.value)


# ══════════════════════════════════════════════════════════════════════
# Service: compressed_history
# ══════════════════════════════════════════════════════════════════════


def test_compressed_history_empty():
    tid = _make_thread()
    out = mtl.compressed_history(tid)
    assert out["count"] == 0
    assert out["entries"] == []


def test_compressed_history_newest_first():
    tid = _make_thread()
    a = _full_summary("a")
    b = _full_summary("b")
    c = _full_summary("c")
    _add_compressed_message(tid, a)
    time.sleep(0.001)
    _add_system_summary_message(tid, b)
    time.sleep(0.001)
    _add_compressed_message(tid, c)
    out = mtl.compressed_history(tid)
    assert out["count"] == 3
    assert out["entries"][0]["summary"] == c
    assert out["entries"][1]["summary"] == b
    assert out["entries"][2]["summary"] == a


def test_compressed_history_limit_truncates():
    tid = _make_thread()
    for i in range(5):
        _add_compressed_message(tid, _full_summary(f"v{i}"))
    out = mtl.compressed_history(tid, limit=2)
    assert out["count"] == 2
    assert out["limit"] == 2


def test_compressed_history_limit_validated():
    tid = _make_thread()
    with pytest.raises(MidTermLayerError):
        mtl.compressed_history(tid, limit=0)
    with pytest.raises(MidTermLayerError):
        mtl.compressed_history(tid, limit=MAX_HISTORY_LIMIT + 1)


def test_compressed_history_skips_non_summary():
    tid = _make_thread()
    cts.get_store().add_message(tid, "user", "hi")
    _add_compressed_message(tid, _full_summary("ok"))
    out = mtl.compressed_history(tid)
    assert out["count"] == 1


def test_compressed_history_unknown_thread_404():
    with pytest.raises(MidTermLayerError) as ei:
        mtl.compressed_history(99999)
    assert "not found" in str(ei.value)


# ══════════════════════════════════════════════════════════════════════
# Service: mid_tier_stats
# ══════════════════════════════════════════════════════════════════════


def test_mid_tier_stats_empty_thread():
    tid = _make_thread()
    out = mtl.mid_tier_stats(tid)
    assert out["total_messages"] == 0
    assert out["summary_count"] == 0
    assert out["by_source"] == {"compressed_summary": 0, "system_summary": 0}
    assert out["compression_ratio"] == 0.0
    assert out["latest_summary_created_at"] is None
    assert out["latest_summary_source"] is None
    assert out["covered_section_count"] == 0
    assert out["section_keys"] == list(SECTION_KEYS)
    # 9 section の coverage 0
    assert all(out["section_coverage"][k] == 0 for k in SECTION_KEYS)


def test_mid_tier_stats_with_mixed_sources():
    tid = _make_thread()
    cts.get_store().add_message(tid, "user", "hi")
    _add_compressed_message(tid, {"context": ["c1", "c2"]})
    time.sleep(0.001)
    _add_system_summary_message(tid, {"goals": ["g1"]})
    out = mtl.mid_tier_stats(tid)
    assert out["total_messages"] == 3
    assert out["summary_count"] == 2
    assert out["by_source"] == {"compressed_summary": 1, "system_summary": 1}
    assert out["compression_ratio"] == pytest.approx(2 / 3)
    assert out["latest_summary_source"] == "system_summary"
    assert out["section_coverage"]["context"] == 2
    assert out["section_coverage"]["goals"] == 1
    assert out["covered_section_count"] == 2


def test_mid_tier_stats_unknown_thread_404():
    with pytest.raises(MidTermLayerError) as ei:
        mtl.mid_tier_stats(99999)
    assert "not found" in str(ei.value)


def test_mid_tier_stats_actor_validated():
    tid = _make_thread()
    with pytest.raises(MidTermLayerError):
        mtl.mid_tier_stats(tid, actor_user_id="   ")


# ══════════════════════════════════════════════════════════════════════
# G7: register_summarizer_backend hook
# ══════════════════════════════════════════════════════════════════════


def test_g7_register_backend_callable_only():
    with pytest.raises(MidTermLayerError):
        mtl.register_summarizer_backend("not callable")
    with pytest.raises(MidTermLayerError):
        mtl.register_summarizer_backend(123)
    # OK paths
    mtl.register_summarizer_backend(lambda msgs: empty_summary())
    assert callable(mtl.get_summarizer_backend())
    mtl.register_summarizer_backend(None)
    assert mtl.get_summarizer_backend() is None


def test_g7_backend_swap_used_in_record(stub_legacy_persist):
    tid = _make_thread()
    # backend が完全に違う summary を返す
    custom = {k: [f"backend-{k}"] for k in SECTION_KEYS}
    mtl.register_summarizer_backend(lambda msgs: custom)
    res = asyncio.run(mtl.record_summary(tid, _full_summary("ignored")))
    assert res["backend_used"] is True
    assert res["summary"] == custom


def test_g7_backend_exception_falls_back_to_provided(stub_legacy_persist):
    tid = _make_thread()
    def boom(msgs):
        raise RuntimeError("backend down")
    mtl.register_summarizer_backend(boom)
    provided = _full_summary("provided")
    res = asyncio.run(mtl.record_summary(tid, provided))
    assert res["backend_used"] is False
    assert res["summary"] == provided


def test_g7_backend_invalid_output_falls_back_to_provided(stub_legacy_persist):
    tid = _make_thread()
    mtl.register_summarizer_backend(lambda msgs: {"invalid_only": ["x"]})
    provided = _full_summary("provided")
    res = asyncio.run(mtl.record_summary(tid, provided))
    assert res["backend_used"] is False
    assert res["summary"] == provided


def test_ac4_backend_exception_emits_warning_log(stub_legacy_persist, caplog):
    """AC-4 spec 文 "emit a warning log (silent failure 防止)" の検証.

    backend が例外を投げた場合 fallback するだけでなく WARNING level の log を
    必ず emit すること. 将来 logger.warning を pass に変えたら fail させる.
    """
    tid = _make_thread()

    def boom(msgs):
        raise RuntimeError("backend kaboom for caplog assert")

    mtl.register_summarizer_backend(boom)
    provided = _full_summary("provided")
    with caplog.at_level("WARNING", logger="services.mid_term_layer"):
        res = asyncio.run(mtl.record_summary(tid, provided))
    assert res["backend_used"] is False
    assert res["summary"] == provided
    warns = [
        r for r in caplog.records
        if r.levelname == "WARNING"
        and "summarizer backend raised" in r.getMessage()
    ]
    assert len(warns) >= 1, (
        f"AC-4 spec 'emit a warning log' violated: expected WARNING log "
        f"about backend raise, got records={[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )
    # silent failure 防止: backend kaboom メッセージが log に含まれる
    assert "backend kaboom for caplog assert" in warns[0].getMessage()


def test_ac4_backend_invalid_output_missing_keys_emits_warning_log(
    stub_legacy_persist, caplog,
):
    """AC-4 spec 文 "missing SECTION_KEYS" → fallback + WARNING log.

    backend が known SECTION_KEYS を 1 つも含まない dict を返したとき,
    fallback するだけでなく WARNING level log を emit すること.
    """
    tid = _make_thread()
    mtl.register_summarizer_backend(lambda msgs: {"invalid_only": ["x"]})
    provided = _full_summary("provided")
    with caplog.at_level("WARNING", logger="services.mid_term_layer"):
        res = asyncio.run(mtl.record_summary(tid, provided))
    assert res["backend_used"] is False
    assert res["summary"] == provided
    warns = [
        r for r in caplog.records
        if r.levelname == "WARNING"
        and "summarizer backend returned invalid output" in r.getMessage()
    ]
    assert len(warns) >= 1, (
        f"AC-4 spec 'missing SECTION_KEYS → emit warning log' violated: "
        f"got records={[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


def test_ac4_backend_invalid_output_wrong_type_emits_warning_log(
    stub_legacy_persist, caplog,
):
    """AC-4 spec 文 "wrong types" → fallback + WARNING log.

    backend が dict 以外 (list / None / str / int) を返したとき,
    _normalize_summary が None を返し fallback + WARNING log.
    """
    tid = _make_thread()
    for bad_output in [None, [], "not a dict", 42, ()]:
        caplog.clear()
        mtl.register_summarizer_backend(lambda msgs, _b=bad_output: _b)
        provided = _full_summary("provided")
        with caplog.at_level("WARNING", logger="services.mid_term_layer"):
            res = asyncio.run(mtl.record_summary(tid, provided))
        assert res["backend_used"] is False, f"bad_output={bad_output!r} not fallback"
        assert res["summary"] == provided
        warns = [
            r for r in caplog.records
            if r.levelname == "WARNING"
            and "summarizer backend returned invalid output" in r.getMessage()
        ]
        assert len(warns) >= 1, (
            f"AC-4 spec 'wrong types ({type(bad_output).__name__}) → "
            f"emit warning log' violated"
        )


def test_g7_backend_disabled_via_use_backend_false(stub_legacy_persist):
    tid = _make_thread()
    mtl.register_summarizer_backend(lambda msgs: _full_summary("backend"))
    provided = _full_summary("provided")
    res = asyncio.run(mtl.record_summary(tid, provided, use_backend=False))
    assert res["backend_used"] is False
    assert res["summary"] == provided


# ══════════════════════════════════════════════════════════════════════
# G8: dual-write helper (record_summary)
# ══════════════════════════════════════════════════════════════════════


def test_g8_record_summary_writes_path_a(stub_legacy_persist):
    tid = _make_thread()
    s = _full_summary("rec")
    res = asyncio.run(mtl.record_summary(tid, s))
    # 経路 A: chat_thread_store に role='system' + compressed_summary
    msg = cts.get_store().get_message(res["message_id"])
    assert msg is not None
    assert msg.role == SUMMARY_ROLE_SYSTEM
    assert msg.compressed_summary == s


def test_g8_record_summary_writes_path_b_when_persist_legacy_true(stub_legacy_persist):
    tid = _make_thread()
    s = _full_summary("rec")
    res = asyncio.run(mtl.record_summary(tid, s, persist_legacy=True))
    assert res["legacy_result"]["status"] == "ok"
    assert len(stub_legacy_persist) == 1
    assert stub_legacy_persist[0]["summary"] == s


def test_g8_record_summary_skips_path_b_when_persist_legacy_false(stub_legacy_persist):
    tid = _make_thread()
    res = asyncio.run(mtl.record_summary(
        tid, _full_summary("x"), persist_legacy=False,
    ))
    assert res["legacy_result"] is None
    assert stub_legacy_persist == []


def test_g8_record_summary_legacy_failure_does_not_raise(monkeypatch):
    tid = _make_thread()

    async def boom(thread_id, summary):
        raise RuntimeError("sqlite down")

    import services.memory_service as ms
    monkeypatch.setattr(ms, "persist_compaction", boom)
    res = asyncio.run(mtl.record_summary(tid, _full_summary("x")))
    assert res["legacy_result"]["status"] == "error"
    # Path A は成功しているべき
    assert res["message_id"] is not None


def test_g8_record_summary_invalid_summary_rejected(stub_legacy_persist):
    tid = _make_thread()
    with pytest.raises(MidTermLayerError):
        asyncio.run(mtl.record_summary(tid, {"unknown": ["x"]}))
    with pytest.raises(MidTermLayerError):
        asyncio.run(mtl.record_summary(tid, "not dict"))
    # state mutate していない
    assert cts.get_store().count_messages(tid) == 0
    assert stub_legacy_persist == []


def test_g8_record_summary_unknown_thread_404(stub_legacy_persist):
    with pytest.raises(MidTermLayerError) as ei:
        asyncio.run(mtl.record_summary(99999, _full_summary("x")))
    assert "not found" in str(ei.value)
    assert stub_legacy_persist == []


def test_g8_record_summary_persist_legacy_must_be_bool():
    tid = _make_thread()
    with pytest.raises(MidTermLayerError):
        asyncio.run(mtl.record_summary(tid, _full_summary("x"), persist_legacy="yes"))


def test_g8_record_summary_use_backend_must_be_bool():
    tid = _make_thread()
    with pytest.raises(MidTermLayerError):
        asyncio.run(mtl.record_summary(tid, _full_summary("x"), use_backend="yes"))


# ══════════════════════════════════════════════════════════════════════
# G9: conversation_summarizer / conversation_memory 不変
# ══════════════════════════════════════════════════════════════════════


def test_g9_conversation_summarizer_unchanged():
    from services import conversation_summarizer as cs
    assert hasattr(cs, "generate_summary")
    assert hasattr(cs, "format_for_prompt")
    assert hasattr(cs, "SUMMARY_PROMPT")


def test_g9_conversation_memory_unchanged():
    from services import conversation_memory as cm
    assert hasattr(cm, "embed_message")
    assert hasattr(cm, "search_related_history")
    assert hasattr(cm, "build_context_for_agent")
    assert hasattr(cm, "estimate_tokens")
    assert hasattr(cm, "CONTEXT_WINDOWS")


def test_g9_chat_thread_store_unchanged():
    """chat_thread_store の API surface が変わっていない."""
    s = cts.ChatThreadStore()
    for sym in (
        "create_thread", "get_thread", "list_threads", "update_thread", "delete_thread",
        "add_message", "get_message", "list_messages", "delete_message", "count_messages",
    ):
        assert hasattr(s, sym), f"chat_thread_store.{sym} missing"


def test_g9_memory_service_unchanged():
    from services import memory_service as ms
    for sym in (
        "emit_event", "persist_compaction", "write_fact",
        "merge_for_session", "mirror_to_obsidian", "fact_fingerprint",
    ):
        assert hasattr(ms, sym), f"memory_service.{sym} missing"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: endpoint smoke
# ══════════════════════════════════════════════════════════════════════


def test_ac1_endpoint_summary(client):
    tid = _make_thread()
    s = _full_summary("v")
    _add_compressed_message(tid, s)
    r = client.get("/api/mid-term/summary", params={"thread_id": tid})
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["summary"] == s
    assert set(body["summary"].keys()) == set(SECTION_KEYS)


def test_ac1_endpoint_compressed(client):
    tid = _make_thread()
    _add_compressed_message(tid, _full_summary("a"))
    _add_system_summary_message(tid, _full_summary("b"))
    r = client.get("/api/mid-term/compressed", params={"thread_id": tid})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2


def test_ac1_endpoint_stats(client):
    tid = _make_thread()
    _add_compressed_message(tid, _full_summary("v"))
    r = client.get("/api/mid-term/stats", params={"thread_id": tid})
    assert r.status_code == 200
    body = r.json()
    assert body["section_keys"] == list(SECTION_KEYS)
    assert body["summary_count"] == 1


def test_ac1_endpoint_record(client, stub_legacy_persist):
    tid = _make_thread()
    s = _full_summary("rec")
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid,
        "summary": s,
        "persist_legacy": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == s
    assert body["legacy_result"]["status"] == "ok"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 2 秒以内 + {detail:{code,message}}
# ══════════════════════════════════════════════════════════════════════


def test_ac2_summary_within_2sec(client):
    tid = _make_thread()
    _add_compressed_message(tid, _full_summary("x"))
    t0 = time.time()
    r = client.get("/api/mid-term/summary", params={"thread_id": tid})
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_compressed_within_2sec(client):
    tid = _make_thread()
    for i in range(50):
        _add_compressed_message(tid, _full_summary(f"v{i}"))
    t0 = time.time()
    r = client.get(
        "/api/mid-term/compressed",
        params={"thread_id": tid, "limit": MAX_HISTORY_LIMIT},
    )
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_stats_within_2sec(client):
    tid = _make_thread()
    for i in range(20):
        _add_compressed_message(tid, _full_summary(f"v{i}"))
    t0 = time.time()
    r = client.get("/api/mid-term/stats", params={"thread_id": tid})
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_record_within_2sec(client, stub_legacy_persist):
    tid = _make_thread()
    t0 = time.time()
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid,
        "summary": _full_summary("x"),
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_consistency(client):
    """全 error path で {detail:{code,message}} で code が 'mid_term.' prefix."""
    cases = [
        ("GET", "/api/mid-term/summary", {"thread_id": 99999}, None, 404),
        ("GET", "/api/mid-term/summary",
         {"thread_id": 1, "actor_user_id": "  "}, None, 401),
        ("GET", "/api/mid-term/summary",
         {"thread_id": 1, "prefer_source": "bogus"}, None, 400),
        ("GET", "/api/mid-term/compressed", {"thread_id": 99999}, None, 404),
        ("GET", "/api/mid-term/stats", {"thread_id": 99999}, None, 404),
    ]
    # thread_id=1 のケースに備え、1 を作っておく
    tid = _make_thread()
    assert tid == 1  # reset_store により毎回 1 から
    for method, path, params, body, expected_status in cases:
        if method == "GET":
            r = client.get(path, params=params)
        else:
            r = client.post(path, json=body)
        assert r.status_code == expected_status, f"{path}/{params}: {r.status_code}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert "code" in detail and "message" in detail
        assert detail["code"].startswith("mid_term."), f"{path}: {detail['code']}"


def test_ac2_record_invalid_summary_returns_400(client, stub_legacy_persist):
    tid = _make_thread()
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid,
        "summary": {"unknown": ["x"]},
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "mid_term.invalid"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: 既存 module 不変 + audit emit / read は emit しない
# ══════════════════════════════════════════════════════════════════════


def test_ac3_summary_no_audit(client, _capture_audit):
    tid = _make_thread()
    _add_compressed_message(tid, _full_summary("v"))
    client.get("/api/mid-term/summary", params={"thread_id": tid})
    assert not [e for e in _capture_audit if e["event_type"].startswith("mid_term.")]


def test_ac3_compressed_no_audit(client, _capture_audit):
    tid = _make_thread()
    client.get("/api/mid-term/compressed", params={"thread_id": tid})
    assert not [e for e in _capture_audit if e["event_type"].startswith("mid_term.")]


def test_ac3_stats_no_audit(client, _capture_audit):
    tid = _make_thread()
    client.get("/api/mid-term/stats", params={"thread_id": tid})
    assert not [e for e in _capture_audit if e["event_type"].startswith("mid_term.")]


def test_ac3_record_emits_audit(client, _capture_audit, stub_legacy_persist):
    tid = _make_thread()
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid,
        "summary": _full_summary("v"),
        "actor_user_id": "alice",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "mid_term.recorded"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert detail["thread_id"] == tid
    # G3 仕様: audit source は 'chat_thread_store' / 'memory_service'
    assert detail["source"] == "chat_thread_store"
    assert detail["legacy_status"] == "ok"
    assert events[0]["user_id"] == "alice"


def test_ac3_existing_modules_api_surface_unchanged(client):
    """summary endpoint 呼出後も既存 chat_threads router が変わっていない."""
    tid = _make_thread()
    _add_compressed_message(tid, _full_summary("v"))
    client.get("/api/mid-term/summary", params={"thread_id": tid})
    # chat_threads router (T-M30-01) 不変確認
    routes = [getattr(r, "path", "") for r in client.app.routes]
    assert "/api/chat-threads" in routes or any(
        p.startswith("/api/chat-threads") for p in routes
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid input は 4xx + state mutate しない
# ══════════════════════════════════════════════════════════════════════


def test_ac4_summary_thread_id_invalid_400_not_422(client):
    """AC-4: 全 4xx は {detail:{code,message}} に統一. 422 は返さない."""
    r = client.get("/api/mid-term/summary", params={"thread_id": 0})
    assert r.status_code == 400, f"{r.status_code}: {r.text}"
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "mid_term.invalid"
    assert "message" in detail


def test_ac4_summary_thread_id_non_numeric_400(client):
    r = client.get("/api/mid-term/summary", params={"thread_id": "abc"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_summary_thread_id_missing_400(client):
    r = client.get("/api/mid-term/summary")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_summary_unknown_thread_404(client):
    r = client.get("/api/mid-term/summary", params={"thread_id": 88888})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "mid_term.not_found"


def test_ac4_summary_invalid_prefer_source_400(client):
    tid = _make_thread()
    r = client.get(
        "/api/mid-term/summary",
        params={"thread_id": tid, "prefer_source": "bogus"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_summary_empty_actor_401(client):
    tid = _make_thread()
    r = client.get(
        "/api/mid-term/summary",
        params={"thread_id": tid, "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "mid_term.unauthorized"


def test_ac4_compressed_invalid_limit_400_not_422(client):
    """AC-4: limit range 違反は 400 + tier1.invalid 形式."""
    tid = _make_thread()
    for bad in (0, MAX_HISTORY_LIMIT + 1):
        r = client.get(
            "/api/mid-term/compressed",
            params={"thread_id": tid, "limit": bad},
        )
        assert r.status_code == 400, f"limit={bad}: {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["code"] == "mid_term.invalid"


def test_ac4_stats_unknown_thread_404(client):
    r = client.get("/api/mid-term/stats", params={"thread_id": 88888})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "mid_term.not_found"


def test_ac4_record_invalid_thread_id_400_not_422(client):
    r = client.post("/api/mid-term/record", json={
        "thread_id": 0, "summary": _full_summary("x"),
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "mid_term.invalid"


def test_ac4_record_unknown_thread_does_not_mutate(
    client, stub_legacy_persist, _capture_audit,
):
    r = client.post("/api/mid-term/record", json={
        "thread_id": 88888, "summary": _full_summary("x"),
    })
    assert r.status_code == 404
    # state mutate なし: legacy にも書かれない / audit emit なし
    assert stub_legacy_persist == []
    assert not [e for e in _capture_audit if e["event_type"] == "mid_term.recorded"]


def test_ac4_record_invalid_summary_does_not_mutate(
    client, stub_legacy_persist, _capture_audit,
):
    tid = _make_thread()
    before_msg_count = cts.get_store().count_messages(tid)
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid, "summary": {"unknown": ["x"]},
    })
    assert r.status_code == 400
    # state mutate なし
    assert cts.get_store().count_messages(tid) == before_msg_count
    assert stub_legacy_persist == []
    assert not [e for e in _capture_audit if e["event_type"] == "mid_term.recorded"]


def test_ac4_record_summary_must_be_dict_400_not_422(client):
    tid = _make_thread()
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid, "summary": "not dict",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_record_missing_thread_id_400(client):
    r = client.post("/api/mid-term/record", json={"summary": _full_summary("x")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_record_missing_summary_400(client):
    tid = _make_thread()
    r = client.post("/api/mid-term/record", json={"thread_id": tid})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_record_persist_legacy_must_be_bool_400(client):
    tid = _make_thread()
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid, "summary": _full_summary("x"),
        "persist_legacy": "yes",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_record_non_dict_body_400(client):
    r = client.post("/api/mid-term/record", json=["not", "dict"])
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mid_term.invalid"


def test_ac4_all_4xx_detail_shape(client):
    """AC-4: 全 endpoint の 4xx response が {detail:{code,message}} 形式."""
    cases = [
        # (method, path, json_or_params, expected_status)
        ("GET", "/api/mid-term/summary", {}, 400),
        ("GET", "/api/mid-term/summary", {"thread_id": 0}, 400),
        ("GET", "/api/mid-term/summary",
         {"thread_id": "x"}, 400),
        ("GET", "/api/mid-term/summary",
         {"thread_id": 88888}, 404),
        ("GET", "/api/mid-term/compressed",
         {"thread_id": 0}, 400),
        ("GET", "/api/mid-term/compressed",
         {"thread_id": 88888}, 404),
        ("GET", "/api/mid-term/stats", {"thread_id": 0}, 400),
        ("GET", "/api/mid-term/stats", {"thread_id": 88888}, 404),
    ]
    for method, path, params, expected in cases:
        r = client.get(path, params=params)
        assert r.status_code == expected, (
            f"{path} {params}: {r.status_code}: {r.text}"
        )
        detail = r.json()["detail"]
        assert isinstance(detail, dict), f"{path}: detail must be dict"
        assert detail.get("code", "").startswith("mid_term."), f"{path}: bad code"
        assert isinstance(detail.get("message", ""), str) and detail["message"]


def test_ac4_endpoint_does_not_mutate_state_on_summary_error(client):
    """summary endpoint 失敗時 in-memory state 変化なし."""
    tid = _make_thread()
    before_count = cts.get_store().count_messages(tid)
    client.get(
        "/api/mid-term/summary",
        params={"thread_id": tid, "prefer_source": "bogus"},
    )
    assert cts.get_store().count_messages(tid) == before_count


# ══════════════════════════════════════════════════════════════════════
# Cross-check: mid layer と既存 store の整合
# ══════════════════════════════════════════════════════════════════════


def test_cross_check_compressed_summary_field_persisted_correctly():
    """chat_thread_store の compressed_summary フィールドに dict を保持できる."""
    tid = _make_thread()
    s = _full_summary("v")
    msg = cts.get_store().add_message(
        tid, "system", "[test]", compressed_summary=s,
    )
    fetched = cts.get_store().get_message(msg.id)
    assert fetched.compressed_summary == s


def test_cross_check_system_summary_role_is_valid():
    """role='system_summary' は ChatThreadStore の VALID_ROLES に無いため,
    mid layer の経路 B は memory_service.persist_compaction が直接書いた
    chat_messages レコードを読む経路を想定する (chat_thread_store.add_message
    では作れない). 本テストはこの仕様境界の明示記録."""
    assert SUMMARY_ROLE_SYSTEM_SUMMARY not in cts.VALID_ROLES
    # chat_thread_store.add_message でこの role を使うと拒否される
    tid = _make_thread()
    with pytest.raises(cts.ChatThreadError):
        cts.get_store().add_message(tid, SUMMARY_ROLE_SYSTEM_SUMMARY, "x")


def test_cross_check_in_memory_path_b_via_internal_dataclass():
    """in-memory store でも経路 B のレコード形を直接構築すれば read できる."""
    import time as _t
    tid = _make_thread()
    store = cts.get_store()
    # 内部 dict に直接挿入 (テスト専用) — 経路 B の Postgres 経由を simulate
    msg = cts.ChatMessage(
        id=99001,
        thread_id=tid,
        role=SUMMARY_ROLE_SYSTEM_SUMMARY,
        content=json.dumps(_full_summary("b")),
        compressed_summary=None,
        token_count=None,
        created_at=_t.time(),
    )
    with store._lock:
        store._messages[msg.id] = msg
        store._by_thread.setdefault(tid, []).append(msg.id)
    out = mtl.latest_summary(tid)
    assert out["found"] is True
    assert out["source"] == "system_summary"


# ══════════════════════════════════════════════════════════════════════
# Module docstring / divergence note (G10 cross-module note)
# ══════════════════════════════════════════════════════════════════════


def test_module_docstring_documents_g7_g10():
    """module docstring に G7-G10 が明示されている (Phase 2 hook の発見性)."""
    doc = mtl.__doc__ or ""
    for tag in ("G7", "G8", "G9", "G10"):
        assert tag in doc, f"module docstring must mention {tag}"


def test_module_docstring_documents_path_a_and_b():
    doc = mtl.__doc__ or ""
    assert "経路 A" in doc
    assert "経路 B" in doc


# ══════════════════════════════════════════════════════════════════════
# Spec gap closure: G1 list_summaries (spec-name alias)
# ══════════════════════════════════════════════════════════════════════


def test_g1_list_summaries_function_exists():
    """AC-1 仕様文 'latest_summary / list_summaries' の名前要件."""
    assert hasattr(mtl, "list_summaries")
    assert callable(mtl.list_summaries)


def test_g1_list_summaries_matches_compressed_history():
    tid = _make_thread()
    s = _full_summary("v")
    cts.get_store().add_message(tid, "system", "[t]", compressed_summary=s)
    a = mtl.list_summaries(tid)
    b = mtl.compressed_history(tid)
    assert a == b


def test_g1_list_endpoint_alias(client):
    tid = _make_thread()
    s = _full_summary("v")
    cts.get_store().add_message(tid, "system", "[t]", compressed_summary=s)
    r_compressed = client.get(
        "/api/mid-term/compressed", params={"thread_id": tid},
    )
    r_list = client.get(
        "/api/mid-term/list", params={"thread_id": tid},
    )
    assert r_compressed.status_code == 200
    assert r_list.status_code == 200
    assert r_compressed.json() == r_list.json()


# ══════════════════════════════════════════════════════════════════════
# Spec gap closure: G2 service-level audit emit
# ══════════════════════════════════════════════════════════════════════


def test_g2_latest_summary_audited_emits_mid_term_read(_capture_audit):
    tid = _make_thread()
    s = _full_summary("v")
    cts.get_store().add_message(tid, "system", "[t]", compressed_summary=s)
    asyncio.run(mtl.latest_summary_audited(tid, emit_audit=True))
    events = [e for e in _capture_audit if e["event_type"] == "mid_term.read"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert detail["thread_id"] == tid
    assert detail["source"] == "chat_thread_store"   # G3 正規化済み
    assert detail["found"] is True


def test_g2_latest_summary_audited_emit_audit_false_skips(_capture_audit):
    tid = _make_thread()
    asyncio.run(mtl.latest_summary_audited(tid, emit_audit=False))
    assert not [e for e in _capture_audit if e["event_type"] == "mid_term.read"]


def test_g2_latest_summary_audited_default_emits(_capture_audit):
    """default emit_audit=True (service 経由直接呼出は emit)."""
    tid = _make_thread()
    asyncio.run(mtl.latest_summary_audited(tid))
    assert [e for e in _capture_audit if e["event_type"] == "mid_term.read"]


def test_g2_http_read_endpoints_do_not_emit_audit(client, _capture_audit):
    """AC-2: 'Read endpoints shall not emit audit events'.
    HTTP GET 経由は service の latest_summary_audited を使わず emit しない."""
    tid = _make_thread()
    s = _full_summary("v")
    cts.get_store().add_message(tid, "system", "[t]", compressed_summary=s)
    client.get("/api/mid-term/summary", params={"thread_id": tid})
    client.get("/api/mid-term/compressed", params={"thread_id": tid})
    client.get("/api/mid-term/list", params={"thread_id": tid})
    client.get("/api/mid-term/stats", params={"thread_id": tid})
    assert not [e for e in _capture_audit if e["event_type"] == "mid_term.read"]


# ══════════════════════════════════════════════════════════════════════
# Spec gap closure: G3 audit source normalization
# ══════════════════════════════════════════════════════════════════════


def test_g3_to_audit_source_mapping():
    assert mtl.to_audit_source("compressed_summary") == "chat_thread_store"
    assert mtl.to_audit_source("system_summary") == "memory_service"
    assert mtl.to_audit_source(None) is None
    assert mtl.to_audit_source("unknown") is None


def test_g3_record_summary_audit_source_field_is_chat_thread_store(
    stub_legacy_persist,
):
    tid = _make_thread()
    result = asyncio.run(mtl.record_summary(
        tid, _full_summary("v"), persist_legacy=False,
    ))
    assert result["audit_source"] == "chat_thread_store"
    assert result["audit_sources"] == ["chat_thread_store"]


def test_g3_record_summary_audit_sources_includes_memory_service_when_legacy_ok(
    stub_legacy_persist,
):
    tid = _make_thread()
    result = asyncio.run(mtl.record_summary(
        tid, _full_summary("v"), persist_legacy=True,
    ))
    # stub_legacy_persist は ok 戻し
    assert result["audit_source"] == "chat_thread_store"
    assert set(result["audit_sources"]) == {"chat_thread_store", "memory_service"}


def test_g3_record_endpoint_audit_uses_chat_thread_store_source(
    client, _capture_audit, stub_legacy_persist,
):
    tid = _make_thread()
    r = client.post("/api/mid-term/record", json={
        "thread_id": tid, "summary": _full_summary("v"),
        "persist_legacy": True,
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "mid_term.recorded"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert detail["source"] == "chat_thread_store"
    assert "compressed_summary" not in (detail.get("source") or "")
    assert set(detail["audit_sources"]) >= {"chat_thread_store"}


# ══════════════════════════════════════════════════════════════════════
# Spec gap closure: G5 lint cross-ref (T-M28-04 UNWANTED)
# ══════════════════════════════════════════════════════════════════════


def test_g5_lint_script_has_no_self_9section_check():
    from pathlib import Path
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "lint-mock.sh"
    ).read_text(encoding="utf-8")
    assert "check_no_self_9section_summary()" in script
    assert "--no-self-9section" in script


def test_g5_lint_check_passes_when_app_code_clean():
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-self-9section"],
        capture_output=True, text=True, timeout=30, cwd=str(repo),
    )
    assert r.returncode == 0, (
        f"lint --no-self-9section failed: stdout={r.stdout[:400]} "
        f"stderr={r.stderr[:400]}"
    )
    assert "OK" in r.stdout


def test_g5_module_does_not_define_self_9section_function():
    import inspect
    src = inspect.getsource(mtl)
    forbidden = (
        "generate_9_section_summary",
        "build_9_section_summary",
        "synthesize_9_section_summary",
        "compose_9_section_summary",
        "build_structured_9_section",
        "make_9_section_summary",
    )
    for token in forbidden:
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert f"def {token}" not in line, (
                f"mid_term_layer must not define {token!r} "
                "(T-M30-03 AC-4 / T-M28-04 cross-ref)"
            )


# ──────────────────────────────────────────────────────────────────────
# Gap closure (post-PR #247 audit): lint #14 通用語 pattern 強化検証
# ──────────────────────────────────────────────────────────────────────


def _run_lint_with_temp_file(tmp_path, file_content: str) -> tuple[int, str]:
    """app code 階層に一時 file を置いて lint --no-self-9section を回す.

    Returns: (returncode, combined stdout+stderr)
    """
    import shutil
    import subprocess
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    target_dir = repo / "backend" / "services"
    # 一時 file を services 配下に書き込み (lint の検索対象に入る)
    target_file = target_dir / "_lint_probe_temp.py"
    try:
        target_file.write_text(file_content, encoding="utf-8")
        r = subprocess.run(
            ["bash", "scripts/lint-mock.sh", "--no-self-9section"],
            capture_output=True, text=True, timeout=30, cwd=str(repo),
        )
        return r.returncode, (r.stdout + r.stderr)
    finally:
        if target_file.exists():
            target_file.unlink()
        # __pycache__ の cleanup
        pycache = target_dir / "__pycache__"
        if pycache.exists():
            for f in pycache.glob("_lint_probe_temp*"):
                f.unlink()
            # remove dir only if empty
            try:
                shutil.rmtree(pycache, ignore_errors=True)
            except OSError:
                pass


@pytest.mark.parametrize("probe_def", [
    # variation 1: <verb>_<9|nine>[_.]section[s][_.]summary
    "def build_9_section_summary(msgs): pass",
    "def build_9section_summary(msgs): pass",        # アンダースコアなし
    "def make_nine_section_summary(msgs): pass",      # nine 英単語
    "def generate_9_sections_summary(msgs): pass",    # 複数形
    "def synthesize_9_section_summary(msgs): pass",
    # variation 2: <verb>_summary_<9|nine>[_.]section[s]
    "def compose_summary_9_sections(msgs): pass",
    "def create_summary_nine_sections(msgs): pass",
    # variation 3: <verb>_<9|nine>[_.]sections?[_.]for_
    "def assemble_9_sections_for_thread(msgs): pass",
    "def construct_nine_section_for_session(msgs): pass",
])
def test_lint_14_catches_self_9section_variations(tmp_path, probe_def):
    """lint #14 が通用語 variation を全部 fail させること."""
    code, output = _run_lint_with_temp_file(
        tmp_path, f"# probe\n{probe_def}\n",
    )
    assert code != 0, (
        f"lint #14 must REJECT variation: {probe_def!r}\n"
        f"output[:600]={output[:600]}"
    )
    assert "NG" in output, (
        f"expected NG in output for {probe_def!r}, got: {output[:400]}"
    )


@pytest.mark.parametrize("benign_def", [
    # benign: 9-section ではない普通の名前
    "def build_summary(msgs): pass",
    "def generate_response(msgs): pass",
    "def compose_payload(msgs): pass",
    "def section_count(): return 9",
])
def test_lint_14_allows_benign_function_names(tmp_path, benign_def):
    """lint #14 が無関係な関数名で false-positive しないこと."""
    code, output = _run_lint_with_temp_file(
        tmp_path, f"# benign probe\n{benign_def}\n",
    )
    assert code == 0, (
        f"lint #14 must NOT reject benign name: {benign_def!r}\n"
        f"output[:600]={output[:600]}"
    )


# ══════════════════════════════════════════════════════════════════════
# Spec gap closure: G6 cross-module SECTION_KEYS invariant
# ══════════════════════════════════════════════════════════════════════


def test_g6_section_keys_is_canonical_source():
    """mid_term_layer.SECTION_KEYS が 9 件 + 全要素 str + 重複なし."""
    assert len(mtl.SECTION_KEYS) == 9
    assert all(isinstance(k, str) and k for k in mtl.SECTION_KEYS)
    assert len(set(mtl.SECTION_KEYS)) == 9


def test_g6_section_keys_match_tier3_when_available():
    """tier3_structured_summary が import 可能なら SECTION_KEYS 一致."""
    try:
        from services import tier3_structured_summary as t3
    except ImportError:
        pytest.skip("tier3_structured_summary not available")
    if not hasattr(t3, "SECTION_KEYS"):
        pytest.skip("tier3 module has no SECTION_KEYS")
    assert tuple(t3.SECTION_KEYS) == tuple(mtl.SECTION_KEYS), (
        "9-section invariant violated cross-module (mid_term_layer vs tier3)"
    )


def test_g6_section_keys_match_tier2_cache_mandatory():
    """tier2_cache.SECTION_KEYS が必ず存在し mid_term_layer と完全一致.

    AC-1 spec 文 "shall hold cross-module (mid_term_layer / tier2_cache /
    tier3_structured_summary)" は tier2_cache を名指ししているため
    skip 不可 (skip すると AC-1 invariant が満たされない).
    KNOWN_SUMMARY_SECTIONS は deprecated alias として SECTION_KEYS と同値.
    """
    from services import tier2_cache as t2
    assert hasattr(t2, "SECTION_KEYS"), (
        "tier2_cache must define SECTION_KEYS (AC-1 cross-module invariant)"
    )
    assert tuple(t2.SECTION_KEYS) == tuple(mtl.SECTION_KEYS), (
        "9-section invariant violated cross-module (mid_term_layer vs tier2)"
    )
    assert tuple(t2.KNOWN_SUMMARY_SECTIONS) == tuple(t2.SECTION_KEYS), (
        "tier2_cache.KNOWN_SUMMARY_SECTIONS must be a same-value alias"
    )


def test_g6_section_keys_match_tier3_mandatory_when_module_present():
    """tier3_structured_summary が存在する場合は SECTION_KEYS 必須 + 一致.

    Phase 1 では tier3 module は optional だが, 存在するときに SECTION_KEYS
    が無い / 不一致は invariant 違反として fail させる.
    """
    try:
        from services import tier3_structured_summary as t3
    except ImportError:
        pytest.skip("tier3_structured_summary not yet merged (PR #128 pending)")
    assert hasattr(t3, "SECTION_KEYS"), (
        "tier3_structured_summary must define SECTION_KEYS (AC-1 invariant)"
    )
    assert tuple(t3.SECTION_KEYS) == tuple(mtl.SECTION_KEYS), (
        "9-section invariant violated cross-module (mid_term_layer vs tier3)"
    )


def test_g6_format_summary_text_uses_section_keys_order():
    """tier2_cache.format_summary_text が SECTION_KEYS 順で出力する.

    入力 dict の挿入順に依存せず, SECTION_KEYS 固定順で markdown 化される
    invariant. これにより cross-module で順序まで安定する.
    """
    from services import tier2_cache as t2
    shuffled = {
        "next_steps": ["s1"],
        "context": ["c1"],
        "decisions": ["d1"],
    }
    rendered = t2.format_summary_text(shuffled)
    idx_context = rendered.find("## context")
    idx_decisions = rendered.find("## decisions")
    idx_next_steps = rendered.find("## next_steps")
    assert idx_context >= 0
    assert idx_decisions >= 0
    assert idx_next_steps >= 0
    assert idx_context < idx_decisions < idx_next_steps, (
        f"format_summary_text must follow SECTION_KEYS order, got "
        f"context@{idx_context} decisions@{idx_decisions} next_steps@{idx_next_steps}"
    )


# ══════════════════════════════════════════════════════════════════════
# Constants / public API surface
# ══════════════════════════════════════════════════════════════════════


def test_audit_event_constants_match_spec():
    assert mtl.AUDIT_EVENT_READ == "mid_term.read"
    assert mtl.AUDIT_EVENT_RECORDED == "mid_term.recorded"
    assert mtl.VALID_AUDIT_SOURCES == ("chat_thread_store", "memory_service")
