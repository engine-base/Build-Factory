"""T-V3-B-19 / F-013: PR review backend (get / approve / comments / merge).

Hermetic tests for the 4 new endpoints + service layer. The DB is mocked at two
layers:

  * Service-level tests: ``pr_service.aiosqlite`` is monkey-patched to the real
    ``aiosqlite`` library + ``DB_PATH`` swapped to a tmp SQLite file pre-seeded
    with workspaces / members / repos / PRs (matches the schema bootstrap in
    ``pr_service._ensure_pr_tables``).
  * Router-level tests: ``pr_service.{get_pr_by_number, approve_pr,
    add_pr_comment, merge_pr}`` are stubbed so the HTTP layer is verified
    independently of the DB layer.

AC coverage (1:1 with audit MD docs/audit/2026-05-16_v3/T-V3-B-19.md):
  AC-F1  EVENT-DRIVEN: merge happy path emits pr_merged audit
  AC-F2  UNWANTED   : merge with unresolved conflicts -> 409
  AC-F3  EVENT-DRIVEN: GET PR happy path returns features.json#F-013 contract
  AC-F4  UNWANTED   : GET PR without auth -> 401
  AC-F5  EVENT-DRIVEN: approve happy path returns approved_at
  AC-F6  UNWANTED   : approve without auth -> 401
  AC-F7  EVENT-DRIVEN: comments happy path returns comment_id
  AC-F8  UNWANTED   : comments without auth -> 401
  AC-F9  UNWANTED   : comments invalid body -> 422
  AC-F10 EVENT-DRIVEN: merge happy path returns merged_at
  AC-F11 UNWANTED   : merge without auth -> 401
  AC-F12 UNWANTED   : merge with invalid merge_method -> 422
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import aiosqlite as real_aiosqlite
import pytest
from fastapi.testclient import TestClient

# Ensure required env vars are set for `services.supabase_client` import.
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
os.environ.setdefault("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
os.environ.setdefault("SUPABASE_ANON_KEY", "stub")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "stub")
os.environ.setdefault("SUPABASE_JWT_SECRET", "stub")

from services import pr_service  # noqa: E402


DEV_USER_ID = "00000000-0000-0000-0000-000000000001"


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE workspace_members (
            workspace_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'contributor',
            invited_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (workspace_id, user_id)
        );
        CREATE TABLE repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            default_branch TEXT DEFAULT 'main',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pull_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            status TEXT DEFAULT 'open',
            head_branch TEXT,
            base_branch TEXT DEFAULT 'main',
            url TEXT,
            has_conflicts INTEGER DEFAULT 0,
            approved_at TEXT,
            approved_by TEXT,
            merged_at TEXT,
            merged_sha TEXT,
            merge_method TEXT,
            html_review_url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pr_comments (
            id TEXT PRIMARY KEY,
            pr_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            author_user_id TEXT NOT NULL,
            body TEXT NOT NULL,
            anchor_file TEXT,
            anchor_line INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (1, '00000000-0000-0000-0000-000000000001', 'admin');
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (1, 'member-user', 'contributor');
        INSERT INTO workspace_members (workspace_id, user_id, role)
            VALUES (2, 'other-admin', 'admin');
        INSERT INTO repos (id, workspace_id, name) VALUES (10, 1, 'repo-a');
        INSERT INTO pull_requests (id, repo_id, number, title, author, status)
            VALUES (100, 10, 42, 'feat: thing', 'masato', 'open');
        INSERT INTO pull_requests (id, repo_id, number, title, status, has_conflicts)
            VALUES (101, 10, 43, 'feat: conflict', 'open', 1);
        INSERT INTO pull_requests (id, repo_id, number, title, status)
            VALUES (102, 10, 44, 'feat: approvable', 'open');
        INSERT INTO pull_requests (id, repo_id, number, title, status,
                                    approved_at, approved_by)
            VALUES (103, 10, 45, 'feat: already approved', 'approved',
                    '2026-05-16T00:00:00+00:00', 'masato');
        INSERT INTO pull_requests (id, repo_id, number, title, status,
                                    approved_at, approved_by,
                                    merged_at, merged_sha, merge_method)
            VALUES (104, 10, 46, 'feat: already merged', 'merged',
                    '2026-05-15T00:00:00+00:00', 'masato',
                    '2026-05-16T00:00:00+00:00', 'sha-xyz', 'squash');
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def svc_db(monkeypatch, tmp_path):
    """Bind pr_service to a tmp SQLite DB pre-seeded with fixtures.

    pr_service was authored to call ``aiosqlite.connect(DB_PATH)`` via the
    ``db.async_db`` shim (which is actually a psycopg adapter at runtime).
    We swap that out for the real ``aiosqlite`` library and a tmp DB file.
    """
    db_path = tmp_path / "t_v3_b_19.db"
    _seed_db(db_path)
    monkeypatch.setattr(pr_service, "aiosqlite", real_aiosqlite, raising=True)
    monkeypatch.setattr(pr_service, "DB_PATH", str(db_path), raising=True)
    return db_path


@pytest.fixture
def captured_audit(monkeypatch):
    """Capture audit emissions for assertion."""
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
    """TestClient with no DB seeding — for router-only tests that stub the service."""
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _arun(coro):
    """Run an async coroutine in a fresh event loop (pytest-asyncio-free)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────
