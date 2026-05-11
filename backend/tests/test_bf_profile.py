"""T-023-01: bf_profile の AC テスト."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services.bf_profile import VALID_THEMES, upsert_profile


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def test_valid_themes_set() -> None:
    assert VALID_THEMES == {"light", "dark", "system"}


@pytest.mark.asyncio
async def test_invalid_theme_raises() -> None:
    with pytest.raises(ValueError):
        await upsert_profile("u1", theme="rainbow")


def test_router_get_returns_default_for_unknown(client) -> None:
    r = client.get("/api/bf-profile", params={"user_id": "unknown_user_zzz"})
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "unknown_user_zzz"
    assert body["theme"] == "light"  # default


def test_router_patch_invalid_theme_returns_400(client) -> None:
    r = client.patch(
        "/api/bf-profile",
        params={"user_id": "u1"},
        json={"theme": "rainbow"},
    )
    assert r.status_code == 400


def test_router_patch_with_valid_data_returns_dict(client) -> None:
    r = client.patch(
        "/api/bf-profile",
        params={"user_id": "test_user_xyz"},
        json={"display_name": "Test User", "theme": "dark", "bio": "hello"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "test_user_xyz"


def test_router_get_user_id_required(client) -> None:
    r = client.get("/api/bf-profile")
    assert r.status_code == 422  # missing required query param
