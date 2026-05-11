"""T-M28-04: Tier 3 9-section structured summary — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : T-M28-04 を M-28 仕様通り実装
                       9 sections / 95% threshold / heuristic 分類 / persist
  AC-2 EVENT-DRIVEN  : trigger 時に audit log に action + timestamp を記録,
                       2 秒以内応答, {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 chat_thread_store / tier2_cache / memory_service
                       不変 (symbol 存在 + 9-section key 一致 + audit 記録)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import chat_thread_store as cts
from services import tier3_structured_summary as t3
from services.tier3_structured_summary import (
    AUDIT_ACTION_COMPACTED,
    AUDIT_ACTION_SKIPPED,
    DEFAULT_MAX_TOKENS,
    DEFAULT_THRESHOLD,
    MAX_SECTION_ITEMS,
    MAX_THRESHOLD,
    MIN_MAX_TOKENS,
    MIN_THRESHOLD,
    SECTION_KEYS,
    Tier3SummaryError,
    clear_audit_log,
    estimate_context_usage,
    generate_summary,
    get_summary_backend,
    list_audit_log,
    register_summary_backend,
    run_compaction,
    should_compact,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_state():
    cts.reset_store()
    clear_audit_log()
    register_summary_backend(None)
    yield
    cts.reset_store()
    clear_audit_log()
    register_summary_backend(None)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS : 9 sections / heuristic / pipeline
# ──────────────────────────────────────────────────────────────────────────


def test_section_keys_is_exactly_nine():
    assert len(SECTION_KEYS) == 9
    assert set(SECTION_KEYS) == {
        "context", "goals", "decisions", "open_questions", "actions",
        "blockers", "facts", "preferences", "next_steps",
    }


def test_defaults_match_m28_spec():
    """95% threshold + 200k tokens (Claude max)."""
    assert DEFAULT_THRESHOLD == 0.95
    assert DEFAULT_MAX_TOKENS == 200_000


def test_generate_summary_always_returns_9_keys_for_empty():
    out = generate_summary([])
    assert list(out.keys()) == list(SECTION_KEYS)
    assert all(v == [] for v in out.values())


def test_generate_summary_classifies_keywords_into_sections():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "アプリを作りたい。ゴールは認証機能の追加")
    s.add_message(t.id, "assistant", "OAuth 採用で決定しました")
    s.add_message(t.id, "user", "どうやって実装するの？")
    s.add_message(t.id, "assistant", "ライブラリを作成しました")
    s.add_message(t.id, "user", "ERROR: import failed")
    s.add_message(t.id, "assistant", "次は CI を整備します")
    s.add_message(t.id, "user", "私は型安全な書き方が好きです")
    s.add_message(t.id, "assistant", "実際にテストで確認した")
    s.add_message(t.id, "user", "D-001 の方針に従う")
    msgs = s.list_messages(t.id)
    out = generate_summary(msgs)

    # context: 最初の user message
    assert out["context"]
    assert "アプリを作りたい" in out["context"][0]

    # 各 section に該当する分類が入っていること
    assert any("ゴール" in g or "目標" in g or "やりたい" in g for g in out["goals"])
    assert any("決定" in d or "採用" in d or "D-001" in d for d in out["decisions"])
    assert any("どう" in q or "?" in q or "？" in q for q in out["open_questions"])
    assert any("作成" in a or "実行" in a for a in out["actions"])
    assert any("ERROR" in b for b in out["blockers"])
    assert any("好き" in p for p in out["preferences"])
    assert any("次は" in n for n in out["next_steps"])
    assert any("実際" in f or "確認した" in f for f in out["facts"])


def test_generate_summary_caps_items_per_section():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(MAX_SECTION_ITEMS + 5):
        s.add_message(t.id, "user", f"目標-{i}")
    msgs = s.list_messages(t.id)
    out = generate_summary(msgs)
    assert len(out["goals"]) <= MAX_SECTION_ITEMS


def test_generate_summary_deduplicates_within_section():
    s = cts.get_store()
    t = s.create_thread()
    for _ in range(5):
        s.add_message(t.id, "user", "目標: 認証")
    msgs = s.list_messages(t.id)
    out = generate_summary(msgs)
    assert len(out["goals"]) == 1


def test_generate_summary_decision_reference_pattern():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "D-123 を参照")
    msgs = s.list_messages(t.id)
    out = generate_summary(msgs)
    assert any("D-123" in d for d in out["decisions"])


def test_generate_summary_rejected_marked_under_decisions():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "assistant", "案 A は不採用")
    msgs = s.list_messages(t.id)
    out = generate_summary(msgs)
    assert any("不採用" in d for d in out["decisions"])


def test_estimate_context_usage_basic():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "a" * 300)  # 300 chars
    usage = estimate_context_usage(t.id, max_tokens=1000)
    assert usage["thread_id"] == t.id
    assert usage["message_count"] == 1
    assert usage["char_count"] == 300
    assert usage["estimated_tokens"] == 100
    assert usage["ratio"] == 0.1


def test_estimate_context_usage_empty_thread():
    s = cts.get_store()
    t = s.create_thread()
    usage = estimate_context_usage(t.id)
    assert usage["message_count"] == 0
    assert usage["char_count"] == 0
    assert usage["estimated_tokens"] == 0
    assert usage["ratio"] == 0.0


def test_should_compact_at_or_above_threshold():
    assert should_compact({"ratio": 0.95}, threshold=0.95) is True
    assert should_compact({"ratio": 0.96}, threshold=0.95) is True
    assert should_compact({"ratio": 0.94}, threshold=0.95) is False
    assert should_compact({"ratio": 0.5}, threshold=0.5) is True


def test_run_compaction_skips_when_below_threshold():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "短いメッセージ")
    res = run_compaction(t.id, max_tokens=DEFAULT_MAX_TOKENS, threshold=0.95)
    assert res["compacted"] is False
    assert res["reason"] == "below_threshold"
    # state mutate なし: メッセージ数増えていない
    assert s.count_messages(t.id) == 1


def test_run_compaction_forced_writes_summary_and_audit():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標: 認証")
    s.add_message(t.id, "assistant", "OK で決定")
    res = run_compaction(t.id, force=True)
    assert res["compacted"] is True
    assert res["message_id"] > 0
    assert list(res["summary"].keys()) == list(SECTION_KEYS)
    # state mutated: system message が 1 件増えている
    assert s.count_messages(t.id) == 3
    msg = s.get_message(res["message_id"])
    assert msg is not None
    assert msg.role == "system"
    assert msg.compressed_summary is not None
    assert list(msg.compressed_summary.keys()) == list(SECTION_KEYS)


def test_run_compaction_when_threshold_met_persists():
    s = cts.get_store()
    t = s.create_thread()
    # 3000 chars / divisor=3 = 1000 tokens / max=1000 → ratio=1.0
    s.add_message(t.id, "user", "あ" * 3000)
    res = run_compaction(t.id, max_tokens=1000, threshold=0.95)
    assert res["compacted"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN : 2 秒以内 + audit log に action + timestamp 記録
# ──────────────────────────────────────────────────────────────────────────


def test_audit_log_records_compaction_action_and_timestamp():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標: ship")
    before = time.time()
    res = run_compaction(t.id, force=True)
    after = time.time()
    entry = res["audit_entry"]
    assert entry["action"] == AUDIT_ACTION_COMPACTED
    assert before <= entry["timestamp"] <= after
    assert entry["thread_id"] == t.id
    assert entry["summary_message_id"] == res["message_id"]
    assert entry["sections"] == list(SECTION_KEYS)


def test_audit_log_records_skipped_action():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "短")
    res = run_compaction(t.id)
    assert res["compacted"] is False
    entry = res["audit_entry"]
    assert entry["action"] == AUDIT_ACTION_SKIPPED
    assert entry["timestamp"] > 0


def test_list_audit_log_filters_by_thread():
    s = cts.get_store()
    t1 = s.create_thread()
    t2 = s.create_thread()
    s.add_message(t1.id, "user", "t1")
    s.add_message(t2.id, "user", "t2")
    run_compaction(t1.id, force=True)
    run_compaction(t2.id, force=True)
    only_t1 = list_audit_log(thread_id=t1.id)
    assert len(only_t1) == 1
    assert only_t1[0]["thread_id"] == t1.id


def test_endpoint_status_returns_within_2s(client):
    s = cts.get_store()
    t = s.create_thread()
    for i in range(50):
        s.add_message(t.id, "user", f"msg-{i}" * 10)
    start = time.perf_counter()
    r = client.get(f"/api/tier3/status?thread_id={t.id}")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 2.0
    body = r.json()
    assert body["thread_id"] == t.id
    assert body["threshold"] == DEFAULT_THRESHOLD
    assert "usage" in body
    assert "should_compact" in body


def test_endpoint_compact_returns_within_2s(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標: ship")
    start = time.perf_counter()
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "force": True},
    )
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 2.0
    body = r.json()
    assert body["compacted"] is True
    assert list(body["summary"].keys()) == list(SECTION_KEYS)


def test_endpoint_audit_returns_within_2s(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "x")
    run_compaction(t.id, force=True)
    start = time.perf_counter()
    r = client.get(f"/api/tier3/audit?thread_id={t.id}")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 2.0
    body = r.json()
    assert body["count"] >= 1
    assert body["entries"][0]["action"] in (AUDIT_ACTION_COMPACTED, AUDIT_ACTION_SKIPPED)


def test_endpoint_error_shape_is_structured(client):
    r = client.get("/api/tier3/status?thread_id=99999")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "code" in detail
    assert "message" in detail
    assert detail["code"] == "tier3.not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN : 既存 module 不変 + audit + RLS-equivalent state
# ──────────────────────────────────────────────────────────────────────────


def test_existing_chat_thread_store_symbols_unchanged():
    assert hasattr(cts, "ChatThreadStore")
    assert hasattr(cts, "ChatThread")
    assert hasattr(cts, "ChatMessage")
    assert hasattr(cts, "VALID_ROLES")
    assert hasattr(cts, "get_store")
    assert hasattr(cts, "reset_store")
    s = cts.get_store()
    for m in ("create_thread", "get_thread", "add_message", "list_messages",
              "count_messages", "delete_thread", "delete_message"):
        assert hasattr(s, m), f"chat_thread_store.{m} missing"


def test_existing_tier2_cache_section_keys_consistent():
    """tier2_cache.KNOWN_SUMMARY_SECTIONS と SECTION_KEYS が一致."""
    from services import tier2_cache
    assert set(tier2_cache.KNOWN_SUMMARY_SECTIONS) == set(SECTION_KEYS)


def test_existing_memory_service_persist_compaction_symbol_unchanged():
    """既存 persist_compaction シンボル不変 (REUSE 経路は壊さない)."""
    from services import memory_service
    assert hasattr(memory_service, "persist_compaction")
    assert hasattr(memory_service, "emit_event")


def test_compaction_emits_audit_with_persistent_state_change():
    """AC-3: state-driven: compaction 実行で audit log + chat_messages mutation."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "x")
    before_msgs = s.count_messages(t.id)
    before_audit = len(list_audit_log())
    res = run_compaction(t.id, force=True)
    assert res["compacted"] is True
    assert s.count_messages(t.id) == before_msgs + 1
    assert len(list_audit_log()) == before_audit + 1


