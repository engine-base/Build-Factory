"""T-V3-B-26: /api/me (profile + settings + api-keys + oauth unlink) tests (F-023).

AC mapping (excerpt — full mapping recorded in docs/audit/2026-05-16_v3/T-V3-B-26.md):
  - AC-F4 / AC-F5 : GET /api/me happy + 401
  - AC-F6 / AC-F7 / AC-F8 : PUT /api/me happy + 401 + 422
  - AC-F1 / AC-F2 / AC-F9 / AC-F10 / AC-F11 : POST /api/me/api-keys happy + 409 + 401 + 422 + encryption
  - AC-F3 / AC-F12 / AC-F13 : DELETE /api/me/oauth/{provider} happy + 401 + revoke

DEV BYPASS は autouse fixture で OFF にしてから明示的に有効化することで
401 系 (no bearer) を検証する.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

# pytest collection 前に Supabase env を default 埋めしておく (auth_middleware import 用)
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


@pytest.fixture(autouse=True)
def _isolated_byok(monkeypatch):
    """byok_store の singleton を test 毎にリセットして冪等にする."""
    from services import byok_store as bs
    bs.reset_store()
    yield
    bs.reset_store()


@pytest.fixture
def in_memory_db(tmp_path, monkeypatch):
    """services.me の DB を一時 SQLite に差し替える (round-trip 検証用)."""
    import aiosqlite
    db_file = tmp_path / "me_test.db"
    from services import me as me_svc
    monkeypatch.setattr(me_svc, "_db", lambda: aiosqlite)
    monkeypatch.setattr(me_svc, "_db_path", lambda: str(db_file))
    return db_file


def _no_auth_client():
    """DEV_BYPASS を切ったクライアントを返す (401 検証用)."""
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "0"
    # auth_middleware は import 時に DEV_BYPASS を読み込むので reload する
    import importlib
    from services import auth_middleware
    importlib.reload(auth_middleware)
    # main も router の Depends を解決し直す必要があるが、Depends は instance ではなく
    # callable 参照なので reload した auth_middleware.require_user は新 callable.
    # 既に登録済 router の Depends を差し替えるため main も reload する.
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
# GET /api/me
# ──────────────────────────────────────────────────────────────────────────────

def test_get_me_returns_user_and_settings(client):
    """AC-F4 EVENT-DRIVEN: GET /api/me 200 with {user, settings}."""
    r = client.get("/api/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "user" in body
    assert "settings" in body
    assert body["user"]["id"]  # dev user has slug=masato
    s = body["settings"]
    assert s["theme"] in {"light", "dark", "system"}
    assert s["locale"]
    assert isinstance(s["notifications_enabled"], bool)


def test_get_me_unauthorized_returns_401():
    """AC-F5 UNWANTED: no auth token → 401."""
    try:
        nc = _no_auth_client()
        r = nc.get("/api/me")
        assert r.status_code == 401
    finally:
        _restore_dev_bypass()


# ──────────────────────────────────────────────────────────────────────────────
# PUT /api/me
# ──────────────────────────────────────────────────────────────────────────────

def test_put_me_happy_returns_updated_at(client):
    """AC-F6 EVENT-DRIVEN: PUT /api/me with valid input → 200 with updated_at."""
    r = client.put(
        "/api/me",
        json={"name": "Alice", "avatar_url": "https://example.com/a.png"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "updated_at" in body and body["updated_at"]
    assert "name" in body.get("changed_fields", [])
    assert "avatar_url" in body.get("changed_fields", [])


def test_put_me_settings_persisted_round_trip(client, in_memory_db):
    """GET after PUT reflects new theme (SQLite-backed round trip)."""
    r = client.put("/api/me", json={"settings": {"theme": "dark", "locale": "en"}})
    assert r.status_code == 200, r.text
    r2 = client.get("/api/me")
    assert r2.status_code == 200
    assert r2.json()["settings"]["theme"] == "dark"
    assert r2.json()["settings"]["locale"] == "en"


def test_put_me_invalid_theme_returns_422(client):
    """AC-F8 UNWANTED: invalid theme → 422 with field-level error map."""
    r = client.put("/api/me", json={"settings": {"theme": "purple"}})
    assert r.status_code == 422, r.text
    detail = r.json().get("detail", {})
    # pydantic は first; service layer の field-level error は fields に入る
    assert ("fields" in detail) or ("loc" in str(detail))


def test_put_me_invalid_avatar_url_returns_422(client):
    """AC-F8 UNWANTED: invalid avatar_url scheme → 422."""
    r = client.put("/api/me", json={"avatar_url": "javascript:alert(1)"})
    assert r.status_code == 422, r.text


def test_put_me_unauthorized_returns_401():
    """AC-F7 UNWANTED: no auth token → 401."""
    try:
        nc = _no_auth_client()
        r = nc.put("/api/me", json={"name": "x"})
        assert r.status_code == 401
    finally:
        _restore_dev_bypass()


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/me/api-keys
# ──────────────────────────────────────────────────────────────────────────────

def test_post_api_keys_happy_returns_key_id_and_masked(client):
    """AC-F9 / AC-F1: POST returns 201 with key_id + masked_key; plaintext NOT exposed."""
    plaintext = "sk-ant-" + "x" * 32
    r = client.post(
        "/api/me/api-keys",
        json={"provider": "anthropic", "key_plaintext": plaintext},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "key_id" in body
    assert "masked_key" in body
    # AC-F1: plaintext は response に含まれない
    assert plaintext not in r.text
    # masked_key 形式: 'sk-ant-...xxxx'
    assert body["masked_key"].endswith(plaintext[-4:])
    # uuid 形式の key_id
    uuid.UUID(body["key_id"])  # raises if invalid


def test_post_api_keys_encrypts_before_persisting(client):
    """AC-F1 EVENT-DRIVEN: key plaintext is encrypted at rest (Fernet ciphertext != plaintext)."""
    plaintext = "sk-ant-" + "y" * 40
    r = client.post(
        "/api/me/api-keys",
        json={"provider": "anthropic", "key_plaintext": plaintext},
    )
    assert r.status_code == 201, r.text
    # Verify via byok_store: ciphertext bytes must NOT contain plaintext bytes
    from services import byok_store as bs
    rec = bs.get_store().get_record("masato", "anthropic")
    assert rec is not None
    assert isinstance(rec.ciphertext, bytes) and len(rec.ciphertext) > 0
    assert plaintext.encode() not in rec.ciphertext
    # Round trip: decrypt should return original
    pt = bs.get_store().get_decrypted_key("masato", "anthropic")
    assert pt == plaintext


def test_post_api_keys_duplicate_provider_returns_409(client):
    """AC-F2 UNWANTED: same provider twice → 409."""
    plaintext1 = "sk-ant-" + "a" * 32
    plaintext2 = "sk-ant-" + "b" * 32
    r1 = client.post(
        "/api/me/api-keys",
        json={"provider": "anthropic", "key_plaintext": plaintext1},
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        "/api/me/api-keys",
        json={"provider": "anthropic", "key_plaintext": plaintext2},
    )
    assert r2.status_code == 409, r2.text
    assert "api_key_conflict" in r2.text


def test_post_api_keys_validation_error_returns_422(client):
    """AC-F11 UNWANTED: invalid body → 422 with field-level error map."""
    # provider に未知の値 (byok_store の SUPPORTED_PROVIDERS check で失敗)
    r = client.post(
        "/api/me/api-keys",
        json={"provider": "wakandan", "key_plaintext": "sk-something"},
    )
    assert r.status_code == 422, r.text


def test_post_api_keys_empty_plaintext_returns_422(client):
    """AC-F11 UNWANTED: empty key_plaintext → 422."""
    r = client.post(
        "/api/me/api-keys",
        json={"provider": "anthropic", "key_plaintext": ""},
    )
    assert r.status_code == 422, r.text


def test_post_api_keys_unauthorized_returns_401():
    """AC-F10 UNWANTED: no auth token → 401."""
    try:
        nc = _no_auth_client()
        r = nc.post(
            "/api/me/api-keys",
            json={"provider": "anthropic", "key_plaintext": "sk-ant-xxx"},
        )
        assert r.status_code == 401
    finally:
        _restore_dev_bypass()


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /api/me/oauth/{provider}
# ──────────────────────────────────────────────────────────────────────────────

def test_delete_oauth_unknown_provider_returns_404(client):
    """OpenAPI enum (anthropic|github|slack|google) 外は FastAPI Literal で 422."""
    r = client.delete("/api/me/oauth/notion")
    # FastAPI Literal path param mismatch is 422 by default
    assert r.status_code in (422, 404), r.text


def test_delete_oauth_not_linked_returns_404(client):
    """AC: provider not linked → 404."""
    r = client.delete("/api/me/oauth/anthropic")
    assert r.status_code == 404, r.text
    assert "not_linked" in r.text or "unknown_provider" in r.text


def test_delete_oauth_happy_returns_unlinked_at(client, monkeypatch):
    """AC-F12 / AC-F3 EVENT-DRIVEN: revoke + unlink → 200 with unlinked_at."""
    from services import oauth_providers as op
    # 1) save_token for 'masato' (dev user)
    op.save_token("github", "masato", {"access_token": "ghp_testtoken"})
    # 2) httpx revoke を no-op に
    revoke_called = {"flag": False}
    async def _noop(*a, **kw):
        revoke_called["flag"] = True
        return None
    monkeypatch.setattr("services.me._try_revoke_remote", _noop)
    try:
        r = client.delete("/api/me/oauth/github")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "unlinked_at" in body and body["unlinked_at"]
        # token must be deleted locally
        assert op.load_token("github", "masato") is None
    finally:
        op.delete_token("github", "masato")


def test_delete_oauth_unauthorized_returns_401():
    """AC-F13 UNWANTED: no auth token → 401."""
    try:
        nc = _no_auth_client()
        r = nc.delete("/api/me/oauth/anthropic")
        assert r.status_code == 401
    finally:
        _restore_dev_bypass()


# ──────────────────────────────────────────────────────────────────────────────
# Service-level unit tests (additional coverage)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_validate_put_me_collects_all_errors():
    from services.me import _validate_put_me
    errs = _validate_put_me(
        name="x" * 999,
        avatar_url="ftp://bad",
        settings={"theme": "neon", "locale": "x" * 99},
    )
    assert "name" in errs
    assert "avatar_url" in errs
    assert "settings.theme" in errs
    assert "settings.locale" in errs


@pytest.mark.asyncio
async def test_service_register_api_key_rejects_empty_plaintext():
    from services.me import register_api_key, ApiKeyValidationError
    with pytest.raises(ApiKeyValidationError):
        await register_api_key("user-test", provider="anthropic", key_plaintext="   ")


@pytest.mark.asyncio
async def test_service_unlink_oauth_unknown_provider():
    from services.me import unlink_oauth, OAuthUnknownProviderError
    with pytest.raises(OAuthUnknownProviderError):
        await unlink_oauth("user-test", "myspace")
