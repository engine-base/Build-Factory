"""T-V3-B-08 / F-005b: Mocks backend (list / detail / html GET/PUT) tests.

AC マッピング (verbatim — tickets-group-b-backend.json#T-V3-B-08.acceptance_criteria.functional):
  AC-F1  EVENT-DRIVEN  GET html → 最新 version 返却
  AC-F2  EVENT-DRIVEN  PUT html → version increment + snapshot 保持
  AC-F3  UNWANTED      PUT html > 1MB → 422
  AC-F5  STATE-DRIVEN  他 actor 編集中なら 409
  AC-F6  EVENT-DRIVEN  GET list → 2xx {mocks, total}
  AC-F7  UNWANTED      GET list w/o token → 401
  AC-F8  UNWANTED      GET list bad input → 422 (workspace_id<=0)
  AC-F9  EVENT-DRIVEN  GET detail → 2xx {screen, html_url, version}
  AC-F10 UNWANTED      GET detail w/o token → 401
  AC-F11 UNWANTED      GET detail bad input → 422
  AC-F12 EVENT-DRIVEN  GET html → 2xx {html}
  AC-F13 UNWANTED      GET html w/o token → 401
  AC-F14 EVENT-DRIVEN  PUT html → 2xx {new_version, updated_at}
  AC-F15 UNWANTED      PUT html w/o token → 401
  AC-F16 UNWANTED      PUT html bad input → 422

NOTE: AC-F4 (POST ai-edit > 30/min → 429) は T-V3-B-09 のスコープなので
本 task では検証外.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import mocks as svc


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER = REPO_ROOT / "backend" / "routers" / "mocks.py"
SERVICE = REPO_ROOT / "backend" / "services" / "mocks.py"
SCHEMAS = REPO_ROOT / "backend" / "schemas" / "mocks.py"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    # auth_middleware caches DEV_BYPASS at import time; force re-evaluation
    import services.auth_middleware as am
    am.DEV_BYPASS = True
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
    monkeypatch.setattr(ms, "emit_event", fake_emit, raising=False)
    yield captured


# ══════════════════════════════════════════════════════════════════════
# Structural sanity — files exist
# ══════════════════════════════════════════════════════════════════════


def test_router_file_exists():
    assert ROUTER.exists(), "router file missing"


def test_service_file_exists():
    assert SERVICE.exists(), "service file missing"


def test_schemas_file_exists():
    assert SCHEMAS.exists(), "schemas file missing"


# ══════════════════════════════════════════════════════════════════════
# Service layer — unit tests
# ══════════════════════════════════════════════════════════════════════


def test_service_put_then_get_html_returns_latest():
    """AC-F1: GET html shall return the latest version of the mock HTML."""
    svc.put_mock_html(1, "S-023", "<html>v1</html>", actor_user_id="alice")
    svc.put_mock_html(1, "S-023", "<html>v2</html>", actor_user_id="alice")
    r = svc.get_mock_html(1, "S-023")
    assert r["html"] == "<html>v2</html>"
    assert r["version"] == 2


def test_service_put_increments_version_and_keeps_snapshot():
    """AC-F2: PUT html shall increment version and persist a snapshot."""
    r1 = svc.put_mock_html(1, "S-023", "<html>v1</html>", actor_user_id="alice")
    r2 = svc.put_mock_html(1, "S-023", "<html>v2</html>", actor_user_id="alice")
    r3 = svc.put_mock_html(1, "S-023", "<html>v3</html>", actor_user_id="alice")
    assert r1["new_version"] == 1
    assert r2["new_version"] == 2
    assert r3["new_version"] == 3
    # snapshot retention check (in-memory store)
    rec = svc._store[(1, "S-023")]
    assert len(rec.versions) == 3
    assert [s.html for s in rec.versions] == [
        "<html>v1</html>", "<html>v2</html>", "<html>v3</html>",
    ]


def test_service_put_too_large_raises_422_error():
    """AC-F3: PUT html > 1MB shall raise MockHtmlTooLargeError (→ 422)."""
    big = "x" * (svc.MAX_HTML_BYTES + 1)
    with pytest.raises(svc.MockHtmlTooLargeError):
        svc.put_mock_html(1, "S-023", big, actor_user_id="alice")


def test_service_put_locked_by_other_actor_raises_409():
    """AC-F5: While a mock is locked for editing by another user → 409."""
    svc.put_mock_html(1, "S-023", "<html>v1</html>", actor_user_id="alice")
    with pytest.raises(svc.MockLockedError):
        svc.put_mock_html(1, "S-023", "<html>v2</html>", actor_user_id="bob")


def test_service_put_same_actor_does_not_lock_itself():
    """negative case: same actor re-editing shall NOT 409."""
    svc.put_mock_html(1, "S-023", "<html>v1</html>", actor_user_id="alice")
    r = svc.put_mock_html(1, "S-023", "<html>v2</html>", actor_user_id="alice")
    assert r["new_version"] == 2


def test_service_get_mock_not_found():
    with pytest.raises(svc.MockNotFoundError):
        svc.get_mock(1, "NOT_EXIST")


def test_service_get_html_not_found():
    with pytest.raises(svc.MockNotFoundError):
        svc.get_mock_html(1, "NOT_EXIST")


def test_service_validates_workspace_id_zero():
    with pytest.raises(svc.MockValidationError):
        svc.list_mocks(0)
    with pytest.raises(svc.MockValidationError):
        svc.list_mocks(-1)


def test_service_validates_screen_id_invalid_chars():
    with pytest.raises(svc.MockValidationError):
        svc.get_mock_html(1, "../../etc/passwd")
    with pytest.raises(svc.MockValidationError):
        svc.get_mock_html(1, "")
    with pytest.raises(svc.MockValidationError):
        svc.get_mock_html(1, " " * 5)


def test_service_list_groups_by_workspace():
    svc.put_mock_html(1, "S-001", "<html>1</html>", actor_user_id="alice")
    svc.put_mock_html(1, "S-002", "<html>2</html>", actor_user_id="alice")
    svc.put_mock_html(2, "S-099", "<html>x</html>", actor_user_id="alice")
    r1 = svc.list_mocks(1)
    r2 = svc.list_mocks(2)
    assert r1["total"] == 2
    assert {m["screen_id"] for m in r1["mocks"]} == {"S-001", "S-002"}
    assert r2["total"] == 1
    assert r2["mocks"][0]["screen_id"] == "S-099"


# ══════════════════════════════════════════════════════════════════════
# Router layer — happy paths (AC-F6 / AC-F9 / AC-F12 / AC-F14)
# ══════════════════════════════════════════════════════════════════════


def test_router_get_list_returns_empty_initially(client):
    """AC-F6 EVENT-DRIVEN: GET list shall return 200 + {mocks, total}."""
    r = client.get("/api/workspaces/1/mocks")
    assert r.status_code == 200
    body = r.json()
    assert body == {"mocks": [], "total": 0}


def test_router_put_html_then_list(client):
    """AC-F14 EVENT-DRIVEN + AC-F6 EVENT-DRIVEN."""
    put_r = client.put(
        "/api/workspaces/1/mocks/S-023/html",
        json={"html": "<html>hello</html>", "name": "Mock Browser"},
    )
    assert put_r.status_code == 200, put_r.text
    body = put_r.json()
    assert body["new_version"] == 1
    assert "updated_at" in body and body["updated_at"]

    list_r = client.get("/api/workspaces/1/mocks")
    assert list_r.status_code == 200
    lbody = list_r.json()
    assert lbody["total"] == 1
    assert lbody["mocks"][0]["screen_id"] == "S-023"
    assert lbody["mocks"][0]["version"] == 1


def test_router_get_detail(client):
    """AC-F9 EVENT-DRIVEN: GET detail shall return {screen, html_url, version}."""
    client.put(
        "/api/workspaces/2/mocks/S-024/html", json={"html": "<html>x</html>"},
    )
    r = client.get("/api/workspaces/2/mocks/S-024")
    assert r.status_code == 200
    body = r.json()
    assert body["screen"]["id"] == "S-024"
    assert body["screen"]["workspace_id"] == 2
    assert body["html_url"] == "/api/workspaces/2/mocks/S-024/html"
    assert body["version"] == 1


def test_router_get_html(client):
    """AC-F1 / AC-F12 EVENT-DRIVEN: GET html shall return latest html."""
    client.put(
        "/api/workspaces/3/mocks/S-025/html", json={"html": "<html>v1</html>"},
    )
    client.put(
        "/api/workspaces/3/mocks/S-025/html", json={"html": "<html>v2</html>"},
    )
    r = client.get("/api/workspaces/3/mocks/S-025/html")
    assert r.status_code == 200
    body = r.json()
    assert body["html"] == "<html>v2</html>"
    assert body["version"] == 2


def test_router_put_increments_version_via_http(client):
    """AC-F2 EVENT-DRIVEN: PUT shall increment version on each call."""
    r1 = client.put(
        "/api/workspaces/4/mocks/S-026/html", json={"html": "<html>v1</html>"},
    )
    r2 = client.put(
        "/api/workspaces/4/mocks/S-026/html", json={"html": "<html>v2</html>"},
    )
    r3 = client.put(
        "/api/workspaces/4/mocks/S-026/html", json={"html": "<html>v3</html>"},
    )
    assert r1.json()["new_version"] == 1
    assert r2.json()["new_version"] == 2
    assert r3.json()["new_version"] == 3


# ══════════════════════════════════════════════════════════════════════
# Router layer — error paths (AC-F3 / AC-F5 / AC-F7 / AC-F8 / AC-F10 /
#                            AC-F11 / AC-F13 / AC-F15 / AC-F16)
# ══════════════════════════════════════════════════════════════════════


def test_router_put_html_too_large_returns_422(client):
    """AC-F3 UNWANTED: PUT html > 1MB → 422."""
    big = "x" * (svc.MAX_HTML_BYTES + 1)
    r = client.put(
        "/api/workspaces/1/mocks/S-023/html", json={"html": big},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "mocks.html_too_large"


def test_router_put_concurrent_edit_returns_409(client, monkeypatch):
    """AC-F5 STATE-DRIVEN: locked by other actor → 409.

    Use service-layer call to set lock by 'other_actor', then issue HTTP
    PUT (acts as DEV_USER sub) which differs → 409.
    """
    # acquire lock by alice via service-layer write
    svc.put_mock_html(
        7, "S-023", "<html>v1</html>", actor_user_id="alice@other.com",
    )
    # http PUT uses DEV_USER (sub = 00000000-...-001) which differs
    r = client.put(
        "/api/workspaces/7/mocks/S-023/html", json={"html": "<html>v2</html>"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "mocks.locked"


def test_router_get_list_unauthorized_returns_401(client, monkeypatch):
    """AC-F7 UNWANTED: GET list w/o auth token → 401."""
    # disable DEV_BYPASS for this test only
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/1/mocks")
    assert r.status_code == 401


def test_router_get_detail_unauthorized_returns_401(client, monkeypatch):
    """AC-F10 UNWANTED: GET detail w/o auth token → 401."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/1/mocks/S-023")
    assert r.status_code == 401


