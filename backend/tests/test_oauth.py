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


# ──────────────────────────────────────────
# T-023-04 AC: UNWANTED — CSRF state mismatch → 400 (code=csrf_mismatch)
# ──────────────────────────────────────────
def test_router_callback_csrf_mismatch_returns_400(client) -> None:
    r = client.post(
        "/api/oauth/slack/callback",
        json={
            "code": "x",
            "redirect_uri": "https://app/cb",
            "owner_id": "user_z",
            "expected_state": "AAA",
            "received_state": "BBB",
        },
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict) and detail.get("code") == "csrf_mismatch"


# ──────────────────────────────────────────
# T-023-04 AC: EVENT — disconnect 後 status は connected=False
# ──────────────────────────────────────────
def test_router_disconnect_clears_token(client) -> None:
    # 直接 save_token → DELETE → status confirm
    save_token("anthropic", "user_dc", {"access_token": "k", "scope": "x"})
    r = client.delete("/api/oauth/anthropic", params={"owner_id": "user_dc"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r2 = client.get("/api/oauth/anthropic/status", params={"owner_id": "user_dc"})
    assert r2.json()["connected"] is False


# ──────────────────────────────────────────────────────────────────────────
# AC 全網羅 補完 + cov 70% → 90%+
# ──────────────────────────────────────────────────────────────────────────

import sys
import types
from typing import Any
from services import oauth_providers as op


# ────── AC-1 UBIQUITOUS: 3 provider × 4 endpoint ──────


def test_three_providers_supported() -> None:
    """AC-1: slack / github / anthropic の 3 種."""
    assert set(PROVIDERS.keys()) == {"slack", "github", "anthropic"}


def test_anthropic_authorize_url_built(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_CLIENT_ID", "anth-id")
    url = build_authorize_url(
        "anthropic", state="s", redirect_uri="https://app/cb",
    )
    assert url.startswith("https://console.anthropic.com/oauth/authorize?")


def test_github_authorize_url_uses_default_scope(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "g-id")
    url = build_authorize_url("github", state="s", redirect_uri="https://app/cb")
    assert "scope=repo" in url  # default_scope = "repo read:user" → url-encoded


# ────── AC-2 EVENT: 正常 callback で token 保存 ──────


def _patch_httpx_response(monkeypatch, *, json_body=None, raise_for_status=False, text_body=None):
    """httpx.AsyncClient.post を mock 化."""
    class _FakeResp:
        def __init__(self):
            self.text = text_body or ""

        def raise_for_status(self):
            if raise_for_status:
                import httpx
                raise httpx.HTTPStatusError("403", request=None, response=None)

        def json(self):
            if json_body is None:
                raise __import__("json").JSONDecodeError("no body", "", 0)
            return json_body

    class _FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, data=None, headers=None):
            return _FakeResp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)


def test_router_callback_happy_path_saves_token(client, monkeypatch) -> None:
    """AC-2: valid code → exchange_code → save_token + connected=True."""
    monkeypatch.setenv("SLACK_CLIENT_ID", "id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret")
    _patch_httpx_response(monkeypatch, json_body={
        "access_token": "xoxb-fresh",
        "scope": "chat:write",
    })
    r = client.post(
        "/api/oauth/slack/callback",
        json={
            "code": "valid-code-123",
            "redirect_uri": "https://app/cb",
            "owner_id": "user_happy",
            "expected_state": "matchme",
            "received_state": "matchme",  # state 一致
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["provider"] == "slack"
    # 連携状態を確認
    r2 = client.get("/api/oauth/slack/status", params={"owner_id": "user_happy"})
    assert r2.json()["connected"] is True


def test_router_callback_no_state_check_when_either_missing(client, monkeypatch) -> None:
    """expected_state or received_state のどちらかが None なら CSRF check skip
    (legacy 互換: state を渡さない caller の動作維持)."""
    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "s")
    _patch_httpx_response(monkeypatch, json_body={"access_token": "gh-ok"})
    r = client.post(
        "/api/oauth/github/callback",
        json={
            "code": "c", "redirect_uri": "https://x/cb", "owner_id": "u_nostate",
            # state を渡さない
        },
    )
    assert r.status_code == 200


# ────── AC-3 EVENT: callback でエラーレスポンス → 永続化しない ──────


def test_router_callback_provider_error_does_not_persist(client, monkeypatch) -> None:
    """AC-3: token exchange が失敗 → 502 + token 保存されない."""
    monkeypatch.setenv("ANTHROPIC_CLIENT_ID", "id")
    monkeypatch.setenv("ANTHROPIC_CLIENT_SECRET", "s")

    # httpx.post が例外を投げる
    class _ErrorClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, *a, **kw):
            raise RuntimeError("provider down")

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _ErrorClient)

    r = client.post(
        "/api/oauth/anthropic/callback",
        json={
            "code": "bad", "redirect_uri": "https://x/cb",
            "owner_id": "user_err",
        },
    )
    assert r.status_code == 502
    # 保存されていないことを確認
    r2 = client.get("/api/oauth/anthropic/status", params={"owner_id": "user_err"})
    assert r2.json()["connected"] is False


