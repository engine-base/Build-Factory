"""T-010d-01: FastAPI WebSocket session subscribe — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : subscribe endpoint 公開 + session_id 単位の購読
  AC-2 EVENT-DRIVEN  : 2 秒以内に成功 or {detail:{code,message}} を返す
  AC-3 STATE-DRIVEN  : audit_logs に ws.session.subscribed / .disconnected を emit
  AC-4 UNWANTED      : invalid input / unauthorized actor は 4xx + {detail:{code,message}}
                       かつ persistent state を mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import stream_bridge as sb
from services.stream_bridge import reset_bridge


@pytest.fixture(autouse=True)
def _reset_bridge():
    reset_bridge()
    yield
    reset_bridge()


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    """audit_logs.emit_event を in-memory list で捕捉."""
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


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: subscribe endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_ws_subscribe_endpoint_exists(client):
    """AC-1: /api/ws/sessions/{session_id} が WebSocket として公開されている."""
    with client.websocket_connect("/api/ws/sessions/501") as ws:
        ws.send_text('{"action":"ping"}')
        msg = ws.receive_json()
        assert msg["type"] == "pong"


def test_ac1_replay_endpoint_exists(client):
    """AC-1: /api/sessions/{session_id}/replay も同セッションで公開."""
    r = client.get("/api/sessions/502/replay", params={"since_seq": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == 502
    assert "messages" in body
    assert body["count"] == 0


def test_ac1_session_isolation_between_subscribers(client):
    """AC-1: session_id 単位で隔離される (501 publish が 502 へ漏れない)."""
    client.post("/api/sessions/511/publish", json={"type": "token", "payload": {"t": "x"}})
    r512 = client.get("/api/sessions/512/replay", params={"since_seq": 0})
    assert r512.json()["count"] == 0
    r511 = client.get("/api/sessions/511/replay", params={"since_seq": 0})
    assert r511.json()["count"] >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内に structured response
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_replay_returns_within_2s(client):
    """AC-2: REST replay が 2 秒以内に成功 response を返す."""
    t0 = time.perf_counter()
    r = client.get("/api/sessions/521/replay", params={"since_seq": 0})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0
    body = r.json()
    assert {"session_id", "since_seq", "count", "messages"} <= set(body.keys())


def test_ac2_replay_error_uses_detail_code_message(client):
    """AC-2 + AC-4: invalid since_seq は {detail:{code,message}} 形式."""
    r = client.get("/api/sessions/522/replay", params={"since_seq": -1})
    assert r.status_code == 400
    body = r.json()
    assert "detail" in body
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "ws.invalid_since_seq"
    assert "message" in body["detail"]


def test_ac2_publish_error_uses_detail_code_message(client):
    """AC-2: publish の empty type も {detail:{code,message}}."""
    r = client.post("/api/sessions/523/publish", json={"type": "", "payload": {}})
    assert r.status_code in (400, 422)
    if r.status_code == 400:
        assert r.json()["detail"]["code"] == "ws.invalid_type"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit_logs に subscribed / disconnected を emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_subscribe_emits_audit_event(client, _capture_audit):
    """AC-3: WS subscribe で ws.session.subscribed が audit_logs に流れる."""
    with client.websocket_connect("/api/ws/sessions/531?user_id=alice") as ws:
        ws.send_text('{"action":"ping"}')
        ws.receive_json()
    subscribed = [e for e in _capture_audit if e["event_type"] == "ws.session.subscribed"]
    assert len(subscribed) >= 1
    assert subscribed[0]["session_id"] == 531
    assert subscribed[0]["user_id"] == "alice"


def test_ac3_disconnect_emits_audit_event(client, _capture_audit):
    """AC-3: WS disconnect で ws.session.disconnected が emit される."""
    with client.websocket_connect("/api/ws/sessions/532?user_id=bob") as ws:
        ws.send_text('{"action":"ping"}')
        ws.receive_json()
    # ws context exit で disconnect emit される
    disconnected = [e for e in _capture_audit if e["event_type"] == "ws.session.disconnected"]
    assert len(disconnected) >= 1
    assert disconnected[0]["session_id"] == 532


def test_ac3_replay_emits_audit_event(client, _capture_audit):
    """AC-3: REST replay も audit_logs に ws.session.replayed を emit."""
    client.get("/api/sessions/533/replay", params={"since_seq": 0, "user_id": "carol"})
    replayed = [e for e in _capture_audit if e["event_type"] == "ws.session.replayed"]
    assert len(replayed) >= 1
    assert replayed[0]["user_id"] == "carol"
    assert replayed[0]["detail"]["since_seq"] == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + {detail:{code,message}} + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_session_id_rejected(client):
    """AC-4: session_id <= 0 は 4xx + structured error."""
    r = client.get("/api/sessions/0/replay")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "ws.invalid_session_id"


def test_ac4_invalid_since_seq_rejected(client):
    """AC-4: since_seq < 0 は 4xx + structured error."""
    r = client.get("/api/sessions/541/replay", params={"since_seq": -10})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "ws.invalid_since_seq"


def test_ac4_empty_user_id_rejected(client):
    """AC-4: user_id が空文字なら 401 + structured error."""
    r = client.get("/api/sessions/542/replay", params={"user_id": "   "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "ws.unauthorized"


def test_ac4_rejected_request_does_not_publish_state(client):
    """AC-4 UNWANTED: rejected request は publish しない (state mutate なし)."""
    # invalid since_seq で reject されても session_logs に書き込まれない
    client.get("/api/sessions/543/replay", params={"since_seq": -1})
    r = client.get("/api/sessions/543/replay", params={"since_seq": 0})
    assert r.json()["count"] == 0


def test_ac4_invalid_ws_session_id_closes_with_policy_violation(client):
    """AC-4: WS で session_id<=0 は close 1008 (policy violation)."""
    from starlette.testclient import WebSocketDisconnect as _Disc
    with pytest.raises(_Disc) as exc:
        with client.websocket_connect("/api/ws/sessions/0") as ws:
            ws.receive_json()
    assert exc.value.code == 1008  # policy violation


def test_ac4_invalid_ws_user_id_closes_with_policy_violation(client):
    """AC-4: WS で whitespace user_id は close 1008 (unauthorized)."""
    from starlette.testclient import WebSocketDisconnect as _Disc
    with pytest.raises(_Disc) as exc:
        with client.websocket_connect("/api/ws/sessions/551?user_id=%20%20") as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_ac4_invalid_ws_since_seq_closes(client):
    """AC-4: WS で since_seq<0 は close 1008."""
    from starlette.testclient import WebSocketDisconnect as _Disc
    with pytest.raises(_Disc) as exc:
        with client.websocket_connect("/api/ws/sessions/552?since_seq=-5") as ws:
            ws.receive_json()
    assert exc.value.code == 1008


# ──────────────────────────────────────────────────────────────────────────
# 補助: error contract shape
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    """全 4xx response が {detail:{code, message}} の shape を持つ."""
    cases = [
        ("/api/sessions/0/replay", {}),
        ("/api/sessions/561/replay", {"since_seq": -1}),
        ("/api/sessions/562/replay", {"user_id": "   "}),
    ]
    for path, params in cases:
        r = client.get(path, params=params)
        assert 400 <= r.status_code < 500
        body = r.json()
        assert isinstance(body.get("detail"), dict)
        assert isinstance(body["detail"].get("code"), str)
        assert isinstance(body["detail"].get("message"), str)
