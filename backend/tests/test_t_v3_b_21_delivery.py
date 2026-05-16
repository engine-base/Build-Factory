"""T-V3-B-21 / F-013: Delivery backend (delivery pack / approve / send-client).

Hermetic tests for the 3 workspace-scoped delivery endpoints + service layer.

AC coverage (1:1 with audit MD docs/audit/2026-05-16_v3/T-V3-B-21.md):
    AC-F1 EVENT-DRIVEN : send-client mints public token + emails client
    AC-F2 EVENT-DRIVEN : GET delivery happy returns {delivery: Delivery}
    AC-F3 UNWANTED     : GET delivery without auth -> 401
    AC-F4 UNWANTED     : GET delivery invalid id -> 422
    AC-F5 EVENT-DRIVEN : approve happy returns {approved_at}
    AC-F6 UNWANTED     : approve without auth -> 401
    AC-F7 EVENT-DRIVEN : send-client happy returns {sent_at, delivery_token}
    AC-F8 UNWANTED     : send-client without auth -> 401
    AC-F9 UNWANTED     : send-client invalid body -> 422
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import aiosqlite as real_aiosqlite
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
os.environ.setdefault("SUPABASE_ANON_KEY", "stub")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "stub")
os.environ.setdefault("SUPABASE_JWT_SECRET", "stub")

from services import client_portal_service as cps  # noqa: E402
from services import delivery_service as ds  # noqa: E402


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
CONTRIB_USER_ID = "11111111-1111-1111-1111-111111111111"
STRANGER_USER_ID = "stranger"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        f"""
        CREATE TABLE workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE workspace_members (
            workspace_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'contributor',
            PRIMARY KEY (workspace_id, user_id)
        );
        CREATE TABLE client_review_tokens (
            id TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            workspace_id INTEGER NOT NULL,
            issued_by TEXT,
            issued_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            client_email TEXT,
            spec_html_url TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO workspaces (id, name, status) VALUES (1, 'Demo workspace', 'active');
        INSERT INTO workspaces (id, name, status) VALUES (2, 'Other workspace', 'active');
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (1, '{DEV_USER_ID}', 'admin');
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (1, '{CONTRIB_USER_ID}', 'contributor');
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (2, '{DEV_USER_ID}', 'contributor');
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def svc_db(monkeypatch, tmp_path):
    """Bind delivery_service + client_portal_service to a tmp seeded SQLite DB."""
    db_path = tmp_path / "t_v3_b_21.db"
    _seed_db(db_path)
    monkeypatch.setattr(ds, "aiosqlite", real_aiosqlite, raising=True)
    monkeypatch.setattr(ds, "DB_PATH", str(db_path), raising=True)
    monkeypatch.setattr(cps, "aiosqlite", real_aiosqlite, raising=True)
    monkeypatch.setattr(cps, "DB_PATH", str(db_path), raising=True)
    return db_path


@pytest.fixture
def captured_audit(monkeypatch):
    events: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        events.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(events)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    return events


@pytest.fixture
def http_client():
    """TestClient with no DB seeding — router-level tests stub the service."""
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def _arun(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────
# Service-level tests
# ─────────────────────────────────────────────────────────────────────────


def test_get_delivery_happy_creates_draft_on_first_read(svc_db, captured_audit):
    """AC-F2: GET delivery auto-bootstraps a draft row and returns Delivery."""
    result = _arun(ds.get_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    assert "delivery" in result
    d = result["delivery"]
    assert d["workspace_id"] == "1"
    assert d["status"] == "draft"
    assert d["approved_at"] is None
    assert d["sent_at"] is None
    assert d["artifact_urls"] == []
    assert any(e["event_type"] == "delivery_read" for e in captured_audit)


def test_get_delivery_403_when_not_member(svc_db, captured_audit):
    with pytest.raises(ds.DeliveryForbiddenError):
        _arun(ds.get_delivery(workspace_id=1, actor_user_id=STRANGER_USER_ID))


def test_get_delivery_422_when_actor_id_empty(svc_db, captured_audit):
    with pytest.raises(ds.DeliveryValidationError):
        _arun(ds.get_delivery(workspace_id=1, actor_user_id="   "))


def test_get_delivery_422_when_workspace_id_invalid(svc_db, captured_audit):
    """AC-F4: invalid workspace_id surfaces as 422 via DeliveryValidationError."""
    with pytest.raises(ds.DeliveryValidationError):
        _arun(ds.get_delivery(workspace_id=0, actor_user_id=DEV_USER_ID))
    with pytest.raises(ds.DeliveryValidationError):
        _arun(ds.get_delivery(workspace_id="not-a-number", actor_user_id=DEV_USER_ID))


def test_approve_delivery_happy(svc_db, captured_audit):
    """AC-F5: approve flips status draft -> approved + returns approved_at."""
    _arun(ds.get_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    result = _arun(ds.approve_delivery(
        workspace_id=1, actor_user_id=DEV_USER_ID,
    ))
    assert "approved_at" in result
    assert result["approved_at"].endswith("+00:00")
    # Re-read shows the new state.
    after = _arun(ds.get_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    assert after["delivery"]["status"] == "approved"
    assert after["delivery"]["approved_at"] is not None
    assert any(e["event_type"] == "delivery_approved" for e in captured_audit)


def test_approve_delivery_403_when_non_admin(svc_db, captured_audit):
    with pytest.raises(ds.DeliveryForbiddenError):
        _arun(ds.approve_delivery(
            workspace_id=1, actor_user_id=CONTRIB_USER_ID,
        ))


def test_approve_delivery_409_when_already_approved(svc_db, captured_audit):
    _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    with pytest.raises(ds.DeliveryConflictError):
        _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))


def test_send_client_happy_mints_token_and_emails(svc_db, captured_audit):
    """AC-F1 / AC-F7: send-client mints token + emails client + returns response."""
    _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    emails: list[dict] = []

    async def stub_email(*, client_email, token, workspace_id):
        emails.append({
            "client_email": client_email,
            "token": token,
            "workspace_id": workspace_id,
        })

    result = _arun(ds.send_client(
        workspace_id=1, actor_user_id=DEV_USER_ID,
        client_email="client@example.test", ttl_days=7,
        email_send_callable=stub_email,
    ))
    assert "sent_at" in result
    assert "delivery_token" in result
    assert isinstance(result["delivery_token"], str)
    assert len(result["delivery_token"]) >= 32
    # Email was invoked exactly once with matching token.
    assert len(emails) == 1
    assert emails[0]["client_email"] == "client@example.test"
    assert emails[0]["token"] == result["delivery_token"]
    assert emails[0]["workspace_id"] == 1
    # State machine flipped to "sent".
    after = _arun(ds.get_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    assert after["delivery"]["status"] == "sent"
    assert after["delivery"]["sent_at"] is not None
    # Audit recorded.
    assert any(
        e["event_type"] == "delivery_sent_client" for e in captured_audit
    )


def test_send_client_persists_token_into_client_review_tokens(svc_db, captured_audit):
    """AC-F1: the minted token must be queryable via client_portal_service."""
    _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))

    async def noop_email(**kwargs):
        return None

    result = _arun(ds.send_client(
        workspace_id=1, actor_user_id=DEV_USER_ID,
        client_email="client@example.test",
        email_send_callable=noop_email,
    ))
    token = result["delivery_token"]
    # The token row must be loadable via the client_portal_service path.
    ws_view = _arun(cps.get_workspace_by_token(token=token))
    assert ws_view["workspace"]["workspace_id"] == "1"


def test_send_client_403_when_non_admin(svc_db, captured_audit):
    _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))

    async def noop_email(**kwargs):
        return None

    with pytest.raises(ds.DeliveryForbiddenError):
        _arun(ds.send_client(
            workspace_id=1, actor_user_id=CONTRIB_USER_ID,
            client_email="client@example.test",
            email_send_callable=noop_email,
        ))