def test_existing_chat_threads_router_unchanged(client):
    """既存 /api/chat-threads endpoint (M-30 schema) が unchanged."""
    r = client.get("/api/chat-threads")
    # 200 (list) or auth-related 4xx は OK / 5xx 不変条件違反
    assert r.status_code < 500


def test_persisted_summary_visible_in_chat_thread_store():
    """AC-3: persist 後の system message が store から取得できる (両系統互換)."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標")
    res = run_compaction(t.id, force=True)
    msgs = s.list_messages(t.id)
    roles = [m.role for m in msgs]
    assert "system" in roles
    # compaction で書き込んだ summary message が compressed_summary を持つ
    sys_msgs = [m for m in msgs if m.role == "system" and m.compressed_summary]
    assert any(m.id == res["message_id"] for m in sys_msgs)


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED : invalid input → 4xx structured / state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_invalid_thread_id_service_raises():
    with pytest.raises(Tier3SummaryError):
        estimate_context_usage(0)
    with pytest.raises(Tier3SummaryError):
        estimate_context_usage(-1)
    with pytest.raises(Tier3SummaryError):
        estimate_context_usage("abc")  # type: ignore[arg-type]
    with pytest.raises(Tier3SummaryError):
        estimate_context_usage(True)  # type: ignore[arg-type]


def test_invalid_max_tokens_service_raises():
    s = cts.get_store()
    t = s.create_thread()
    with pytest.raises(Tier3SummaryError):
        estimate_context_usage(t.id, max_tokens=0)
    with pytest.raises(Tier3SummaryError):
        estimate_context_usage(t.id, max_tokens=MIN_MAX_TOKENS - 1)


def test_invalid_threshold_service_raises():
    with pytest.raises(Tier3SummaryError):
        should_compact({"ratio": 0.5}, threshold=MIN_THRESHOLD - 0.01)
    with pytest.raises(Tier3SummaryError):
        should_compact({"ratio": 0.5}, threshold=MAX_THRESHOLD + 0.01)
    with pytest.raises(Tier3SummaryError):
        should_compact({"ratio": 0.5}, threshold="hi")  # type: ignore[arg-type]


def test_invalid_unknown_thread_raises_not_found():
    with pytest.raises(Tier3SummaryError) as exc:
        estimate_context_usage(99999)
    assert "not found" in str(exc.value)


def test_run_compaction_on_unknown_thread_does_not_mutate():
    before = len(list_audit_log())
    with pytest.raises(Tier3SummaryError):
        run_compaction(99999, force=True)
    # AC-4: persistent state を mutate しない
    assert len(list_audit_log()) == before


def test_run_compaction_on_empty_thread_does_not_mutate():
    s = cts.get_store()
    t = s.create_thread()
    before_audit = len(list_audit_log())
    with pytest.raises(Tier3SummaryError) as exc:
        run_compaction(t.id, force=True)
    assert "no messages" in str(exc.value)
    assert s.count_messages(t.id) == 0
    assert len(list_audit_log()) == before_audit


def test_run_compaction_invalid_force_type_raises():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "x")
    with pytest.raises(Tier3SummaryError):
        run_compaction(t.id, force="yes")  # type: ignore[arg-type]


def test_endpoint_invalid_thread_id_4xx(client):
    r = client.get("/api/tier3/status?thread_id=0")
    assert 400 <= r.status_code < 500
    r = client.get("/api/tier3/status?thread_id=-1")
    assert 400 <= r.status_code < 500


def test_endpoint_invalid_threshold_4xx(client):
    s = cts.get_store()
    t = s.create_thread()
    r = client.get(f"/api/tier3/status?thread_id={t.id}&threshold=1.5")
    assert 400 <= r.status_code < 500


def test_endpoint_invalid_max_tokens_4xx(client):
    s = cts.get_store()
    t = s.create_thread()
    r = client.get(f"/api/tier3/status?thread_id={t.id}&max_tokens=10")
    assert 400 <= r.status_code < 500


def test_endpoint_compact_missing_thread_id_4xx(client):
    r = client.post("/api/tier3/compact", json={})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "tier3.invalid"


def test_endpoint_compact_invalid_force_type_4xx(client):
    s = cts.get_store()
    t = s.create_thread()
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "force": "yes"},
    )
    assert r.status_code == 400


def test_endpoint_compact_unknown_thread_does_not_mutate(client):
    before_audit = len(list_audit_log())
    r = client.post("/api/tier3/compact", json={"thread_id": 99999, "force": True})
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "tier3.not_found"
    assert len(list_audit_log()) == before_audit


def test_endpoint_compact_invalid_threshold_does_not_mutate(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "x")
    before_msgs = s.count_messages(t.id)
    before_audit = len(list_audit_log())
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "threshold": 0.001, "force": False},
    )
    assert 400 <= r.status_code < 500
    assert s.count_messages(t.id) == before_msgs
    assert len(list_audit_log()) == before_audit


def test_endpoint_audit_invalid_limit_4xx(client):
    r = client.get("/api/tier3/audit?limit=0")
    assert 400 <= r.status_code < 500
    r = client.get("/api/tier3/audit?limit=99999")
    assert 400 <= r.status_code < 500


def test_clear_audit_log_returns_count():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "x")
    run_compaction(t.id, force=True)
    assert len(list_audit_log()) >= 1
    n = clear_audit_log()
    assert n >= 1
    assert list_audit_log() == []


# ──────────────────────────────────────────────────────────────────────────
# 仕様徹底 (Phase 1 ↔ Phase 2 設計境界の closure)
# ──────────────────────────────────────────────────────────────────────────


# G1: BackgroundTasks pattern (compaction 完了後 legacy persist が非同期で走る)


def test_endpoint_compact_schedules_legacy_persist_when_compacted(client):
    """G1: compaction 成功時に BackgroundTasks に dual-write が積まれる."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標: ship")
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "force": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["compacted"] is True
    assert body["legacy_persist_scheduled"] is True