# Service-level tests (real SQLite DB, hermetic)
# ─────────────────────────────────────────────────────────────────────────


def test_get_pr_by_number_happy_returns_contract(svc_db, captured_audit):
    """AC-F3: GET happy returns pr + html_review_url shape."""
    result = _arun(pr_service.get_pr_by_number(
        workspace_id=1, pr_number=42, actor_user_id=DEV_USER_ID,
    ))
    assert "pr" in result
    assert "html_review_url" in result
    assert result["pr"]["id"] == 100
    assert result["pr"]["number"] == 42
    assert result["pr"]["title"] == "feat: thing"
    assert isinstance(result["html_review_url"], str)


def test_get_pr_by_number_404_when_missing(svc_db, captured_audit):
    with pytest.raises(pr_service.PRNotFoundError):
        _arun(pr_service.get_pr_by_number(
            workspace_id=1, pr_number=9999, actor_user_id=DEV_USER_ID,
        ))


def test_get_pr_forbidden_for_non_member(svc_db, captured_audit):
    with pytest.raises(pr_service.PRForbiddenError):
        _arun(pr_service.get_pr_by_number(
            workspace_id=1, pr_number=42, actor_user_id="stranger",
        ))


def test_approve_pr_happy_emits_audit(svc_db, captured_audit):
    """AC-F5: approve happy path."""
    result = _arun(pr_service.approve_pr(
        pr_id=102, actor_user_id=DEV_USER_ID, comment="LGTM",
    ))
    assert "approved_at" in result
    assert result["approved_at"].endswith("+00:00")
    assert any(e["event_type"] == "pr_approved" for e in captured_audit)


def test_approve_pr_409_when_already_approved(svc_db, captured_audit):
    with pytest.raises(pr_service.PRConflictError):
        _arun(pr_service.approve_pr(pr_id=103, actor_user_id=DEV_USER_ID))


def test_approve_pr_409_when_already_merged(svc_db, captured_audit):
    with pytest.raises(pr_service.PRConflictError):
        _arun(pr_service.approve_pr(pr_id=104, actor_user_id=DEV_USER_ID))


def test_approve_pr_forbidden_for_non_admin(svc_db, captured_audit):
    """contributor cannot approve."""
    with pytest.raises(pr_service.PRForbiddenError):
        _arun(pr_service.approve_pr(pr_id=102, actor_user_id="member-user"))


def test_add_pr_comment_happy_returns_uuid(svc_db, captured_audit):
    """AC-F7: comments happy."""
    result = _arun(pr_service.add_pr_comment(
        pr_id=100, actor_user_id="member-user", body="please fix line 3",
        anchor_file="foo.py", anchor_line=3,
    ))
    cid = result["comment_id"]
    # validate uuid shape
    uuid.UUID(cid)
    assert any(e["event_type"] == "pr_comment_added" for e in captured_audit)


def test_add_pr_comment_422_empty_body(svc_db, captured_audit):
    """AC-F9: invalid body."""
    with pytest.raises(pr_service.PRValidationError):
        _arun(pr_service.add_pr_comment(
            pr_id=100, actor_user_id=DEV_USER_ID, body="   ",
        ))


