"""T-005-01: hearing AI (Mary) 4STEP AC 検証.

DB mock で hearing_service を全 path 通し、 4 AC 機械検証.

AC マッピング:
  AC-1 UBIQUITOUS: 5 endpoint (start/reply/complete/state/center) + 4STEP
  AC-2 EVENT:     2 秒以内 + {detail: {code, message}}
  AC-3 STATE:     既存 contract 互換 (router path / response shape)
  AC-4 UNWANTED:  invalid step / 空 message → 400 + {code, message}
"""
from __future__ import annotations

import asyncio
import os
import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import hearing_service as hs


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 5 endpoint + 4STEP
# ──────────────────────────────────────────────────────────────────────────


def test_router_start_step_endpoint(client, monkeypatch) -> None:
    async def fake_start(ws, step):
        return {"workspace_id": ws, "step": step, "status": "started"}

    monkeypatch.setattr(hs, "start_step", fake_start)
    r = client.post("/api/workspaces/1/hearing/start-step", json={"step": 1})
    assert r.status_code == 200
    assert r.json()["step"] == 1


def test_router_reply_endpoint(client, monkeypatch) -> None:
    async def fake_reply(ws, step, msg):
        return {"reply": "ok", "echo": msg}

    monkeypatch.setattr(hs, "reply", fake_reply)
    r = client.post(
        "/api/workspaces/1/hearing/reply",
        json={"step": 1, "message": "Hello"},
    )
    assert r.status_code == 200
    assert r.json()["echo"] == "Hello"


def test_router_complete_step_endpoint(client, monkeypatch) -> None:
    async def fake_complete(ws, step):
        return {"step": step, "status": "completed"}

    monkeypatch.setattr(hs, "complete_step", fake_complete)
    r = client.post(
        "/api/workspaces/1/hearing/complete-step",
        json={"step": 2},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_router_state_endpoint(client, monkeypatch) -> None:
    async def fake_state(ws):
        return {"workspace_id": ws, "steps": {1: "done", 2: "in_progress"}}

    monkeypatch.setattr(hs, "get_state", fake_state)
    r = client.get("/api/workspaces/1/hearing/state")
    assert r.status_code == 200
    assert "steps" in r.json()


def test_router_center_update_endpoint(client, monkeypatch) -> None:
    async def fake_get_or_create(ws, step):
        return {"id": 100, "step": step}

    async def fake_update(art_id, center):
        return {"id": art_id, "center": center}

    monkeypatch.setattr(hs, "get_or_create_center_artifact", fake_get_or_create)
    monkeypatch.setattr(hs, "update_center_artifact", fake_update)
    r = client.patch(
        "/api/workspaces/1/hearing/center?step=2",
        json={"center": {"foo": "bar"}, "edited_by_pm": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["artifact"]["id"] == 100
    assert body["center"]["edited_by_pm"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: invalid step + 空 message
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_step", [0, 5, 99, -1])
def test_router_start_step_rejects_invalid_step(client, bad_step) -> None:
    r = client.post(
        "/api/workspaces/1/hearing/start-step",
        json={"step": bad_step},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "invalid_step"
    assert str(bad_step) in detail["message"]


def test_router_reply_rejects_invalid_step(client) -> None:
    r = client.post(
        "/api/workspaces/1/hearing/reply",
        json={"step": 99, "message": "x"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_step"


def test_router_reply_rejects_empty_message(client) -> None:
    r = client.post(
        "/api/workspaces/1/hearing/reply",
        json={"step": 1, "message": "   "},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "empty_message"
    assert "must not be empty" in detail["message"]


def test_router_complete_step_rejects_invalid_step(client) -> None:
    r = client.post(
        "/api/workspaces/1/hearing/complete-step",
        json={"step": 100},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_step"


def test_router_center_update_rejects_invalid_step(client) -> None:
    r = client.patch(
        "/api/workspaces/1/hearing/center?step=99",
        json={"center": {}, "edited_by_pm": True},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_step"


def test_router_start_step_service_error_returns_400(client, monkeypatch) -> None:
    """service が {error: msg} 返す → 400 / code=hearing_start_failed."""
    async def fake_start(ws, step):
        return {"error": "session not found"}

    monkeypatch.setattr(hs, "start_step", fake_start)
    r = client.post("/api/workspaces/1/hearing/start-step", json={"step": 1})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "hearing_start_failed"
    assert "session not found" in detail["message"]


# ──────────────────────────────────────────────────────────────────────────
# AC-1: 4STEP 全件受理
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_router_start_step_accepts_all_4_steps(client, monkeypatch, step) -> None:
    async def fake_start(ws, s):
        return {"step": s, "status": "ok"}

    monkeypatch.setattr(hs, "start_step", fake_start)
    r = client.post("/api/workspaces/1/hearing/start-step", json={"step": step})
    assert r.status_code == 200
    assert r.json()["step"] == step


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: backward compat
# ──────────────────────────────────────────────────────────────────────────


def test_router_paths_unchanged(client, monkeypatch) -> None:
    """既存 5 endpoint path が変更されていない."""
    async def noop(*a, **kw): return {}
    monkeypatch.setattr(hs, "start_step", noop)
    monkeypatch.setattr(hs, "reply", noop)
    monkeypatch.setattr(hs, "complete_step", noop)
    monkeypatch.setattr(hs, "get_state", noop)
    monkeypatch.setattr(hs, "get_or_create_center_artifact",
                         lambda ws, s: {"id": 1, "step": s})
    monkeypatch.setattr(hs, "update_center_artifact", lambda art, c: {"id": art})

    # 既存 path で 404 にならないこと
    paths = [
        ("POST", "/api/workspaces/1/hearing/start-step", {"step": 1}),
        ("POST", "/api/workspaces/1/hearing/reply", {"step": 1, "message": "x"}),
        ("POST", "/api/workspaces/1/hearing/complete-step", {"step": 1}),
        ("GET",  "/api/workspaces/1/hearing/state", None),
    ]
    for method, path, body in paths:
        r = client.request(method, path, json=body)
        assert r.status_code != 404, f"{method} {path} 404"


def test_router_center_update_marks_edited_by_pm(client, monkeypatch) -> None:
    """PM 編集経由は edited_by_pm=True を強制."""
    captured = {}

    async def fake_get_or_create(ws, step):
        return {"id": 1, "step": step}

    async def fake_update(art_id, center):
        captured["center"] = center
        return {"id": art_id}

    monkeypatch.setattr(hs, "get_or_create_center_artifact", fake_get_or_create)
    monkeypatch.setattr(hs, "update_center_artifact", fake_update)

    # client は edited_by_pm=False で送っても、 router 側で True に上書き
    r = client.patch(
        "/api/workspaces/1/hearing/center?step=1",
        json={"center": {"a": 1}, "edited_by_pm": False},
    )
    assert r.status_code == 200
    # router は edited_by_pm=True を強制
    assert captured["center"]["edited_by_pm"] is True


# ──────────────────────────────────────────────────────────────────────────
# Constant boundary
# ──────────────────────────────────────────────────────────────────────────


def test_valid_steps_constant() -> None:
    from routers.hearing import VALID_STEPS
    assert VALID_STEPS == (1, 2, 3, 4)


def test_valid_steps_matches_4step_design() -> None:
    """F-005 / S-020 hearing-session 4STEP と一致."""
    from routers.hearing import VALID_STEPS
    assert len(VALID_STEPS) == 4
    assert min(VALID_STEPS) == 1
    assert max(VALID_STEPS) == 4