def test_send_client_409_when_not_approved(svc_db, captured_audit):
    """AC: send-client before approve -> 409 (state machine)."""
    _arun(ds.get_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))

    async def noop_email(**kwargs):
        return None

    with pytest.raises(ds.DeliveryConflictError):
        _arun(ds.send_client(
            workspace_id=1, actor_user_id=DEV_USER_ID,
            client_email="client@example.test",
            email_send_callable=noop_email,
        ))


def test_send_client_422_invalid_email(svc_db, captured_audit):
    """AC-F9 (service layer): malformed client_email -> DeliveryValidationError."""
    _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))

    async def noop_email(**kwargs):
        return None

    with pytest.raises(ds.DeliveryValidationError):
        _arun(ds.send_client(
            workspace_id=1, actor_user_id=DEV_USER_ID,
            client_email="not-an-email",
            email_send_callable=noop_email,
        ))


def test_send_client_422_invalid_ttl(svc_db, captured_audit):
    _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))

    async def noop_email(**kwargs):
        return None

    with pytest.raises(ds.DeliveryValidationError):
        _arun(ds.send_client(
            workspace_id=1, actor_user_id=DEV_USER_ID,
            client_email="client@example.test", ttl_days=-1,
            email_send_callable=noop_email,
        ))
    with pytest.raises(ds.DeliveryValidationError):
        _arun(ds.send_client(
            workspace_id=1, actor_user_id=DEV_USER_ID,
            client_email="client@example.test", ttl_days=400,
            email_send_callable=noop_email,
        ))


