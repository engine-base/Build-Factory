"""T-V3-B-01: Auth backend (login/signup/password-reset) — F-001 tests.

Build-Factory v3 Phase 1 Wave 1 / Group B-1.

AC マッピング (docs/audit/2026-05-16_v3/T-V3-B-01.md / Tier 2 functional 13 AC):

- AC-F1  EVENT-DRIVEN  : login with valid email/password → 200 with
                          access_token + refresh_token + user_id
- AC-F2  UNWANTED      : login with invalid credentials → 401 generic (no user
                          enumeration)
- AC-F3  EVENT-DRIVEN  : password-reset always returns 2xx (no account
                          enumeration), sends email only if account exists
- AC-F4  EVENT-DRIVEN  : login valid inputs → 2xx contract from
                          features.json#F-001 (incl. access_token)
- AC-F5  UNWANTED      : login without a valid auth token → 401
- AC-F6  UNWANTED      : login body validation failure → 422 with field-level
                          error map
- AC-F7  UNWANTED      : login above rate limit (5/min/ip) → 429
- AC-F8  EVENT-DRIVEN  : signup with valid inputs → 2xx with contract incl.
                          user_id
- AC-F9  UNWANTED      : signup body validation failure → 422
- AC-F10 UNWANTED      : signup above rate limit (3/hour/ip) → 429
- AC-F11 EVENT-DRIVEN  : password-reset with valid inputs → 2xx with contract
                          incl. status
- AC-F12 UNWANTED      : password-reset body validation failure → 422
- AC-F13 UNWANTED      : password-reset above rate limit (3/hour/ip) → 429
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────
# fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Each test starts with a fresh user store + rate-limiter buckets.

    Tests assert exact rate-limit behaviour, so isolation is mandatory.
    """
    from services.auth import get_rate_limiter, get_user_store

    get_user_store().reset()
    get_rate_limiter().reset()
    yield
    get_user_store().reset()
    get_rate_limiter().reset()


def _signup(client: TestClient, *, email: str, password: str, name: str = "User") -> dict:
    """Signup via API (used to seed users for login tests)."""
    r = client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "name": name},
        headers={"x-forwarded-for": "127.0.0.1"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ──────────────────────────────────────────────────────────────────────
# AC-F1 EVENT-DRIVEN: When valid email/password is submitted to POST
# /api/auth/login, the system shall return 200 with access_token +
# refresh_token + user_id.
# ──────────────────────────────────────────────────────────────────────


def test_ac_f1_login_valid_returns_200_with_tokens_and_user_id(client: TestClient) -> None:
    _signup(client, email="alice@example.com", password="passw0rd!")
    r = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "passw0rd!"},
        headers={"x-forwarded-for": "10.0.0.1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body and isinstance(body["access_token"], str) and body["access_token"]
    assert "refresh_token" in body and isinstance(body["refresh_token"], str) and body["refresh_token"]
    assert "user_id" in body and isinstance(body["user_id"], str) and body["user_id"]
    assert body.get("mfa_required") is False


# ──────────────────────────────────────────────────────────────────────
# AC-F2 UNWANTED: If invalid credentials are submitted to POST
# /api/auth/login, the system shall return 401 with a generic message
# (no user enumeration).
# ──────────────────────────────────────────────────────────────────────


def test_ac_f2_login_invalid_credentials_returns_401_generic(client: TestClient) -> None:
    # Unknown email
    r1 = client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "passw0rd!"},
        headers={"x-forwarded-for": "10.0.0.2"},
    )
    assert r1.status_code == 401, r1.text
    body1 = r1.json()
    # generic message, no enumeration
    assert "ghost@example.com" not in str(body1)
    assert "not found" not in str(body1).lower()
    assert "unknown" not in str(body1).lower()

    # Known email with wrong password — must return SAME shape / message.
    _signup(client, email="bob@example.com", password="rightpass1")
    r2 = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "wrongpass1"},
        headers={"x-forwarded-for": "10.0.0.3"},
    )
    assert r2.status_code == 401
    body2 = r2.json()
    # AC-F2 absolutely requires both paths to be indistinguishable.
    assert body1["detail"]["code"] == body2["detail"]["code"] == "UNAUTHORIZED"
    assert body1["detail"]["message"] == body2["detail"]["message"]


# ──────────────────────────────────────────────────────────────────────
# AC-F3 EVENT-DRIVEN: When POST /api/auth/password-reset is called with
# an email, the system shall always return 2xx (no account enumeration)
# and send reset email only if the account exists.
# ──────────────────────────────────────────────────────────────────────


def test_ac_f3_password_reset_no_account_enumeration(client: TestClient) -> None:
    _signup(client, email="exists@example.com", password="passw0rd!")

    # Existing account
    r_exists = client.post(
        "/api/auth/password-reset",
        json={"email": "exists@example.com"},
        headers={"x-forwarded-for": "10.0.0.4"},
    )
    # Non-existing account
    r_ghost = client.post(
        "/api/auth/password-reset",
        json={"email": "ghost@example.com"},
        headers={"x-forwarded-for": "10.0.0.5"},
    )

    # AC-F3: always 2xx, regardless of whether the account exists.
    assert 200 <= r_exists.status_code < 300
    assert 200 <= r_ghost.status_code < 300

    # Same response body (no enumeration).
    assert r_exists.json() == r_ghost.json()