def test_add_pr_comment_422_anchor_line_zero(svc_db, captured_audit):
    with pytest.raises(pr_service.PRValidationError):
        _arun(pr_service.add_pr_comment(
            pr_id=100, actor_user_id=DEV_USER_ID, body="x",
            anchor_line=0,
        ))


def test_merge_pr_happy_emits_pr_merged_audit(svc_db, captured_audit):
    """AC-F1 / AC-F10: merge happy + pr_merged audit."""
    # approve first
    _arun(pr_service.approve_pr(pr_id=102, actor_user_id=DEV_USER_ID))
    result = _arun(pr_service.merge_pr(
        pr_id=102, actor_user_id=DEV_USER_ID, merge_method="squash",
    ))
    assert "merged_at" in result
    assert "sha" in result
    assert result["sha"].startswith("stub-")
    assert any(e["event_type"] == "pr_merged" for e in captured_audit)


def test_merge_pr_409_on_conflicts(svc_db, captured_audit):
    """AC-F2: unresolved conflicts -> 409."""
    with pytest.raises(pr_service.PRConflictError):
        _arun(pr_service.merge_pr(
            pr_id=101, actor_user_id=DEV_USER_ID, merge_method="squash",
        ))


def test_merge_pr_409_when_not_approved(svc_db, captured_audit):
    with pytest.raises(pr_service.PRConflictError):
        _arun(pr_service.merge_pr(
            pr_id=100, actor_user_id=DEV_USER_ID, merge_method="squash",
        ))


def test_merge_pr_422_invalid_merge_method(svc_db, captured_audit):
    """AC-F12: invalid merge_method -> 422."""
    with pytest.raises(pr_service.PRValidationError):
        _arun(pr_service.merge_pr(
            pr_id=102, actor_user_id=DEV_USER_ID, merge_method="bogus",
        ))


def test_merge_pr_uses_injected_github_callable(svc_db, captured_audit):
    """github_merge_callable receives (pr_id, merge_method)."""
    captured: list[tuple] = []

    async def fake_gh(pr_id: int, merge_method: str) -> dict[str, Any]:
        captured.append((pr_id, merge_method))
        return {"sha": "real-sha-abc"}

    _arun(pr_service.approve_pr(pr_id=102, actor_user_id=DEV_USER_ID))
    result = _arun(pr_service.merge_pr(
        pr_id=102, actor_user_id=DEV_USER_ID, merge_method="rebase",
        github_merge_callable=fake_gh,
    ))
    assert captured == [(102, "rebase")]
    assert result["sha"] == "real-sha-abc"


# ─────────────────────────────────────────────────────────────────────────
# HTTP-level tests via FastAPI TestClient (service is stubbed)
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def stub_service(monkeypatch):
    """Stub all 4 pr_service mutators to avoid DB hits in router tests."""
    state = {
        "approved": set(),
        "merged": set(),
        "conflicting": {101},
        "approved_seed": {103},
        "merged_seed": {104},
        "missing": {9999},
    }

    async def fake_get(*, workspace_id, pr_number, actor_user_id):
        if pr_number in state["missing"]:
            raise pr_service.PRNotFoundError("not found")
        return {
            "pr": {"id": 100 if pr_number == 42 else 200,
                   "number": pr_number, "title": "stub", "status": "open"},
            "html_review_url": "/stub-url",
        }

    async def fake_approve(*, pr_id, actor_user_id, comment=None):
        if pr_id in state["approved_seed"] or pr_id in state["approved"]:
            raise pr_service.PRConflictError("already approved")
        if pr_id in state["merged_seed"]:
            raise pr_service.PRConflictError("already merged")
        state["approved"].add(pr_id)
        return {"approved_at": "2026-05-16T12:00:00+00:00"}

    async def fake_comment(*, pr_id, actor_user_id, body,
                           anchor_file=None, anchor_line=None):
        if not body or not body.strip():
            raise pr_service.PRValidationError("body required")
        return {"comment_id": str(uuid.uuid4())}

    async def fake_merge(*, pr_id, actor_user_id, merge_method,
                         github_merge_callable=None):
        if pr_id in state["conflicting"]:
            raise pr_service.PRConflictError("conflicts")
        if pr_id not in state["approved"] and pr_id not in state["approved_seed"]:
            raise pr_service.PRConflictError("not approved")
        return {"merged_at": "2026-05-16T12:30:00+00:00", "sha": "stub-sha"}

    monkeypatch.setattr(pr_service, "get_pr_by_number", fake_get)
    monkeypatch.setattr(pr_service, "approve_pr", fake_approve)
    monkeypatch.setattr(pr_service, "add_pr_comment", fake_comment)
    monkeypatch.setattr(pr_service, "merge_pr", fake_merge)
    return state


