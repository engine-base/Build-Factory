"""T-V3-B-27 / F-024: GET /api/accounts/{id}/dashboard tests.

EARS AC coverage:
  AC-F4  EVENT-DRIVEN : aggregate KPI across caller's workspaces in the account
                        — test_aggregates_caller_workspaces
  AC-F8  EVENT-DRIVEN : 2xx shape matches openapi — test_response_shape
  AC-F9  UNWANTED     : missing/invalid token -> 401 — test_requires_auth
  AC-F10 UNWANTED     : invalid id -> 422 — test_invalid_account_id
                       account not found -> 404 — test_not_found
                       not a member -> 403 — test_forbidden_not_member
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    os.environ["DISABLE_BACKGROUND_WORKERS"] = "1"
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    os.environ.setdefault("SUPABASE_URL", "https://stub.supabase.co")
    os.environ.setdefault("SUPABASE_ANON_KEY", "stub-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "stub-service-key")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "stub-jwt-secret")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _stub_db(monkeypatch):
    """Stub account_service / db helpers so tests don't touch SQLite."""
    from services import account_dashboard as acc_dash

    accounts: dict[int, dict] = {
        1: {"id": 1, "name": "acme", "is_active": 1},
        2: {"id": 2, "name": "globex", "is_active": 1},
    }
    members: set[tuple[int, str]] = {
        (1, "00000000-0000-0000-0000-000000000001"),  # DEV_USER sub
    }
    caller_workspaces = {
        (1, "00000000-0000-0000-0000-000000000001"): [
            {"id": 10, "name": "ws-A", "status": "active", "member_role": "owner"},
            {"id": 11, "name": "ws-B", "status": "active", "member_role": "ws_admin"},
        ],
    }

    async def fake_get_account(aid):
        return accounts.get(aid)

    async def fake_is_member(aid, user_id):
        return (aid, user_id) in members

    async def fake_list_ws(aid, user_id):
        return caller_workspaces.get((aid, user_id), [])

    monkeypatch.setattr(acc_dash, "_get_account", fake_get_account)
    monkeypatch.setattr(acc_dash, "_is_account_member", fake_is_member)
    monkeypatch.setattr(
        acc_dash, "_list_caller_workspaces_in_account", fake_list_ws,
    )

    # workspace_dashboard.get_dashboard_stats stubbed to return fixed KPI
    from services import workspace_dashboard as wd

    async def fake_stats(workspace_id, *, now=None):
        return {
            "workspace_id": workspace_id,
            "progress": 0.5 if workspace_id == 10 else 0.25,
            "completed_tasks": 5 if workspace_id == 10 else 2,
            "running_sessions": 1,
            "monthly_cost_jpy": 1000.0,
            "pending_approvals": 1 if workspace_id == 10 else 0,
            "total_tasks": 10,
            "computed_at": 0.0,
            "duration_ms": 0,
        }
    monkeypatch.setattr(wd, "get_dashboard_stats", fake_stats)
    yield


# ─────────────────────────────────────────────────────────────────────
# Tier 1: structural / Tier 3 lint-style
# ─────────────────────────────────────────────────────────────────────


def test_module_files_exist():
    assert (REPO_ROOT / "backend" / "services" / "account_dashboard.py").exists()
    assert (REPO_ROOT / "backend" / "schemas" / "account_dashboard.py").exists()


def test_no_langchain_imports():
    txt = (REPO_ROOT / "backend" / "services" / "account_dashboard.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("langgraph", "langchain", "litellm"):
        for line in txt.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(f"import {forbidden}"), line
            assert not stripped.startswith(f"from {forbidden}"), line


# ─────────────────────────────────────────────────────────────────────
# Tier 2: functional EARS AC
# ─────────────────────────────────────────────────────────────────────


def test_aggregates_caller_workspaces(client):
    """AC-F4 EVENT-DRIVEN: aggregate KPI across caller's workspaces."""
    r = client.get("/api/accounts/1/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == 1
    assert len(body["workspaces"]) == 2
    kpi = body["kpi"]
    assert kpi["workspace_count"] == 2
    assert kpi["completed_tasks"] == 7  # 5 + 2
    assert kpi["running_sessions"] == 2  # 1 + 1
    assert kpi["monthly_cost_jpy"] == pytest.approx(2000.0)
    assert kpi["pending_approvals"] == 1


def test_response_shape(client):
    """AC-F8: response keys match schemas.account_dashboard.AccountDashboardResponse."""
    r = client.get("/api/accounts/1/dashboard")
    assert r.status_code == 200
    body = r.json()
    for key in ("account_id", "workspaces", "kpi", "computed_at", "duration_ms"):
        assert key in body
    for ws in body["workspaces"]:
        for key in (
            "id", "name", "status", "role",
            "progress", "completed_tasks", "running_sessions",
            "monthly_cost_jpy", "pending_approvals",
        ):
            assert key in ws, f"missing ws key {key}"


def test_invalid_account_id_returns_422(client):
    """AC-F10: account_id <= 0 -> 422 with field map."""
    r = client.get("/api/accounts/0/dashboard")
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "validation_error"
    assert "errors" in detail


def test_not_found_returns_404(client):
    """404: account row missing."""
    r = client.get("/api/accounts/999/dashboard")
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["code"] == "account_not_found"


def test_forbidden_not_member(client):
    """403: caller not a member of the account."""
    r = client.get("/api/accounts/2/dashboard")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "forbidden"


def test_requires_auth_when_bypass_off(client, monkeypatch):
    """AC-F9 UNWANTED: when DEV_BYPASS is off and no token -> 401."""
    from services import auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/accounts/1/dashboard")
    assert r.status_code == 401, r.text


def test_kpi_aggregate_progress_is_average(client):
    """AC-F4 EVENT-DRIVEN: total_progress is averaged across workspaces."""
    r = client.get("/api/accounts/1/dashboard")
    body = r.json()
    expected = (0.5 + 0.25) / 2
    assert body["kpi"]["total_progress"] == pytest.approx(expected, abs=1e-6)


def test_empty_workspaces_yields_zero_kpi(client, monkeypatch):
    """When caller belongs to the account but to zero workspaces, KPI=0."""
    from services import account_dashboard as acc_dash

    async def fake_list_ws(aid, user_id):
        return []
    monkeypatch.setattr(acc_dash, "_list_caller_workspaces_in_account", fake_list_ws)
    r = client.get("/api/accounts/1/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["kpi"]["workspace_count"] == 0
    assert body["kpi"]["total_progress"] == 0.0
    assert body["kpi"]["completed_tasks"] == 0
    assert body["workspaces"] == []
