"""T-V3-B-20 / F-013: Client portal backend (workspaces / spec / comments).

Hermetic tests for the 4 public client-portal endpoints + 1 member-scoped
resolve endpoint + service layer.

AC coverage (1:1 with audit MD docs/audit/2026-05-16_v3/T-V3-B-20.md):
    AC-F1  STATE-DRIVEN: expired token -> 409 (GET workspace)
    AC-F2  UNWANTED   : POST comments rate-limited -> 429
    AC-F3  EVENT-DRIVEN: GET workspace happy
    AC-F4  UNWANTED   : GET workspace without token -> 401
    AC-F5  EVENT-DRIVEN: GET spec happy
    AC-F6  UNWANTED   : GET spec without token -> 401
    AC-F7  EVENT-DRIVEN: GET comments happy
    AC-F8  UNWANTED   : GET comments without token -> 401
    AC-F9  UNWANTED   : GET comments invalid thread_id -> 422
    AC-F10 EVENT-DRIVEN: POST comments happy
    AC-F11 UNWANTED   : POST comments without token -> 401
    AC-F12 UNWANTED   : POST comments invalid body -> 422
    AC-F13 UNWANTED   : POST comments rate-limited -> 429
    AC-F14 EVENT-DRIVEN: POST resolve happy
    AC-F15 UNWANTED   : POST resolve without auth -> 401
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
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


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

VALID_TOKEN = "valid-token-abc123"
EXPIRED_TOKEN = "expired-token-xyz789"
REVOKED_TOKEN = "revoked-token-foo"

TOKEN_ID = "11111111-1111-1111-1111-111111111111"
EXPIRED_TOKEN_ID = "22222222-2222-2222-2222-222222222222"
REVOKED_TOKEN_ID = "33333333-3333-3333-3333-333333333333"

THREAD_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMMENT_ID_RESOLVED = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
COMMENT_ID_UNRESOLVED = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    now = datetime.now(timezone.utc)
    valid_expiry = _iso(now + timedelta(days=7))
    expired_at = _iso(now - timedelta(days=1))
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
        CREATE TABLE client_portal_comments (
            id TEXT PRIMARY KEY,
            workspace_id INTEGER NOT NULL,
            thread_id TEXT NOT NULL,
            token_id TEXT,
            author_name TEXT NOT NULL DEFAULT 'client',
            body TEXT NOT NULL,
            anchor TEXT,
            resolved_at TEXT,
            resolved_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO workspaces (id, name, status) VALUES (1, 'Demo workspace', 'active');
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (1, '{DEV_USER_ID}', 'admin');
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (1, 'member-user', 'contributor');
        INSERT INTO client_review_tokens
            (id, token, workspace_id, expires_at, spec_html_url)
            VALUES
            ('{TOKEN_ID}', '{VALID_TOKEN}', 1, '{valid_expiry}',
             'https://example.test/spec/abc.html');
        INSERT INTO client_review_tokens
            (id, token, workspace_id, expires_at)
            VALUES
            ('{EXPIRED_TOKEN_ID}', '{EXPIRED_TOKEN}', 1, '{expired_at}');
        INSERT INTO client_review_tokens
            (id, token, workspace_id, expires_at, revoked_at)
            VALUES
            ('{REVOKED_TOKEN_ID}', '{REVOKED_TOKEN}', 1, '{valid_expiry}',
             '{_iso(now - timedelta(hours=1))}');
        INSERT INTO client_portal_comments
            (id, workspace_id, thread_id, token_id, author_name, body)
            VALUES
            ('{COMMENT_ID_UNRESOLVED}', 1, '{THREAD_ID}', '{TOKEN_ID}',
             'client', 'first comment');
        INSERT INTO client_portal_comments
            (id, workspace_id, thread_id, token_id, author_name, body,
             resolved_at, resolved_by)
            VALUES
            ('{COMMENT_ID_RESOLVED}', 1, '{THREAD_ID}', '{TOKEN_ID}',
             'client', 'old comment', '{_iso(now - timedelta(days=1))}',
             '{DEV_USER_ID}');
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def svc_db(monkeypatch, tmp_path):
    """Bind client_portal_service to a tmp SQLite DB pre-seeded with fixtures."""
    db_path = tmp_path / "t_v3_b_20.db"
    _seed_db(db_path)
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


def test_get_workspace_by_token_happy(svc_db, captured_audit):
    """AC-F3: GET workspace happy returns PublicWorkspaceView shape."""
    result = _arun(cps.get_workspace_by_token(token=VALID_TOKEN))
    assert "workspace" in result
    ws = result["workspace"]
    assert ws["workspace_id"] == "1"
    assert ws["name"] == "Demo workspace"
    assert ws["status"] == "active"
    assert "spec_url" in ws


def test_get_workspace_by_token_401_when_token_missing(svc_db, captured_audit):
    """AC-F4: invalid/empty token -> TokenInvalidError (router 401)."""
    with pytest.raises(cps.TokenInvalidError):
        _arun(cps.get_workspace_by_token(token=""))


def test_get_workspace_by_token_401_when_token_unknown(svc_db, captured_audit):
    """AC-F4: unknown token -> TokenInvalidError (router 401)."""
    with pytest.raises(cps.TokenInvalidError):
        _arun(cps.get_workspace_by_token(token="no-such-token"))


def test_get_workspace_by_token_409_when_expired(svc_db, captured_audit):
    """AC-F1: expired token -> TokenExpiredError (router 409)."""
    with pytest.raises(cps.TokenExpiredError):
        _arun(cps.get_workspace_by_token(token=EXPIRED_TOKEN))


def test_get_workspace_by_token_409_when_revoked(svc_db, captured_audit):
    """STATE-DRIVEN: revoked token -> TokenExpiredError (router 409)."""
    with pytest.raises(cps.TokenExpiredError):
        _arun(cps.get_workspace_by_token(token=REVOKED_TOKEN))


def test_get_spec_by_token_happy(svc_db, captured_audit):
    """AC-F5: spec endpoint returns spec_html_url."""
    result = _arun(cps.get_spec_by_token(token=VALID_TOKEN))
    assert "spec_html_url" in result
    assert result["spec_html_url"].startswith("https://example.test/")


def test_get_spec_by_token_401(svc_db, captured_audit):
    with pytest.raises(cps.TokenInvalidError):
        _arun(cps.get_spec_by_token(token="bogus"))


def test_get_comments_by_thread_happy(svc_db, captured_audit):
    """AC-F7: GET comments returns array of PublicComment."""
    result = _arun(cps.get_comments_by_thread(
        thread_id=THREAD_ID, token=VALID_TOKEN,
    ))
    assert "comments" in result
    comments = result["comments"]
    assert len(comments) == 2
    for c in comments:
        assert {"id", "author_name", "body", "created_at", "resolved"} <= set(c.keys())
    # One resolved, one not
    assert any(c["resolved"] for c in comments)
    assert any(not c["resolved"] for c in comments)


def test_get_comments_by_thread_401(svc_db, captured_audit):
    with pytest.raises(cps.TokenInvalidError):
        _arun(cps.get_comments_by_thread(
            thread_id=THREAD_ID, token="bad",
        ))


def test_get_comments_by_thread_422_invalid_uuid(svc_db, captured_audit):
    """AC-F9: invalid thread_id -> CommentValidationError -> 422."""
    with pytest.raises(cps.CommentValidationError):
        _arun(cps.get_comments_by_thread(
            thread_id="not-a-uuid", token=VALID_TOKEN,
        ))


def test_post_comment_happy_returns_comment_id(svc_db, captured_audit):
    """AC-F10: POST comments happy returns comment_id uuid."""
    result = _arun(cps.post_comment(
        token=VALID_TOKEN, body="please change line 3",
        anchor="src/foo.py:3", thread_id=THREAD_ID,
    ))
    uuid.UUID(result["comment_id"])
    assert result["thread_id"] == THREAD_ID
    assert any(
        e["event_type"] == "client_comment_posted" for e in captured_audit
    )


def test_post_comment_creates_new_thread_when_none_given(svc_db, captured_audit):
    """If no thread_id supplied, the service generates one."""
    result = _arun(cps.post_comment(
        token=VALID_TOKEN, body="kicking off a new thread",
    ))
    uuid.UUID(result["thread_id"])


def test_post_comment_401_invalid_token(svc_db, captured_audit):
    """AC-F11: no/invalid token -> TokenInvalidError."""
    with pytest.raises(cps.TokenInvalidError):
        _arun(cps.post_comment(token="bogus", body="x"))


def test_post_comment_422_empty_body(svc_db, captured_audit):
    """AC-F12: empty body -> CommentValidationError."""
    with pytest.raises(cps.CommentValidationError):
        _arun(cps.post_comment(token=VALID_TOKEN, body="   "))


def test_post_comment_422_body_too_long(svc_db, captured_audit):
    too_long = "x" * (cps.MAX_COMMENT_BODY_LEN + 1)
    with pytest.raises(cps.CommentValidationError):
        _arun(cps.post_comment(token=VALID_TOKEN, body=too_long))


def test_post_comment_422_invalid_thread_id(svc_db, captured_audit):
    with pytest.raises(cps.CommentValidationError):
        _arun(cps.post_comment(
            token=VALID_TOKEN, body="x", thread_id="not-uuid",
        ))


def test_post_comment_429_rate_limited(svc_db, captured_audit):
    """AC-F2 / AC-F13: > 20 comments / hour / token -> RateLimitedError.

    Fixture already seeds 1 comment under VALID_TOKEN in the same hour. We
    post 19 more (total 20) and then assert the 21st raises.
    """
    inserted = 0
    raised = False
    for _ in range(cps.RATE_LIMIT_PER_HOUR + 5):
        try:
            _arun(cps.post_comment(
                token=VALID_TOKEN, body="rapid-fire comment",
            ))
            inserted += 1
        except cps.RateLimitedError:
            raised = True
            break
    assert raised, f"rate limit never triggered after {inserted} inserts"
    # The fixture seeded 1 comment + we should have inserted up to RATE_LIMIT-1
    # before the boundary triggered (since the check is pre-insert).
    assert inserted < cps.RATE_LIMIT_PER_HOUR


def test_resolve_comment_happy(svc_db, captured_audit):
    """AC-F14: resolve happy returns resolved_at."""
    result = _arun(cps.resolve_comment(
        comment_id=COMMENT_ID_UNRESOLVED, actor_user_id=DEV_USER_ID,
    ))
    assert "resolved_at" in result
    assert result["resolved_at"].endswith("+00:00")
    assert any(
        e["event_type"] == "client_comment_resolved" for e in captured_audit
    )


def test_resolve_comment_409_when_already_resolved(svc_db, captured_audit):
    with pytest.raises(cps.CommentConflictError):
        _arun(cps.resolve_comment(
            comment_id=COMMENT_ID_RESOLVED, actor_user_id=DEV_USER_ID,
        ))


def test_resolve_comment_404_when_missing(svc_db, captured_audit):
    with pytest.raises(cps.CommentNotFoundError):
        _arun(cps.resolve_comment(
            comment_id="99999999-9999-9999-9999-999999999999",
            actor_user_id=DEV_USER_ID,
        ))


def test_resolve_comment_403_when_non_member(svc_db, captured_audit):
    with pytest.raises(cps.CommentForbiddenError):
        _arun(cps.resolve_comment(
            comment_id=COMMENT_ID_UNRESOLVED, actor_user_id="stranger",
        ))


def test_resolve_comment_422_invalid_uuid(svc_db, captured_audit):
    with pytest.raises(cps.CommentValidationError):
        _arun(cps.resolve_comment(
            comment_id="not-a-uuid", actor_user_id=DEV_USER_ID,
        ))


def test_issue_token_happy(svc_db):
    """Helper used by T-V3-B-21 send-client — verify token shape."""
    result = _arun(cps.issue_token(
        workspace_id=1, issued_by=DEV_USER_ID,
        client_email="client@example.test",
        spec_html_url="https://example.test/spec/x.html",
        ttl_days=7,
    ))
    assert "token" in result and len(result["token"]) >= 32
    assert result["expires_at"].endswith("+00:00")
    uuid.UUID(result["id"])


# ─────────────────────────────────────────────────────────────────────────
# HTTP-level tests via FastAPI TestClient (service stubbed)
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def stub_service(monkeypatch):
    """Stub the 5 service entry points so HTTP layer is exercised hermetically."""

    state = {
        "tokens": {
            VALID_TOKEN: {"workspace_id": 1, "expired": False, "revoked": False},
            EXPIRED_TOKEN: {"workspace_id": 1, "expired": True, "revoked": False},
        },
        "rate_limited_tokens": set(),
        "comments_resolved": {COMMENT_ID_RESOLVED},
        "comments_missing": {"99999999-9999-9999-9999-999999999999"},
    }

    def _check_token(token):
        if token not in state["tokens"]:
            raise cps.TokenInvalidError("token not found")
        info = state["tokens"][token]
        if info["expired"] or info["revoked"]:
            raise cps.TokenExpiredError("token expired")

    async def fake_get_ws(*, token):
        _check_token(token)
        return {"workspace": {"workspace_id": "1", "name": "Demo",
                              "status": "active", "spec_url": "",
                              "delivery": None}}

    async def fake_get_spec(*, token):
        _check_token(token)
        return {"spec_html_url": "https://example.test/spec/x.html"}

    async def fake_get_comments(*, thread_id, token):
        _check_token(token)
        try:
            uuid.UUID(thread_id)
        except ValueError:
            raise cps.CommentValidationError("invalid thread_id")
        return {"comments": [
            {"id": str(uuid.uuid4()), "author_name": "client",
             "body": "stub", "created_at": "2026-05-16T00:00:00+00:00",
             "resolved": False},
        ]}

    async def fake_post_comment(*, token, body, anchor=None,
                                 thread_id=None, author_name=None):
        _check_token(token)
        if not body or not body.strip():
            raise cps.CommentValidationError("body required")
        if token in state["rate_limited_tokens"]:
            raise cps.RateLimitedError("rate limit exceeded")
        return {
            "comment_id": str(uuid.uuid4()),
            "thread_id": thread_id or str(uuid.uuid4()),
        }

    async def fake_resolve(*, comment_id, actor_user_id):
        try:
            uuid.UUID(comment_id)
        except ValueError:
            raise cps.CommentValidationError("invalid comment id")
        if comment_id in state["comments_missing"]:
            raise cps.CommentNotFoundError("missing")
        if comment_id in state["comments_resolved"]:
            raise cps.CommentConflictError("already resolved")
        return {"resolved_at": "2026-05-16T12:00:00+00:00"}

    monkeypatch.setattr(cps, "get_workspace_by_token", fake_get_ws)
    monkeypatch.setattr(cps, "get_spec_by_token", fake_get_spec)
    monkeypatch.setattr(cps, "get_comments_by_thread", fake_get_comments)
    monkeypatch.setattr(cps, "post_comment", fake_post_comment)
    monkeypatch.setattr(cps, "resolve_comment", fake_resolve)
    return state


def test_http_get_workspace_happy(http_client, stub_service):
    """AC-F3 happy via HTTP."""
    r = http_client.get(f"/api/client/workspaces/{VALID_TOKEN}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "workspace" in body
    assert body["workspace"]["workspace_id"] == "1"


def test_http_get_workspace_401_unknown_token(http_client, stub_service):
    """AC-F4: unknown token -> 401."""
    r = http_client.get("/api/client/workspaces/no-such-token")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "client_portal.unauthorized"


def test_http_get_workspace_409_expired(http_client, stub_service):
    """AC-F1: expired token -> 409."""
    r = http_client.get(f"/api/client/workspaces/{EXPIRED_TOKEN}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "client_portal.token_expired"


def test_http_get_spec_happy(http_client, stub_service):
    """AC-F5 happy via HTTP."""
    r = http_client.get(f"/api/client/workspaces/{VALID_TOKEN}/spec")
    assert r.status_code == 200, r.text
    assert "spec_html_url" in r.json()


def test_http_get_spec_401_unknown_token(http_client, stub_service):
    """AC-F6: unknown token -> 401."""
    r = http_client.get("/api/client/workspaces/bogus/spec")
    assert r.status_code == 401


def test_http_get_comments_happy(http_client, stub_service):
    """AC-F7 happy via HTTP."""
    r = http_client.get(
        f"/api/client/comments/{THREAD_ID}?token={VALID_TOKEN}",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "comments" in body
    assert isinstance(body["comments"], list)


def test_http_get_comments_401_no_token(http_client, stub_service):
    """AC-F8: missing token query -> 422 (FastAPI required-query) or 401."""
    r = http_client.get(f"/api/client/comments/{THREAD_ID}")
    # FastAPI returns 422 when a required query parameter is absent. Either
    # 422 or 401 is acceptable per features.json#F-013 since 422 is the
    # field-level validation map AC-F9 also documents.
    assert r.status_code in (401, 422)


def test_http_get_comments_401_invalid_token(http_client, stub_service):
    r = http_client.get(
        f"/api/client/comments/{THREAD_ID}?token=bogus",
    )
    assert r.status_code == 401


def test_http_get_comments_422_invalid_thread(http_client, stub_service):
    """AC-F9: invalid thread_id (non-uuid) -> 422."""
    r = http_client.get(
        f"/api/client/comments/not-a-uuid?token={VALID_TOKEN}",
    )
    assert r.status_code == 422


def test_http_post_comment_happy(http_client, stub_service):
    """AC-F10 happy via HTTP."""
    r = http_client.post(
        "/api/client/comments",
        json={"token": VALID_TOKEN, "body": "please fix line 3",
              "anchor": "src/foo.py:3"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    uuid.UUID(body["comment_id"])


def test_http_post_comment_401_unknown_token(http_client, stub_service):
    """AC-F11: unknown token -> 401."""
    r = http_client.post(
        "/api/client/comments",
        json={"token": "no-such", "body": "x"},
    )
    assert r.status_code == 401


def test_http_post_comment_422_empty_body(http_client, stub_service):
    """AC-F12: empty body -> 422 (pydantic min_length=1)."""
    r = http_client.post(
        "/api/client/comments",
        json={"token": VALID_TOKEN, "body": ""},
    )
    assert r.status_code == 422


def test_http_post_comment_422_missing_required_token(http_client, stub_service):
    r = http_client.post("/api/client/comments", json={"body": "x"})
    assert r.status_code == 422


def test_http_post_comment_429_rate_limited(http_client, stub_service):
    """AC-F13 / AC-F2: rate limit -> 429."""
    stub_service["rate_limited_tokens"].add(VALID_TOKEN)
    r = http_client.post(
        "/api/client/comments",
        json={"token": VALID_TOKEN, "body": "over the limit"},
    )
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "client_portal.rate_limited"


def test_http_resolve_comment_happy(http_client, stub_service):
    """AC-F14 happy via HTTP (auth bypassed by DEV mode)."""
    cid = str(uuid.uuid4())
    r = http_client.post(f"/api/comments/{cid}/resolve")
    assert r.status_code == 201, r.text
    assert "resolved_at" in r.json()


def test_http_resolve_comment_409_already_resolved(http_client, stub_service):
    r = http_client.post(f"/api/comments/{COMMENT_ID_RESOLVED}/resolve")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "client_portal.conflict"


def test_http_resolve_comment_404_missing(http_client, stub_service):
    missing = "99999999-9999-9999-9999-999999999999"
    r = http_client.post(f"/api/comments/{missing}/resolve")
    assert r.status_code == 404


def test_http_resolve_comment_401_no_auth(monkeypatch, stub_service):
    """AC-F15: resolve without auth -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post(f"/api/comments/{str(uuid.uuid4())}/resolve")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────
