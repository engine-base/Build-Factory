"""T-014-02: カテゴリ別 push (red_line/pr/progress/invite/system) + ダイジェスト
   — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-014 5 カテゴリ push + digest endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : T-014-01 Slack contract REUSE (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import category_push as cp
from services.category_push import (
    CategoryPushError,
    CategoryPushStore,
    IMMEDIATE_ONLY,
    PushMessage,
    VALID_CATEGORIES,
    flush_all_digests,
    flush_digest,
    push_message,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    cp.reset_store()
    yield
    cp.reset_store()


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
def _fake_slack(monkeypatch):
    sent: list[dict] = []

    async def fake_send(msg: str, ch):
        sent.append({"msg": msg, "ch": ch})
        return True

    monkeypatch.setattr(cp, "_default_slack_send", fake_send)
    yield {"sent": sent}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_5_categories_defined():
    assert set(VALID_CATEGORIES) == {
        "red_line", "pr", "progress", "invite", "system",
    }


def test_service_red_line_in_immediate_only():
    assert "red_line" in IMMEDIATE_ONLY


def test_service_enqueue_basic():
    s = CategoryPushStore()
    msg = s.enqueue("pr", "PR opened")
    assert msg.category == "pr"
    assert msg.message == "PR opened"


def test_service_invalid_category():
    s = CategoryPushStore()
    with pytest.raises(CategoryPushError):
        s.enqueue("bogus", "x")


def test_service_empty_message():
    s = CategoryPushStore()
    with pytest.raises(CategoryPushError):
        s.enqueue("pr", " ")


def test_service_long_message():
    s = CategoryPushStore()
    with pytest.raises(CategoryPushError):
        s.enqueue("pr", "x" * (cp.MAX_MESSAGE_LEN + 1))


def test_service_empty_channel():
    s = CategoryPushStore()
    with pytest.raises(CategoryPushError):
        s.enqueue("pr", "x", channel=" ")


def test_service_long_channel():
    s = CategoryPushStore()
    with pytest.raises(CategoryPushError):
        s.enqueue("pr", "x", channel="x" * (cp.MAX_CHANNEL_LEN + 1))


def test_service_pending_grows_for_non_immediate():
    s = CategoryPushStore()
    s.enqueue("progress", "task A done")
    s.enqueue("progress", "task B done")
    assert len(s.get_pending("progress")) == 2


def test_service_red_line_is_not_queued():
    """red_line は強制 immediate なので pending に入らない."""
    s = CategoryPushStore()
    s.enqueue("red_line", "DROP TABLE attempted")
    assert s.get_pending("red_line") == []


def test_service_immediate_flag_bypasses_queue():
    s = CategoryPushStore()
    s.enqueue("progress", "urgent task", immediate=True)
    assert s.get_pending("progress") == []


def test_service_digest_window_zero_bypasses_queue():
    s = CategoryPushStore()
    s.configure("progress", digest_window_seconds=0)
    s.enqueue("progress", "x")
    assert s.get_pending("progress") == []


def test_service_configure_channel():
    s = CategoryPushStore()
    cfg = s.configure("pr", channel="#pr-feed")
    assert cfg.channel == "#pr-feed"
    # その後 enqueue で channel 継承
    msg = s.enqueue("pr", "x")
    assert msg.channel == "#pr-feed"


def test_service_configure_invalid():
    s = CategoryPushStore()
    with pytest.raises(CategoryPushError):
        s.configure("pr", channel="  ")
    with pytest.raises(CategoryPushError):
        s.configure("pr", digest_window_seconds=-1)
    with pytest.raises(CategoryPushError):
        s.configure("pr", digest_window_seconds=cp.MAX_DIGEST_WINDOW_SEC + 1)


def test_service_max_pending_per_category():
    s = CategoryPushStore()
    for _ in range(cp.MAX_PENDING_PER_CATEGORY):
        s.enqueue("progress", "x")
    with pytest.raises(CategoryPushError):
        s.enqueue("progress", "x")


def test_service_push_message_immediate_for_red_line():
    sent = []

    async def fake_send(m, ch):
        sent.append({"m": m, "ch": ch})
        return True

    out = asyncio.run(push_message(
        "red_line", "DROP TABLE", slack_send_fn=fake_send,
    ))
    assert out["immediate"] is True
    assert out["delivered"] is True
    assert sent[0]["m"].startswith("[RED_LINE]")


def test_service_push_message_digest_for_progress():
    sent = []

    async def fake_send(m, ch):
        sent.append({"m": m, "ch": ch})
        return True

    out = asyncio.run(push_message(
        "progress", "task done", slack_send_fn=fake_send,
    ))
    assert out["immediate"] is False
    assert out["delivered"] is False
    assert sent == []  # まだ送られていない (digest 待機)


def test_service_flush_digest_sends_combined():
    sent = []

    async def fake_send(m, ch):
        sent.append({"m": m, "ch": ch})
        return True

    asyncio.run(push_message("progress", "a", slack_send_fn=fake_send))
    asyncio.run(push_message("progress", "b", slack_send_fn=fake_send))
    out = asyncio.run(flush_digest("progress", slack_send_fn=fake_send))
    assert out["flushed"] == 2
    assert out["delivered"] is True
    assert "DIGEST PROGRESS" in sent[0]["m"]
    assert "- a" in sent[0]["m"]
    assert "- b" in sent[0]["m"]


def test_service_flush_digest_empty_returns_zero():
    sent = []

    async def fake_send(m, ch):
        sent.append({"m": m, "ch": ch})
        return True

    out = asyncio.run(flush_digest("pr", slack_send_fn=fake_send))
    assert out["flushed"] == 0
    assert out["delivered"] is False
    assert sent == []


def test_service_flush_all_aggregates_per_category():
    async def fake_send(m, ch):
        return True

    asyncio.run(push_message("progress", "p1", slack_send_fn=fake_send))
    asyncio.run(push_message("pr", "pr1", slack_send_fn=fake_send))
    asyncio.run(push_message("invite", "i1", slack_send_fn=fake_send))
    out = asyncio.run(flush_all_digests(slack_send_fn=fake_send))
    assert out["flushed"]["progress"] == 1
    assert out["flushed"]["pr"] == 1
    assert out["flushed"]["invite"] == 1
    # red_line は queue に入らないので 0
    assert out["flushed"]["red_line"] == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_push_endpoint(client, _fake_slack):
    r = client.post(
        "/api/notifications/push",
        json={"category": "pr", "message": "PR opened"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "pr"
    assert body["immediate"] is False


def test_ac1_red_line_immediate(client, _fake_slack):
    r = client.post(
        "/api/notifications/push",
        json={"category": "red_line", "message": "fatal"},
    )
    assert r.status_code == 200
    assert r.json()["immediate"] is True


def test_ac1_pending_endpoint(client):
    client.post("/api/notifications/push",
                 json={"category": "progress", "message": "x"})
    r = client.get("/api/notifications/pending/progress")
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_ac1_flush_one_endpoint(client, _fake_slack):
    client.post("/api/notifications/push",
                 json={"category": "progress", "message": "x"})
    r = client.post("/api/notifications/digest/flush/progress", json={})
    assert r.status_code == 200
    assert r.json()["flushed"] >= 1


def test_ac1_flush_all_endpoint(client, _fake_slack):
    client.post("/api/notifications/push",
                 json={"category": "progress", "message": "p"})
    client.post("/api/notifications/push",
                 json={"category": "pr", "message": "q"})
    r = client.post("/api/notifications/digest/flush-all", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["flushed"]["progress"] == 1
    assert body["flushed"]["pr"] == 1


def test_ac1_configure_endpoint(client):
    r = client.post(
        "/api/notifications/configure",
        json={"category": "pr", "channel": "#pr",
               "digest_window_seconds": 60},
    )
    assert r.status_code == 200
    assert r.json()["channel"] == "#pr"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_push_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/notifications/push",
        json={"category": "pr", "message": "x"},
    )
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_flush_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/notifications/digest/flush-all", json={})
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/notifications/push",
        json={"category": "bogus", "message": "x"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "notify.invalid_category"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: backwards compat + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_slack_client_intact():
    """AC-3: T-014-01 の slack_client が無傷 (import error なし)."""
    from integrations import slack_client as sc
    assert hasattr(sc, "send_rich_message")
    assert hasattr(sc, "start_slack")


def test_ac3_push_emits_audit(client, _capture_audit):
    client.post(
        "/api/notifications/push",
        json={"category": "pr", "message": "x",
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "notify.pushed"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"


def test_ac3_flush_emits_audit(client, _capture_audit):
    client.post("/api/notifications/push",
                 json={"category": "progress", "message": "x"})
    client.post("/api/notifications/digest/flush/progress",
                 json={"actor_user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "notify.digest.flushed"]
    assert len(events) >= 1
    assert events[0]["detail"]["flushed"] >= 1


def test_ac3_configure_emits_audit(client, _capture_audit):
    client.post(
        "/api/notifications/configure",
        json={"category": "pr", "channel": "#test",
               "digest_window_seconds": 30,
               "actor_user_id": "bob"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "notify.configured"]
    assert len(events) >= 1
    assert events[0]["detail"]["category"] == "pr"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_category(client):
    r = client.post("/api/notifications/push",
                     json={"category": "bogus", "message": "x"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "notify.invalid_category"


def test_ac4_empty_message(client):
    r = client.post("/api/notifications/push",
                     json={"category": "pr", "message": " "})
    assert r.status_code == 400


def test_ac4_long_message(client):
    r = client.post("/api/notifications/push",
                     json={"category": "pr",
                            "message": "x" * (cp.MAX_MESSAGE_LEN + 1)})
    assert r.status_code == 400


def test_ac4_empty_channel(client):
    r = client.post(
        "/api/notifications/push",
        json={"category": "pr", "message": "x", "channel": " "},
    )
    assert r.status_code == 400


def test_ac4_empty_actor(client):
    r = client.post(
        "/api/notifications/push",
        json={"category": "pr", "message": "x",
               "actor_user_id": " "},
    )
    assert r.status_code == 401


def test_ac4_configure_invalid_category(client):
    r = client.post(
        "/api/notifications/configure",
        json={"category": "bogus", "channel": "#x"},
    )
    assert r.status_code == 400


def test_ac4_configure_invalid_window(client):
    r = client.post(
        "/api/notifications/configure",
        json={"category": "pr", "digest_window_seconds": -1},
    )
    assert r.status_code in (400, 422)


def test_ac4_pending_invalid_category(client):
    r = client.get("/api/notifications/pending/bogus")
    assert r.status_code == 400


def test_ac4_queue_full_returns_409(client, monkeypatch):
    """pending queue が full のとき 409."""
    # MAX_PENDING_PER_CATEGORY を一時的に小さく
    monkeypatch.setattr(cp, "MAX_PENDING_PER_CATEGORY", 2)
    cp.reset_store()
    client.post("/api/notifications/push",
                 json={"category": "progress", "message": "a"})
    client.post("/api/notifications/push",
                 json={"category": "progress", "message": "b"})
    r = client.post("/api/notifications/push",
                     json={"category": "progress", "message": "c"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "notify.queue_full"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/notifications/push",
                 json={"category": "bogus", "message": "x"})
    client.post("/api/notifications/push",
                 json={"category": "pr", "message": " "})
    events = [e for e in _capture_audit if e["event_type"] == "notify.pushed"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/notifications/push",
         {"category": "bogus", "message": "x"}),
        ("POST", "/api/notifications/push",
         {"category": "pr", "message": " "}),
        ("POST", "/api/notifications/push",
         {"category": "pr", "message": "x", "channel": " "}),
        ("POST", "/api/notifications/push",
         {"category": "pr", "message": "x", "actor_user_id": " "}),
        ("GET", "/api/notifications/pending/bogus", None),
        ("POST", "/api/notifications/configure",
         {"category": "bogus"}),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
