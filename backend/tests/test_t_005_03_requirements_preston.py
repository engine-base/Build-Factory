"""T-005-03: requirements AI Preston 6STEP (requirements REFACTOR) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-005 の 7 endpoint 公開 (start/reply/complete/state/aggregated/center/download)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 route prefix / response shape 不変 + audit emit
  AC-4 UNWANTED      : invalid workspace_id / step / 空 message / 不正 fmt は 4xx +
                       structured + persistent state mutate しない
"""
from __future__ import annotations

import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


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
def _fake_rs(monkeypatch):
    """requirements_service の async 関数を fake 化."""
    import services.requirements_service as rs

    state_log: list[dict] = []

    async def fake_start_step(workspace_id, step):
        state_log.append({"action": "start", "ws": workspace_id, "step": step})
        return {"status": "started", "step": step}

    async def fake_reply(workspace_id, step, message):
        state_log.append({"action": "reply", "ws": workspace_id, "step": step,
                          "msg_len": len(message)})
        return {"status": "replied", "step": step}

    async def fake_complete(workspace_id, step):
        state_log.append({"action": "complete", "ws": workspace_id, "step": step})
        return {"status": "completed", "step": step}

    async def fake_get_state(workspace_id):
        return {"workspace_id": workspace_id, "current_step": 1}

    async def fake_aggregated(workspace_id):
        return {"workspace_id": workspace_id, "tabs": {}}

    async def fake_get_or_create_center(workspace_id, step):
        return {"id": f"art-{workspace_id}-{step}"}

    async def fake_update_center(artifact_id, center, mark_status=None):
        return {"id": artifact_id, "center": center}

    async def fake_render_html(workspace_id, tab):
        return f"<html>{workspace_id}/{tab}</html>"

    async def fake_render_md(workspace_id, tab):
        return f"# {workspace_id}/{tab}"

    async def fake_render_json(workspace_id, tab):
        return {"workspace_id": workspace_id, "tab": tab}

    monkeypatch.setattr(rs, "start_step", fake_start_step)
    monkeypatch.setattr(rs, "reply", fake_reply)
    monkeypatch.setattr(rs, "complete_step", fake_complete)
    monkeypatch.setattr(rs, "get_state", fake_get_state)
    monkeypatch.setattr(rs, "get_aggregated_view", fake_aggregated)
    monkeypatch.setattr(rs, "get_or_create_center_artifact", fake_get_or_create_center)
    monkeypatch.setattr(rs, "update_center_artifact", fake_update_center)
    monkeypatch.setattr(rs, "render_html", fake_render_html)
    monkeypatch.setattr(rs, "render_markdown", fake_render_md)
    monkeypatch.setattr(rs, "render_json", fake_render_json)
    yield {"state_log": state_log}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 7 endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_start_step_endpoint_exists(client):
    r = client.post("/api/workspaces/1/requirements/start-step", json={"step": 1})
    assert r.status_code == 200


def test_ac1_reply_endpoint_exists(client):
    r = client.post("/api/workspaces/1/requirements/reply",
                     json={"step": 1, "message": "test reply"})
    assert r.status_code == 200


def test_ac1_complete_step_endpoint_exists(client):
    r = client.post("/api/workspaces/1/requirements/complete-step", json={"step": 1})
    assert r.status_code == 200


def test_ac1_state_endpoint_exists(client):
    r = client.get("/api/workspaces/1/requirements/state")
    assert r.status_code == 200


def test_ac1_aggregated_endpoint_exists(client):
    r = client.get("/api/workspaces/1/requirements/aggregated-view")
    assert r.status_code == 200


def test_ac1_center_endpoint_exists(client):
    r = client.patch(
        "/api/workspaces/1/requirements/center?step=1",
        json={"center": {"foo": "bar"}},
    )
    assert r.status_code == 200


def test_ac1_download_endpoint_exists(client):
    for fmt in ("html", "md", "json"):
        r = client.get(f"/api/workspaces/1/requirements/download/all.{fmt}")
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_reply_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/workspaces/1/requirements/reply",
                     json={"step": 2, "message": "test"})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_state_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/workspaces/1/requirements/state")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/workspaces/0/requirements/start-step", json={"step": 1})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "requirements.invalid_workspace_id"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 contract 不変 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_route_prefix_unchanged():
    from routers.requirements import router
    assert router.prefix == "/api/workspaces"


