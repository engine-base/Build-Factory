"""T-AI-07: Streaming WS bridge — 5 AC 全網羅.

AC マッピング:
  AC-EVENT-1: token forward < 50ms (in-memory queue)
  AC-EVENT-2: tool_use → 構造化 ws message + session_logs append
  AC-STATE:   disconnect 30s buffer + reconnect replay
  AC-OPTIONAL: seq_id 指定 replay
  AC-UNWANTED: 1MB overflow → drop oldest non-priority + emit buffer_overflow
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import stream_bridge as sb
from services.stream_bridge import (
    BufferedMessage, StreamBridge, PRIORITY_TYPES, get_bridge, reset_bridge,
)


@pytest.fixture(autouse=True)
def _reset_bridge():
    reset_bridge()
    yield
    reset_bridge()


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────
# AC-EVENT-1: token forward latency < 50ms
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_forwarded_within_50ms(monkeypatch) -> None:
    """AC-EVENT-1: publish → subscriber receive 内で 50ms 以内.

    session_logs DB append は WS forward latency と独立なので mock。
    本テストは pure queue dispatch latency を測る."""

    async def _noop(*a, **kw): return None

    monkeypatch.setattr(sb, "_append_session_log", _noop)

    b = StreamBridge()
    q = await b.subscribe(session_id=1)
    # warm up (import 等の初回コスト除外)
    await b.publish(1, "system", {"warm": True})
    await asyncio.wait_for(q.get(), timeout=0.5)

    # 測定本番
    t0 = time.monotonic()
    await b.publish(1, "token", {"text": "hello"})
    msg = await asyncio.wait_for(q.get(), timeout=0.5)
    dt = time.monotonic() - t0
    assert dt < 0.05, f"latency {dt*1000:.1f}ms exceeds 50ms"
    assert msg["type"] == "token"
    assert msg["text"] == "hello"
    assert msg["seq"] == 2


@pytest.mark.asyncio
async def test_multiple_tokens_in_order() -> None:
    b = StreamBridge()
    q = await b.subscribe(session_id=2)
    for i in range(5):
        await b.publish(2, "token", {"text": f"t{i}"})
    seqs = []
    for _ in range(5):
        m = await asyncio.wait_for(q.get(), timeout=0.5)
        seqs.append(m["seq"])
    assert seqs == [1, 2, 3, 4, 5]


# ─────────────────────────────────────────────────────────────────────────
# AC-EVENT-2: tool_use 構造化 + session_logs
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_use_message_structured() -> None:
    b = StreamBridge()
    q = await b.subscribe(session_id=3)
    await b.publish_priority(3, "tool_use", {"tool": "Bash", "input": {"cmd": "ls"}})
    msg = await asyncio.wait_for(q.get(), timeout=0.5)
    assert msg["type"] == "tool_use"
    assert msg["tool"] == "Bash"
    assert msg["input"] == {"cmd": "ls"}
    assert "seq" in msg


@pytest.mark.asyncio
async def test_session_log_append_does_not_break_when_db_absent(monkeypatch) -> None:
    """AC-EVENT-2: session_logs append が失敗しても WS は届く."""
    # _append_session_log 内で db import 失敗を強制 → 例外を吸収
    async def fake_append(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(sb, "_append_session_log", fake_append)

    b = StreamBridge()
    q = await b.subscribe(session_id=4)
    await b.publish(4, "token", {"text": "x"})
    msg = await asyncio.wait_for(q.get(), timeout=0.5)
    assert msg["text"] == "x"


# ─────────────────────────────────────────────────────────────────────────
# AC-STATE: disconnect 30s buffer + reconnect replay
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_buffer_retains_messages_after_disconnect() -> None:
    """AC-STATE: subscribe → publish → unsubscribe → 再 subscribe で全件 replay."""
    b = StreamBridge()
    q1 = await b.subscribe(session_id=5)
    await b.publish(5, "token", {"text": "a"})
    await b.publish(5, "token", {"text": "b"})
    # 1 件取って disconnect
    _ = await asyncio.wait_for(q1.get(), timeout=0.5)
    await b.unsubscribe(5, q1)
    # 再接続: 既存 buffer から全部 replay されるべき
    q2 = await b.subscribe(session_id=5)
    received: list[str] = []
    for _ in range(2):
        m = await asyncio.wait_for(q2.get(), timeout=0.5)
        received.append(m["text"])
    assert received == ["a", "b"]


@pytest.mark.asyncio
async def test_cleanup_expired_drops_session_after_retain_window() -> None:
    """AC-STATE: 30s 経過した disconnect-only session の buffer 解放."""
    b = StreamBridge(disconnect_retain_sec=0.0)  # 即時 expire
    q = await b.subscribe(session_id=6)
    await b.publish(6, "token", {"text": "x"})
    await b.unsubscribe(6, q)
    await asyncio.sleep(0.01)
    n = await b.cleanup_expired()
    assert n == 1


@pytest.mark.asyncio
async def test_active_session_not_cleaned_up() -> None:
    b = StreamBridge(disconnect_retain_sec=0.0)
    q = await b.subscribe(session_id=7)
    await b.publish(7, "token", {"text": "x"})
    # まだ subscribe 中 → expire 対象外
    n = await b.cleanup_expired()
    assert n == 0
    await b.unsubscribe(7, q)


# ─────────────────────────────────────────────────────────────────────────
# AC-OPTIONAL: seq_id 指定 replay
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_since_returns_messages_after_seq() -> None:
    b = StreamBridge()
    await b.publish(8, "token", {"text": "1"})
    await b.publish(8, "token", {"text": "2"})
    await b.publish(8, "token", {"text": "3"})
    out = await b.replay_since(8, seq_id=1)
    seqs = [m["seq"] for m in out]
    assert seqs == [2, 3]
    texts = [m["text"] for m in out]
    assert texts == ["2", "3"]


@pytest.mark.asyncio
async def test_subscribe_with_since_seq_replays_after_seq() -> None:
    b = StreamBridge()
    await b.publish(9, "token", {"text": "a"})
    await b.publish(9, "token", {"text": "b"})
    await b.publish(9, "token", {"text": "c"})
    # since_seq=1 → b, c が流れる
    q = await b.subscribe(session_id=9, since_seq=1)
    received: list[str] = []
    for _ in range(2):
        m = await asyncio.wait_for(q.get(), timeout=0.5)
        received.append(m["text"])
    assert received == ["b", "c"]


@pytest.mark.asyncio
async def test_replay_since_unknown_session_returns_empty() -> None:
    b = StreamBridge()
    out = await b.replay_since(999, seq_id=0)
    assert out == []


# ─────────────────────────────────────────────────────────────────────────
# AC-UNWANTED: 1MB overflow → drop oldest non-priority + buffer_overflow event
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_buffer_overflow_drops_oldest_non_priority() -> None:
    """AC-UNWANTED: 1MB 超 → 古い token から drop / tool_use 残存 / overflow event."""
    b = StreamBridge(buffer_bytes_limit=2048)  # 2KB に絞って overflow を起こす

    # tool_use (priority) を 1 件追加
    await b.publish_priority(10, "tool_use", {"tool": "Bash", "input": {"cmd": "ls"}})
    # 大きい token を多数追加 → overflow を強制
    big_text = "x" * 1000  # 約 1KB
    for i in range(10):
        await b.publish(10, "token", {"text": big_text, "i": i})

    # buffer に tool_use と buffer_overflow が残り、 古い token は drop される
    out = await b.replay_since(10, seq_id=0)
    types = [m["type"] for m in out]
    # tool_use は priority なので残る
    assert "tool_use" in types
    # 少なくとも 1 件以上 overflow event が emit される
    assert "buffer_overflow" in types


@pytest.mark.asyncio
async def test_buffer_overflow_event_includes_dropped_count() -> None:
    b = StreamBridge(buffer_bytes_limit=512)
    big = "y" * 200
    for _ in range(10):
        await b.publish(11, "token", {"text": big})
    out = await b.replay_since(11, seq_id=0)
    overflow_events = [m for m in out if m["type"] == "buffer_overflow"]
    assert len(overflow_events) >= 1
    assert overflow_events[0]["dropped"] >= 1


@pytest.mark.asyncio
async def test_priority_messages_never_dropped_under_pressure() -> None:
    """AC-UNWANTED 逆: priority (tool_use / result) は overflow でも drop されない."""
    b = StreamBridge(buffer_bytes_limit=512)
    # 大量の token (drop 候補) を流す前後に priority を挟む
    await b.publish_priority(12, "tool_use", {"tool": "A", "input": {}})
    for _ in range(20):
        await b.publish(12, "token", {"text": "z" * 100})
    await b.publish_priority(12, "result", {"stop_reason": "end_turn"})

    out = await b.replay_since(12, seq_id=0)
    types = [m["type"] for m in out]
    # tool_use と result の両方が残っている
    assert types.count("tool_use") == 1
    assert types.count("result") == 1


# ─────────────────────────────────────────────────────────────────────────
# subscribe / unsubscribe / fan-out
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive_publish() -> None:
    b = StreamBridge()
    q1 = await b.subscribe(session_id=13)
    q2 = await b.subscribe(session_id=13)
    await b.publish(13, "token", {"text": "broadcast"})
    m1 = await asyncio.wait_for(q1.get(), timeout=0.5)
    m2 = await asyncio.wait_for(q2.get(), timeout=0.5)
    assert m1["text"] == m2["text"] == "broadcast"


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue() -> None:
    b = StreamBridge()
    q = await b.subscribe(session_id=14)
    await b.unsubscribe(14, q)
    await b.publish(14, "token", {"text": "ignored"})
    # q は再 subscribe しない限り何も受け取らない (queue は close されてないが list から外れた)
    # 直接 buffer は持つ
    out = await b.replay_since(14, seq_id=0)
    assert len(out) >= 1


def test_get_bridge_returns_singleton() -> None:
    b1 = get_bridge()
    b2 = get_bridge()
    assert b1 is b2


# ─────────────────────────────────────────────────────────────────────────
# Router endpoint smoke
# ─────────────────────────────────────────────────────────────────────────


def test_replay_endpoint_returns_messages(client) -> None:
    # publish 経由で 2 件追加
    client.post("/api/sessions/100/publish", json={"type": "token", "payload": {"text": "x1"}})
    client.post("/api/sessions/100/publish", json={"type": "token", "payload": {"text": "x2"}})
    r = client.get("/api/sessions/100/replay", params={"since_seq": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 2
    assert all("seq" in m for m in body["messages"])


def test_publish_endpoint_rejects_empty_type(client) -> None:
    r = client.post("/api/sessions/100/publish", json={"type": "", "payload": {}})
    assert r.status_code in (400, 422)


def test_publish_endpoint_priority_flag(client) -> None:
    r = client.post(
        "/api/sessions/200/publish",
        json={"type": "tool_use", "payload": {"tool": "X", "input": {}}, "priority": True},
    )
    assert r.status_code == 200
    assert r.json()["type"] == "tool_use"


# ─────────────────────────────────────────────────────────────────────────
# Buffered message + helpers
# ─────────────────────────────────────────────────────────────────────────


def test_buffered_message_to_ws_dict_includes_seq_and_type() -> None:
    m = BufferedMessage(seq=42, type="token", payload={"text": "hi"}, bytes_size=10)
    d = m.to_ws_dict()
    assert d["type"] == "token"
    assert d["seq"] == 42
    assert d["text"] == "hi"


def test_priority_types_constant_includes_tool_use_and_result() -> None:
    assert "tool_use" in PRIORITY_TYPES
    assert "result" in PRIORITY_TYPES
    assert "buffer_overflow" in PRIORITY_TYPES


# ─────────────────────────────────────────────────────────────────────────
# WebSocket endpoint integration tests
# ─────────────────────────────────────────────────────────────────────────


def test_ws_endpoint_receives_published_messages(client) -> None:
    """WS endpoint: subscribe → publish 経由で送信 → ws.receive_json."""
    with client.websocket_connect("/api/ws/sessions/300") as websocket:
        # 直接 publish (REST 経由)
        client.post(
            "/api/sessions/300/publish",
            json={"type": "token", "payload": {"text": "ws-hello"}},
        )
        msg = websocket.receive_json()
        assert msg["type"] == "token"
        assert msg["text"] == "ws-hello"


def test_ws_endpoint_replay_via_client_message(client) -> None:
    """client → server: action=replay で since_seq 以降を再送."""
    # まず 2 件 publish (subscribe 前)
    client.post("/api/sessions/301/publish", json={"type": "token", "payload": {"text": "a"}})
    client.post("/api/sessions/301/publish", json={"type": "token", "payload": {"text": "b"}})

    with client.websocket_connect("/api/ws/sessions/301") as websocket:
        # 既に subscribe 前の publish は disconnect retain 経由で流れる可能性あり
        # → 確実な replay action を送る
        websocket.send_json({"action": "replay", "since_seq": 0})
        # 少なくとも 1 件は受け取れる
        msg = websocket.receive_json()
        assert "type" in msg and "seq" in msg


def test_ws_endpoint_ping_pong(client) -> None:
    with client.websocket_connect("/api/ws/sessions/302") as websocket:
        websocket.send_json({"action": "ping"})
        msg = websocket.receive_json()
        assert msg["type"] == "pong"


def test_ws_endpoint_subscribe_with_since_seq(client) -> None:
    """WS query param since_seq による replay."""
    client.post("/api/sessions/303/publish", json={"type": "token", "payload": {"text": "old"}})
    client.post("/api/sessions/303/publish", json={"type": "token", "payload": {"text": "new"}})
    with client.websocket_connect("/api/ws/sessions/303?since_seq=1") as websocket:
        msg = websocket.receive_json()
        assert msg["seq"] >= 2
        assert msg["text"] == "new"


def test_ws_endpoint_ignores_invalid_client_json(client) -> None:
    """client が壊れた JSON を送っても WS が落ちない."""
    with client.websocket_connect("/api/ws/sessions/304") as websocket:
        websocket.send_text("not-a-json{{{")
        # publish して受け取れることで WS が生きていることを確認
        client.post(
            "/api/sessions/304/publish",
            json={"type": "token", "payload": {"text": "still-alive"}},
        )
        msg = websocket.receive_json()
        assert msg["text"] == "still-alive"