def test_send_client_email_failure_propagates(svc_db, captured_audit):
    """If the email callable raises, the service surfaces the error + audits."""
    _arun(ds.approve_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))

    async def boom_email(**kwargs):
        raise RuntimeError("smtp down")

    with pytest.raises(RuntimeError):
        _arun(ds.send_client(
            workspace_id=1, actor_user_id=DEV_USER_ID,
            client_email="client@example.test",
            email_send_callable=boom_email,
        ))
    # Audit recorded the failure.
    assert any(
        e["event_type"] == "delivery_send_failed" for e in captured_audit
    )


# ─────────────────────────────────────────────────────────────────────────
# HTTP-level tests via FastAPI TestClient (service stubbed)
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def stub_service(monkeypatch):
    """Stub the 3 service entry points so HTTP layer is exercised hermetically."""

    state: dict = {
        "delivery": {
            "id": "deadbeef-dead-beef-dead-beefdeadbeef",
            "workspace_id": "1",
            "status": "draft",
            "approved_at": None,
            "sent_at": None,
            "artifact_urls": [],
        },
        "non_members": {"2"},  # workspace_id (string) where caller is not a member
        "non_admins": {"3"},   # member but not admin
        "approved_at": None,
    }

    async def fake_get(*, workspace_id, actor_user_id):
        ws = str(workspace_id)
        if ws in state["non_members"]:
            raise ds.DeliveryForbiddenError("not member")
        return {"delivery": dict(state["delivery"], workspace_id=ws)}

    async def fake_approve(*, workspace_id, actor_user_id):
        ws = str(workspace_id)
        if ws in state["non_members"]:
            raise ds.DeliveryForbiddenError("not member")
        if ws in state["non_admins"]:
            raise ds.DeliveryForbiddenError("not admin")
        if state["delivery"]["status"] != "draft":
            raise ds.DeliveryConflictError("not draft")
        state["delivery"]["status"] = "approved"
        state["delivery"]["approved_at"] = "2026-05-16T12:00:00+00:00"
        state["approved_at"] = state["delivery"]["approved_at"]
        return {"approved_at": state["delivery"]["approved_at"]}

    async def fake_send_client(
        *, workspace_id, actor_user_id, client_email,
        ttl_days=None, email_send_callable=None, issue_token_callable=None,
    ):
        ws = str(workspace_id)
        if ws in state["non_members"]:
            raise ds.DeliveryForbiddenError("not member")
        if ws in state["non_admins"]:
            raise ds.DeliveryForbiddenError("not admin")
        if state["delivery"]["status"] != "approved":
            raise ds.DeliveryConflictError("not approved")
        state["delivery"]["status"] = "sent"
        state["delivery"]["sent_at"] = "2026-05-16T13:00:00+00:00"
        return {
            "sent_at": state["delivery"]["sent_at"],
            "delivery_token": "stub-token-" + "a" * 32,
        }

    monkeypatch.setattr(ds, "get_delivery", fake_get)
    monkeypatch.setattr(ds, "approve_delivery", fake_approve)
    monkeypatch.setattr(ds, "send_client", fake_send_client)
    return state


def test_http_get_delivery_happy(http_client, stub_service):
    """AC-F2 via HTTP."""
    r = http_client.get("/api/workspaces/1/delivery")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "delivery" in body
    assert body["delivery"]["workspace_id"] == "1"
    assert body["delivery"]["status"] in ("draft", "approved", "sent", "accepted")


def test_http_get_delivery_403_when_not_member(http_client, stub_service):
    """403 surfaces from DeliveryForbiddenError."""
    r = http_client.get("/api/workspaces/2/delivery")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "delivery.forbidden"


def test_http_get_delivery_422_invalid_id(http_client, stub_service):
    """AC-F4: invalid path id (non-integer) -> 422."""
    r = http_client.get("/api/workspaces/not-a-number/delivery")
    assert r.status_code == 422


def test_http_get_delivery_401_when_no_auth(monkeypatch, stub_service):
    """AC-F3: no auth bypass + no token -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/workspaces/1/delivery")
    assert r.status_code == 401


def test_http_approve_delivery_happy(http_client, stub_service):
    """AC-F5 via HTTP returns 201 + {approved_at}."""
    r = http_client.post("/api/workspaces/1/delivery/approve")
    assert r.status_code == 201, r.text
    body = r.json()
    assert "approved_at" in body


def test_http_approve_delivery_401_when_no_auth(monkeypatch, stub_service):
    """AC-F6: no auth -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/workspaces/1/delivery/approve")
    assert r.status_code == 401


def test_http_approve_delivery_409_already_approved(http_client, stub_service):
    """409 when delivery already approved (stub leaves status='approved' after first call)."""
    r1 = http_client.post("/api/workspaces/1/delivery/approve")
    assert r1.status_code == 201
    r2 = http_client.post("/api/workspaces/1/delivery/approve")
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "delivery.conflict"


