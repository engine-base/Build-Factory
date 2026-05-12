"""T-M28-04: Tier 3 9-section structured summary persistence — 4 AC 全網羅.

AC マッピング (1:1 テスト):
  AC-1 UBIQUITOUS    : SDK 生成 9-section summary を chat_messages.compressed_
                       summary へ persist; application code は summary 自前生成
                       しない (check-section-keys-uniqueness.py で機械検知).
                       SECTION_KEYS は mid_term_layer から re-export (重複定義
                       禁止 / G10 cross-module invariant).
  AC-2 EVENT-DRIVEN  : run_compaction 呼出時に 2 秒以内応答 + memory_compacted
                       audit event (summary_message_id + section_keys 付き).
  AC-3 STATE-DRIVEN  : validation 失敗時は append-only 経路 A も書き込まない
                       (state mutate なし). 成功時は chat_thread_store の
                       既存 messages を保持 (append-only).
  AC-4 UNWANTED      : 不正 schema (9 sections 欠落 / dict でない / section 値
                       が list でない) → Tier3PersistError → 4xx
                       {detail:{code,message}}. application code が summary
                       生成すれば lint script が fail (T-M30-03 で追加済).
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import chat_thread_store as cts
from services import tier3_structured_summary as t3
from services.mid_term_layer import SECTION_KEYS
from services.tier3_structured_summary import (
    COMPACTION_AUDIT_EVENT,
    Tier3PersistError,
    run_compaction,
    validate_9_section_summary,
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
    yield
    cts.reset_store()


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    """memory_service.emit_event を mock し audit 出力を集める."""
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
        return 5000 + len(persisted)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "persist_compaction", fake_persist_compaction)
    return persisted


def _make_thread() -> int:
    return cts.get_store().create_thread(title="T-M28-04 test").id


def _full_summary(prefix: str = "v") -> dict[str, list[str]]:
    """全 9 section に bullet を 1 件ずつ持つ valid summary."""
    return {k: [f"{prefix}-{k}-1"] for k in SECTION_KEYS}


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: SECTION_KEYS は mid_term_layer の re-export (G10)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_section_keys_is_re_export_from_mid_term_layer():
    """tier3 SECTION_KEYS は mid_term_layer.SECTION_KEYS と同一参照
    (リスト literal の重複定義禁止)."""
    from services.mid_term_layer import SECTION_KEYS as mtl_keys
    # tuple identity (re-export なので同一オブジェクト)
    assert t3.SECTION_KEYS is mtl_keys
    assert len(t3.SECTION_KEYS) == 9


def test_ac1_module_does_not_define_its_own_section_literal():
    """tier3 module source に 9-section literal の重複定義が無い
    (check-section-keys-uniqueness.py の対象外 = import only)."""
    import ast
    import inspect
    src = inspect.getsource(t3)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            strs = {e.value for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            assert not set(SECTION_KEYS).issubset(strs), (
                "tier3 must not redefine the 9-section keys; "
                "import from mid_term_layer instead"
            )


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: validate_9_section_summary 純粋関数
# ══════════════════════════════════════════════════════════════════════


def test_validate_accepts_full_9_section_summary():
    s = _full_summary("x")
    out = validate_9_section_summary(s)
    assert set(out.keys()) == set(SECTION_KEYS)
    assert all(isinstance(v, list) for v in out.values())


def test_validate_returns_normalized_with_none_as_empty_list():
    s = {k: None for k in SECTION_KEYS}
    out = validate_9_section_summary(s)
    assert all(v == [] for v in out.values())


def test_validate_coerces_non_str_items_to_str():
    s = {k: [1, 2.5, "ok"] for k in SECTION_KEYS}
    out = validate_9_section_summary(s)
    assert out["context"] == ["1", "2.5", "ok"]


def test_validate_filters_none_items():
    s = {k: ["a", None, "b"] for k in SECTION_KEYS}
    out = validate_9_section_summary(s)
    assert out["context"] == ["a", "b"]


def test_validate_ignores_extra_keys():
    s = _full_summary("x")
    s["__extra_future__"] = ["should be ignored"]
    out = validate_9_section_summary(s)
    assert "__extra_future__" not in out
    assert set(out.keys()) == set(SECTION_KEYS)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid schema は Tier3PersistError
# ══════════════════════════════════════════════════════════════════════


def test_validate_rejects_non_dict():
    for bad in (None, [], "string", 42, True):
        with pytest.raises(Tier3PersistError):
            validate_9_section_summary(bad)


def test_validate_rejects_missing_sections():
    incomplete = {k: [] for k in SECTION_KEYS[:5]}  # 5 sections only
    with pytest.raises(Tier3PersistError, match="missing sections"):
        validate_9_section_summary(incomplete)


def test_validate_rejects_non_list_section_value():
    s = _full_summary("x")
    s["context"] = "single string not list"
    with pytest.raises(Tier3PersistError, match="must be a list"):
        validate_9_section_summary(s)


def test_validate_thread_id_rejects_bad_types():
    for bad in (0, -1, "1", 1.5, True, False, None):
        with pytest.raises(Tier3PersistError):
            t3._validate_thread_id(bad)


def test_validate_actor_user_id_rejects_blank():
    with pytest.raises(Tier3PersistError):
        t3._validate_actor_user_id("   ")


def test_validate_actor_user_id_rejects_too_long():
    with pytest.raises(Tier3PersistError):
        t3._validate_actor_user_id("x" * (t3.MAX_ACTOR_USER_ID_LEN + 1))


def test_validate_actor_user_id_accepts_none():
    assert t3._validate_actor_user_id(None) is None


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: validation 失敗時に state mutate しない
# ══════════════════════════════════════════════════════════════════════


def test_ac3_invalid_summary_does_not_mutate_chat_thread_store(_capture_audit):
    tid = _make_thread()
    msgs_before = cts.get_store().list_messages(tid)
    with pytest.raises(Tier3PersistError):
        asyncio.run(run_compaction(tid, {"context": []}))  # missing sections
    msgs_after = cts.get_store().list_messages(tid)
    assert msgs_before == msgs_after
    # audit も emit されない (validation 失敗は emit 前)
    assert all(e["event_type"] != COMPACTION_AUDIT_EVENT for e in _capture_audit)


def test_ac3_unknown_thread_does_not_mutate(_capture_audit):
    with pytest.raises(Tier3PersistError, match="not found"):
        asyncio.run(run_compaction(99999, _full_summary("x")))
    assert all(e["event_type"] != COMPACTION_AUDIT_EVENT for e in _capture_audit)


def test_ac3_invalid_actor_does_not_mutate(_capture_audit):
    tid = _make_thread()
    with pytest.raises(Tier3PersistError):
        asyncio.run(run_compaction(
            tid, _full_summary("x"), actor_user_id="  ",
        ))
    assert cts.get_store().list_messages(tid) == []
    assert all(e["event_type"] != COMPACTION_AUDIT_EVENT for e in _capture_audit)


def test_ac3_persist_appends_only(_capture_audit, stub_legacy_persist):
    """成功時は既存 messages を保持し append のみ (destructive mutation なし)."""
    tid = _make_thread()
    # 既存メッセージ
    store = cts.get_store()
    pre1 = store.add_message(tid, "user", "hello")
    pre2 = store.add_message(tid, "assistant", "hi there")
    pre_ids = {pre1.id, pre2.id}

    asyncio.run(run_compaction(tid, _full_summary("x")))

    after = store.list_messages(tid)
    after_ids = {m.id for m in after}
    # 既存 id は全部残る + 新規 1 件追加 (system role)
    assert pre_ids.issubset(after_ids)
    assert len(after) == 3
    assert after[-1].role == "system"
    assert after[-1].compressed_summary is not None


# ══════════════════════════════════════════════════════════════════════
# AC-1 / AC-2: 成功経路の return / audit
# ══════════════════════════════════════════════════════════════════════


def test_ac1_run_compaction_success_returns_message_id(
    _capture_audit, stub_legacy_persist,
):
    tid = _make_thread()
    s = _full_summary("ok")
    result = asyncio.run(run_compaction(tid, s))
    assert result["thread_id"] == tid
    assert isinstance(result["summary_message_id"], int)
    assert result["section_keys"] == list(SECTION_KEYS)
    # legacy 経路 B も成功
    assert result["legacy_result"]["status"] == "ok"


def test_ac1_compressed_summary_field_holds_normalized(
    _capture_audit, stub_legacy_persist,
):
    tid = _make_thread()
    s = _full_summary("ok")
    result = asyncio.run(run_compaction(tid, s))
    msg_id = result["summary_message_id"]
    persisted = cts.get_store().get_message(msg_id)
    assert persisted is not None
    assert set(persisted.compressed_summary.keys()) == set(SECTION_KEYS)


def test_ac2_audit_event_emitted_with_section_keys(
    _capture_audit, stub_legacy_persist,
):
    tid = _make_thread()
    result = asyncio.run(run_compaction(tid, _full_summary("v"), actor_user_id="u-1"))
    compact_events = [e for e in _capture_audit
                      if e["event_type"] == COMPACTION_AUDIT_EVENT]
    assert len(compact_events) == 1
    ev = compact_events[0]
    assert ev["session_id"] == tid
    assert ev["user_id"] == "u-1"
    assert ev["detail"]["summary_message_id"] == result["summary_message_id"]
    assert ev["detail"]["section_keys"] == list(SECTION_KEYS)


def test_ac2_run_compaction_within_2sec(_capture_audit, stub_legacy_persist):
    tid = _make_thread()
    t0 = time.time()
    asyncio.run(run_compaction(tid, _full_summary("v")))
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_persist_legacy_false_skips_path_b(_capture_audit, stub_legacy_persist):
    tid = _make_thread()
    result = asyncio.run(run_compaction(
        tid, _full_summary("v"), persist_legacy=False,
    ))
    assert result["legacy_result"] is None
    # 経路 A は実行されている
    assert isinstance(result["summary_message_id"], int)


# ══════════════════════════════════════════════════════════════════════
# Endpoint smoke (AC-1/AC-2/AC-4)
# ══════════════════════════════════════════════════════════════════════


def test_endpoint_persist_success(client, _capture_audit, stub_legacy_persist):
    tid = _make_thread()
    r = client.post("/api/tier3/persist", json={
        "thread_id": tid,
        "summary": _full_summary("ok"),
    })
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"] == tid
    assert body["section_keys"] == list(SECTION_KEYS)


def test_endpoint_persist_within_2sec(client, _capture_audit, stub_legacy_persist):
    tid = _make_thread()
    t0 = time.time()
    r = client.post("/api/tier3/persist", json={
        "thread_id": tid,
        "summary": _full_summary("v"),
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_endpoint_persist_invalid_schema_400(client, _capture_audit):
    tid = _make_thread()
    r = client.post("/api/tier3/persist", json={
        "thread_id": tid,
        "summary": {"context": []},  # missing 8 sections
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "tier3.invalid"
    assert "missing sections" in detail["message"]


def test_endpoint_persist_unknown_thread_404(client, _capture_audit):
    r = client.post("/api/tier3/persist", json={
        "thread_id": 99999,
        "summary": _full_summary("v"),
    })
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "tier3.not_found"


def test_endpoint_persist_blank_actor_401(client, _capture_audit):
    tid = _make_thread()
    r = client.post("/api/tier3/persist", json={
        "thread_id": tid,
        "summary": _full_summary("v"),
        "actor_user_id": "   ",
    })
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["code"] == "tier3.unauthorized"


def test_endpoint_persist_thread_id_zero_rejected(client):
    """pydantic validation (thread_id > 0) でも事前に弾かれることを確認."""
    r = client.post("/api/tier3/persist", json={
        "thread_id": 0,
        "summary": _full_summary("v"),
    })
    # 422 (pydantic) or 400 (service) のいずれかで弾かれる
    assert r.status_code in (400, 422)
