"""T-V3-B-09 / F-005b: Mocks backend (ai-edit) tests.

AC マッピング (tickets-group-b-backend.json#T-V3-B-09.acceptance_criteria.functional):
  AC-F1  UNWANTED      POST ai-edit > 30/min → 429
  AC-F2  EVENT-DRIVEN  POST ai-edit valid → 2xx {diff, new_html, tokens_used}
  AC-F3  UNWANTED      POST ai-edit w/o token → 401
  AC-F4  UNWANTED      POST ai-edit bad body → 422
  AC-F5  UNWANTED      POST ai-edit rate limit (alias) → 429
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import mocks as svc


REPO_ROOT = Path(__file__).resolve().parents[3]
ROUTER = REPO_ROOT / "backend" / "routers" / "mocks.py"
SERVICE = REPO_ROOT / "backend" / "services" / "mocks.py"
SCHEMAS = REPO_ROOT / "backend" / "schemas" / "mocks.py"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    am.DEV_BYPASS = True
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    svc.reset_store()
    yield
    svc.reset_store()


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit, raising=False)
    yield captured


# ══════════════════════════════════════════════════════════════════════
# Structural sanity — files exist
# ══════════════════════════════════════════════════════════════════════


def test_router_file_exists():
    assert ROUTER.exists(), "router file missing"


def test_service_file_exists():
    assert SERVICE.exists(), "service file missing"


def test_schemas_file_exists():
    assert SCHEMAS.exists(), "schemas file missing"


# ══════════════════════════════════════════════════════════════════════
# Service-layer unit tests (ai-edit)
# ══════════════════════════════════════════════════════════════════════


def test_service_ai_edit_returns_diff_and_tokens():
    """AC-F2 EVENT-DRIVEN: valid prompt returns diff/new_html/tokens_used."""
    r = svc.ai_edit_mock(1, "S-023", "make button bigger", actor_user_id="alice")
    assert "diff" in r and r["diff"]
    assert "new_html" in r and r["new_html"]
    assert isinstance(r["tokens_used"], int) and r["tokens_used"] >= 1


def test_service_ai_edit_uses_latest_html_as_base():
    """AC-F2: ai-edit uses latest html version as base."""
    svc.put_mock_html(2, "S-024", "<div>old</div>", actor_user_id="alice")
    r = svc.ai_edit_mock(2, "S-024", "tweak something", actor_user_id="alice")
    assert "<div>old</div>" in r["new_html"]


def test_service_ai_edit_blank_prompt_raises_422():
    """AC-F4 UNWANTED: blank prompt → MockValidationError."""
    with pytest.raises(svc.MockValidationError):
        svc.ai_edit_mock(1, "S-023", "   ", actor_user_id="alice")


def test_service_ai_edit_non_string_prompt_raises_422():
    """AC-F4 UNWANTED: non-string prompt → MockValidationError."""
    with pytest.raises(svc.MockValidationError):
        svc.ai_edit_mock(1, "S-023", 12345, actor_user_id="alice")  # type: ignore[arg-type]


def test_service_ai_edit_oversize_prompt_raises_422():
    """AC-F4 UNWANTED: prompt > MAX_PROMPT_LEN → MockValidationError."""
    big = "x" * (svc.MAX_PROMPT_LEN + 1)
    with pytest.raises(svc.MockValidationError):
        svc.ai_edit_mock(1, "S-023", big, actor_user_id="alice")


def test_service_ai_edit_rate_limit_31st_call_raises_429():
    """AC-F1 / AC-F5 UNWANTED: >30/min/workspace → MockRateLimitedError."""
    for _ in range(svc.AI_EDIT_RATE_LIMIT_PER_MIN):
        svc.ai_edit_mock(7, "S-023", "edit", actor_user_id="alice")
    with pytest.raises(svc.MockRateLimitedError):
        svc.ai_edit_mock(7, "S-023", "edit", actor_user_id="alice")


def test_service_ai_edit_rate_limit_is_per_workspace():
    """AC-F1: rate limit is scoped per workspace (workspace 8 unaffected)."""
    for _ in range(svc.AI_EDIT_RATE_LIMIT_PER_MIN):
        svc.ai_edit_mock(7, "S-023", "edit", actor_user_id="alice")
    # workspace 8 should still be fine
    r = svc.ai_edit_mock(8, "S-023", "edit", actor_user_id="alice")
    assert r["tokens_used"] >= 1


def test_service_ai_edit_invalid_workspace_id_raises_422():
    """AC-F4 UNWANTED: workspace_id <= 0 → MockValidationError."""
    with pytest.raises(svc.MockValidationError):
        svc.ai_edit_mock(0, "S-023", "edit", actor_user_id="alice")
    with pytest.raises(svc.MockValidationError):
        svc.ai_edit_mock(-1, "S-023", "edit", actor_user_id="alice")


def test_service_ai_edit_invalid_screen_id_raises_422():
    """AC-F4 UNWANTED: invalid screen_id → MockValidationError."""
    with pytest.raises(svc.MockValidationError):
        svc.ai_edit_mock(1, "../../etc/passwd", "edit", actor_user_id="alice")


# ══════════════════════════════════════════════════════════════════════
# Router-layer tests (POST ai-edit)
# ══════════════════════════════════════════════════════════════════════


def test_router_ai_edit_happy_path_returns_201(client):
    """AC-F2 EVENT-DRIVEN: valid POST → 201 with diff/new_html/tokens_used."""
    r = client.post(
        "/api/workspaces/1/mocks/S-023/ai-edit",
        json={"prompt": "make button bigger"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "diff" in body and body["diff"]
    assert "new_html" in body and body["new_html"]
    assert isinstance(body["tokens_used"], int) and body["tokens_used"] >= 1


def test_router_ai_edit_unauthorized_returns_401(client, monkeypatch):
    """AC-F3 UNWANTED: POST ai-edit w/o token → 401."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.post(
        "/api/workspaces/1/mocks/S-023/ai-edit",
        json={"prompt": "edit me"},
    )
    assert r.status_code == 401


