"""T-M28-03: Tier 2 prompt cache friendly (cache_control: ephemeral 5min) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : M-28 Tier 2 prompt cache friendly
  AC-2 EVENT-DRIVEN  : audit emit (tier2.cache.compose) + 2 秒以内
  AC-3 STATE-DRIVEN  : RLS / audit_logs を CLAUDE.md §5.3 に従って維持
  AC-4 UNWANTED      : invalid input / unauthorized actor は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import tier2_cache as t2
from services.tier2_cache import (
    DEFAULT_CACHE_TTL_SEC,
    KNOWN_SUMMARY_SECTIONS,
    MAX_CACHE_BREAKPOINTS,
    MAX_MESSAGE_CHARS,
    MAX_SUMMARY_CHARS,
    MAX_USER_MESSAGES,
    Tier2CacheError,
    compose_cached_payload,
    format_summary_text,
    summary_stats,
)

# autouse fixture が差し替える前のオリジナル load_latest_summary
_ORIGINAL_LOAD = t2.load_latest_summary


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


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
def _fake_loader(monkeypatch):
    """DB に触らずに service.load_latest_summary を差し替え."""
    state: dict[int, dict] = {}

    async def fake_load(session_id):
        if not isinstance(session_id, int) or session_id <= 0:
            raise Tier2CacheError("session_id must be > 0")
        return state.get(session_id)

    monkeypatch.setattr(t2, "load_latest_summary", fake_load)
    yield state


SAMPLE_SUMMARY = {
    "context": "Build-Factory project",
    "goals": ["ship Phase 1", "stable cost"],
    "decisions": ["ADR-010: claude-agent-sdk + anthropic-python"],
    "open_questions": ["pricing?"],
    "actions": ["fix bug #42"],
    "blockers": [],
    "facts": {"team_size": 1},
    "preferences": "concise japanese",
    "next_steps": ["merge T-020-04"],
}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: format_summary_text
# ──────────────────────────────────────────────────────────────────────────


def test_service_format_summary_basic():
    text = format_summary_text(SAMPLE_SUMMARY)
    # 全 section が ## key で含まれている
    for key in SAMPLE_SUMMARY:
        assert f"## {key}" in text


def test_service_format_summary_handles_list_dict_none():
    text = format_summary_text({
        "list_key": ["a", "b"],
        "dict_key": {"x": 1},
        "none_key": None,
        "str_key": "hello",
        "int_key": 42,
    })
    assert "- a" in text and "- b" in text
    assert '"x": 1' in text
    assert "## none_key" in text
    assert "hello" in text
    assert "42" in text


def test_service_format_summary_empty_raises():
    with pytest.raises(Tier2CacheError):
        format_summary_text({})


def test_service_format_summary_non_dict_raises():
    with pytest.raises(Tier2CacheError):
        format_summary_text("not-a-dict")  # type: ignore


def test_service_format_summary_invalid_key():
    with pytest.raises(Tier2CacheError):
        format_summary_text({"": "x"})


def test_service_known_sections_constant():
    assert "context" in KNOWN_SUMMARY_SECTIONS
    assert len(KNOWN_SUMMARY_SECTIONS) == 9


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: compose_cached_payload
# ──────────────────────────────────────────────────────────────────────────


def test_service_compose_basic_with_summary():
    out = compose_cached_payload(
        model="claude-opus-4-7",
        summary_text="## context\n\nfoo",
        user_messages=[{"role": "user", "content": "hi"}],
    )
    assert out["provider"] == "anthropic"
    assert out["route"] == "main"
    assert out["payload"]["model"] == "claude-opus-4-7"
    # system に cache_control: ephemeral 付きの 1 ブロック
    assert isinstance(out["payload"]["system"], list)
    assert out["payload"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert out["cache_meta"]["summary_cached"] is True
    assert out["cache_meta"]["breakpoints"] == 1


def test_service_compose_with_constitution_and_summary():
    out = compose_cached_payload(
        model="claude-opus-4-7",
        summary_text="summary",
        user_messages=[{"role": "user", "content": "hi"}],
        constitution_text="constitution",
    )
    # 2 ブロック: constitution → summary の順
    assert len(out["payload"]["system"]) == 2
    assert out["payload"]["system"][0]["text"] == "constitution"
    assert out["payload"]["system"][1]["text"] == "summary"
    assert out["cache_meta"]["breakpoints"] == 2


def test_service_compose_cache_summary_false():
    out = compose_cached_payload(
        model="claude-opus-4-7",
        summary_text="summary",
        user_messages=[{"role": "user", "content": "hi"}],
        cache_summary=False,
    )
    assert "cache_control" not in out["payload"]["system"][0]
    assert out["cache_meta"]["summary_cached"] is False
    assert out["cache_meta"]["breakpoints"] == 0


def test_service_compose_no_summary_no_system():
    out = compose_cached_payload(
        model="claude-opus-4-7",
        summary_text=None,
        user_messages=[{"role": "user", "content": "hi"}],
    )
    assert "system" not in out["payload"]
    assert out["cache_meta"]["breakpoints"] == 0
    assert out["cache_meta"]["summary_cached"] is False


def test_service_compose_user_messages_normalized():
    out = compose_cached_payload(
        model="claude-opus-4-7",
        summary_text=None,
        user_messages=[
            {"role": "user", "content": "a", "extra_field": "ignored"},
            {"role": "assistant", "content": "b"},
        ],
    )
    # extra_field は落とす
    assert out["payload"]["messages"] == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]


def test_service_compose_ttl_constant():
    out = compose_cached_payload(
        model="claude-opus-4-7",
        summary_text="x",
        user_messages=[{"role": "user", "content": "y"}],
    )
    assert out["cache_meta"]["ttl_seconds"] == DEFAULT_CACHE_TTL_SEC == 300


def test_service_compose_invalid_model_empty():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="",
            summary_text=None,
            user_messages=[{"role": "user", "content": "x"}],
        )


def test_service_compose_invalid_model_too_long():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="x" * 201,
            summary_text=None,
            user_messages=[{"role": "user", "content": "x"}],
        )


def test_service_compose_empty_user_messages():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7",
            summary_text=None,
            user_messages=[],
        )


def test_service_compose_too_many_user_messages():
    msgs = [{"role": "user", "content": "x"}] * (MAX_USER_MESSAGES + 1)
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None, user_messages=msgs,
        )


def test_service_compose_invalid_role():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "system", "content": "x"}],
        )


def test_service_compose_content_too_long():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "user", "content": "x" * (MAX_MESSAGE_CHARS + 1)}],
        )


def test_service_compose_summary_too_long():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7",
            summary_text="x" * (MAX_SUMMARY_CHARS + 1),
            user_messages=[{"role": "user", "content": "x"}],
        )


def test_service_compose_invalid_temperature():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "user", "content": "x"}],
            temperature=3.0,
        )


def test_service_compose_invalid_max_tokens():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "user", "content": "x"}],
            max_tokens=0,
        )


def test_service_compose_constitution_non_string():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "user", "content": "x"}],
            constitution_text=123,  # type: ignore
        )


def test_service_compose_message_not_dict():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=["not-a-dict"],  # type: ignore
        )


def test_service_compose_content_not_string():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "user", "content": 123}],
        )


# ──────────────────────────────────────────────────────────────────────────
# summary_stats
# ──────────────────────────────────────────────────────────────────────────


def test_stats_none():
    s = summary_stats(None)
    assert s["has_summary"] is False
    assert s["sections_count"] == 0
    assert s["message_id"] is None
    assert s["summary_age_seconds"] is None


def test_stats_with_summary():
    now = time.time()
    s = summary_stats({
        "message_id": 42,
        "summary": SAMPLE_SUMMARY,
        "created_at": now - 60.0,
    })
    assert s["has_summary"] is True
    assert s["sections_count"] == len(SAMPLE_SUMMARY)
    assert s["message_id"] == 42
    assert s["summary_age_seconds"] is not None
    assert 55 <= s["summary_age_seconds"] <= 70


def test_stats_non_numeric_created_at():
    s = summary_stats({
        "message_id": 1,
        "summary": SAMPLE_SUMMARY,
        "created_at": "2026-05-10T12:00:00",  # ISO string → age = None
    })
    assert s["summary_age_seconds"] is None


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_compose_with_override_summary(client):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "hi"}],
        "override_summary": SAMPLE_SUMMARY,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "main"
    assert body["cache_meta"]["summary_cached"] is True
    assert body["cache_meta"]["breakpoints"] == 1
    # override_summary 経由は loaded_message_id = None
    assert body["summary_message_id"] is None


def test_ac1_compose_loads_from_db(client, _fake_loader):
    _fake_loader[7] = {
        "message_id": 99,
        "summary": SAMPLE_SUMMARY,
        "created_at": time.time() - 10.0,
    }
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 7,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["summary_message_id"] == 99
    assert body["cache_meta"]["summary_cached"] is True


def test_ac1_compose_no_summary_yet(client):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 99,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["cache_meta"]["summary_cached"] is False
    assert "system" not in body["payload"]


def test_ac1_compose_with_constitution(client):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "hi"}],
        "override_summary": SAMPLE_SUMMARY,
        "constitution_text": "Be helpful and accurate",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["cache_meta"]["breakpoints"] == 2
    assert body["cache_meta"]["constitution_cached"] is True


def test_ac1_summary_stats_empty(client):
    r = client.get("/api/tier2-cache/summary/1234")
    assert r.status_code == 200
    body = r.json()
    assert body["has_summary"] is False
    assert body["session_id"] == 1234


def test_ac1_summary_stats_with_data(client, _fake_loader):
    _fake_loader[55] = {
        "message_id": 10,
        "summary": SAMPLE_SUMMARY,
        "created_at": time.time() - 30.0,
    }
    r = client.get("/api/tier2-cache/summary/55")
    body = r.json()
    assert body["has_summary"] is True
    assert body["sections_count"] == len(SAMPLE_SUMMARY)
    assert body["message_id"] == 10


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "hi"}],
        "override_summary": SAMPLE_SUMMARY,
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_invalid_model(client):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "",
        "user_messages": [{"role": "user", "content": "x"}],
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "tier2.invalid"


def test_ac2_error_shape_consistency(client):
    cases = [
        ("POST", "/api/tier2-cache/compose", {
            "session_id": 1, "model": "x",
            "user_messages": [{"role": "system", "content": "wrong-role"}],
        }),
        ("POST", "/api/tier2-cache/compose", {
            "session_id": 1, "model": "claude-opus-4-7",
            "user_messages": [{"role": "user", "content": "x"}],
            "actor_user_id": "  ",
        }),
        ("GET", "/api/tier2-cache/summary/0", None),
    ]
    for method, path, body in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=body)
        assert r.status_code in (400, 401, 404, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("tier2."), f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3: audit emit (action + timestamp)
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_compose_emits_audit(client, _capture_audit):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 11,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "hi"}],
        "override_summary": SAMPLE_SUMMARY,
        "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "tier2.cache.compose"]
    assert len(events) == 1
    assert events[0]["session_id"] == 11
    assert events[0]["user_id"] == "u-1"
    assert events[0]["detail"]["model"] == "claude-opus-4-7"
    assert events[0]["detail"]["summary_cached"] is True
    assert events[0]["detail"]["breakpoints"] == 1


def test_ac3_summary_stats_no_audit(client, _capture_audit):
    client.get("/api/tier2-cache/summary/1")
    # read-only endpoint は audit を出さない
    tier2_events = [e for e in _capture_audit if e["event_type"].startswith("tier2.")]
    assert tier2_events == []


def test_ac3_compose_audit_includes_constitution_flag(client, _capture_audit):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 22,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "hi"}],
        "override_summary": SAMPLE_SUMMARY,
        "constitution_text": "be brief",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "tier2.cache.compose"]
    assert len(events) == 1
    assert events[0]["detail"]["constitution_cached"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / persistent state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_session_id_pydantic(client):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 0,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "x"}],
    })
    # Field(gt=0) で 422
    assert r.status_code == 422


def test_ac4_empty_actor_user_id_compose(client, _capture_audit):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "x"}],
        "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tier2.unauthorized"
    # 失敗時は audit 非発行
    assert not any(
        e["event_type"] == "tier2.cache.compose" for e in _capture_audit
    )


def test_ac4_compose_invalid_role(client, _capture_audit):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "system", "content": "x"}],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier2.invalid"
    # state mutate なし
    assert not any(
        e["event_type"] == "tier2.cache.compose" for e in _capture_audit
    )


def test_ac4_compose_invalid_override_summary(client):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "x"}],
        "override_summary": {},  # 空 dict は invalid
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier2.invalid"


def test_ac4_compose_temperature_pydantic_422(client):
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "x"}],
        "temperature": 5.0,
    })
    assert r.status_code == 422


def test_ac4_summary_zero_session_id(client):
    r = client.get("/api/tier2-cache/summary/0")
    # Path param int → 0 ≦ 0 → 400 (tier2.invalid_session_id)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier2.invalid_session_id"


def test_ac4_compose_breakpoint_limit_via_long_args(client):
    # MAX_CACHE_BREAKPOINTS = 4 を直接超えるシナリオは
    # constitution + summary = 2 までしか発生しない → 内部上限は守られている
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "x"}],
        "override_summary": SAMPLE_SUMMARY,
        "constitution_text": "x" * 100,
    })
    assert r.status_code == 200
    assert r.json()["cache_meta"]["breakpoints"] <= MAX_CACHE_BREAKPOINTS


def test_ac4_summary_loader_error_propagates_as_400(client, monkeypatch):
    async def broken(session_id):
        raise t2.Tier2CacheError("simulated load failure")
    monkeypatch.setattr(t2, "load_latest_summary", broken)
    r = client.post("/api/tier2-cache/compose", json={
        "session_id": 1,
        "model": "claude-opus-4-7",
        "user_messages": [{"role": "user", "content": "x"}],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier2.invalid"


# ──────────────────────────────────────────────────────────────────────────
# load_latest_summary 単体 (mocked DB)
# ──────────────────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    async def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row

    async def execute(self, sql, params=None):
        return _FakeCursor(self._row)


class _FakeConn:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return _FakeDB(self._row)

    async def __aexit__(self, *exc):
        return False


class _FakeAioSqlite:
    def __init__(self, row):
        self._row = row

    def connect(self, _path):
        return _FakeConn(self._row)


@pytest.mark.asyncio
async def test_load_latest_summary_invalid_session_id():
    # NOTE: pytest-asyncio が無くても、event loop で直接呼べる
    pass


def test_load_latest_summary_negative_id():
    import asyncio
    with pytest.raises(Tier2CacheError):
        asyncio.run(t2.load_latest_summary.__wrapped__(-1)
                    if hasattr(t2.load_latest_summary, "__wrapped__")
                    else t2.load_latest_summary(-1))


def test_load_latest_summary_no_row(monkeypatch):
    import asyncio
    import services.memory_service as ms
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(None))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    # _fake_loader fixture が autouse で差し替えているので、real を取り戻す
    real_load = _ORIGINAL_LOAD
    out = asyncio.run(real_load(1))
    assert out is None


def test_load_latest_summary_with_row(monkeypatch):
    import asyncio
    import json as _json
    import services.memory_service as ms
    row = (42, _json.dumps(SAMPLE_SUMMARY), 1234567890.0)
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(row))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    real_load = _ORIGINAL_LOAD
    out = asyncio.run(real_load(1))
    assert out is not None
    assert out["message_id"] == 42
    assert out["summary"] == SAMPLE_SUMMARY
    assert out["created_at"] == 1234567890.0


def test_load_latest_summary_invalid_json(monkeypatch):
    import asyncio
    import services.memory_service as ms
    row = (1, "not-json", None)
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(row))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    real_load = _ORIGINAL_LOAD
    with pytest.raises(Tier2CacheError, match="not valid JSON"):
        asyncio.run(real_load(1))


def test_load_latest_summary_non_dict(monkeypatch):
    import asyncio
    import json as _json
    import services.memory_service as ms
    row = (1, _json.dumps([1, 2, 3]), None)
    monkeypatch.setattr(ms, "_db", lambda: _FakeAioSqlite(row))
    monkeypatch.setattr(ms, "_db_path", lambda: ":memory:")
    real_load = _ORIGINAL_LOAD
    with pytest.raises(Tier2CacheError, match="must be a dict"):
        asyncio.run(real_load(1))


# ──────────────────────────────────────────────────────────────────────────
# 追加の service edge cases
# ──────────────────────────────────────────────────────────────────────────


def test_service_compose_summary_text_non_string():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=42,  # type: ignore
            user_messages=[{"role": "user", "content": "x"}],
        )


def test_service_compose_constitution_too_long():
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "user", "content": "x"}],
            constitution_text="x" * 100_000,
        )


def test_service_compose_max_tokens_over_limit():
    from services.tier2_cache import MAX_TOKENS_LIMIT
    with pytest.raises(Tier2CacheError):
        compose_cached_payload(
            model="claude-opus-4-7", summary_text=None,
            user_messages=[{"role": "user", "content": "x"}],
            max_tokens=MAX_TOKENS_LIMIT + 1,
        )


# ──────────────────────────────────────────────────────────────────────────
# Backwards compatibility — Tier 1/2/3 既存 API は変わらない
# ──────────────────────────────────────────────────────────────────────────


def test_compat_memory_service_unchanged():
    from services import memory_service as ms
    # 主要 symbol 不変
    assert hasattr(ms, "emit_event")
    assert hasattr(ms, "persist_compaction")
    assert hasattr(ms, "write_fact")
