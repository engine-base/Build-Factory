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
    list_audit_log,
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
    yield
    cts.reset_store()
    clear_audit_log()


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


def test_existing_short_term_layer_router_endpoints_compat(client):
    """既存 /api/short-term endpoint が unchanged (200 を返す)."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "u")
    r = client.get(f"/api/short-term/stats?thread_id={t.id}")
    assert r.status_code == 200


def test_existing_short_term_window_still_sees_summary_message(client):
    """AC-3: persist 後の system message も短期 window に出現する (両系統互換)."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "目標")
    run_compaction(t.id, force=True)
    r = client.get(f"/api/short-term/window?thread_id={t.id}&limit=10")
    assert r.status_code == 200
    body = r.json()
    roles = [m["role"] for m in body["messages"]]
    assert "system" in roles


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