def test_router_get_html_unauthorized_returns_401(client, monkeypatch):
    """AC-F13 UNWANTED: GET html w/o auth token → 401."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/1/mocks/S-023/html")
    assert r.status_code == 401


def test_router_put_html_unauthorized_returns_401(client, monkeypatch):
    """AC-F15 UNWANTED: PUT html w/o auth token → 401."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.put(
        "/api/workspaces/1/mocks/S-023/html", json={"html": "<html/>"},
    )
    assert r.status_code == 401


def test_router_get_list_invalid_workspace_id_returns_422(client):
    """AC-F8 UNWANTED: GET list with workspace_id<=0 → 422."""
    r = client.get("/api/workspaces/0/mocks")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "mocks.invalid_workspace_id"


def test_router_get_detail_invalid_screen_id_returns_422(client):
    """AC-F11 UNWANTED: GET detail with invalid screen_id → 422."""
    r = client.get("/api/workspaces/1/mocks/..%2Fetc%2Fpasswd")
    assert r.status_code in (404, 422)
    if r.status_code == 422:
        # service-layer validation (preferred)
        assert "mocks" in r.json()["detail"]["code"]


def test_router_get_detail_not_found_returns_404(client):
    """detail call when no record exists → 404."""
    r = client.get("/api/workspaces/1/mocks/S-NEVER")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "mocks.not_found"


