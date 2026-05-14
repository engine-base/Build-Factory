"""T-004-02: workspace 作成 API (workspaces.py REFACTOR) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-004 workspace 作成 endpoint 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 contract (route prefix / shape) 不変 + audit emit
  AC-4 UNWANTED      : invalid input / 空 actor / 不明 workspace は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time

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
def _fake_ws_service(monkeypatch):
    """workspace_service の create/get を fake."""
    import services.workspace_service as wsvc

    store: dict[int, dict] = {}
    next_id = {"v": 100}

    async def fake_create(*, account_id, name, description=None,
                           project_meta=None, creator_user_id="masato",
                           preferred_provider=None):
        # T-024-04 cascade: preferred_provider を受け取れるように後方互換 update.
        if name == "_FORCE_ERR_":
            raise ValueError("name conflict simulated")
        wid = next_id["v"]
        next_id["v"] += 1
        row = {
            "id": wid, "account_id": account_id, "name": name,
            "description": description, "creator_user_id": creator_user_id,
            "status": "active",
            "preferred_provider": preferred_provider or "auto",
        }
        store[wid] = row
        return row

    async def fake_get(workspace_id):
        return store.get(workspace_id)

    monkeypatch.setattr(wsvc, "create_workspace", fake_create)
    monkeypatch.setattr(wsvc, "get_workspace", fake_get)
    yield {"store": store}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_create_endpoint_exists(client):
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "テスト案件",
               "creator_user_id": "alice"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "テスト案件"
    assert "id" in body


def test_ac1_get_endpoint_exists(client):
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "get-test", "creator_user_id": "alice"},
    )
    wid = r.json()["id"]
    r = client.get(f"/api/workspaces/{wid}")
    assert r.status_code == 200
    assert r.json()["id"] == wid


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_create_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "perf-test", "creator_user_id": "alice"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/workspaces",
        json={"account_id": 0, "name": "x", "creator_user_id": "alice"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "workspaces.invalid_account_id"
    assert "message" in body["detail"]


def test_ac2_get_404_uses_detail_code_message(client):
    r = client.get("/api/workspaces/999999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "workspaces.not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 contract 不変 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_route_prefix_unchanged():
    from routers.workspaces import router
    assert router.prefix == "/api/workspaces"


def test_ac3_existing_routes_still_defined():
    from routers.workspaces import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    expected = {
        "/api/workspaces",
        "/api/workspaces/{workspace_id}",
        "/api/workspaces/{workspace_id}/members",
        "/api/workspaces/{workspace_id}/members/{user_id}",
        "/api/workspaces/{workspace_id}/transfer-ownership",
        "/api/workspaces/{workspace_id}/invitations",
    }
    assert expected <= paths


def test_ac3_workspace_create_model_backwards_compat():
    from routers.workspaces import WorkspaceCreate
    fields = WorkspaceCreate.model_fields
    expected = {"account_id", "name", "description", "project_meta", "creator_user_id"}
    assert expected <= set(fields.keys())  # 旧 field 全件保持


def test_ac3_create_emits_audit(client, _capture_audit):
    client.post(
        "/api/workspaces",
        json={"account_id": 5, "name": "audit-test", "creator_user_id": "carol"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "workspaces.created"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "carol"
    assert events[0]["detail"]["account_id"] == 5
    assert events[0]["detail"]["name"] == "audit-test"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_account_id_zero_rejected(client, _fake_ws_service):
    before = len(_fake_ws_service["store"])
    r = client.post(
        "/api/workspaces",
        json={"account_id": 0, "name": "x", "creator_user_id": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.invalid_account_id"
    after = len(_fake_ws_service["store"])
    assert after == before  # mutate なし


def test_ac4_account_id_negative_rejected(client):
    r = client.post(
        "/api/workspaces",
        json={"account_id": -1, "name": "x", "creator_user_id": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.invalid_account_id"


def test_ac4_empty_name_rejected(client, _fake_ws_service):
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "   ", "creator_user_id": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.invalid_name"


def test_ac4_long_name_rejected(client):
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "x" * 101, "creator_user_id": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.name_too_long"


def test_ac4_empty_creator_rejected(client):
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "ok", "creator_user_id": "   "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "workspaces.unauthorized"


def test_ac4_long_description_rejected(client):
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "ok", "creator_user_id": "alice",
               "description": "x" * 2001},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.description_too_long"


def test_ac4_service_value_error_returns_400(client):
    """service が ValueError raise したら 400 create_failed."""
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "_FORCE_ERR_", "creator_user_id": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.create_failed"


def test_ac4_get_invalid_id_rejected(client):
    r = client.get("/api/workspaces/0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.invalid_id"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_ws_service):
    """AC-4 UNWANTED: rejected create で workspaces.created を emit しない."""
    client.post("/api/workspaces",
                 json={"account_id": 0, "name": "x", "creator_user_id": "a"})
    client.post("/api/workspaces",
                 json={"account_id": 1, "name": "   ", "creator_user_id": "a"})
    events = [e for e in _capture_audit if e["event_type"] == "workspaces.created"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/workspaces",
         {"account_id": 0, "name": "x", "creator_user_id": "a"}),
        ("POST", "/api/workspaces",
         {"account_id": 1, "name": "   ", "creator_user_id": "a"}),
        ("POST", "/api/workspaces",
         {"account_id": 1, "name": "ok", "creator_user_id": "   "}),
        ("POST", "/api/workspaces",
         {"account_id": 1, "name": "x" * 101, "creator_user_id": "a"}),
        ("GET", "/api/workspaces/0", None),
        ("GET", "/api/workspaces/999999", None),
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