def test_router_callback_unknown_provider_404(client) -> None:
    r = client.post(
        "/api/oauth/notion/callback",
        json={"code": "c", "redirect_uri": "https://x", "owner_id": "u"},
    )
    assert r.status_code == 404


def test_router_callback_missing_config_503(client, monkeypatch) -> None:
    """CLIENT_ID / SECRET 未設定 → 503."""
    monkeypatch.delenv("SLACK_CLIENT_ID", raising=False)
    monkeypatch.delenv("SLACK_CLIENT_SECRET", raising=False)
    r = client.post(
        "/api/oauth/slack/callback",
        json={"code": "c", "redirect_uri": "https://x", "owner_id": "u"},
    )
    assert r.status_code == 503


# ────── AC-4 UNWANTED: CSRF state mismatch ──────


def test_router_callback_csrf_mismatch_emits_audit(client, monkeypatch) -> None:
    """CSRF mismatch → 400 + oauth.csrf_rejected audit emit.

    monkeypatch.setattr で services.memory_service.emit_event を差し替え.
    sys.modules.pop は他 test の cached import を壊すため使わない."""
    captured: list = []

    async def emit_event(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event": event_type, "user_id": user_id, "detail": detail})

    monkeypatch.setattr("services.memory_service.emit_event", emit_event)

    r = client.post(
        "/api/oauth/github/callback",
        json={
            "code": "x", "redirect_uri": "https://x", "owner_id": "u",
            "expected_state": "AAA", "received_state": "BBB",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "csrf_mismatch"
    # audit event 発火
    assert any(e["event"] == "oauth.csrf_rejected" for e in captured)


# ────── Status / Disconnect の unknown provider ──────


def test_router_status_unknown_provider_returns_404(client) -> None:
    r = client.get("/api/oauth/notion/status", params={"owner_id": "u"})
    assert r.status_code == 404


def test_router_disconnect_unknown_provider_returns_404(client) -> None:
    r = client.delete("/api/oauth/notion", params={"owner_id": "u"})
    assert r.status_code == 404


def test_router_disconnect_with_no_token_returns_ok_false(client) -> None:
    """既に切断済 / 未連携 → ok=False (delete_token が False を返す)."""
    r = client.delete("/api/oauth/slack", params={"owner_id": "never_connected"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ────── exchange_code 直接呼出 + token URL form-encoded fallback ──────


@pytest.mark.asyncio
async def test_exchange_code_returns_json_body(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_CLIENT_ID", "id")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "s")
    _patch_httpx_response(monkeypatch, json_body={"access_token": "xoxb-direct"})
    out = await exchange_code("slack", code="c", redirect_uri="https://x/cb")
    assert out["access_token"] == "xoxb-direct"


@pytest.mark.asyncio
async def test_exchange_code_falls_back_to_form_encoded(monkeypatch) -> None:
    """GitHub legacy 等で JSON でなく x-www-form-urlencoded → parse_qs fallback."""
    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "s")
    _patch_httpx_response(
        monkeypatch,
        json_body=None,  # JSONDecodeError を発生させる
        text_body="access_token=ghp-form&scope=repo",
    )
    out = await exchange_code("github", code="c", redirect_uri="https://x/cb")
    assert out["access_token"] == "ghp-form"
    assert out["scope"] == "repo"


@pytest.mark.asyncio
async def test_exchange_code_unknown_provider_raises() -> None:
    with pytest.raises(UnknownProviderError):
        await exchange_code("notion", code="c", redirect_uri="https://x/cb")


@pytest.mark.asyncio
async def test_exchange_code_missing_secret_raises(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_CLIENT_ID", "id")
    monkeypatch.delenv("SLACK_CLIENT_SECRET", raising=False)
    with pytest.raises(OAuthConfigError):
        await exchange_code("slack", code="c", redirect_uri="https://x/cb")


def test_save_token_for_unknown_provider_raises() -> None:
    with pytest.raises(UnknownProviderError):
        save_token("notion", "u", {"access_token": "x"})


def test_load_token_for_unknown_provider_raises() -> None:
    with pytest.raises(UnknownProviderError):
        load_token("notion", "u")


def test_load_token_returns_none_when_stored_value_is_invalid_json() -> None:
    """encrypted_store に invalid JSON が入っていたら None (graceful)."""
    from services import encrypted_store
    encrypted_store.set_secret("oauth", "slack", "not-a-json{{{", owner_id="u_bad")
    out = load_token("slack", "u_bad")
    assert out is None


def test_list_providers_returns_three() -> None:
    assert set(op.list_providers()) == {"slack", "github", "anthropic"}
