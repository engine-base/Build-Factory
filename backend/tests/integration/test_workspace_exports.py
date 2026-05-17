"""T-V3-D-10: POST /api/workspaces/{id}/exports integration tests (F-031).

AC mapping (Tier 2 functional):
  - AC-F2 : POST with kind 'spec_pdf'|'delivery_report' → 201 + { job_id }
  - AC-F5 : non-member → 403
  - Aux   : 401 (no auth) / 404 (workspace 不在) / 422 (validation)
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
def isolated_export_db(tmp_path, monkeypatch):
    import aiosqlite
    db_file = tmp_path / "export_test.db"
    from services import export_service as svc
    monkeypatch.setattr(svc, "_db", lambda: aiosqlite)
    monkeypatch.setattr(svc, "_db_path", lambda: str(db_file))
    return db_file


@pytest.fixture
def fake_workspace(monkeypatch):
    """workspace_service.get_workspace / get_member を test 用に stub."""
    from routers import workspace_exports as we

    # workspace_id=42 = member / 43 = non-member / 99 = 不在
    async def fake_get_workspace(wid):
        if wid in (42, 43):
            return {"id": wid, "name": f"ws-{wid}"}
        return None

    async def fake_get_member(wid, uid):
        if wid == 42 and uid == "masato":
            return {"workspace_id": wid, "user_id": uid, "role": "owner"}
        return None

    monkeypatch.setattr(we.ws, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(we.ws, "get_member", fake_get_member)
    return {"member_ws": 42, "non_member_ws": 43, "missing_ws": 99}


# ──────────────────────────────────────────────────────────────────────────────
# AC-F2 happy path
# ──────────────────────────────────────────────────────────────────────────────


def test_post_export_returns_201_with_job_id(client, isolated_export_db, fake_workspace):
    """AC-F2 EVENT-DRIVEN: POST with kind=spec_pdf → 201 + { job_id, status: 'queued' }."""
    wid = fake_workspace["member_ws"]
    r = client.post(
        f"/api/workspaces/{wid}/exports",
        json={"type": "spec_pdf"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "job_id" in body
    uuid.UUID(body["job_id"])  # uuid format
    assert body["status"] == "queued"
    assert body["kind"] == "spec_pdf"
    assert body["workspace_id"] == wid
    assert body["requested_at"]


def test_post_export_delivery_report(client, isolated_export_db, fake_workspace):
    """AC-F2: delivery_report も同様に enqueue 成功."""
    wid = fake_workspace["member_ws"]
    r = client.post(
        f"/api/workspaces/{wid}/exports",
        json={"type": "delivery_report", "options": {"format": "pdf"}},
    )
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "delivery_report"


# ──────────────────────────────────────────────────────────────────────────────
# AC-F5: membership enforcement
# ──────────────────────────────────────────────────────────────────────────────


def test_post_export_non_member_returns_403(client, isolated_export_db, fake_workspace):
    """AC-F5 UNWANTED: non-member → 403."""
    wid = fake_workspace["non_member_ws"]
    r = client.post(
        f"/api/workspaces/{wid}/exports",
        json={"type": "spec_pdf"},
    )
    assert r.status_code == 403, r.text
    detail = r.json().get("detail", {})
    assert detail.get("code") == "workspaces.forbidden"


def test_post_export_unknown_workspace_returns_404(client, isolated_export_db, fake_workspace):
    """404 UNWANTED: workspace 不在 → 404."""
    wid = fake_workspace["missing_ws"]
    r = client.post(
        f"/api/workspaces/{wid}/exports",
        json={"type": "spec_pdf"},
    )
    assert r.status_code == 404, r.text
    detail = r.json().get("detail", {})
    assert detail.get("code") == "workspaces.not_found"


def test_post_export_invalid_kind_returns_422(client, isolated_export_db, fake_workspace):
    """422 UNWANTED: invalid kind → 422."""
    wid = fake_workspace["member_ws"]
    r = client.post(
        f"/api/workspaces/{wid}/exports",
        json={"type": "video_mp4"},  # not in ALLOWED_KINDS
    )
    assert r.status_code == 422, r.text
    detail = r.json().get("detail", {})
    assert detail.get("code") == "export.validation_error"


def test_post_export_missing_body_returns_422(client, isolated_export_db, fake_workspace):
    """422: missing required 'type' → pydantic 422."""
    wid = fake_workspace["member_ws"]
    r = client.post(f"/api/workspaces/{wid}/exports", json={})
    assert r.status_code == 422
