"""T-010b-05: sessions table 状態遷移管理 — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010b で sessions transition endpoint + 状態機械 service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + 状態遷移ルール強制
  AC-4 UNWANTED      : invalid input / 不正 transition / not_found は 4xx +
                       structured / persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from integrations.claude_agent_runner import (
    ClaudeAgentRunner,
    InMemorySessionStore,
    SessionRecord,
)
from services.session_state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    SessionNotFoundError,
    SessionStateMachineError,
    TERMINAL_STATES,
    TransitionResult,
    VALID_STATES,
    is_valid_transition,
    transition_session,
)


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
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _fake_runner(monkeypatch):
    """agent_runner の runner を fake (InMemorySessionStore) に差し替え."""
    import routers.agent_runner as ar
    runner = ClaudeAgentRunner(store=InMemorySessionStore())
    monkeypatch.setattr(ar, "_runner", runner)
    yield {"runner": runner, "store": runner.store}
    monkeypatch.setattr(ar, "_runner", None)


def _seed_session(store, *, status: str = "running") -> int:
    rec = SessionRecord(prompt="test", status=status)
    rec_with_id = asyncio.run(store.create_session(rec))
    return rec_with_id.id


# ──────────────────────────────────────────────────────────────────────────
# Service 単体 (状態機械)
# ──────────────────────────────────────────────────────────────────────────


def test_service_valid_states_are_5():
    assert set(VALID_STATES) == {"running", "done", "crashed", "cancelled", "paused"}


def test_service_terminal_states():
    assert TERMINAL_STATES == frozenset({"done", "cancelled"})


@pytest.mark.parametrize("frm,to,expected", [
    ("running", "done", True),
    ("running", "crashed", True),
    ("running", "cancelled", True),
    ("running", "paused", True),
    ("paused", "running", True),
    ("paused", "cancelled", True),
    ("crashed", "running", True),
    ("crashed", "cancelled", True),
    # invalid
    ("done", "running", False),
    ("done", "crashed", False),
    ("cancelled", "running", False),
    ("running", "running", False),  # 同状態
    ("paused", "done", False),       # paused → done は明示的に運用しない
    ("paused", "crashed", False),
    ("crashed", "done", False),
    ("running", "unknown", False),   # invalid state
])
def test_service_is_valid_transition(frm, to, expected):
    assert is_valid_transition(frm, to) == expected


def test_service_transition_running_to_done():
    state: dict = {"status": "running"}

    async def load(sid):
        return state if sid == 1 else None

    async def update(sid, new, reason):
        state["status"] = new
        state["reason"] = reason

    result = asyncio.run(transition_session(
        1, "done", load_fn=load, update_fn=update,
    ))
    assert isinstance(result, TransitionResult)
    assert result.from_status == "running"
    assert result.to_status == "done"
    assert state["status"] == "done"


def test_service_transition_invalid_raises():
    async def load(sid):
        return {"status": "done"}

    async def update(sid, new, reason):
        pass

    with pytest.raises(InvalidTransitionError):
        asyncio.run(transition_session(
            1, "running", load_fn=load, update_fn=update,
        ))


def test_service_transition_session_not_found():
    async def load(sid):
        return None

    async def update(sid, new, reason):
        pass

    with pytest.raises(SessionNotFoundError):
        asyncio.run(transition_session(
            999, "done", load_fn=load, update_fn=update,
        ))


def test_service_invalid_session_id():
    async def load(sid):
        return {"status": "running"}

    async def update(sid, new, reason):
        pass

    with pytest.raises(SessionStateMachineError):
        asyncio.run(transition_session(
            0, "done", load_fn=load, update_fn=update,
        ))


def test_service_invalid_to_status():
    async def load(sid):
        return {"status": "running"}

    async def update(sid, new, reason):
        pass

    with pytest.raises(InvalidTransitionError):
        asyncio.run(transition_session(
            1, "bogus", load_fn=load, update_fn=update,
        ))


def test_service_reason_too_long_rejected():
    async def load(sid):
        return {"status": "running"}

    async def update(sid, new, reason):
        pass

    with pytest.raises(SessionStateMachineError):
        asyncio.run(transition_session(
            1, "crashed", reason="x" * 2001,
            load_fn=load, update_fn=update,
        ))


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_transition_endpoint_exists(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"])
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "done"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == sid
    assert body["from_status"] == "running"
    assert body["to_status"] == "done"


def test_ac1_running_to_paused(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"])
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "paused"},
    )
    assert r.status_code == 200
    assert r.json()["to_status"] == "paused"


def test_ac1_crashed_to_running_with_reason(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"], status="crashed")
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "running", "reason": "resume after fix"},
    )
    assert r.status_code == 200
    assert r.json()["to_status"] == "running"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"])
    t0 = time.perf_counter()
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "done"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/agent/sessions/0/transition",
                     json={"to_status": "done"})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "agent.invalid_session_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + state 反映
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_emits_audit(client, _fake_runner, _capture_audit):
    sid = _seed_session(_fake_runner["store"])
    client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "done", "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "agent.session.transitioned"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["from_status"] == "running"
    assert events[0]["detail"]["to_status"] == "done"


def test_ac3_status_actually_updates_in_store(client, _fake_runner):
    """AC-3: 遷移後 GET /api/agent/sessions/{id} で新 status を観測."""
    sid = _seed_session(_fake_runner["store"])
    client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "paused"},
    )
    r = client.get(f"/api/agent/sessions/{sid}")
    assert r.json()["session"]["status"] == "paused"


def test_ac3_crashed_records_reason(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"])
    client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "crashed", "reason": "OOM error"},
    )
    rec = _fake_runner["store"]._sessions[sid]
    assert rec.status == "crashed"
    assert rec.crash_reason == "OOM error"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_session_id(client):
    r = client.post("/api/agent/sessions/0/transition",
                     json={"to_status": "done"})
    assert r.status_code == 400


def test_ac4_session_not_found(client):
    r = client.post("/api/agent/sessions/99999/transition",
                     json={"to_status": "done"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "agent.session_not_found"


def test_ac4_invalid_to_status(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"])
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "bogus"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.invalid_to_status"


def test_ac4_invalid_transition_returns_409(client, _fake_runner):
    """terminal state (done) からの transition は 409."""
    sid = _seed_session(_fake_runner["store"], status="done")
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "running"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "agent.invalid_transition"
    # state mutate なし
    assert _fake_runner["store"]._sessions[sid].status == "done"


def test_ac4_same_state_transition_rejected(client, _fake_runner):
    """同状態への遷移 (running → running) は 409."""
    sid = _seed_session(_fake_runner["store"])
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "running"},
    )
    assert r.status_code == 409


def test_ac4_empty_actor_rejected(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"])
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "done", "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "agent.unauthorized"


def test_ac4_long_reason_rejected(client, _fake_runner):
    sid = _seed_session(_fake_runner["store"])
    r = client.post(
        f"/api/agent/sessions/{sid}/transition",
        json={"to_status": "crashed", "reason": "x" * 2001},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.reason_too_large"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_runner):
    """AC-4 UNWANTED: 失敗時に audit emit / store mutate なし."""
    sid = _seed_session(_fake_runner["store"], status="done")
    client.post(f"/api/agent/sessions/{sid}/transition",
                 json={"to_status": "running"})
    client.post("/api/agent/sessions/99999/transition",
                 json={"to_status": "done"})
    events = [e for e in _capture_audit if e["event_type"] == "agent.session.transitioned"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _fake_runner):
    sid_done = _seed_session(_fake_runner["store"], status="done")
    sid_running = _seed_session(_fake_runner["store"])
    cases = [
        ("POST", "/api/agent/sessions/0/transition", {"to_status": "done"}),
        ("POST", "/api/agent/sessions/99999/transition", {"to_status": "done"}),
        ("POST", f"/api/agent/sessions/{sid_running}/transition",
         {"to_status": "bogus"}),
        ("POST", f"/api/agent/sessions/{sid_done}/transition",
         {"to_status": "running"}),
        ("POST", f"/api/agent/sessions/{sid_running}/transition",
         {"to_status": "done", "actor_user_id": "  "}),
        ("POST", f"/api/agent/sessions/{sid_running}/transition",
         {"to_status": "crashed", "reason": "x" * 2001}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