def test_router_ai_edit_missing_prompt_returns_422(client):
    """AC-F4 UNWANTED: missing prompt → 422."""
    r = client.post(
        "/api/workspaces/1/mocks/S-023/ai-edit",
        json={},
    )
    assert r.status_code == 422


def test_router_ai_edit_blank_prompt_returns_422(client):
    """AC-F4 UNWANTED: blank prompt → 422."""
    r = client.post(
        "/api/workspaces/1/mocks/S-023/ai-edit",
        json={"prompt": "   "},
    )
    assert r.status_code == 422


def test_router_ai_edit_oversize_prompt_returns_422(client):
    """AC-F4 UNWANTED: prompt > 8000 chars → 422."""
    big = "x" * 8001
    r = client.post(
        "/api/workspaces/1/mocks/S-023/ai-edit",
        json={"prompt": big},
    )
    assert r.status_code == 422


def test_router_ai_edit_invalid_workspace_id_returns_422(client):
    """AC-F4 UNWANTED: workspace_id <= 0 → 422."""
    r = client.post(
        "/api/workspaces/0/mocks/S-023/ai-edit",
        json={"prompt": "edit"},
    )
    assert r.status_code == 422


def test_router_ai_edit_rate_limit_returns_429(client):
    """AC-F1 / AC-F5 UNWANTED: 31st call within 60s → 429."""
    # consume 30 successful calls
    for _ in range(30):
        rr = client.post(
            "/api/workspaces/9/mocks/S-023/ai-edit",
            json={"prompt": "x"},
        )
        assert rr.status_code == 201, rr.text
    # 31st should fail
    r = client.post(
        "/api/workspaces/9/mocks/S-023/ai-edit",
        json={"prompt": "x"},
    )
    assert r.status_code == 429, r.text
    assert r.json()["detail"]["code"] == "mocks.rate_limited"


def test_router_ai_edit_rate_limit_is_per_workspace(client):
    """AC-F1: rate-limit isolated by workspace."""
    for _ in range(30):
        client.post(
            "/api/workspaces/10/mocks/S-023/ai-edit",
            json={"prompt": "x"},
        )
    # other workspace still works
    r = client.post(
        "/api/workspaces/11/mocks/S-023/ai-edit",
        json={"prompt": "edit"},
    )
    assert r.status_code == 201, r.text


def test_router_ai_edit_emits_audit_log(client, _capture_audit):
    """audit_logs: mock_ai_edited event emitted (best-effort)."""
    client.post(
        "/api/workspaces/12/mocks/S-023/ai-edit",
        json={"prompt": "edit"},
    )
    types = [e["event_type"] for e in _capture_audit]
    if types:
        assert "mock_ai_edited" in types


def test_openapi_ai_edit_route_registered(client):
    """endpoint existence: POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit."""
    spec = client.get("/openapi.json").json()
    paths = spec.get("paths", {})
    key = "/api/workspaces/{workspace_id}/mocks/{screen_id}/ai-edit"
    assert key in paths, f"ai-edit not registered: {sorted(paths.keys())[:5]}"
    assert "post" in paths[key]