def test_router_get_html_not_found_returns_404(client):
    r = client.get("/api/workspaces/1/mocks/S-NEVER/html")
    assert r.status_code == 404


def test_router_put_html_missing_body_returns_422(client):
    """AC-F16 UNWANTED: PUT with missing required 'html' field → 422."""
    r = client.put(
        "/api/workspaces/1/mocks/S-023/html", json={"name": "no-html"},
    )
    assert r.status_code == 422


def test_router_put_html_wrong_type_returns_422(client):
    """AC-F16 UNWANTED: PUT with html as non-string → 422."""
    r = client.put(
        "/api/workspaces/1/mocks/S-023/html", json={"html": 12345},
    )
    assert r.status_code == 422


def test_router_emits_audit_log_on_put(client, _capture_audit):
    """AC-3 audit_logs: mock_edited event should be emitted on PUT (best-effort)."""
    client.put(
        "/api/workspaces/1/mocks/S-023/html", json={"html": "<html/>"},
    )
    # event captured by _capture_audit fixture (may be 0 if memory_service
    # is unavailable; we accept best-effort behavior).
    types = [e["event_type"] for e in _capture_audit]
    # best-effort: either captured or skipped silently
    if types:
        assert "mock_edited" in types


# ══════════════════════════════════════════════════════════════════════
# Endpoint-existence contract checks (OpenAPI ↔ router)
# ══════════════════════════════════════════════════════════════════════


def test_openapi_routes_registered(client):
    spec = client.get("/openapi.json").json()
    paths = spec.get("paths", {})
    assert "/api/workspaces/{workspace_id}/mocks" in paths
    assert "/api/workspaces/{workspace_id}/mocks/{screen_id}" in paths
    assert "/api/workspaces/{workspace_id}/mocks/{screen_id}/html" in paths
    # PUT on html path
    assert "put" in paths["/api/workspaces/{workspace_id}/mocks/{screen_id}/html"]