def test_http_send_client_happy(http_client, stub_service):
    """AC-F7 via HTTP returns 201 + {sent_at, delivery_token}."""
    http_client.post("/api/workspaces/1/delivery/approve")
    r = http_client.post(
        "/api/workspaces/1/delivery/send-client",
        json={"client_email": "client@example.test", "ttl_days": 7},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "sent_at" in body
    assert "delivery_token" in body
    assert len(body["delivery_token"]) >= 16


def test_http_send_client_401_when_no_auth(monkeypatch, stub_service):
    """AC-F8: no auth -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post(
        "/api/workspaces/1/delivery/send-client",
        json={"client_email": "client@example.test"},
    )
    assert r.status_code == 401


def test_http_send_client_422_invalid_email(http_client, stub_service):
    """AC-F9: malformed body (bad email) -> 422 from Pydantic."""
    r = http_client.post(
        "/api/workspaces/1/delivery/send-client",
        json={"client_email": "not-an-email"},
    )
    assert r.status_code == 422


def test_http_send_client_422_missing_client_email(http_client, stub_service):
    """AC-F9: missing required client_email -> 422."""
    r = http_client.post(
        "/api/workspaces/1/delivery/send-client",
        json={},
    )
    assert r.status_code == 422


def test_http_send_client_422_invalid_ttl(http_client, stub_service):
    r = http_client.post(
        "/api/workspaces/1/delivery/send-client",
        json={"client_email": "client@example.test", "ttl_days": 0},
    )
    assert r.status_code == 422


def test_http_send_client_409_not_approved(http_client, stub_service):
    """409 when delivery not yet approved."""
    r = http_client.post(
        "/api/workspaces/1/delivery/send-client",
        json={"client_email": "client@example.test"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "delivery.conflict"


def test_http_send_client_403_when_non_admin(http_client, stub_service):
    """403 surfaces from DeliveryForbiddenError (non-admin)."""
    r = http_client.post(
        "/api/workspaces/3/delivery/send-client",
        json={"client_email": "client@example.test"},
    )
    assert r.status_code == 403


# ─────────────────────────────────────────────────────────────────────────
# Source / wiring invariants
# ─────────────────────────────────────────────────────────────────────────


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_router_is_wired_into_main():
    main_src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert "delivery_router" in main_src
    assert "app.include_router(delivery_router)" in main_src


def test_service_module_exports_required_symbols():
    """3 endpoint paths -> 3 service entry points."""
    for name in ("get_delivery", "approve_delivery", "send_client"):
        assert hasattr(ds, name), f"missing {name}"
    for err in (
        "DeliveryServiceError", "DeliveryNotFoundError",
        "DeliveryForbiddenError", "DeliveryConflictError",
        "DeliveryValidationError",
    ):
        assert hasattr(ds, err), f"missing {err}"
    assert ds.VALID_STATUSES == ("draft", "approved", "sent", "accepted")


def test_migration_creates_workspace_deliveries_with_rls():
    """Gate 4 (RLS coverage): migration enables RLS on workspace_deliveries."""
    mig = (
        REPO_ROOT / "supabase" / "migrations"
        / "20260518000000_workspace_deliveries.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS workspace_deliveries" in mig
    assert "ALTER TABLE workspace_deliveries ENABLE ROW LEVEL SECURITY" in mig
    assert "workspace_deliveries_service_role" in mig
    assert "workspace_deliveries_workspace_member_select" in mig
    assert "workspace_deliveries_workspace_admin_insert" in mig
    assert "workspace_deliveries_workspace_admin_update" in mig
    # CHECK constraint enforces the 4 statuses.
    assert "draft" in mig and "approved" in mig and "sent" in mig and "accepted" in mig


def test_artifact_urls_serialised_as_json(svc_db, captured_audit):
    """Serialiser must turn JSON-stored artifact_urls into a Python list."""
    # First call bootstraps the draft row + table.
    _arun(ds.get_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    # Now patch artifact_urls directly via SQLite.
    import sqlite3 as s
    db_path = svc_db
    conn = s.connect(str(db_path))
    conn.execute(
        "UPDATE workspace_deliveries "
        "SET artifact_urls = ? WHERE workspace_id = ?",
        (json.dumps([
            "https://example.test/spec.pdf",
            "https://example.test/code.zip",
        ]), 1),
    )
    conn.commit()
    conn.close()
    result = _arun(ds.get_delivery(workspace_id=1, actor_user_id=DEV_USER_ID))
    urls = result["delivery"]["artifact_urls"]
    assert isinstance(urls, list)
    assert "https://example.test/spec.pdf" in urls
    assert "https://example.test/code.zip" in urls
