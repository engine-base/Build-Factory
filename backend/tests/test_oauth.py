"""T-023-04: OAuth providers の smoke test."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.oauth_providers import (
    PROVIDERS, build_authorize_url, exchange_code,
    save_token, load_token, delete_token,
    UnknownProviderError, OAuthConfigError,
)


@pytest.fixture(autouse=True)
def _isolated_creds_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BF_CREDENTIALS_DIR", str(tmp_path))
    import importlib
    import services.credentials_store as cs
    importlib.reload(cs)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def test_known_providers() -> None:
    assert set(PROVIDERS.keys()) == {"slack", "github", "anthropic"}


def test_authorize_url_requires_client_id(monkeypatch) -> None:
    monkeypatch.delenv("SLACK_CLIENT_ID", raising=False)
    with pytest.raises(OAuthConfigError):
        build_authorize_url("slack", state="abc", redirect_uri="https://x/cb")


def test_authorize_url_built_correctly(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_CLIENT_ID", "test-client-id")
    url = build_authorize_url(
        "slack", state="s123", redirect_uri="https://app/cb", scope="chat:write",
    )
    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    assert "client_id=test-client-id" in url
    assert "state=s123" in url
    assert "scope=chat" in url  # url-encode で : は %3A になる


def test_authorize_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError):
        build_authorize_url("notion", state="x", redirect_uri="https://x/cb")


def test_save_and_load_token_roundtrip() -> None:
    save_token("slack", "user_1", {"access_token": "xoxb-abc", "scope": "chat:write"})
    token = load_token("slack", "user_1")
    assert token is not None
    assert token["access_token"] == "xoxb-abc"


def test_delete_token() -> None:
    save_token("github", "user_2", {"access_token": "ghp-x"})
    assert delete_token("github", "user_2") is True
    assert load_token("github", "user_2") is None


# ──────────────────────────────────────────
# Router E2E
# ──────────────────────────────────────────

def test_router_providers_endpoint(client) -> None:
    r = client.get("/api/oauth/providers")
    assert r.status_code == 200
    assert set(r.json()["providers"]) == {"slack", "github", "anthropic"}


def test_router_authorize_unknown_provider(client) -> None:
    r = client.get("/api/oauth/notion/authorize", params={"redirect_uri": "https://x/cb"})
    assert r.status_code == 404


def test_router_authorize_missing_config(client, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    r = client.get("/api/oauth/github/authorize", params={"redirect_uri": "https://x/cb"})
    assert r.status_code == 503


def test_router_authorize_ok(client, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "gh-id")
    r = client.get(
        "/api/oauth/github/authorize",
        params={"redirect_uri": "https://app/cb"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "authorize_url" in body
    assert body["authorize_url"].startswith("https://github.com/login/oauth/authorize?")
    assert "state" in body


def test_router_status_not_connected(client) -> None:
    r = client.get("/api/oauth/slack/status", params={"owner_id": "no_such_user"})
    assert r.status_code == 200
    assert r.json()["connected"] is False
