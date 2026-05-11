"""T-014-01: Slack Bolt 統合 (REUSE existing slack_client + slack_block_kit).

AC マッピング:
  AC-1 UBIQUITOUS    : F-014 Slack Bolt 統合 endpoint (status / notify / approval-notify)
  AC-2 EVENT-DRIVEN  : 2 秒以内に成功 or {detail:{code,message}} を返す
  AC-3 STATE-DRIVEN  : 既存実装 (slack_client / slack_block_kit) を import し regression 無し
  AC-4 UNWANTED      : invalid input / unauthorized actor は 4xx + {detail:{code,message}}
                       かつ persistent state を mutate しない
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_slack_state():
    """各 test 前に slack_client の module-level state を初期化."""
    from integrations import slack_client as sc
    sc._slack_enabled = False
    sc._app = None
    yield
    sc._slack_enabled = False
    sc._app = None


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


def _enable_fake_slack(monkeypatch, *, send_should_raise: bool = False,
                       approval_returns_ts: str | None = "1735000000.000100"):
    """Slack を fake 接続済み状態にする (AC-3 REUSE 検証用)."""
    from integrations import slack_client as sc

    sent_messages: list[dict] = []

    class _FakeAuthResult(dict):
        def get(self, key, default=None):
            return {"bot_id": "B_FAKE", "user": "fakebot", "team": "FakeTeam"}.get(key, default)

    class _FakeClient:
        async def auth_test(self):
            return _FakeAuthResult()

        async def chat_postMessage(self, *, channel, text, blocks=None):
            if send_should_raise:
                raise RuntimeError("simulated slack error")
            sent_messages.append({"channel": channel, "text": text, "blocks": blocks})
            return {"ts": "1735000000.0001"}

    fake_app = SimpleNamespace(client=_FakeClient())
    sc._app = fake_app
    sc._slack_enabled = True

    async def fake_approval_notify(approval_id, title, preview):
        if send_should_raise:
            raise RuntimeError("simulated approval error")
        return approval_returns_ts

    monkeypatch.setattr(sc, "send_approval_notification", fake_approval_notify)
    return sent_messages


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: status / notify / approval-notify endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_status_endpoint_exists(client):
    """AC-1: GET /api/slack/status が status を返す."""
    r = client.get("/api/slack/status")
    assert r.status_code == 200
    body = r.json()
    assert {"enabled", "bot_token_configured", "app_token_configured", "channel"} <= set(body.keys())


def test_ac1_notify_endpoint_exists(client):
    """AC-1: POST /api/slack/notify が定義されている."""
    r = client.post("/api/slack/notify", json={"text": "hello"})
    # not_enabled でも 503 (endpoint 存在は確認)
    assert r.status_code in (200, 503)


def test_ac1_approval_notify_endpoint_exists(client):
    """AC-1: POST /api/slack/approval-notify が定義されている."""
    r = client.post(
        "/api/slack/approval-notify",
        json={"approval_id": 1, "title": "テスト"},
    )
    assert r.status_code in (200, 503)


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内に structured response
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_status_returns_within_2s(client):
    """AC-2: status response が 2 秒以内."""
    t0 = time.perf_counter()
    r = client.get("/api/slack/status")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_notify_success_returns_within_2s(client, monkeypatch, _capture_audit):
    """AC-2: notify success で 2 秒以内 + audit emit."""
    sent = _enable_fake_slack(monkeypatch)
    t0 = time.perf_counter()
    r = client.post(
        "/api/slack/notify",
        json={"text": "hello world", "channel": "#test", "user_id": "alice"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0
    assert len(sent) == 1
    assert sent[0]["channel"] == "#test"
    # AC-3: audit log emit
    events = [e for e in _capture_audit if e["event_type"] == "slack.notify.sent"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"


def test_ac2_approval_notify_success_returns_within_2s(client, monkeypatch, _capture_audit):
    """AC-2: approval-notify success で 2 秒以内 + slack_ts 返却."""
    _enable_fake_slack(monkeypatch, approval_returns_ts="1735000000.000999")
    t0 = time.perf_counter()
    r = client.post(
        "/api/slack/approval-notify",
        json={"approval_id": 42, "title": "確認お願いします", "preview": "詳細...", "user_id": "alice"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0
    assert r.json()["slack_ts"] == "1735000000.000999"
    events = [e for e in _capture_audit if e["event_type"] == "slack.approval_notify.sent"]
    assert len(events) >= 1


def test_ac2_error_uses_detail_code_message(client):
    """AC-2: error response は {detail:{code,message}} 形式."""
    r = client.post("/api/slack/notify", json={"text": ""})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "slack.invalid_text"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 slack_client / slack_block_kit を REUSE / regression 無し
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_imports_existing_slack_client():
    """AC-3: 新 router は既存 integrations/slack_client を import する (REUSE)."""
    from routers import slack_integration
    src = open(slack_integration.__file__).read()
    assert "from integrations import slack_client" in src


def test_ac3_existing_slack_client_module_loads():
    """AC-3: 既存 slack_client module が import error 無く load される."""
    from integrations import slack_client as sc
    assert hasattr(sc, "start_slack")
    assert hasattr(sc, "stop_slack")
    assert hasattr(sc, "send_rich_message")
    assert hasattr(sc, "send_approval_notification")


def test_ac3_existing_slack_block_kit_module_loads():
    """AC-3: 既存 slack_block_kit module が import error 無く load される."""
    from integrations import slack_block_kit as sbk
    assert hasattr(sbk, "render_message_for_slack")


def test_ac3_status_reads_live_state(client, monkeypatch):
    """AC-3: status endpoint が既存 slack_client._slack_enabled / ._app を読む."""
    _enable_fake_slack(monkeypatch)
    r = client.get("/api/slack/status")
    body = r.json()
    assert body["enabled"] is True
    assert body["bot_id"] == "B_FAKE"


def test_ac3_notify_routes_through_existing_send_rich_message(client, monkeypatch, _capture_audit):
    """AC-3: rich=True で既存 send_rich_message を経由する."""
    from integrations import slack_client as sc
    sent = _enable_fake_slack(monkeypatch)
    called = {"count": 0}

    async def fake_rich(text, *, channel=None):
        called["count"] += 1

    monkeypatch.setattr(sc, "send_rich_message", fake_rich)
    r = client.post(
        "/api/slack/notify",
        json={"text": "hi", "rich": True, "user_id": "x"},
    )
    assert r.status_code == 200
    assert called["count"] == 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + {detail:{code,message}} + no state mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_notify_rejects_empty_text(client, monkeypatch, _capture_audit):
    """AC-4: empty text は 400 + invalid_text + slack 呼ばれない."""
    sent = _enable_fake_slack(monkeypatch)
    r = client.post("/api/slack/notify", json={"text": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slack.invalid_text"
    assert len(sent) == 0
    # AC-4: state mutate なし — sent audit event も無い
    sent_events = [e for e in _capture_audit if e["event_type"] == "slack.notify.sent"]
    assert len(sent_events) == 0


def test_ac4_notify_rejects_empty_channel(client, monkeypatch):
    """AC-4: 空 channel は 400 + invalid_channel."""
    _enable_fake_slack(monkeypatch)
    r = client.post("/api/slack/notify", json={"text": "hi", "channel": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slack.invalid_channel"


def test_ac4_notify_rejects_empty_user_id(client, monkeypatch):
    """AC-4: 空 user_id は 401 + unauthorized."""
    _enable_fake_slack(monkeypatch)
    r = client.post("/api/slack/notify", json={"text": "hi", "user_id": "   "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "slack.unauthorized"


def test_ac4_approval_notify_rejects_invalid_id(client, monkeypatch):
    """AC-4: approval_id<=0 は 4xx (pydantic gt=0 or 400 invalid_approval_id)."""
    _enable_fake_slack(monkeypatch)
    r = client.post(
        "/api/slack/approval-notify",
        json={"approval_id": 0, "title": "x"},
    )
    assert 400 <= r.status_code < 500


def test_ac4_approval_notify_rejects_empty_title(client, monkeypatch):
    """AC-4: empty title は 400 + invalid_title."""
    _enable_fake_slack(monkeypatch)
    r = client.post(
        "/api/slack/approval-notify",
        json={"approval_id": 1, "title": "   "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slack.invalid_title"


def test_ac4_not_enabled_returns_503(client, _capture_audit):
    """AC-4: Slack 未接続時は 503 + not_enabled で persistent state mutate しない."""
    # _enable_fake_slack を呼ばない → _slack_enabled = False
    r = client.post("/api/slack/notify", json={"text": "hi"})
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "slack.not_enabled"
    # AC-3: skipped audit event は emit される (mutate ではなく log のみ)
    skipped = [e for e in _capture_audit if e["event_type"] == "slack.notify.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["detail"]["reason"] == "not_enabled"


def test_ac4_send_failure_returns_502(client, monkeypatch):
    """AC-4: 下流 SDK エラーは 502 + send_failed (structured)."""
    _enable_fake_slack(monkeypatch, send_should_raise=True)
    r = client.post("/api/slack/notify", json={"text": "hi"})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "slack.send_failed"


def test_ac4_approval_send_failure_returns_502(client, monkeypatch):
    """AC-4: approval 下流エラーも 502 + send_failed."""
    _enable_fake_slack(monkeypatch, send_should_raise=True)
    r = client.post(
        "/api/slack/approval-notify",
        json={"approval_id": 1, "title": "x", "preview": "y"},
    )
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "slack.send_failed"


# ──────────────────────────────────────────────────────────────────────────
# 補助: error contract shape 一貫性
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, monkeypatch):
    """全 error response が {detail:{code:str, message:str}} の shape."""
    _enable_fake_slack(monkeypatch)
    cases = [
        ("POST", "/api/slack/notify", {"text": ""}),
        ("POST", "/api/slack/notify", {"text": "hi", "channel": "   "}),
        ("POST", "/api/slack/notify", {"text": "hi", "user_id": "   "}),
        ("POST", "/api/slack/approval-notify", {"approval_id": 1, "title": ""}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 600, f"{path}: status={r.status_code}"
        body = r.json()
        assert isinstance(body.get("detail"), (dict, list))  # pydantic 422 は list
        if isinstance(body["detail"], dict):
            assert isinstance(body["detail"].get("code"), str)
            assert isinstance(body["detail"].get("message"), str)
