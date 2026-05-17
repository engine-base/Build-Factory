"""T-V3-D-10: /api/me/api-tokens integration tests (F-030).

AC mapping (Tier 2 functional):
  - AC-F1 : POST /api/me/api-tokens with valid scope → 201 + token shown once
  - AC-F4 : plaintext token shall NOT be returned a second time (regression)
  - Aux   : 401 (no auth) / 422 (validation) / 429 (rate-limit) / 404 (revoke)

DEV BYPASS は autouse fixture で OFF にしてから明示的に有効化することで
401 系 (no bearer) を検証する.
"""
from __future__ import annotations

import os
import uuid

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


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """services.api_token_service の DB を一時 SQLite (real aiosqlite) に差し替える."""
    import aiosqlite
    db_file = tmp_path / "api_token_test.db"
    from services import api_token_service as svc
    monkeypatch.setattr(svc, "_db", lambda: aiosqlite)
    monkeypatch.setattr(svc, "_db_path", lambda: str(db_file))
    return db_file


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
# POST /api/me/api-tokens — happy path
# ──────────────────────────────────────────────────────────────────────────────


def test_post_api_tokens_returns_201_with_plaintext_once(client, isolated_db):
    """AC-F1 EVENT-DRIVEN: POST returns 201 with { token_id, plaintext_token_shown_once,
    token_hint, expires_at, ... }."""
    r = client.post(
        "/api/me/api-tokens",
        json={
            "name": "ci-token-1",
            "scopes": ["read:workspaces", "write:tasks"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "token_id" in body
    uuid.UUID(body["token_id"])  # must be uuid
    assert "plaintext_token_shown_once" in body
    plaintext = body["plaintext_token_shown_once"]
    assert plaintext.startswith("bft_")
    assert len(plaintext) > 20
    assert body["token_hint"].startswith("bft_") and "..." in body["token_hint"]
    assert body["expires_at"]
    assert body["name"] == "ci-token-1"
    assert body["scopes"] == ["read:workspaces", "write:tasks"]


def test_post_api_tokens_stores_hash_only_never_plaintext(client, isolated_db):
    """AC-F1: token hash (sha256) を api_tokens に persist, plaintext は保存しない."""
    r = client.post(
        "/api/me/api-tokens",
        json={"name": "ci-token-hash", "scopes": ["read:all"]},
    )
    assert r.status_code == 201
    plaintext = r.json()["plaintext_token_shown_once"]

    # DB を直接見て plaintext が一切記録されていないことを検証
    import sqlite3
    conn = sqlite3.connect(str(isolated_db))
    rows = conn.execute("SELECT token_hash, token_hint, name FROM api_tokens").fetchall()
    conn.close()
    assert len(rows) >= 1
    for token_hash, token_hint, _name in rows:
        assert token_hash != plaintext
        assert plaintext not in token_hash
        # hint は plaintext の一部を含むが、full plaintext は含まない
        assert plaintext not in token_hint
        # hash は 64 char hex (sha256)
        assert len(token_hash) == 64
        int(token_hash, 16)  # raises if not hex


# ──────────────────────────────────────────────────────────────────────────────
# AC-F4 critical: display-once contract
# ──────────────────────────────────────────────────────────────────────────────


def test_token_never_returned_a_second_time(client, isolated_db):
    """AC-F4 UNWANTED: plaintext token shall NOT be returned by GET /api/me/api-tokens
    or any subsequent call. このテストが fail したら regression gate fail.
    """
    r = client.post(
        "/api/me/api-tokens",
        json={"name": "display-once-token", "scopes": ["read:all"]},
    )
    assert r.status_code == 201
    plaintext = r.json()["plaintext_token_shown_once"]
    token_id = r.json()["token_id"]

    # GET list は plaintext を絶対に返さない
    r2 = client.get("/api/me/api-tokens")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "tokens" in body
    assert plaintext not in r2.text
    for tok in body["tokens"]:
        assert "plaintext_token_shown_once" not in tok
        assert "token_hash" not in tok
        # hint のみ公開
        if tok["token_id"] == token_id:
            assert tok.get("token_hint", "").startswith("bft_")


# ──────────────────────────────────────────────────────────────────────────────
# Validation / rate-limit / revoke
# ──────────────────────────────────────────────────────────────────────────────


def test_post_api_tokens_invalid_body_returns_422(client, isolated_db):
    """422 UNWANTED: empty scopes → 422."""
    r = client.post(
        "/api/me/api-tokens",
        json={"name": "no-scope", "scopes": []},
    )
    assert r.status_code == 422, r.text


def test_post_api_tokens_rate_limited_returns_429(client, isolated_db):
    """429 EVENT-DRIVEN: > MAX_TOKENS_PER_HOUR → 429."""
    from services import api_token_service as svc
    # 5 個作る → 6 個目で 429
    for i in range(svc.MAX_TOKENS_PER_HOUR_PER_USER):
        r = client.post(
            "/api/me/api-tokens",
            json={"name": f"rl-{i}", "scopes": ["read:all"]},
        )
        assert r.status_code == 201, r.text
    r = client.post(
        "/api/me/api-tokens",
        json={"name": "over-limit", "scopes": ["read:all"]},
    )
    assert r.status_code == 429, r.text
    detail = r.json().get("detail", {})
    assert detail.get("code") == "api_token.rate_limited"


def test_delete_api_tokens_revokes(client, isolated_db):
    """DELETE /api/me/api-tokens/{id} returns { token_id, revoked_at }."""
    r = client.post(
        "/api/me/api-tokens",
        json={"name": "to-revoke", "scopes": ["read:all"]},
    )
    assert r.status_code == 201
    token_id = r.json()["token_id"]
    r2 = client.delete(f"/api/me/api-tokens/{token_id}")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["token_id"] == token_id
    assert body["revoked_at"]


def test_delete_unknown_token_returns_404(client, isolated_db):
    """404 UNWANTED: 不在 token → 404."""
    r = client.delete(f"/api/me/api-tokens/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_post_api_tokens_unauthorized_returns_401(isolated_db):
    """401 UNWANTED: no auth → 401."""
    try:
        nc = _no_auth_client()
        r = nc.post(
            "/api/me/api-tokens",
            json={"name": "x", "scopes": ["read:all"]},
        )
        assert r.status_code == 401
    finally:
        _restore_dev_bypass()
