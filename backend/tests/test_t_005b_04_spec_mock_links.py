"""T-005b-04: 仕様 ↔ モック双方向リンク — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-005b で spec ↔ mock CRUD endpoint + service 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + 重複 reject (整合性)
  AC-4 UNWANTED      : invalid input は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import spec_mock_link as svc


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    svc.reset_store()
    yield
    svc.reset_store()


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


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_create_link_basic():
    r = svc.create_link(1, "overview.目的", 100, created_by="alice")
    assert r["id"] == 1
    assert r["spec_section_id"] == "overview.目的"
    assert r["mock_id"] == 100
    assert r["created_by"] == "alice"


def test_service_duplicate_link_raises():
    svc.create_link(1, "x", 1)
    with pytest.raises(svc.DuplicateLinkError):
        svc.create_link(1, "x", 1)


def test_service_different_workspaces_allowed():
    svc.create_link(1, "x", 1)
    svc.create_link(2, "x", 1)  # 別 workspace は OK


def test_service_list_for_spec():
    svc.create_link(1, "screens.login", 100)
    svc.create_link(1, "screens.login", 101)
    svc.create_link(1, "screens.signup", 100)
    links = svc.list_links_for_spec("screens.login")
    assert len(links) == 2


def test_service_list_for_mock():
    svc.create_link(1, "a", 100)
    svc.create_link(1, "b", 100)
    svc.create_link(1, "c", 200)
    links = svc.list_links_for_mock(100)
    assert len(links) == 2


def test_service_delete_link():
    r = svc.create_link(1, "x", 1)
    assert svc.delete_link(r["id"]) is True
    assert svc.get_link(r["id"]) is None


def test_service_validate_empty_section():
    with pytest.raises(svc.SpecMockLinkError):
        svc.create_link(1, "  ", 1)


def test_service_validate_workspace_zero():
    with pytest.raises(svc.SpecMockLinkError):
        svc.create_link(0, "x", 1)


def test_service_validate_section_too_long():
    with pytest.raises(svc.SpecMockLinkError):
        svc.create_link(1, "x" * 201, 1)


def test_service_workspace_scoped_lookup():
    svc.create_link(1, "x", 100)
    svc.create_link(2, "x", 100)
    a = svc.list_links_for_spec("x", workspace_id=1)
    assert len(a) == 1
    assert a[0]["workspace_id"] == 1


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_create_endpoint_exists(client):
    r = client.post(
        "/api/spec-mock-links",
        json={"workspace_id": 1, "spec_section_id": "overview.目的", "mock_id": 100},
    )
    assert r.status_code == 200
    assert r.json()["mock_id"] == 100


def test_ac1_list_by_spec_endpoint_exists(client):
    client.post("/api/spec-mock-links",
                 json={"workspace_id": 1, "spec_section_id": "abc", "mock_id": 1})
    r = client.get("/api/spec-mock-links?spec_section_id=abc")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_ac1_list_by_mock_endpoint_exists(client):
    client.post("/api/spec-mock-links",
                 json={"workspace_id": 1, "spec_section_id": "y", "mock_id": 99})
    r = client.get("/api/spec-mock-links?mock_id=99")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_ac1_get_link_endpoint_exists(client):
    res = client.post("/api/spec-mock-links",
                       json={"workspace_id": 1, "spec_section_id": "g",
                              "mock_id": 1}).json()
    r = client.get(f"/api/spec-mock-links/{res['id']}")
    assert r.status_code == 200


def test_ac1_delete_link_endpoint_exists(client):
    res = client.post("/api/spec-mock-links",
                       json={"workspace_id": 1, "spec_section_id": "d",
                              "mock_id": 1}).json()
    r = client.delete(f"/api/spec-mock-links/{res['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_create_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/spec-mock-links",
                     json={"workspace_id": 1, "spec_section_id": "p", "mock_id": 1})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_list_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/spec-mock-links?spec_section_id=x")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/spec-mock-links",
                     json={"workspace_id": 0, "spec_section_id": "x", "mock_id": 1})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "spec_mock_links.invalid_workspace_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + 重複 reject
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_create_emits_audit(client, _capture_audit):
    client.post(
        "/api/spec-mock-links",
        json={"workspace_id": 5, "spec_section_id": "audit", "mock_id": 7,
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit
              if e["event_type"] == "spec_mock_links.created"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["spec_section_id"] == "audit"


def test_ac3_delete_emits_audit(client, _capture_audit):
    res = client.post("/api/spec-mock-links",
                       json={"workspace_id": 1, "spec_section_id": "del",
                              "mock_id": 1}).json()
    client.delete(f"/api/spec-mock-links/{res['id']}?actor_user_id=bob")
    events = [e for e in _capture_audit
              if e["event_type"] == "spec_mock_links.deleted"]
    assert len(events) >= 1
    assert events[-1]["user_id"] == "bob"


def test_ac3_duplicate_returns_409(client):
    client.post("/api/spec-mock-links",
                 json={"workspace_id": 1, "spec_section_id": "dup", "mock_id": 1})
    r = client.post("/api/spec-mock-links",
                     json={"workspace_id": 1, "spec_section_id": "dup", "mock_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "spec_mock_links.duplicate"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_workspace_id_rejected(client):
    r = client.post("/api/spec-mock-links",
                     json={"workspace_id": 0, "spec_section_id": "x", "mock_id": 1})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "spec_mock_links.invalid_workspace_id"


def test_ac4_empty_section_rejected(client):
    r = client.post("/api/spec-mock-links",
                     json={"workspace_id": 1, "spec_section_id": "  ", "mock_id": 1})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "spec_mock_links.invalid_spec_section_id"


def test_ac4_long_section_rejected(client):
    r = client.post(
        "/api/spec-mock-links",
        json={"workspace_id": 1, "spec_section_id": "x" * 201, "mock_id": 1},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "spec_mock_links.spec_section_id_too_long"


def test_ac4_invalid_mock_id_rejected(client):
    r = client.post("/api/spec-mock-links",
                     json={"workspace_id": 1, "spec_section_id": "x", "mock_id": 0})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "spec_mock_links.invalid_mock_id"


def test_ac4_empty_actor_rejected(client):
    r = client.post(
        "/api/spec-mock-links",
        json={"workspace_id": 1, "spec_section_id": "x", "mock_id": 1,
               "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "spec_mock_links.unauthorized"


def test_ac4_list_missing_query_rejected(client):
    r = client.get("/api/spec-mock-links")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "spec_mock_links.missing_query"


def test_ac4_get_invalid_id_rejected(client):
    r = client.get("/api/spec-mock-links/0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "spec_mock_links.invalid_id"


def test_ac4_get_not_found(client):
    r = client.get("/api/spec-mock-links/999999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "spec_mock_links.not_found"


def test_ac4_delete_not_found(client):
    r = client.delete("/api/spec-mock-links/999999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "spec_mock_links.not_found"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/spec-mock-links",
                 json={"workspace_id": 0, "spec_section_id": "x", "mock_id": 1})
    client.post("/api/spec-mock-links",
                 json={"workspace_id": 1, "spec_section_id": " ", "mock_id": 1})
    events = [e for e in _capture_audit
              if e["event_type"] == "spec_mock_links.created"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/spec-mock-links",
         {"workspace_id": 0, "spec_section_id": "x", "mock_id": 1}),
        ("POST", "/api/spec-mock-links",
         {"workspace_id": 1, "spec_section_id": "  ", "mock_id": 1}),
        ("POST", "/api/spec-mock-links",
         {"workspace_id": 1, "spec_section_id": "x", "mock_id": 0}),
        ("POST", "/api/spec-mock-links",
         {"workspace_id": 1, "spec_section_id": "x", "mock_id": 1,
          "actor_user_id": "  "}),
        ("GET", "/api/spec-mock-links", None),
        ("GET", "/api/spec-mock-links/0", None),
        ("GET", "/api/spec-mock-links/999999", None),
        ("DELETE", "/api/spec-mock-links/999999", None),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        elif method == "DELETE":
            r = client.delete(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