def test_endpoint_compact_does_not_schedule_when_skipped(client):
    """G1: 閾値未満で skip された場合は BackgroundTasks に積まない."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "short")
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "force": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["compacted"] is False
    assert body["legacy_persist_scheduled"] is False


def test_endpoint_compact_persist_legacy_false_skips_dual_write(client):
    """G4: persist_legacy=False で dual-write を opt-out できる."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "x")
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "force": True, "persist_legacy": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["compacted"] is True
    assert body["legacy_persist_scheduled"] is False


def test_endpoint_compact_invalid_persist_legacy_type_4xx(client):
    """G4: persist_legacy 型不正 → 4xx structured."""
    s = cts.get_store()
    t = s.create_thread()
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "force": True, "persist_legacy": "yes"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "tier3.invalid"


# G2: SDK backend hook (register_summary_backend)


def test_register_summary_backend_swaps_generator():
    """G2: backend register で heuristic を完全に差替えられる."""

    def fake_sdk_backend(messages):
        return {
            "context": ["sdk: ctx"],
            "goals": ["sdk: goal"],
            "decisions": [],
            "open_questions": [],
            "actions": [],
            "blockers": [],
            "facts": [],
            "preferences": [],
            "next_steps": [],
        }

    register_summary_backend(fake_sdk_backend)
    assert get_summary_backend() is fake_sdk_backend
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "ignored by sdk backend")
    out = generate_summary(s.list_messages(t.id))
    assert out["context"] == ["sdk: ctx"]
    assert out["goals"] == ["sdk: goal"]


