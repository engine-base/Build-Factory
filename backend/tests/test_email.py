"""T-V3-B-30 / F-028: Email backend (templates list + test-send) AC tests.

Coverage (functional AC, audit MD ↔ test 1:1):
  AC-F1 / AC-F8 UNWANTED  : POST /api/email/test-send >10/hour/workspace → 429
  AC-F2          EVENT    : GET /api/email/templates → 2xx + templates[]
  AC-F3          UNWANTED : GET /api/email/templates no auth → 401
  AC-F4          UNWANTED : GET /api/email/templates invalid x-workspace-id → 422
  AC-F5          EVENT    : POST /api/email/test-send valid → 201 + delivery_id
  AC-F6          UNWANTED : POST /api/email/test-send no auth → 401
  AC-F7          UNWANTED : POST /api/email/test-send invalid body → 422

Additional invariants:
  - listed templates contain the 5 standard names
  - rate limit Retry-After header is exposed
  - rate-limit counter resets when bucket purged
"""
from __future__ import annotations

import os
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from services import email as email_service


@pytest.fixture(scope="function")
def client(monkeypatch) -> Iterator[TestClient]:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    # Strict auth OFF by default → dev bypass yields DEV_USER (matches AC-F2/F5).
    monkeypatch.delenv("EMAIL_API_STRICT_AUTH", raising=False)
    # Ensure clean in-memory store between tests so rate-limit buckets reset.
    email_service.reset_store()
    from main import app
    # NOTE: do not use `with TestClient(app)` — lifespan tries to connect to
    # local Postgres which isn't available in CI.
    yield TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────
# AC-F2 EVENT-DRIVEN: GET /api/email/templates → 2xx + templates[]
# ─────────────────────────────────────────────────────────
def test_list_templates_returns_seeded_defaults(client) -> None:
    r = client.get("/api/email/templates")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "templates" in body
    names = {t["name"] for t in body["templates"]}
    expected = {
        "signup_verify", "password_reset", "invitation",
        "task_notification", "weekly_summary",
    }
    assert expected.issubset(names), f"missing standard templates: {expected - names}"
    # AC-policy: shape matches openapi.yaml#EmailTemplate
    sample = next(t for t in body["templates"] if t["name"] == "signup_verify")
    for k in ("id", "name", "subject", "variables", "version", "is_active"):
        assert k in sample
    assert sample["is_active"] is True
    assert isinstance(sample["variables"], list)


def test_list_templates_workspace_filter_with_header(client) -> None:
    r = client.get("/api/email/templates", headers={"x-workspace-id": "42"})
    assert r.status_code == 200
    assert r.json()["workspace_id"] == 42


