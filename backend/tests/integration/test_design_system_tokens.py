"""T-V3-D-10: GET /api/design-system/tokens integration tests (F-029).

AC mapping (Tier 2 functional):
  - AC-F3 : GET /api/design-system/tokens → 200 + { tokens: DesignToken[] }
            (color / typography / spacing / icons sourced from
            docs/mocks/2026-05-09_v1/design-tokens.md).
  - Aux   : 401 (no auth — Wave 4 では auth 必須)
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-test")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "service-test")
os.environ.setdefault("SUPABASE_JWT_SECRET", "secret-test")


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def _no_auth_client():
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "0"
    import importlib
    from services import auth_middleware
    importlib.reload(auth_middleware)
    import main
    importlib.reload(main)
    return TestClient(main.app, raise_server_exceptions=False)


def _restore_dev_bypass():
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import importlib
    from services import auth_middleware
    importlib.reload(auth_middleware)
    import main
    importlib.reload(main)


# ──────────────────────────────────────────────────────────────────────────────
# AC-F3 happy path
# ──────────────────────────────────────────────────────────────────────────────


def test_get_design_system_tokens_returns_catalog(client):
    """AC-F3: 200 + { tokens: DesignToken[] } with required categories."""
    r = client.get("/api/design-system/tokens")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tokens" in body
    tokens = body["tokens"]
    assert isinstance(tokens, list)
    assert len(tokens) >= 20  # color (15) + typography (8) + spacing (7) + radius (3) + icons (1)
    # AC-F3: 必須カテゴリ (color / typography / spacing / icons) を網羅
    cats = {t["category"] for t in tokens}
    assert "color" in cats
    assert "typography" in cats
    assert "spacing" in cats
    assert "icons" in cats
    # source 明記
    assert body.get("source") == "docs/mocks/2026-05-09_v1/design-tokens.md"


def test_brand_primary_color_matches_engine_base_green(client):
    """AC-F3 + CLAUDE.md §5.2: ENGINE BASE green = #1a6648."""
    r = client.get("/api/design-system/tokens")
    assert r.status_code == 200
    tokens = r.json()["tokens"]
    primary = next(
        (t for t in tokens if t.get("token") == "--bf-primary"),
        None,
    )
    assert primary is not None, "--bf-primary token must be present"
    assert primary["value"] == "#1a6648"
    assert primary["category"] == "color"
    assert primary["subcategory"] == "brand"


def test_lucide_icons_token_present(client):
    """CLAUDE.md §5.1: Lucide Icons のみ (絵文字禁止)."""
    r = client.get("/api/design-system/tokens")
    assert r.status_code == 200
    tokens = r.json()["tokens"]
    icon = next((t for t in tokens if t.get("token") == "lucide"), None)
    assert icon is not None
    assert icon["category"] == "icons"
    assert "lucide" in icon["value"].lower()


def test_all_tokens_have_required_fields(client):
    """schema: 各 token に token/value/category/subcategory/description 必須."""
    r = client.get("/api/design-system/tokens")
    assert r.status_code == 200
    tokens = r.json()["tokens"]
    for t in tokens:
        assert "token" in t and t["token"]
        assert "value" in t and t["value"]
        assert "category" in t and t["category"]
        assert "subcategory" in t
        assert "description" in t


def test_get_design_system_tokens_unauthorized_returns_401():
    """401 UNWANTED: no auth → 401."""
    try:
        nc = _no_auth_client()
        r = nc.get("/api/design-system/tokens")
        assert r.status_code == 401
    finally:
        _restore_dev_bypass()