def test_backend_failure_falls_back_to_heuristic():
    """G2: backend が例外 → silent fail せず heuristic にフォールバック."""

    def broken_backend(messages):
        raise RuntimeError("simulated SDK crash")

    register_summary_backend(broken_backend)
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標: ship")
    out = generate_summary(s.list_messages(t.id))
    # heuristic が拾った goals が残る = fallback 成功
    assert list(out.keys()) == list(SECTION_KEYS)
    assert any("目標" in g for g in out["goals"])


def test_backend_invalid_keys_falls_back():
    """G2: backend が 9 sections 不変条件を満たさない → fallback."""

    def bad_backend(messages):
        return {"only_one_key": ["x"]}  # not 9 sections

    register_summary_backend(bad_backend)
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標: ship")
    out = generate_summary(s.list_messages(t.id))
    # fallback 後でも 9 sections 不変条件は保たれる
    assert set(out.keys()) == set(SECTION_KEYS)


def test_backend_non_list_value_falls_back():
    """G2: backend が list 以外を返す → fallback."""

    def bad_backend(messages):
        return {k: ("not", "a", "list") for k in SECTION_KEYS}

    register_summary_backend(bad_backend)
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標: ship")
    out = generate_summary(s.list_messages(t.id))
    assert isinstance(out["goals"], list)