# ──────────────────────────────────────────────────────────────────────
# AC-F4 EVENT-DRIVEN: When POST /api/auth/login is called with valid
# inputs by an authorized caller, the system shall return 2xx with the
# contract defined in features.json#F-001 (incl. access_token).
# ──────────────────────────────────────────────────────────────────────


def test_ac_f4_login_returns_features_json_contract(client: TestClient) -> None:
    _signup(client, email="carol@example.com", password="passw0rd!")
    r = client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "passw0rd!"},
        headers={"x-forwarded-for": "10.0.0.6"},
    )
    assert 200 <= r.status_code < 300
    body = r.json()
    # features.json#F-001 outputs_2xx contract:
    for k in ("access_token", "refresh_token", "user_id", "mfa_required"):
        assert k in body, f"missing key: {k}"


# ──────────────────────────────────────────────────────────────────────
# AC-F5 UNWANTED: If POST /api/auth/login is called without a valid auth
# token, the system shall return 401.
# ──────────────────────────────────────────────────────────────────────


def test_ac_f5_login_invalid_authorization_header_returns_401(client: TestClient) -> None:
    _signup(client, email="dave@example.com", password="passw0rd!")
    # Pass a malformed Authorization header
    r = client.post(
        "/api/auth/login",
        json={"email": "dave@example.com", "password": "passw0rd!"},
        headers={"Authorization": "NotBearer xxx", "x-forwarded-for": "10.0.0.7"},
    )
    assert r.status_code == 401, r.text