def test_http_get_pr_happy(http_client, stub_service):
    """AC-F3 happy path through HTTP."""
    r = http_client.get("/api/workspaces/1/prs/42")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pr" in body and "html_review_url" in body


def test_http_get_pr_404_when_missing(http_client, stub_service):
    r = http_client.get("/api/workspaces/1/prs/9999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "prs.not_found"


def test_http_get_pr_401_when_no_auth(monkeypatch, stub_service):
    """AC-F4: without auth -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/workspaces/1/prs/42")
    assert r.status_code == 401


def test_http_approve_happy(http_client, stub_service):
    """AC-F5: approve happy."""
    r = http_client.post("/api/prs/102/approve", json={"comment": "LGTM"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "approved_at" in body


def test_http_approve_409_when_already_approved(http_client, stub_service):
    r = http_client.post("/api/prs/103/approve", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "prs.conflict"


def test_http_approve_401_no_auth(monkeypatch, stub_service):
    """AC-F6: approve without auth -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/prs/102/approve", json={})
    assert r.status_code == 401


def test_http_comment_happy(http_client, stub_service):
    """AC-F7: comments happy."""
    r = http_client.post(
        "/api/prs/100/comments",
        json={"body": "please fix", "anchor_file": "foo.py", "anchor_line": 3},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["comment_id"]
    uuid.UUID(cid)


def test_http_comment_422_empty_body(http_client, stub_service):
    """AC-F9: empty body -> 422."""
    r = http_client.post("/api/prs/100/comments", json={"body": ""})
    assert r.status_code == 422


def test_http_comment_401_no_auth(monkeypatch, stub_service):
    """AC-F8: comments without auth -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/prs/100/comments", json={"body": "hi"})
    assert r.status_code == 401


def test_http_merge_happy(http_client, stub_service):
    """AC-F1 / AC-F10: merge happy."""
    http_client.post("/api/prs/102/approve", json={})
    r = http_client.post("/api/prs/102/merge", json={"merge_method": "squash"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "merged_at" in body and "sha" in body


def test_http_merge_409_on_conflicts(http_client, stub_service):
    """AC-F2: 409 on conflicts."""
    r = http_client.post("/api/prs/101/merge", json={"merge_method": "squash"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "prs.conflict"


def test_http_merge_422_invalid_method(http_client, stub_service):
    """AC-F12: invalid merge_method -> 422."""
    r = http_client.post("/api/prs/102/merge", json={"merge_method": "bogus"})
    assert r.status_code == 422


def test_http_merge_401_no_auth(monkeypatch, stub_service):
    """AC-F11: merge without auth -> 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/prs/102/merge", json={"merge_method": "squash"})
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────
# Source / wiring invariants
# ─────────────────────────────────────────────────────────────────────────


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_router_is_wired_into_main():
    main_src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert "prs_router" in main_src
    assert "app.include_router(prs_router)" in main_src


def test_service_module_exports_required_symbols():
    """4 endpoint paths -> 4 service functions."""
    for name in ("get_pr_by_number", "approve_pr", "add_pr_comment", "merge_pr"):
        assert hasattr(pr_service, name), f"missing {name}"
    assert pr_service.VALID_MERGE_METHODS == ("squash", "merge", "rebase")


def test_migration_pr_comments_has_rls_enabled():
    """Gate 4 (RLS coverage): pr_comments migration enables RLS."""
    mig = (REPO_ROOT / "supabase" / "migrations"
           / "20260516000000_pr_comments.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS pr_comments" in mig
    assert "ALTER TABLE pr_comments ENABLE ROW LEVEL SECURITY" in mig
    assert "pr_comments_service_role" in mig
    assert "pr_comments_workspace_member_select" in mig
    assert "pr_comments_workspace_member_insert" in mig
