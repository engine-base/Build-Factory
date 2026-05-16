"""T-V3-B-09 / F-005b: Components backend (catalog + usage) tests.

AC マッピング:
  AC-F6  EVENT-DRIVEN  GET /components → 2xx {components}
  AC-F7  UNWANTED      GET /components w/o token → 401
  AC-F8  UNWANTED      GET /components bad input → 422
  AC-F9  EVENT-DRIVEN  GET /components/{id}/usage → 2xx {usages}
  AC-F10 UNWANTED      GET /components/{id}/usage w/o token → 401
  AC-F11 UNWANTED      GET /components/{id}/usage bad input → 422
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import components as svc


REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTER = REPO_ROOT / "backend" / "routers" / "components.py"
SERVICE = REPO_ROOT / "backend" / "services" / "components.py"
SCHEMAS = REPO_ROOT / "backend" / "schemas" / "components.py"


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


def test_service_list_components_empty_initially():
    """AC-F6: empty workspace → {components: []}."""
    r = svc.list_components(1)
    assert r == {"components": []}


def test_service_register_and_list_components():
    """AC-F6: registered components show up scoped per workspace."""
    svc.register_component(1, id="btn-primary", name="Primary Button", type="button")
    svc.register_component(1, id="card-spec", name="Spec Card", type="card")
    svc.register_component(2, id="btn-primary", name="W2 Button", type="button")
    r1 = svc.list_components(1)
    assert len(r1["components"]) == 2
    assert {c["id"] for c in r1["components"]} == {"btn-primary", "card-spec"}
    # workspace 2 isolated
    r2 = svc.list_components(2)
    assert len(r2["components"]) == 1
    assert r2["components"][0]["name"] == "W2 Button"


def test_service_get_component_usage_not_found_raises_404():
    """component が存在しなければ ComponentNotFoundError (→ 404)."""
    with pytest.raises(svc.ComponentNotFoundError):
        svc.get_component_usage(1, "no-such-cid")


def test_service_get_component_usage_empty():
    """AC-F9: usage が無い場合 {usages: []}."""
    svc.register_component(1, id="btn-primary", name="Primary Button")
    r = svc.get_component_usage(1, "btn-primary")
    assert r == {"usages": []}


def test_service_get_component_usage_with_data():
    """AC-F9: usage 登録後の取得."""
    svc.register_component(1, id="btn-primary", name="Primary Button")
    svc.register_usage(1, "btn-primary", "S-023", screen_name="Mock Browser")
    svc.register_usage(
        1, "btn-primary", "S-024", screen_name="Component Catalog",
        instance_count=3,
    )
    r = svc.get_component_usage(1, "btn-primary")
    assert len(r["usages"]) == 2
    sids = [u["screen_id"] for u in r["usages"]]
    assert sids == ["S-023", "S-024"]
    s024 = next(u for u in r["usages"] if u["screen_id"] == "S-024")
    assert s024["instance_count"] == 3


def test_service_validates_workspace_id():
    with pytest.raises(svc.ComponentValidationError):
        svc.list_components(0)
    with pytest.raises(svc.ComponentValidationError):
        svc.list_components(-1)


def test_service_validates_component_id():
    with pytest.raises(svc.ComponentValidationError):
        svc.get_component_usage(1, "../../etc/passwd")
    with pytest.raises(svc.ComponentValidationError):
        svc.get_component_usage(1, "")


# ══════════════════════════════════════════════════════════════════════
# Router-layer tests
# ══════════════════════════════════════════════════════════════════════


def test_router_get_components_returns_200(client):
    """AC-F6 EVENT-DRIVEN: GET /components → 200 + {components}."""
    r = client.get("/api/workspaces/1/components")
    assert r.status_code == 200
    body = r.json()
    assert body == {"components": []}


def test_router_get_components_with_registered(client):
    """AC-F6: with registered components."""
    svc.register_component(3, id="card-task", name="Task Card", type="card")
    r = client.get("/api/workspaces/3/components")
    assert r.status_code == 200
    body = r.json()
    assert len(body["components"]) == 1
    assert body["components"][0]["id"] == "card-task"


def test_router_get_components_unauthorized_returns_401(client, monkeypatch):
    """AC-F7 UNWANTED: GET /components w/o token → 401."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/1/components")
    assert r.status_code == 401


def test_router_get_components_invalid_workspace_id_returns_422(client):
    """AC-F8 UNWANTED: workspace_id <= 0 → 422."""
    r = client.get("/api/workspaces/0/components")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "components.invalid_workspace_id"


def test_router_get_component_usage_returns_200(client):
    """AC-F9 EVENT-DRIVEN: GET usage → 200 + {usages}."""
    svc.register_component(4, id="btn-primary", name="Primary")
    svc.register_usage(4, "btn-primary", "S-023")
    r = client.get("/api/workspaces/4/components/btn-primary/usage")
    assert r.status_code == 200
    body = r.json()
    assert len(body["usages"]) == 1
    assert body["usages"][0]["screen_id"] == "S-023"


def test_router_get_component_usage_not_found_returns_404(client):
    """If component not found → 404."""
    r = client.get("/api/workspaces/1/components/no-such/usage")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "components.not_found"


def test_router_get_component_usage_unauthorized_returns_401(client, monkeypatch):
    """AC-F10 UNWANTED: GET usage w/o token → 401."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/1/components/btn-primary/usage")
    assert r.status_code == 401


def test_router_get_component_usage_invalid_workspace_id_returns_422(client):
    """AC-F11 UNWANTED: workspace_id <= 0 → 422."""
    r = client.get("/api/workspaces/0/components/btn-primary/usage")
    assert r.status_code == 422


def test_openapi_routes_registered(client):
    spec = client.get("/openapi.json").json()
    paths = spec.get("paths", {})
    assert "/api/workspaces/{workspace_id}/components" in paths
    assert (
        "/api/workspaces/{workspace_id}/components/{component_id}/usage" in paths
    )