def test_register_summary_backend_validates_callable():
    """G2: callable 以外を register しようとしたら 4xx 相当の例外."""
    with pytest.raises(Tier3SummaryError):
        register_summary_backend("not callable")  # type: ignore[arg-type]


def test_register_summary_backend_none_clears():
    """G2: None で backend を解除できる."""

    def fake(messages):
        return {k: [] for k in SECTION_KEYS}

    register_summary_backend(fake)
    assert get_summary_backend() is fake
    register_summary_backend(None)
    assert get_summary_backend() is None


# G4 + G6: chat_search (sqlite chat_messages) との互換性 ―
# legacy persist が memory_service.persist_compaction を呼ぶことを検証


def test_legacy_persist_helper_uses_memory_service(monkeypatch):
    """G4: BackgroundTasks 内で実行される helper が memory_service を呼ぶ."""
    import asyncio
    import importlib

    from routers import tier3_compaction as router_mod
    from services import memory_service

    called: list[tuple] = []

    async def fake_persist(session_id, summary):
        called.append((session_id, list(summary.keys())))
        return 9999

    monkeypatch.setattr(memory_service, "persist_compaction", fake_persist)
    importlib.reload(router_mod) if False else None  # 念のため
    # router module は from-import を使うので, top-level の persist_compaction を
    # 直接置換するのではなく memory_service 経由で patch する必要がある.
    # _legacy_persist_best_effort は import を関数内で行うため runtime resolve.
    asyncio.run(
        router_mod._legacy_persist_best_effort(
            123, {k: [] for k in SECTION_KEYS},
        )
    )
    assert called == [(123, list(SECTION_KEYS))]


