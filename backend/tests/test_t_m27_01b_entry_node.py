"""T-M27-01b: Intent Router entry node — 4 AC 全網羅.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : claude-agent-sdk runtime / LangGraph 不使用.
                       (user_message, session_id) → chosen_persona.
  AC-2 EVENT-DRIVEN  : audit emit m27.entry_node.dispatched +
                       chosen_persona / latency_ms / session_id (2秒以内).
  AC-3 STATE-DRIVEN  : audit emit は best-effort / session routing は
                       in-memory store 経由 (RLS は Phase 2 in-memory 境界).
  AC-4 UNWANTED      : LangGraph import → lint で fail (本 module source 確認) /
                       invalid input → IntentRouterEntryError → 4xx /
                       state mutate なし.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import time
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from services import intent_router_entry as ire
from services.intent_router_entry import (
    DEFAULT_PERSONA,
    DISPATCH_AUDIT_EVENT,
    IntentRouterEntryError,
    MAX_ACTOR_USER_ID_LEN,
    MAX_MESSAGE_CHARS,
    MAX_SESSION_ID_LEN,
    PERSONA_BY_SKILL,
    VALID_PERSONA_KEYS,
    dispatch,
    map_intent_to_persona,
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
def _capture_audit(monkeypatch):
    """memory_service.emit_event を mock し audit を集める."""
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
def stub_classifier(monkeypatch):
    """intent_classifier.classify を stub する (固定 intent 返却)."""
    calls: list[dict] = []

    def make(intent_payload: dict):
        async def fake_classify(message, **kwargs):
            calls.append({"message": message, "kwargs": kwargs})
            return intent_payload
        import services.intent_classifier as ic
        monkeypatch.setattr(ic, "classify", fake_classify)
        return calls
    return make


def _intent(skill: Optional[str] = None,
            top_kind: str = "mode",
            top_value: str = "chat",
            explicit_type: Optional[str] = None,
            ) -> dict:
    """intent_classifier.classify 風の dict を生成."""
    explicit = {"type": explicit_type, "content": "..."} if explicit_type else None
    return {
        "message_preview": "hello",
        "explicit_intent": explicit,
        "mode": "chat",
        "skill": skill,
        "top_signal": {
            "kind": top_kind,
            "value": top_value,
            "detail": None,
            "priority_rank": 1,
        },
        "config": {"rules_only": False, "backend_used": False,
                   "had_history": False, "had_primary_skill": False},
        "meta": {"latency_ms": 0.1, "input_chars": 5},
    }


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: LangGraph 不使用 (source 確認)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_no_langgraph_import_in_entry_node_source():
    """本 module source に LangGraph/LangChain import が無い (ADR-010)."""
    src = inspect.getsource(ire)
    for token in ("langgraph", "langchain"):
        for line in src.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert token not in stripped.lower(), (
                    f"intent_router_entry must not import {token} (ADR-010)"
                )


def test_ac1_no_langgraph_import_in_router_source():
    """router 側にも LangGraph/LangChain import 無し."""
    from routers import intent_router as ir
    src = inspect.getsource(ir)
    for token in ("langgraph", "langchain"):
        for line in src.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert token not in stripped.lower()


def test_ac1_valid_persona_keys_contains_bmad_personas():
    """CLAUDE.md §3 の BMAD 10 ペルソナを VALID_PERSONA_KEYS に保持."""
    for p in ("mary", "devon", "quinn", "preston", "winston", "sally",
              "secretary", "reviewer", "brand", "mockup", "logan"):
        assert p in VALID_PERSONA_KEYS, f"missing persona: {p}"


def test_ac1_persona_by_skill_values_are_valid_personas():
    """PERSONA_BY_SKILL の右辺は全て VALID_PERSONA_KEYS のいずれか."""
    for skill, persona in PERSONA_BY_SKILL.items():
        assert persona in VALID_PERSONA_KEYS, (
            f"PERSONA_BY_SKILL[{skill!r}] = {persona!r} not in VALID_PERSONA_KEYS"
        )


def test_ac1_default_persona_is_secretary():
    assert DEFAULT_PERSONA == "secretary"
    assert DEFAULT_PERSONA in VALID_PERSONA_KEYS


# ══════════════════════════════════════════════════════════════════════
# map_intent_to_persona (純粋関数 / unit testable)
# ══════════════════════════════════════════════════════════════════════


def test_map_explicit_remember_to_secretary():
    intent = _intent(explicit_type="remember")
    assert map_intent_to_persona(intent) == "secretary"


@pytest.mark.parametrize("skill,expected", [
    ("hearing", "mary"),
    ("ba", "mary"),
    ("requirements", "preston"),
    ("pm", "preston"),
    ("architecture", "winston"),
    ("design", "winston"),
    ("dev", "devon"),
    ("implementation", "devon"),
    ("qa", "quinn"),
    ("test", "quinn"),
    ("review", "reviewer"),
    ("brand", "brand"),
    ("mockup", "mockup"),
    ("curator", "logan"),
])
def test_map_skill_direct_lookup(skill, expected):
    intent = _intent(skill=skill)
    assert map_intent_to_persona(intent) == expected


def test_map_skill_case_insensitive():
    """skill は case insensitive で lookup."""
    intent = _intent(skill="HEARING")
    assert map_intent_to_persona(intent) == "mary"


def test_map_top_signal_skill_when_skill_field_none():
    """skill=None でも top_signal.kind == 'skill' なら lookup される."""
    intent = _intent(skill=None, top_kind="skill", top_value="qa")
    assert map_intent_to_persona(intent) == "quinn"


def test_map_unknown_skill_to_default():
    intent = _intent(skill="some_unknown_skill_xyz")
    assert map_intent_to_persona(intent) == DEFAULT_PERSONA


def test_map_mode_only_to_default():
    intent = _intent(skill=None, top_kind="mode", top_value="chat")
    assert map_intent_to_persona(intent) == DEFAULT_PERSONA


def test_map_non_dict_to_default():
    for bad in (None, [], "string", 42):
        assert map_intent_to_persona(bad) == DEFAULT_PERSONA


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: validation
# ══════════════════════════════════════════════════════════════════════


def test_validate_message_rejects_empty_blank():
    for bad in ("", "   ", None, 1, [], {}):
        with pytest.raises(IntentRouterEntryError):
            ire._validate_message(bad)


def test_validate_message_rejects_too_long():
    with pytest.raises(IntentRouterEntryError):
        ire._validate_message("x" * (MAX_MESSAGE_CHARS + 1))


def test_validate_session_id_rejects_bad():
    for bad in ("", "  ", None, 1, []):
        with pytest.raises(IntentRouterEntryError):
            ire._validate_session_id(bad)


def test_validate_session_id_rejects_too_long():
    with pytest.raises(IntentRouterEntryError):
        ire._validate_session_id("s" * (MAX_SESSION_ID_LEN + 1))


def test_validate_actor_user_id_accepts_none():
    assert ire._validate_actor_user_id(None) is None


def test_validate_actor_user_id_rejects_blank():
    with pytest.raises(IntentRouterEntryError):
        ire._validate_actor_user_id("   ")


def test_validate_actor_user_id_rejects_too_long():
    with pytest.raises(IntentRouterEntryError):
        ire._validate_actor_user_id("x" * (MAX_ACTOR_USER_ID_LEN + 1))


def test_validate_actor_user_id_rejects_non_string():
    with pytest.raises(IntentRouterEntryError):
        ire._validate_actor_user_id(123)


# ══════════════════════════════════════════════════════════════════════
# dispatch: 成功経路 (AC-1 / AC-2)
# ══════════════════════════════════════════════════════════════════════


def test_dispatch_returns_chosen_persona(stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="hearing"))
    result = asyncio.run(dispatch("こんにちは", "sess-1"))
    assert result["session_id"] == "sess-1"
    assert result["chosen_persona"] == "mary"
    assert result["chosen_persona"] in VALID_PERSONA_KEYS
    assert isinstance(result["latency_ms"], float)
    assert "intent" in result


def test_dispatch_passes_actor_to_classifier(stub_classifier, _capture_audit):
    calls = stub_classifier(_intent(skill="dev"))
    asyncio.run(dispatch("実装して", "sess-x", actor_user_id="alice"))
    assert len(calls) == 1
    assert calls[0]["kwargs"]["actor_user_id"] == "alice"


def test_dispatch_passes_history_to_classifier(stub_classifier, _capture_audit):
    calls = stub_classifier(_intent(skill="test"))
    history = [{"role": "user", "content": "previous"}]
    asyncio.run(dispatch("テスト", "s-1", history=history))
    assert calls[0]["kwargs"]["history"] == history


def test_dispatch_rules_only_propagates(stub_classifier, _capture_audit):
    calls = stub_classifier(_intent(skill="qa"))
    asyncio.run(dispatch("qa", "s-1", rules_only=True))
    assert calls[0]["kwargs"]["rules_only"] is True


def test_dispatch_unknown_skill_returns_default(stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="unknown_xyz"))
    result = asyncio.run(dispatch("hi", "s-1"))
    assert result["chosen_persona"] == DEFAULT_PERSONA


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: audit emit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_audit_emits_dispatch_event(stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="dev"))
    result = asyncio.run(dispatch("実装", "sess-A", actor_user_id="alice"))
    events = [e for e in _capture_audit
              if e["event_type"] == DISPATCH_AUDIT_EVENT]
    assert len(events) == 1
    ev = events[0]
    detail = ev["detail"]
    assert detail["session_id"] == "sess-A"
    assert detail["chosen_persona"] == "devon"
    assert "latency_ms" in detail
    assert isinstance(detail["latency_ms"], float)
    assert detail["actor_user_id"] == "alice"
    # audit_event_id が返り値に含まれる
    assert result["audit_event_id"] is not None


def test_ac2_dispatch_within_2sec(stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="hearing"))
    t0 = time.time()
    asyncio.run(dispatch("hi", "s-1"))
    assert (time.time() - t0) < 2.0


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN + AC-4 UNWANTED: validation 失敗で audit emit なし
# ══════════════════════════════════════════════════════════════════════


def test_ac3_invalid_message_does_not_emit_audit(stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="hearing"))
    with pytest.raises(IntentRouterEntryError):
        asyncio.run(dispatch("   ", "s-1"))
    assert all(e["event_type"] != DISPATCH_AUDIT_EVENT for e in _capture_audit)


def test_ac3_invalid_session_does_not_emit_audit(stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="hearing"))
    with pytest.raises(IntentRouterEntryError):
        asyncio.run(dispatch("ok", ""))
    assert all(e["event_type"] != DISPATCH_AUDIT_EVENT for e in _capture_audit)


def test_ac3_blank_actor_does_not_emit_audit(stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="hearing"))
    with pytest.raises(IntentRouterEntryError):
        asyncio.run(dispatch("ok", "s-1", actor_user_id="   "))
    assert all(e["event_type"] != DISPATCH_AUDIT_EVENT for e in _capture_audit)


def test_ac4_classifier_error_propagates_as_entry_error(_capture_audit, monkeypatch):
    """T-M27-02 (intent_classifier) の入力 4xx を T-M27-01b の 4xx に変換."""
    import services.intent_classifier as ic

    async def fake_classify(*a, **kw):
        raise ic.IntentClassifierError("bad input from classifier")

    monkeypatch.setattr(ic, "classify", fake_classify)
    with pytest.raises(IntentRouterEntryError, match="intent classification"):
        asyncio.run(dispatch("ok", "s-1"))


# ══════════════════════════════════════════════════════════════════════
# Endpoint smoke (4xx + 200)
# ══════════════════════════════════════════════════════════════════════


def test_endpoint_dispatch_success(client, stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="qa"))
    r = client.post("/api/intent-router/dispatch", json={
        "user_message": "テスト書いて", "session_id": "s-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["chosen_persona"] == "quinn"
    assert body["session_id"] == "s-1"


def test_endpoint_dispatch_within_2sec(client, stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="dev"))
    t0 = time.time()
    r = client.post("/api/intent-router/dispatch", json={
        "user_message": "実装", "session_id": "s-1",
    })
    assert r.status_code == 200
    assert (time.time() - t0) < 2.0


def test_endpoint_dispatch_invalid_400(client, _capture_audit):
    """pydantic 又は service で 400/422 (min_length=1 で blank reject)."""
    r = client.post("/api/intent-router/dispatch", json={
        "user_message": "", "session_id": "s-1",
    })
    assert r.status_code in (400, 422)


def test_endpoint_dispatch_unauthorized_401(client, stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="dev"))
    r = client.post("/api/intent-router/dispatch", json={
        "user_message": "hi", "session_id": "s-1", "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "intent_router.unauthorized"


def test_endpoint_dispatch_audit_has_full_detail(client, stub_classifier, _capture_audit):
    stub_classifier(_intent(skill="hearing"))
    r = client.post("/api/intent-router/dispatch", json={
        "user_message": "ヒアリング", "session_id": "s-end",
        "actor_user_id": "alice",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit
              if e["event_type"] == DISPATCH_AUDIT_EVENT]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert detail["session_id"] == "s-end"
    assert detail["chosen_persona"] == "mary"
    assert "latency_ms" in detail


def test_endpoint_personas_list(client):
    r = client.get("/api/intent-router/personas")
    assert r.status_code == 200
    body = r.json()
    assert body["default_persona"] == DEFAULT_PERSONA
    assert "mary" in body["valid_personas"]
    assert body["persona_by_skill"]["hearing"] == "mary"