# ─────────────────────────────────────────────────────────
# AC-F3 UNWANTED: GET /api/email/templates no auth → 401
# ─────────────────────────────────────────────────────────
def test_list_templates_unauthenticated_returns_401(client, monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_API_STRICT_AUTH", "1")
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    r = client.get("/api/email/templates")
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["code"] == "email.unauthorized"


# ─────────────────────────────────────────────────────────
# AC-F4 UNWANTED: invalid x-workspace-id → 422
# ─────────────────────────────────────────────────────────
def test_list_templates_invalid_workspace_id_returns_422(client) -> None:
    r = client.get("/api/email/templates", headers={"x-workspace-id": "not-a-number"})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "email.invalid_workspace_id"
    assert detail["field"] == "x-workspace-id"


# ─────────────────────────────────────────────────────────
# AC-F5 EVENT-DRIVEN: POST /api/email/test-send valid → 201 + delivery_id
# ─────────────────────────────────────────────────────────
def _first_template_id(client: TestClient) -> str:
    r = client.get("/api/email/templates")
    assert r.status_code == 200
    return r.json()["templates"][0]["id"]


def test_test_send_returns_201_with_delivery_id(client) -> None:
    tid = _first_template_id(client)
    r = client.post(
        "/api/email/test-send",
        json={"template_id": tid, "recipient": "user@example.com"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["delivery_id"]
    assert "queued_at" in body
    assert body["status"] == "queued"
    assert body["template_id"] == tid
    assert body["recipient"] == "user@example.com"


# ─────────────────────────────────────────────────────────
# AC-F6 UNWANTED: POST /api/email/test-send no auth → 401
# ─────────────────────────────────────────────────────────
def test_test_send_unauthenticated_returns_401(client, monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_API_STRICT_AUTH", "1")
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    tid = "00000000-0000-0000-0000-000000000000"
    r = client.post(
        "/api/email/test-send",
        json={"template_id": tid, "recipient": "user@example.com"},
    )
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["code"] == "email.unauthorized"


# ─────────────────────────────────────────────────────────
# AC-F7 UNWANTED: invalid body → 422
# ─────────────────────────────────────────────────────────
def test_test_send_missing_template_id_returns_422(client) -> None:
    r = client.post("/api/email/test-send", json={"recipient": "user@example.com"})
    assert r.status_code == 422, r.text


def test_test_send_invalid_recipient_returns_422(client) -> None:
    tid = _first_template_id(client)
    r = client.post(
        "/api/email/test-send",
        json={"template_id": tid, "recipient": "not-an-email"},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "email.invalid_recipient"
    assert detail["field"] == "recipient"


def test_test_send_unknown_template_returns_404(client) -> None:
    r = client.post(
        "/api/email/test-send",
        json={
            "template_id": "11111111-1111-1111-1111-111111111111",
            "recipient": "user@example.com",
        },
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "email.template_not_found"


# ─────────────────────────────────────────────────────────
# AC-F1 / AC-F8 UNWANTED: 10/hour/workspace 超過 → 429
# ─────────────────────────────────────────────────────────
def test_test_send_rate_limit_returns_429(client, monkeypatch) -> None:
    # Lower the limit to a tiny number to exercise the gate quickly.
    monkeypatch.setenv("EMAIL_TEST_SEND_RATE_LIMIT", "3")
    monkeypatch.setenv("EMAIL_TEST_SEND_RATE_WINDOW", "3600")
    # Reset store after env tweak so the in-memory limit picks up new env.
    email_service.reset_store()

    tid = _first_template_id(client)
    payload = {"template_id": tid, "recipient": "user@example.com"}
    headers = {"x-workspace-id": "7"}

    # 3 OK then 1 should trip the limiter.
    for _ in range(3):
        r = client.post("/api/email/test-send", json=payload, headers=headers)
        assert r.status_code == 201, r.text
    r = client.post("/api/email/test-send", json=payload, headers=headers)
    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "email.rate_limited"
    assert detail["retry_after"] >= 1
    assert detail["limit"] == 3
    assert r.headers.get("Retry-After") == str(detail["retry_after"])


def test_rate_limit_is_per_workspace(client, monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_TEST_SEND_RATE_LIMIT", "2")
    email_service.reset_store()
    tid = _first_template_id(client)
    payload = {"template_id": tid, "recipient": "user@example.com"}

    # workspace 1 spends its quota.
    for _ in range(2):
        r = client.post("/api/email/test-send", json=payload, headers={"x-workspace-id": "1"})
        assert r.status_code == 201
    r = client.post("/api/email/test-send", json=payload, headers={"x-workspace-id": "1"})
    assert r.status_code == 429
    # workspace 2 still has full quota — proves bucket is scoped.
    r = client.post("/api/email/test-send", json=payload, headers={"x-workspace-id": "2"})
    assert r.status_code == 201, r.text


# ─────────────────────────────────────────────────────────
# Service-layer unit tests (raises typed errors)
# ─────────────────────────────────────────────────────────
def test_service_invalid_recipient_raises() -> None:
    email_service.reset_store()
    with pytest.raises(email_service.InvalidRecipientError):
        email_service.enqueue_test_send(
            workspace_id=None, template_id="any", recipient="oops",
        )


def test_service_template_not_found_raises() -> None:
    email_service.reset_store()
    with pytest.raises(email_service.TemplateNotFoundError):
        email_service.enqueue_test_send(
            workspace_id=None,
            template_id="00000000-0000-0000-0000-000000000000",
            recipient="ok@example.com",
        )


def test_service_list_templates_filters_inactive() -> None:
    email_service.reset_store()
    rows = email_service.list_templates(None)
    assert len(rows) >= 5
    assert all(r["is_active"] for r in rows)
