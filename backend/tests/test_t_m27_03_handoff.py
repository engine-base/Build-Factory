"""T-M27-03: Agent / Role Selector + handoff (SDK Task tool wrapper + ai_employees lookup).

AC マッピング (1:1 テスト):
  AC-1 UBIQUITOUS    : SDK Task tool wrapper + ai_employees lookup (REUSE).
                       自前 handoff/orchestration ロジックは実装しない.
  AC-2 EVENT-DRIVEN  : handoff invoke 時に m27.handoff audit emit / 全 endpoint
                       2 秒以内 + structured response.
  AC-3 STATE-DRIVEN  : 既存 ai_employee_store 不変 / read endpoint で audit emit
                       しない / session_id pass-through.
  AC-4 UNWANTED      : invalid persona / unauthorized / unknown target →
                       4xx structured. state mutate なし.

Spec gap closure (G22-G25):
  G22 register_handoff_backend (SDK Task tool 差替点)
  G23 Phase 1 stub mode (backend 未登録時は scheduled status + audit のみ)
  G24 ai_employee_store symbol surface 不変 + lookup 必須
  G25 audit emit 必須 (失敗時 raise, silent failure 防止)
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import handoff_service as hs
from services.handoff_service import (
    HandoffError,
    MAX_ACTOR_USER_ID_LEN,
    MAX_CONTEXT_CHARS,
    MAX_MESSAGE_CHARS,
    MAX_PERSONA_KEY_LEN,
    MAX_SESSION_ID_LEN,
    VALID_STATUSES,
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
def _reset_backend():
    hs.register_handoff_backend(None)
    yield
    hs.register_handoff_backend(None)


@pytest.fixture(autouse=True)
def _seed_personas_and_employees():
    """各テスト前に ai_employee_store を reset + 必須 persona/employee を seed."""
    from services.ai_employee_store import reset_store, get_store
    reset_store()
    store = get_store()
    # source = mary (BA) / target = devon (Dev) / quinn (QA)
    mary = store.create_persona("mary", "Mary (BA)", specialty="business-analyst")
    devon = store.create_persona("devon", "Devon (Dev)", specialty="developer")
    quinn = store.create_persona("quinn", "Quinn (QA)", specialty="qa")
    store.create_employee("emp_mary", "Mary", persona_id=mary.id, role_level="member")
    store.create_employee("emp_devon", "Devon", persona_id=devon.id, role_level="member")
    store.create_employee("emp_quinn", "Quinn", persona_id=quinn.id, role_level="member")
    yield
    reset_store()


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


# ══════════════════════════════════════════════════════════════════════
# Constants & invariants
# ══════════════════════════════════════════════════════════════════════


def test_constants_sane():
    assert VALID_STATUSES == ("scheduled", "dispatched", "failed")
    assert MAX_MESSAGE_CHARS > 0
    assert MAX_PERSONA_KEY_LEN > 0
    assert MAX_CONTEXT_CHARS > 0


# ══════════════════════════════════════════════════════════════════════
# Validation (AC-4)
# ══════════════════════════════════════════════════════════════════════


def test_validate_persona_key_rejects_empty():
    for bad in ("", "   ", None, 123, "x" * (MAX_PERSONA_KEY_LEN + 1)):
        with pytest.raises(HandoffError):
            hs._validate_persona_key(bad, field_name="persona_key")
    assert hs._validate_persona_key("mary", field_name="x") == "mary"


def test_validate_persona_key_rejects_invalid_chars():
    for bad in ("mary devon", "mary/devon", "mary.devon", "mary!"):
        with pytest.raises(HandoffError):
            hs._validate_persona_key(bad, field_name="x")


def test_validate_message_rejects_empty_and_oversized():
    for bad in ("", "  ", None, 123, "x" * (MAX_MESSAGE_CHARS + 1)):
        with pytest.raises(HandoffError):
            hs._validate_message(bad)
    assert hs._validate_message("  hello  ") == "hello"


def test_validate_context_none_returns_empty():
    assert hs._validate_context(None) == {}


def test_validate_context_rejects_non_dict():
    for bad in ("not dict", [], 123):
        with pytest.raises(HandoffError):
            hs._validate_context(bad)


def test_validate_context_rejects_non_json_serializable():
    class X:
        pass
    with pytest.raises(HandoffError):
        hs._validate_context({"x": X()})


def test_validate_context_rejects_oversized():
    big = {"x": "a" * (MAX_CONTEXT_CHARS + 1)}
    with pytest.raises(HandoffError):
        hs._validate_context(big)


def test_validate_session_id():
    assert hs._validate_session_id(None) is None
    assert hs._validate_session_id(" s1 ") == "s1"
    for bad in ("", "  ", 1, "x" * (MAX_SESSION_ID_LEN + 1)):
        with pytest.raises(HandoffError):
            hs._validate_session_id(bad)


def test_validate_actor_user_id():
    assert hs._validate_actor_user_id(None) is None
    assert hs._validate_actor_user_id(" alice ") == "alice"
    for bad in ("", "   ", 1, "x" * (MAX_ACTOR_USER_ID_LEN + 1)):
        with pytest.raises(HandoffError):
            hs._validate_actor_user_id(bad)


# ══════════════════════════════════════════════════════════════════════
# G22: backend hook
# ══════════════════════════════════════════════════════════════════════


def test_g22_register_backend_callable_only():
    with pytest.raises(HandoffError):
        hs.register_handoff_backend("not callable")
    with pytest.raises(HandoffError):
        hs.register_handoff_backend(123)
    hs.register_handoff_backend(lambda **kw: {"status": "dispatched"})
    assert hs.get_handoff_backend() is not None
    hs.register_handoff_backend(None)
    assert hs.get_handoff_backend() is None


def test_g22_backend_used_when_registered():
    sentinel = {"status": "dispatched", "task_id": "sdk-task-123"}
    hs.register_handoff_backend(lambda **kw: sentinel)
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="please implement",
    ))
    assert out["status"] == "dispatched"
    assert out["config"]["backend_used"] is True
    assert out["backend_result"] == sentinel


def test_g22_async_backend_also_works():
    async def async_backend(**kw):
        return {"status": "dispatched", "via": "async"}
    hs.register_handoff_backend(async_backend)
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement",
    ))
    assert out["status"] == "dispatched"
    assert out["backend_result"]["via"] == "async"


# ══════════════════════════════════════════════════════════════════════
# G23: Phase 1 stub mode (backend 未登録 / 例外 / 不正出力 で fallback)
# ══════════════════════════════════════════════════════════════════════


def test_g23_no_backend_returns_scheduled():
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement",
    ))
    assert out["status"] == "scheduled"
    assert out["config"]["backend_used"] is False
    assert out["backend_result"] is None


def test_g23_backend_exception_falls_back():
    def boom(**kw):
        raise RuntimeError("SDK down")
    hs.register_handoff_backend(boom)
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement",
    ))
    assert out["status"] == "scheduled"
    assert out["config"]["backend_used"] is False


def test_g23_backend_invalid_output_falls_back():
    cases = [
        (lambda **kw: "not a dict"),
        (lambda **kw: {}),  # missing status
        (lambda **kw: {"status": "bogus"}),  # invalid status
        (lambda **kw: {"status": 123}),  # non-string status
    ]
    for bad in cases:
        hs.register_handoff_backend(bad)
        out = asyncio.run(hs.request_handoff(
            source_persona="mary", target_persona="devon",
            message="implement",
        ))
        assert out["status"] == "scheduled", f"backend {bad} should fall back"
        assert out["config"]["backend_used"] is False


def test_g23_use_backend_false_skips_backend():
    hs.register_handoff_backend(lambda **kw: {"status": "dispatched"})
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement",
        use_backend=False,
    ))
    assert out["status"] == "scheduled"
    assert out["config"]["backend_used"] is False


# ══════════════════════════════════════════════════════════════════════
# G24: ai_employee_store symbol surface + lookup 必須
# ══════════════════════════════════════════════════════════════════════


def test_g24_ai_employee_store_symbols_unchanged():
    from services import ai_employee_store as aes
    for sym in ("get_store", "reset_store", "AIEmployeeError",
                "AIEmployeeStore", "Persona", "AIEmployee"):
        assert hasattr(aes, sym), f"ai_employee_store.{sym} missing"
    store = aes.get_store()
    for method in ("create_persona", "get_persona", "get_persona_by_key",
                   "list_personas", "create_employee", "list_employees"):
        assert hasattr(store, method), f"store.{method} missing"


def test_g24_unknown_target_persona_raises():
    with pytest.raises(HandoffError):
        asyncio.run(hs.request_handoff(
            source_persona="mary", target_persona="nonexistent",
            message="x",
        ))


def test_g24_target_persona_resolved_includes_full_dict():
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement",
    ))
    resolved = out["target_persona_resolved"]
    assert resolved is not None
    assert resolved["persona_key"] == "devon"
    assert resolved["specialty"] == "developer"
    assert "id" in resolved


def test_g24_list_handoff_targets_returns_active_employees():
    items = hs.list_handoff_targets()
    keys = sorted(item["persona_key"] for item in items)
    assert keys == ["devon", "mary", "quinn"]
    for item in items:
        assert "employee_id" in item
        assert "display_name" in item
        assert "role_level" in item


# ══════════════════════════════════════════════════════════════════════
# G25: audit emit 必須
# ══════════════════════════════════════════════════════════════════════


def test_g25_handoff_emits_audit(_capture_audit):
    asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement", actor_user_id="alice", session_id="s1",
    ))
    events = [e for e in _capture_audit if e["event_type"] == "m27.handoff"]
    assert len(events) == 1
    e = events[0]
    assert e["user_id"] == "alice"
    assert e["session_id"] == "s1"
    d = e["detail"]
    assert d["source_persona"] == "mary"
    assert d["target_persona"] == "devon"
    assert d["status"] == "scheduled"  # Phase 1 stub
    assert "target_persona_id" in d
    assert "latency_ms" in d
    assert "message_chars" in d


def test_g25_audit_emit_failure_raises(monkeypatch):
    async def broken_emit(*args, **kwargs):
        raise RuntimeError("audit_logs unavailable")
    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", broken_emit)
    with pytest.raises(RuntimeError):
        asyncio.run(hs.request_handoff(
            source_persona="mary", target_persona="devon",
            message="x",
        ))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: REUSE handoff (SDK wrapper) + lookup
# ══════════════════════════════════════════════════════════════════════


def test_ac1_request_handoff_basic_shape():
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement feature X",
    ))
    for key in ("status", "source_persona", "target_persona",
                "target_persona_resolved", "session_id", "message_preview",
                "config", "meta", "backend_result"):
        assert key in out, f"missing key: {key}"
    assert out["status"] in VALID_STATUSES


def test_ac1_message_preview_truncates():
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="x" * 200,
    ))
    assert len(out["message_preview"]) == 80


def test_ac1_endpoint_handoff(client):
    r = client.post("/api/handoff", json={
        "source_persona": "mary",
        "target_persona": "devon",
        "message": "please implement feature X",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "scheduled"
    assert body["source_persona"] == "mary"
    assert body["target_persona"] == "devon"


def test_ac1_endpoint_targets(client):
    r = client.get("/api/handoff/targets")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert len(body["items"]) == 3


def test_ac1_endpoint_health(client):
    r = client.get("/api/handoff/health")
    assert r.status_code == 200
    body = r.json()
    assert "backend_registered" in body
    assert body["phase"] == "stub"
    assert body["ai_employee_store"]["available"] is True
    assert body["ai_employee_store"]["persona_count"] == 3
    assert body["ai_employee_store"]["employee_count"] == 3


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 2 秒以内 + audit emit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_handoff_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "devon",
        "message": "x",
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_targets_within_2sec(client):
    t0 = time.time()
    r = client.get("/api/handoff/targets")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_health_within_2sec(client):
    t0 = time.time()
    r = client.get("/api/handoff/health")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_endpoint_emits_audit(client, _capture_audit):
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "devon",
        "message": "implement", "actor_user_id": "bob",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "m27.handoff"]
    assert len(events) == 1
    assert events[0]["user_id"] == "bob"


def test_ac2_error_shape_consistency(client):
    """Error 系は {detail:{code,message}} + prefix=handoff."""
    cases = [
        # unauthorized actor
        ({"source_persona": "mary", "target_persona": "devon",
          "message": "x", "actor_user_id": "  "}, 401, "handoff.unauthorized"),
        # unknown target → service raises → 404
        ({"source_persona": "mary", "target_persona": "nonexistent",
          "message": "x"}, 404, "handoff.not_found"),
        # source == target
        ({"source_persona": "mary", "target_persona": "mary",
          "message": "x"}, 400, "handoff.invalid"),
    ]
    for body, expected_status, expected_code in cases:
        r = client.post("/api/handoff", json=body)
        assert r.status_code == expected_status, f"{body}: {r.status_code}"
        detail = r.json()["detail"]
        assert detail["code"] == expected_code, f"{body}: {detail['code']}"
        assert "message" in detail


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read endpoint で audit emit しない / 既存 module 不変
# ══════════════════════════════════════════════════════════════════════


def test_ac3_targets_no_audit(client, _capture_audit):
    client.get("/api/handoff/targets")
    assert not [e for e in _capture_audit if e["event_type"].startswith("m27.")]


def test_ac3_health_no_audit(client, _capture_audit):
    client.get("/api/handoff/health")
    assert not [e for e in _capture_audit if e["event_type"].startswith("m27.")]


def test_ac3_session_id_pass_through():
    out = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="x", session_id="sess-abc",
    ))
    assert out["session_id"] == "sess-abc"
    assert out["config"]["had_session"] is True


def test_ac3_existing_routers_present(client):
    paths = [getattr(r, "path", "") for r in client.app.routes]
    assert "/health" in paths
    assert any(p.startswith("/api/ai/employees") or p.startswith("/api/employees") for p in paths)
    assert "/api/handoff" in paths
    assert "/api/handoff/targets" in paths


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_missing_required_fields_pydantic_422(client):
    for body in (
        {},
        {"source_persona": "mary"},  # missing target + message
        {"source_persona": "mary", "target_persona": "devon"},  # missing msg
    ):
        r = client.post("/api/handoff", json=body)
        assert r.status_code == 422, f"{body}: {r.status_code}"


def test_ac4_oversized_message_pydantic_422(client):
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "devon",
        "message": "x" * (MAX_MESSAGE_CHARS + 1),
    })
    assert r.status_code == 422


def test_ac4_invalid_persona_key_returns_400(client):
    r = client.post("/api/handoff", json={
        "source_persona": "mary devon",
        "target_persona": "devon",
        "message": "x",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "handoff.invalid"


def test_ac4_unauthorized_actor_401(client):
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "devon",
        "message": "x", "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "handoff.unauthorized"


def test_ac4_unknown_target_404(client):
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "nonexistent",
        "message": "x",
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "handoff.not_found"


def test_ac4_source_eq_target_400(client):
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "mary",
        "message": "x",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "handoff.invalid"


def test_ac4_invalid_workspace_id_400(client):
    r = client.get("/api/handoff/targets?workspace_id=0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "handoff.invalid"


def test_ac4_unauthorized_no_audit_emitted(client, _capture_audit):
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "devon",
        "message": "x", "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert not [e for e in _capture_audit if e["event_type"] == "m27.handoff"]


def test_ac4_unknown_target_no_audit_emitted(client, _capture_audit):
    r = client.post("/api/handoff", json={
        "source_persona": "mary", "target_persona": "nonexistent",
        "message": "x",
    })
    assert r.status_code == 404
    assert not [e for e in _capture_audit if e["event_type"] == "m27.handoff"]


def test_ac4_invalid_context_400():
    with pytest.raises(HandoffError):
        asyncio.run(hs.request_handoff(
            source_persona="mary", target_persona="devon",
            message="x", context="not dict",
        ))


# ══════════════════════════════════════════════════════════════════════
# ADR-010: LangGraph 不使用 (lint-no-langgraph + ソース検査の二重ガード)
# ══════════════════════════════════════════════════════════════════════


def _strip_comments_and_docstrings(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


def test_no_langgraph_import_in_service():
    import inspect
    src = _strip_comments_and_docstrings(inspect.getsource(hs))
    assert "langgraph" not in src.lower()
    assert "langchain" not in src.lower()


def test_no_langgraph_import_in_router():
    from routers import handoff as router_mod
    import inspect
    src = _strip_comments_and_docstrings(inspect.getsource(router_mod))
    assert "langgraph" not in src.lower()
    assert "langchain" not in src.lower()


def test_no_self_routing_keywords_in_service():
    """ADR-010 §UNWANTED: 自前 routing/orchestration を実装していないことを
    キーワードで verify (message bus / dispatcher / orchestrator)."""
    import inspect
    src = _strip_comments_and_docstrings(inspect.getsource(hs))
    # 「自前で routing を実装する」コード片の不在
    assert "messagebus" not in src.lower()
    assert "message_bus" not in src.lower()
    # dispatch という名前の独自 dispatcher 実装はないが backend hook 用語 OK
    # (validate された backend を呼ぶだけ)


# ══════════════════════════════════════════════════════════════════════
# Module docstring (G22-G25 + 設計境界 明示)
# ══════════════════════════════════════════════════════════════════════


def test_module_docstring_documents_g22_g25():
    doc = hs.__doc__ or ""
    for tag in ("G22", "G23", "G24", "G25"):
        assert tag in doc, f"module docstring must mention {tag}"


def test_module_docstring_documents_adr_010_and_sdk():
    doc = hs.__doc__ or ""
    assert "ADR-010" in doc
    assert "claude-agent-sdk" in doc
    assert "Task tool" in doc


def test_module_docstring_documents_reuse_constraint():
    doc = hs.__doc__ or ""
    assert "REUSE" in doc
    # 自前禁止文言
    assert ("self-implement" in doc.lower()
            or "self implement" in doc.lower()
            or "再実装" in doc
            or "自前" in doc), "docstring must state no self-implementation"


# ══════════════════════════════════════════════════════════════════════
# Spec gap closure G26-G28 (T-M27-03 AC との残 gap)
# ══════════════════════════════════════════════════════════════════════


# ── G26 AC-2 audit detail に timestamp ────────────────────────────────


def test_g26_ac2_audit_detail_includes_timestamp(_capture_audit):
    """AC-2 EVENT-DRIVEN: tickets.json は audit detail に timestamp を要求."""
    t0 = time.time()
    asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement", session_id="s1", actor_user_id="alice",
    ))
    t1 = time.time()
    events = [e for e in _capture_audit if e["event_type"] == "m27.handoff"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert "timestamp" in detail, "AC-2: audit detail must include timestamp"
    assert isinstance(detail["timestamp"], (int, float))
    # handoff 実行時刻の範囲内
    assert t0 <= detail["timestamp"] <= t1 + 0.5


def test_g26_audit_detail_full_required_fields(_capture_audit):
    """AC-2 で要求される source_persona / target_persona / session_id /
    timestamp の 4 attrs が全部 audit detail に含まれる."""
    asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="implement", session_id="sess-X", actor_user_id="alice",
    ))
    events = [e for e in _capture_audit if e["event_type"] == "m27.handoff"]
    d = events[0]["detail"]
    for required in ("source_persona", "target_persona", "session_id", "timestamp"):
        assert required in d, f"AC-2 detail missing {required!r}"
    assert d["source_persona"] == "mary"
    assert d["target_persona"] == "devon"
    assert d["session_id"] == "sess-X"


# ── G27 AC-3 SDK session resume (session_token) ───────────────────────


def test_g27_ac3_session_token_returned(_capture_audit):
    """AC-3 STATE-DRIVEN: SDK session resume token を request_handoff 戻り値
    に含める. backend 未登録時は session_id を session_token として流用."""
    result = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="impl", session_id="sdk-sess-1",
    ))
    assert "session_token" in result, "AC-3: return must include session_token"
    assert result["session_token"] == "sdk-sess-1"


def test_g27_ac3_session_token_in_audit_detail(_capture_audit):
    """audit detail にも session_token を含めて SDK session resume が
    観測可能であることを保証する."""
    asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon",
        message="impl", session_id="sdk-sess-2",
    ))
    events = [e for e in _capture_audit if e["event_type"] == "m27.handoff"]
    detail = events[0]["detail"]
    assert detail.get("session_token") == "sdk-sess-2"


def test_g27_ac3_no_session_id_yields_null_token(_capture_audit):
    """session_id が無ければ session_token も None (RLS 境界の明示)."""
    result = asyncio.run(hs.request_handoff(
        source_persona="mary", target_persona="devon", message="impl",
    ))
    assert result["session_token"] is None


def test_g27_ac3_backend_provided_token_takes_precedence(_capture_audit):
    """backend が session_token を返した場合は backend の値を優先する
    (SDK 側で session resume token が更新されるケース)."""
    def backend(**kwargs):
        return {
            "status": "dispatched",
            "session_token": "sdk-renewed-token-xyz",
        }
    hs.register_handoff_backend(backend)
    try:
        result = asyncio.run(hs.request_handoff(
            source_persona="mary", target_persona="devon",
            message="impl", session_id="old-sess",
        ))
        assert result["session_token"] == "sdk-renewed-token-xyz"
        events = [e for e in _capture_audit
                  if e["event_type"] == "m27.handoff"]
        assert events[0]["detail"]["session_token"] == "sdk-renewed-token-xyz"
    finally:
        hs.register_handoff_backend(None)


def test_g27_ac3_backend_token_blank_falls_back_to_session_id(_capture_audit):
    """backend が session_token に空文字を返した場合は session_id に fallback."""
    hs.register_handoff_backend(lambda **kw: {
        "status": "dispatched", "session_token": "   ",
    })
    try:
        result = asyncio.run(hs.request_handoff(
            source_persona="mary", target_persona="devon",
            message="impl", session_id="fallback-sess",
        ))
        assert result["session_token"] == "fallback-sess"
    finally:
        hs.register_handoff_backend(None)


# ── G28 AC-4 lint script: handoff 自前実装の禁止語検知 ────────────────


def _repo_root():
    """test 実行時の cwd に関わらず repo root を解決する."""
    from pathlib import Path
    p = Path(__file__).resolve()
    # backend/tests/test_*.py → backend/tests → backend → repo root
    return p.parents[2]


def test_g28_ac4_lint_script_has_no_self_handoff_check():
    """scripts/lint-mock.sh に check_no_self_handoff が定義されている
    (T-M27-03 AC-4 の機械検知)."""
    text = (_repo_root() / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_no_self_handoff()" in text, (
        "lint-mock.sh must define check_no_self_handoff (T-M27-03 AC-4)"
    )
    assert "--no-self-handoff" in text, (
        "lint-mock.sh must expose --no-self-handoff CLI mode"
    )


def test_g28_ac4_handoff_service_has_no_forbidden_tokens():
    """handoff_service.py の source に自前実装の禁止語が含まれない."""
    src_path = _repo_root() / "backend" / "services" / "handoff_service.py"
    src = src_path.read_text(encoding="utf-8")
    forbidden = [
        "manual_route_to_persona", "custom_subagent_dispatch",
        "self_handoff_dispatch", "handoff_loop", "role_router_loop",
        "impl_handoff_locally", "run_subagent_internally",
    ]
    for token in forbidden:
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert token not in line, (
                f"handoff_service must not define/use {token!r} "
                "(T-M27-03 AC-4 / ADR-010)"
            )


def test_g28_ac4_lint_check_pass_when_handoff_service_clean():
    """check_no_self_handoff を CLI 単独実行で起動し PASS することを確認."""
    import subprocess
    root = _repo_root()
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-self-handoff"],
        capture_output=True, text=True, timeout=30, cwd=str(root),
    )
    assert r.returncode == 0, (
        f"lint --no-self-handoff failed: stdout={r.stdout[:500]} "
        f"stderr={r.stderr[:500]}"
    )
    assert "OK" in r.stdout