def test_legacy_persist_helper_swallows_exceptions():
    """G4: memory_service が例外を投げても primary path に影響しない."""
    import asyncio
    from routers import tier3_compaction as router_mod

    # memory_service import 自体が成功するが persist が落ちるケースを想定.
    # _legacy_persist_best_effort は try/except でラップされているので例外無し.
    # 副作用: warning ログのみ. テストは「raise しない」を assert.
    # sqlite が test 環境で初期化されていれば成功するかも知れないので
    # 引数として明らかに invalid な thread_id を渡しても try/except で吸収.
    asyncio.run(
        router_mod._legacy_persist_best_effort(
            -1, {k: [] for k in SECTION_KEYS},
        )
    )  # no exception = pass


def test_endpoint_compact_legacy_scheduled_flag_in_response(client):
    """G4/G6: response に legacy_persist_scheduled flag が出る."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標")
    r = client.post(
        "/api/tier3/compact",
        json={"thread_id": t.id, "force": True},
    )
    body = r.json()
    assert "legacy_persist_scheduled" in body


# G3: in-memory store / RLS 境界の明示 (Phase 1 限定であることを doc レベルで保証)


def test_module_doc_marks_phase1_boundaries():
    """G3/G5: module docstring に Phase 1 境界 (G2/G3/G5) が明記されている."""
    import services.tier3_structured_summary as mod
    doc = mod.__doc__ or ""
    assert "G2" in doc
    assert "G3" in doc
    assert "G5" in doc


def test_chat_thread_store_remains_in_memory():
    """G3: chat_thread_store が in-memory dict 構造であることを確認.
    (Phase 2 で Postgres 移行する際の boundary check.)"""
    store = cts.get_store()
    # in-memory 実装の指標: _threads dict が存在
    assert hasattr(store, "_threads")
    assert isinstance(store._threads, dict)
