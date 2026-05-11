"""T-011-03: エスカレ通知 (Slack DM + UI バッジ) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-011 エスカレ通知 endpoint + service (Slack DM + UI バッジ)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + Slack 未接続でもバッジは記録 + 他人 badge 既読不可
  AC-4 UNWANTED      : invalid input は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import escalation_notifier as en
from services.escalation_notifier import (
    Badge,
    EscalationError,
    EscalationStore,
    VALID_SEVERITIES,
    escalate,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    en.reset_store()
    yield
    en.reset_store()


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
    """default slack send を fake (sent log) に."""
    sent: list[dict] = []

    async def fake_send(message: str, channel):
        sent.append({"message": message, "channel": channel})
        return True

    monkeypatch.setattr(en, "_default_slack_send", fake_send)
    yield {"sent": sent}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_add_badge_basic():
    s = EscalationStore()
    b = s.add_badge(
        user_id="alice", severity="warning", label="L", message="m",
        slack_delivered=True,
    )
    assert b.user_id == "alice"
    assert b.severity == "warning"
    assert b.read_at is None


def test_service_invalid_user_id():
    s = EscalationStore()
    with pytest.raises(EscalationError):
        s.add_badge(user_id="  ", severity="info", label="L",
                     message="m", slack_delivered=False)
    with pytest.raises(EscalationError):
        s.add_badge(user_id="x" * 201, severity="info", label="L",
                     message="m", slack_delivered=False)


def test_service_invalid_severity():
    s = EscalationStore()
    with pytest.raises(EscalationError):
        s.add_badge(user_id="alice", severity="bogus",
                     label="L", message="m", slack_delivered=False)


def test_service_invalid_label():
    s = EscalationStore()
    with pytest.raises(EscalationError):
        s.add_badge(user_id="alice", severity="info",
                     label=" ", message="m", slack_delivered=False)
    with pytest.raises(EscalationError):
        s.add_badge(user_id="alice", severity="info",
                     label="x" * 201, message="m", slack_delivered=False)


def test_service_invalid_message():
    s = EscalationStore()
    with pytest.raises(EscalationError):
        s.add_badge(user_id="alice", severity="info",
                     label="L", message=" ", slack_delivered=False)
    with pytest.raises(EscalationError):
        s.add_badge(user_id="alice", severity="info",
                     label="L", message="x" * 4001, slack_delivered=False)


def test_service_list_filters_read():
    s = EscalationStore()
    b1 = s.add_badge(user_id="a", severity="info", label="L1",
                      message="m1", slack_delivered=False)
    b2 = s.add_badge(user_id="a", severity="info", label="L2",
                      message="m2", slack_delivered=False)
    s.mark_read(b1.id, user_id="a")
    assert len(s.list_for_user("a")) == 1
    assert len(s.list_for_user("a", include_read=True)) == 2


def test_service_list_sorts_by_severity():
    s = EscalationStore()
    s.add_badge(user_id="a", severity="info", label="i1",
                 message="m", slack_delivered=False)
    s.add_badge(user_id="a", severity="redline", label="r1",
                 message="m", slack_delivered=False)
    s.add_badge(user_id="a", severity="critical", label="c1",
                 message="m", slack_delivered=False)
    s.add_badge(user_id="a", severity="warning", label="w1",
                 message="m", slack_delivered=False)
    items = s.list_for_user("a")
    severities = [b.severity for b in items]
    # VALID_SEVERITIES = (info, warning, critical, redline)
    # severity rank: info=0 → redline=3, ソートは -rank なので redline 先頭
    assert severities[0] == "redline"
    assert severities[-1] == "info"


def test_service_mark_read():
    s = EscalationStore()
    b = s.add_badge(user_id="a", severity="info", label="L",
                     message="m", slack_delivered=False)
    assert s.mark_read(b.id, user_id="a") is True
    assert s.mark_read(b.id, user_id="a") is False  # already read


def test_service_mark_read_other_user_raises():
    s = EscalationStore()
    b = s.add_badge(user_id="a", severity="info", label="L",
                     message="m", slack_delivered=False)
    with pytest.raises(EscalationError):
        s.mark_read(b.id, user_id="b")


def test_service_mark_read_unknown_returns_false():
    s = EscalationStore()
    assert s.mark_read(99, user_id="a") is False


def test_service_invalid_badge_id():
    s = EscalationStore()
    with pytest.raises(EscalationError):
        s.mark_read(0, user_id="a")


def test_service_clear_user_returns_count():
    s = EscalationStore()
    s.add_badge(user_id="a", severity="info", label="L",
                 message="m", slack_delivered=False)
    s.add_badge(user_id="a", severity="info", label="L",
                 message="m", slack_delivered=False)
    s.add_badge(user_id="b", severity="info", label="L",
                 message="m", slack_delivered=False)
    assert s.clear_user("a") == 2
    assert s.clear_user("a") == 0
    assert s.list_for_user("b") != []


def test_service_max_per_user():
    s = EscalationStore()
    for i in range(en.MAX_BADGES_PER_USER):
        s.add_badge(user_id="a", severity="info", label="L",
                     message="m", slack_delivered=False)
    with pytest.raises(EscalationError):
        s.add_badge(user_id="a", severity="info", label="L",
                     message="m", slack_delivered=False)


def test_service_escalate_invokes_slack_and_creates_badge():
    sent: list[dict] = []

    async def fake_send(msg, ch):
        sent.append({"msg": msg, "ch": ch})
        return True

    en.reset_store()
    out = asyncio.run(escalate(
        "alice", "critical issue", severity="critical",
        badge_label="DB outage", slack_send_fn=fake_send,
    ))
    assert out["slack_delivered"] is True
    assert sent[0]["msg"].startswith("[CRITICAL]")
    assert en.get_store().list_for_user("alice")[0].label == "DB outage"


def test_service_escalate_without_slack():
    async def fake_send(msg, ch):
        return False

    en.reset_store()
    out = asyncio.run(escalate(
        "alice", "issue", slack_dm=False, slack_send_fn=fake_send,
    ))
    # slack_dm=False → fake_send は呼ばれない
    assert out["slack_delivered"] is False


def test_service_escalate_invalid_severity_raises():
    async def fake_send(msg, ch):
        return True

    with pytest.raises(EscalationError):
        asyncio.run(escalate(
            "alice", "x", severity="bogus", slack_send_fn=fake_send,
        ))


def test_service_escalate_empty_user_raises():
    async def fake_send(msg, ch):
        return True

    with pytest.raises(EscalationError):
        asyncio.run(escalate("  ", "x", slack_send_fn=fake_send))


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_notify_endpoint(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "issue X",
               "severity": "warning", "badge_label": "DB"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "alice"
    assert body["severity"] == "warning"


def test_ac1_list_badges_endpoint(client):
    client.post("/api/escalation/notify",
                 json={"target_user_id": "alice", "message": "x",
                        "severity": "info", "badge_label": "L"})
    r = client.get("/api/escalation/badges/alice")
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_ac1_mark_read_endpoint(client):
    b = client.post("/api/escalation/notify",
                     json={"target_user_id": "alice", "message": "x",
                            "severity": "info", "badge_label": "L"}).json()
    r = client.post(
        f"/api/escalation/badges/{b['badge_id']}/read",
        json={"user_id": "alice"},
    )
    assert r.status_code == 200
    assert r.json()["read"] is True


def test_ac1_clear_endpoint(client):
    client.post("/api/escalation/notify",
                 json={"target_user_id": "alice", "message": "x",
                        "severity": "info", "badge_label": "L"})
    r = client.delete("/api/escalation/badges/alice")
    assert r.status_code == 200
    assert r.json()["cleared"] >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_notify_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x",
               "severity": "info", "badge_label": "L"},
    )
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_list_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/escalation/badges/alice")
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "  ", "message": "x"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "escalation.invalid_target_user"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + Slack 未接続でもバッジ記録 + 他人 badge 既読不可
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_notify_emits_audit(client, _capture_audit):
    client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x",
               "severity": "redline", "badge_label": "L",
               "actor_user_id": "secretary"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "escalation.notified"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "secretary"
    assert events[0]["detail"]["target_user_id"] == "alice"
    assert events[0]["detail"]["severity"] == "redline"


def test_ac3_slack_failure_still_creates_badge(client, monkeypatch):
    """AC-3: Slack 送信失敗してもバッジは記録 (state 保証)."""
    async def fake_send(msg, ch):
        return False

    monkeypatch.setattr(en, "_default_slack_send", fake_send)
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x",
               "severity": "info", "badge_label": "L"},
    )
    assert r.status_code == 200
    assert r.json()["slack_delivered"] is False
    # バッジは記録されている
    badges = client.get("/api/escalation/badges/alice").json()
    assert badges["count"] >= 1


def test_ac3_other_user_cannot_mark_read(client):
    b = client.post("/api/escalation/notify",
                     json={"target_user_id": "alice", "message": "x",
                            "severity": "info", "badge_label": "L"}).json()
    r = client.post(
        f"/api/escalation/badges/{b['badge_id']}/read",
        json={"user_id": "bob"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "escalation.forbidden"


def test_ac3_mark_read_emits_audit(client, _capture_audit):
    b = client.post("/api/escalation/notify",
                     json={"target_user_id": "alice", "message": "x",
                            "severity": "info", "badge_label": "L"}).json()
    client.post(
        f"/api/escalation/badges/{b['badge_id']}/read",
        json={"user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "escalation.badge.read"]
    assert len(events) >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_target_user(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "  ", "message": "x"},
    )
    assert r.status_code == 400


def test_ac4_long_target_user(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "x" * 201, "message": "x"},
    )
    assert r.status_code == 400


def test_ac4_empty_message(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "  "},
    )
    assert r.status_code == 400


def test_ac4_long_message(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x" * 4001},
    )
    assert r.status_code == 400


def test_ac4_invalid_severity(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x", "severity": "bogus"},
    )
    assert r.status_code == 400


def test_ac4_empty_badge_label(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x", "badge_label": " "},
    )
    assert r.status_code == 400


def test_ac4_empty_slack_channel(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x",
               "slack_channel": "  "},
    )
    assert r.status_code == 400


def test_ac4_empty_actor(client):
    r = client.post(
        "/api/escalation/notify",
        json={"target_user_id": "alice", "message": "x",
               "actor_user_id": "  "},
    )
    assert r.status_code == 401


def test_ac4_mark_read_unknown_badge(client):
    r = client.post(
        "/api/escalation/badges/99999/read",
        json={"user_id": "alice"},
    )
    assert r.status_code == 404


def test_ac4_mark_read_already_read(client):
    b = client.post("/api/escalation/notify",
                     json={"target_user_id": "alice", "message": "x",
                            "severity": "info", "badge_label": "L"}).json()
    client.post(f"/api/escalation/badges/{b['badge_id']}/read",
                 json={"user_id": "alice"})
    r = client.post(f"/api/escalation/badges/{b['badge_id']}/read",
                     json={"user_id": "alice"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "escalation.already_read"


def test_ac4_invalid_badge_id(client):
    r = client.post("/api/escalation/badges/0/read",
                     json={"user_id": "alice"})
    assert r.status_code == 400


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/escalation/notify",
                 json={"target_user_id": "  ", "message": "x"})
    client.post("/api/escalation/notify",
                 json={"target_user_id": "alice", "message": " "})
    events = [e for e in _capture_audit if e["event_type"] == "escalation.notified"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/escalation/notify",
         {"target_user_id": "  ", "message": "x"}),
        ("POST", "/api/escalation/notify",
         {"target_user_id": "a", "message": " "}),
        ("POST", "/api/escalation/notify",
         {"target_user_id": "a", "message": "x", "severity": "bogus"}),
        ("POST", "/api/escalation/notify",
         {"target_user_id": "a", "message": "x", "actor_user_id": "  "}),
        ("POST", "/api/escalation/badges/0/read", {"user_id": "a"}),
        ("POST", "/api/escalation/badges/99999/read", {"user_id": "a"}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
