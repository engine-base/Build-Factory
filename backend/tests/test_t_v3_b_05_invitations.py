"""T-V3-B-05 (F-004): Public invitation lookup — GET /api/invitations/{token}.

3-tier AC マッピング (Tier 2 Functional):
  AC-F3  : GET /invitations/{token} past expires_at → 409
  AC-F13 : GET /invitations/{token} valid → 2xx with {invitation}

実装: backend/routers/invitations.py + backend/services/invitation_service.py
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    from main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def _fake_inv(monkeypatch):
    """invitation_service.public_lookup を fake."""
    import services.invitation_service as svc

    table: dict[str, dict] = {}

    async def fake_public_lookup(token: str):
        return table.get(token)

    monkeypatch.setattr(svc, "public_lookup", fake_public_lookup)
    return table


# ════════════════════════════════════════════════════════════════════════
# AC-F13 EVENT-DRIVEN: valid token → 2xx with invitation contract
# ════════════════════════════════════════════════════════════════════════


def test_ac_f13_valid_account_invitation_returns_200(client, _fake_inv):
    token = "abc12345-account"
    _fake_inv[token] = {
        "scope": "account",
        "account_id": 1,
        "email": "u@example.com",
        "role": "member",
        "status": "pending",
        "expires_at": "2099-01-01T00:00:00",
        "invited_by": "alice",
        "is_expired": False,
    }
    r = client.get(f"/api/invitations/{token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "invitation" in body
    assert body["invitation"]["email"] == "u@example.com"
    assert body["invitation"]["scope"] == "account"
    assert body["invitation"]["account_id"] == 1


def test_ac_f13_valid_workspace_invitation_returns_200(client, _fake_inv):
    token = "ws-token-xxxxxxxxx"
    _fake_inv[token] = {
        "scope": "workspace",
        "workspace_id": 7,
        "email": "ws@example.com",
        "role": "contributor",
        "status": "pending",
        "expires_at": "2099-01-01T00:00:00",
        "invited_by": "alice",
        "is_expired": False,
    }
    r = client.get(f"/api/invitations/{token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["invitation"]["scope"] == "workspace"
    assert body["invitation"]["workspace_id"] == 7


# ════════════════════════════════════════════════════════════════════════
# AC-F3 UNWANTED: expired token → 409
# ════════════════════════════════════════════════════════════════════════


def test_ac_f3_expired_token_returns_409(client, _fake_inv):
    token = "expired-token-abc"
    _fake_inv[token] = {
        "scope": "account",
        "account_id": 1,
        "email": "u@example.com",
        "role": "member",
        "status": "pending",
        "expires_at": "2020-01-01T00:00:00",
        "is_expired": True,
    }
    r = client.get(f"/api/invitations/{token}")
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["code"] == "invitations.expired"


def test_already_accepted_token_returns_409(client, _fake_inv):
    token = "already-used-abc"
    _fake_inv[token] = {
        "scope": "workspace",
        "workspace_id": 3,
        "email": "u@example.com",
        "role": "contributor",
        "status": "accepted",
        "is_expired": False,
    }
    r = client.get(f"/api/invitations/{token}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "invitations.already_used"


def test_unknown_token_returns_404(client, _fake_inv):
    r = client.get("/api/invitations/no-such-token-9999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "invitations.not_found"


def test_too_short_token_returns_400(client, _fake_inv):
    r = client.get("/api/invitations/short")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_token"


# ════════════════════════════════════════════════════════════════════════
# invitation_service unit tests (Tier 2 / Tier 3 unit coverage)
# ════════════════════════════════════════════════════════════════════════


def test_rate_limit_independent_per_account():
    from services import invitation_service as inv

    inv.configure_rate_limit(max_requests=2, window_seconds=60.0)
    inv.reset_rate_limit()
    a, _ = inv.check_invitation_rate_limit(1)
    b, _ = inv.check_invitation_rate_limit(1)
    c, _ = inv.check_invitation_rate_limit(1)
    assert a and b and not c
    # account 2 はバケットが独立
    d, _ = inv.check_invitation_rate_limit(2)
    assert d is True
    inv.configure_rate_limit(max_requests=20, window_seconds=3600.0)


def test_rate_limit_decrements_remaining():
    from services import invitation_service as inv

    inv.configure_rate_limit(max_requests=5, window_seconds=60.0)
    inv.reset_rate_limit()
    allowed, remaining1 = inv.check_invitation_rate_limit(10)
    assert allowed and remaining1 == 4
    _, remaining2 = inv.check_invitation_rate_limit(10)
    assert remaining2 == 3
    inv.configure_rate_limit(max_requests=20, window_seconds=3600.0)