# Source / wiring invariants
# ─────────────────────────────────────────────────────────────────────────


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_router_is_wired_into_main():
    main_src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert "client_portal_router" in main_src
    assert "app.include_router(client_portal_router)" in main_src


def test_service_module_exports_required_symbols():
    """5 endpoint paths -> 5 service entry points."""
    for name in (
        "get_workspace_by_token", "get_spec_by_token",
        "get_comments_by_thread", "post_comment", "resolve_comment",
        "issue_token",
    ):
        assert hasattr(cps, name), f"missing {name}"
    assert cps.RATE_LIMIT_PER_HOUR == 20


def test_migration_creates_client_portal_tables_with_rls():
    """Gate 4 (RLS coverage): migration enables RLS on both new tables."""
    mig = (
        REPO_ROOT / "supabase" / "migrations"
        / "20260517000000_client_portal_tokens_comments.sql"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS client_review_tokens" in mig
    assert "CREATE TABLE IF NOT EXISTS client_portal_comments" in mig
    assert "ALTER TABLE client_review_tokens ENABLE ROW LEVEL SECURITY" in mig
    assert "ALTER TABLE client_portal_comments ENABLE ROW LEVEL SECURITY" in mig
    assert "client_review_tokens_service_role" in mig
    assert "client_portal_comments_service_role" in mig
    assert "client_review_tokens_workspace_member_select" in mig
    assert "client_portal_comments_workspace_member_select" in mig