def test_ac3_all_existing_routes_still_defined():
    from routers.requirements import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    expected = {
        "/api/workspaces/{workspace_id}/requirements/start-step",
        "/api/workspaces/{workspace_id}/requirements/reply",
        "/api/workspaces/{workspace_id}/requirements/complete-step",
        "/api/workspaces/{workspace_id}/requirements/state",
        "/api/workspaces/{workspace_id}/requirements/aggregated-view",
        "/api/workspaces/{workspace_id}/requirements/center",
        "/api/workspaces/{workspace_id}/requirements/download/{tab}.{fmt}",
    }
    assert expected <= paths


def test_ac3_existing_request_models_backwards_compat():
    """AC-3: 旧 caller の payload で動く (actor_user_id は optional 追加)."""
    from routers.requirements import StartStepBody, ReplyBody, CompleteStepBody
    # 旧 field のみで作れる
    s = StartStepBody(step=1)
    assert s.step == 1
    r = ReplyBody(step=1, message="x")
    assert r.message == "x"
    c = CompleteStepBody(step=2)
    assert c.step == 2


def test_ac3_reply_emits_audit(client, _capture_audit):
    client.post(
        "/api/workspaces/5/requirements/reply",
        json={"step": 3, "message": "important info",
               "actor_user_id": "preston"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "requirements.message.replied"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "preston"
    assert events[0]["detail"]["workspace_id"] == 5
    assert events[0]["detail"]["step"] == 3


def test_ac3_complete_emits_audit(client, _capture_audit):
    client.post(
        "/api/workspaces/5/requirements/complete-step",
        json={"step": 4, "actor_user_id": "preston"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "requirements.step.completed"]
    assert events[-1]["detail"]["step"] == 4


def test_ac3_center_emits_audit(client, _capture_audit):
    client.patch(
        "/api/workspaces/5/requirements/center?step=2",
        json={"center": {"x": "y"}, "actor_user_id": "preston"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "requirements.center.updated"]
    assert events[-1]["detail"]["step"] == 2


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_workspace_id_rejected(client, _fake_rs):
    before = len(_fake_rs["state_log"])
    r = client.post("/api/workspaces/0/requirements/start-step", json={"step": 1})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.invalid_workspace_id"
    after = len(_fake_rs["state_log"])
    assert after == before


def test_ac4_step_out_of_range_rejected(client):
    for step in (0, 7, 100):
        r = client.post("/api/workspaces/1/requirements/start-step",
                         json={"step": step})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "requirements.invalid_step"


def test_ac4_empty_message_rejected(client):
    r = client.post("/api/workspaces/1/requirements/reply",
                     json={"step": 1, "message": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.invalid_message"


def test_ac4_long_message_rejected(client):
    r = client.post(
        "/api/workspaces/1/requirements/reply",
        json={"step": 1, "message": "x" * 20001},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.message_too_long"


def test_ac4_empty_actor_rejected(client):
    r = client.post("/api/workspaces/1/requirements/start-step",
                     json={"step": 1, "actor_user_id": "  "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "requirements.unauthorized"


def test_ac4_invalid_format_rejected(client):
    r = client.get("/api/workspaces/1/requirements/download/all.xml")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.invalid_format"


def test_ac4_invalid_center_dict_rejected(client):
    """center が dict 以外は 422 (Pydantic) or 400 (validator)."""
    r = client.patch("/api/workspaces/1/requirements/center?step=1",
                      json={"center": "not_dict"})
    assert r.status_code in (400, 422)


def test_ac4_invalid_step_for_center_rejected(client):
    r = client.patch("/api/workspaces/1/requirements/center?step=99",
                      json={"center": {}})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.invalid_step"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_rs):
    """AC-4 UNWANTED: rejected で audit emit / service 呼び出しなし."""
    client.post("/api/workspaces/0/requirements/start-step", json={"step": 1})
    client.post("/api/workspaces/1/requirements/reply", json={"step": 99, "message": "x"})
    client.post("/api/workspaces/1/requirements/reply", json={"step": 1, "message": "  "})
    events = [e for e in _capture_audit if "requirements." in e["event_type"]]
    # state.replied / step.started 等の "成功 event" は 0 件
    success_events = [e for e in events if e["event_type"] in (
        "requirements.step.started", "requirements.message.replied",
        "requirements.step.completed", "requirements.center.updated",
    )]
    assert len(success_events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/workspaces/0/requirements/start-step", {"step": 1}),
        ("POST", "/api/workspaces/1/requirements/start-step", {"step": 99}),
        ("POST", "/api/workspaces/1/requirements/reply", {"step": 1, "message": "  "}),
        ("POST", "/api/workspaces/1/requirements/reply",
         {"step": 1, "message": "x" * 20001}),
        ("POST", "/api/workspaces/1/requirements/start-step",
         {"step": 1, "actor_user_id": "  "}),
        ("GET", "/api/workspaces/1/requirements/download/all.xml", None),
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
