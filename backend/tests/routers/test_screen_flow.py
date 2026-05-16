"""T-V3-B-09 / F-005b: Screen-flow backend tests.

AC マッピング:
  AC-F12 EVENT-DRIVEN  GET /screen-flow → 2xx {nodes, edges}
  AC-F13 UNWANTED      GET /screen-flow w/o token → 401
  AC-F14 UNWANTED      GET /screen-flow bad input → 422
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import screen_flow as svc


REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTER = REPO_ROOT / "backend" / "routers" / "screen_flow.py"
SERVICE = REPO_ROOT / "backend" / "services" / "screen_flow.py"
SCHEMAS = REPO_ROOT / "backend" / "schemas" / "screen_flow.py"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    am.DEV_BYPASS = True
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    svc.reset_store()
    yield
    svc.reset_store()


# ══════════════════════════════════════════════════════════════════════
# Structural sanity
# ══════════════════════════════════════════════════════════════════════


def test_router_file_exists():
    assert ROUTER.exists()


def test_service_file_exists():
    assert SERVICE.exists()


def test_schemas_file_exists():
    assert SCHEMAS.exists()


# ══════════════════════════════════════════════════════════════════════
# Service-layer tests
# ══════════════════════════════════════════════════════════════════════


def test_service_get_screen_flow_empty_initially():
    """AC-F12: empty graph → {nodes: [], edges: []}."""
    r = svc.get_screen_flow(1)
    assert r == {"nodes": [], "edges": []}


def test_service_register_node_and_get():
    """AC-F12: registered nodes appear scoped per workspace."""
    svc.register_node(1, screen_id="S-023", name="Mock Browser", kind="screen")
    svc.register_node(1, screen_id="S-024", name="Component Catalog")
    svc.register_node(2, screen_id="S-099", name="Other WS Screen")
    r1 = svc.get_screen_flow(1)
    assert {n["screen_id"] for n in r1["nodes"]} == {"S-023", "S-024"}
    r2 = svc.get_screen_flow(2)
    assert {n["screen_id"] for n in r2["nodes"]} == {"S-099"}


def test_service_register_edge_and_get():
    """AC-F12: edges scoped per workspace."""
    svc.register_node(1, screen_id="S-023")
    svc.register_node(1, screen_id="S-024")
    svc.register_edge(
        1, from_screen_id="S-023", to_screen_id="S-024",
        trigger="click 'open catalog'",
    )
    r = svc.get_screen_flow(1)
    assert len(r["edges"]) == 1
    e = r["edges"][0]
    assert e["from_screen_id"] == "S-023"
    assert e["to_screen_id"] == "S-024"
    assert e["trigger"] == "click 'open catalog'"


def test_service_validates_workspace_id():
    with pytest.raises(svc.ScreenFlowValidationError):
        svc.get_screen_flow(0)
    with pytest.raises(svc.ScreenFlowValidationError):
        svc.get_screen_flow(-1)


def test_service_validates_screen_id_in_register():
    with pytest.raises(svc.ScreenFlowValidationError):
        svc.register_node(1, screen_id="../../etc/passwd")
    with pytest.raises(svc.ScreenFlowValidationError):
        svc.register_edge(1, from_screen_id="", to_screen_id="S-024")


# ══════════════════════════════════════════════════════════════════════
# Router-layer tests
# ══════════════════════════════════════════════════════════════════════


def test_router_get_screen_flow_empty_returns_200(client):
    """AC-F12 EVENT-DRIVEN: GET /screen-flow → 200 + empty graph."""
    r = client.get("/api/workspaces/1/screen-flow")
    assert r.status_code == 200
    body = r.json()
    assert body == {"nodes": [], "edges": []}


def test_router_get_screen_flow_with_data(client):
    """AC-F12: GET /screen-flow returns nodes + edges."""
    svc.register_node(5, screen_id="S-023", name="Mock Browser")
    svc.register_node(5, screen_id="S-024", name="Catalog")
    svc.register_edge(5, from_screen_id="S-023", to_screen_id="S-024", trigger="next")
    r = client.get("/api/workspaces/5/screen-flow")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1


def test_router_get_screen_flow_unauthorized_returns_401(client, monkeypatch):
    """AC-F13 UNWANTED: GET /screen-flow w/o token → 401."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/1/screen-flow")
    assert r.status_code == 401


def test_router_get_screen_flow_invalid_workspace_id_returns_422(client):
    """AC-F14 UNWANTED: workspace_id <= 0 → 422."""
    r = client.get("/api/workspaces/0/screen-flow")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "screen_flow.invalid_workspace_id"


def test_openapi_route_registered(client):
    spec = client.get("/openapi.json").json()
    paths = spec.get("paths", {})
    assert "/api/workspaces/{workspace_id}/screen-flow" in paths