# ──────────────────────────────────────────────────────────────────────
# AC-F6 UNWANTED: If POST /api/auth/login receives a request body failing
# validation, the system shall return 422 with a field-level error map.
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing fields
        {"email": "not-an-email", "password": "passw0rd!"},  # invalid email
        {"email": "user@example.com"},  # missing password
        {"email": "user@example.com", "password": "short"},  # password < 8
    ],
)
def test_ac_f6_login_invalid_body_returns_422(client: TestClient, payload: dict) -> None:
    r = client.post(
        "/api/auth/login",
        json=payload,
        headers={"x-forwarded-for": "10.0.0.8"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    # FastAPI default: {"detail": [{"loc":[...], "msg":"...", "type":"..."}, ...]}
    assert "detail" in body
    assert isinstance(body["detail"], list)
    assert len(body["detail"]) >= 1
    # field-level error map: each item points to a body field.
    for issue in body["detail"]:
        assert "loc" in issue


# ──────────────────────────────────────────────────────────────────────
# AC-F7 UNWANTED: If POST /api/auth/login is called above the rate limit
# (5/min/ip), the system shall return 429.
# ──────────────────────────────────────────────────────────────────────


def test_ac_f7_login_rate_limit_5_per_min_per_ip_returns_429(client: TestClient) -> None:
    ip = "10.0.0.9"
    # First 5 requests must NOT be rate-limited (regardless of credentials).
    for i in range(5):
        r = client.post(
            "/api/auth/login",
            json={"email": f"u{i}@example.com", "password": "passw0rd!"},
            headers={"x-forwarded-for": ip},
        )
        assert r.status_code != 429, f"request {i} unexpectedly 429: {r.text}"

    # 6th request must be 429.
    r6 = client.post(
        "/api/auth/login",
        json={"email": "u6@example.com", "password": "passw0rd!"},
        headers={"x-forwarded-for": ip},
    )
    assert r6.status_code == 429, r6.text
    body = r6.json()
    assert body["detail"]["code"] == "RATE_LIMITED"


# ──────────────────────────────────────────────────────────────────────
# AC-F8 EVENT-DRIVEN: When POST /api/auth/signup is called with valid
# inputs by an authorized caller, the system shall return 2xx with the
# contract defined in features.json#F-001 (incl. user_id).
# ──────────────────────────────────────────────────────────────────────


def test_ac_f8_signup_valid_returns_2xx_with_user_id(client: TestClient) -> None:
    r = client.post(
        "/api/auth/signup",
        json={"email": "eve@example.com", "password": "passw0rd!", "name": "Eve"},
        headers={"x-forwarded-for": "10.0.0.10"},
    )
    assert 200 <= r.status_code < 300, r.text
    body = r.json()
    # features.json#F-001 signup outputs_2xx:
    assert "user_id" in body and isinstance(body["user_id"], str) and body["user_id"]
    assert "verify_email_sent" in body and isinstance(body["verify_email_sent"], bool)


# ──────────────────────────────────────────────────────────────────────
# AC-F9 UNWANTED: signup body validation failure → 422 with field-level
# error map.
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        {},  # empty
        {"email": "not-an-email", "password": "passw0rd!", "name": "X"},
        {"email": "x@example.com", "password": "passw0rd!"},  # missing name
        {"email": "x@example.com", "password": "short", "name": "X"},  # password < 8
        {"email": "x@example.com", "password": "passw0rd!", "name": ""},  # empty name
    ],
)
def test_ac_f9_signup_invalid_body_returns_422(client: TestClient, payload: dict) -> None:
    r = client.post(
        "/api/auth/signup",
        json=payload,
        headers={"x-forwarded-for": "10.0.0.11"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert "detail" in body
    assert isinstance(body["detail"], list) and len(body["detail"]) >= 1
    for issue in body["detail"]:
        assert "loc" in issue


# ──────────────────────────────────────────────────────────────────────
# AC-F10 UNWANTED: signup above rate limit (3/hour/ip) → 429.
# ──────────────────────────────────────────────────────────────────────


def test_ac_f10_signup_rate_limit_3_per_hour_per_ip_returns_429(client: TestClient) -> None:
    ip = "10.0.0.12"
    for i in range(3):
        r = client.post(
            "/api/auth/signup",
            json={"email": f"sue{i}@example.com", "password": "passw0rd!", "name": f"S{i}"},
            headers={"x-forwarded-for": ip},
        )
        assert r.status_code != 429, f"request {i} unexpectedly 429"

    r4 = client.post(
        "/api/auth/signup",
        json={"email": "sue3@example.com", "password": "passw0rd!", "name": "S3"},
        headers={"x-forwarded-for": ip},
    )
    assert r4.status_code == 429, r4.text
    assert r4.json()["detail"]["code"] == "RATE_LIMITED"


# ──────────────────────────────────────────────────────────────────────
# AC-F11 EVENT-DRIVEN: password-reset valid inputs → 2xx with contract
# incl. status.
# ──────────────────────────────────────────────────────────────────────


def test_ac_f11_password_reset_valid_returns_2xx_with_status(client: TestClient) -> None:
    r = client.post(
        "/api/auth/password-reset",
        json={"email": "anyone@example.com"},
        headers={"x-forwarded-for": "10.0.0.13"},
    )
    assert 200 <= r.status_code < 300, r.text
    body = r.json()
    assert "status" in body and isinstance(body["status"], str) and body["status"]


# ──────────────────────────────────────────────────────────────────────
# AC-F12 UNWANTED: password-reset body validation failure → 422.
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "not-an-email"},
        {"not_email": "x@example.com"},
    ],
)
def test_ac_f12_password_reset_invalid_body_returns_422(client: TestClient, payload: dict) -> None:
    r = client.post(
        "/api/auth/password-reset",
        json=payload,
        headers={"x-forwarded-for": "10.0.0.14"},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert "detail" in body
    assert isinstance(body["detail"], list) and len(body["detail"]) >= 1


# ──────────────────────────────────────────────────────────────────────
# AC-F13 UNWANTED: password-reset above rate limit (3/hour/ip) → 429.
# ──────────────────────────────────────────────────────────────────────


def test_ac_f13_password_reset_rate_limit_3_per_hour_per_ip_returns_429(client: TestClient) -> None:
    ip = "10.0.0.15"
    for _ in range(3):
        r = client.post(
            "/api/auth/password-reset",
            json={"email": "anyone@example.com"},
            headers={"x-forwarded-for": ip},
        )
        assert r.status_code != 429

    r4 = client.post(
        "/api/auth/password-reset",
        json={"email": "anyone@example.com"},
        headers={"x-forwarded-for": ip},
    )
    assert r4.status_code == 429, r4.text
    assert r4.json()["detail"]["code"] == "RATE_LIMITED"


# ──────────────────────────────────────────────────────────────────────
# Additional regression: rate-limit isolation across IPs
# (sanity check for the per-ip semantics in AC-F7 / AC-F10 / AC-F13)
# ──────────────────────────────────────────────────────────────────────


def test_rate_limit_buckets_isolated_per_ip(client: TestClient) -> None:
    # IP A hits its 5-per-min login limit, but IP B is unaffected.
    for i in range(5):
        client.post(
            "/api/auth/login",
            json={"email": f"a{i}@example.com", "password": "passw0rd!"},
            headers={"x-forwarded-for": "1.1.1.1"},
        )
    r_a = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "passw0rd!"},
        headers={"x-forwarded-for": "1.1.1.1"},
    )
    r_b = client.post(
        "/api/auth/login",
        json={"email": "b@example.com", "password": "passw0rd!"},
        headers={"x-forwarded-for": "2.2.2.2"},
    )
    assert r_a.status_code == 429
    assert r_b.status_code != 429


# ──────────────────────────────────────────────────────────────────────
# Additional regression: signup duplicate email → 409 (features.json#F-001
# outputs_4xx 409 "email already exists").
# ──────────────────────────────────────────────────────────────────────


def test_signup_duplicate_email_returns_409(client: TestClient) -> None:
    _signup(client, email="dup@example.com", password="passw0rd!")
    r = client.post(
        "/api/auth/signup",
        json={"email": "dup@example.com", "password": "passw0rd!", "name": "Dup"},
        headers={"x-forwarded-for": "3.3.3.3"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "CONFLICT"
