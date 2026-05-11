"""T-004-03: workspace_invitations 発行 API — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-004 で workspace_invitations 発行 endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + RLS は migration 側で担保
  AC-4 UNWANTED      : invalid email / role / 期間 / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _fake_ws(monkeypatch):
    """workspace_service.create_invitation を fake."""
    import services.workspace_service as wsvc
    invitations: list[dict] = []

    async def fake_create(workspace_id, email, *, role, invited_by, expires_in_days):
        if email == "force-error@example.com":
            raise RuntimeError("simulated DB error")
        inv = {
            "workspace_id": workspace_id,
            "email": email,
            "role": role,
            "token": f"tok-{len(invitations)+1}",
            "expires_at": "2026-06-01T00:00:00",
            "invitation_url": f"/invite/tok-{len(invitations)+1}",
        }
        invitations.append(inv)
        return inv

    monkeypatch.setattr(wsvc, "create_invitation", fake_create)
    yield {"invitations": invitations}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_invitation_endpoint_exists(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "test@example.com", "role": "contributor",
               "invited_by": "alice", "expires_in_days": 7},
    )
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert "expires_at" in body
    assert body["email"] == "test@example.com"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "perf@example.com", "role": "viewer",
               "invited_by": "alice", "expires_in_days": 7},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "not-an-email", "invited_by": "alice"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "invitations.invalid_email"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_emits_audit_event(client, _capture_audit):
    client.post(
        "/api/workspaces/3/invitations",
        json={"email": "audit@example.com", "role": "admin",
               "invited_by": "alice", "expires_in_days": 14},
    )
    events = [e for e in _capture_audit
              if e["event_type"] == "workspaces.invitation.created"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["workspace_id"] == 3
    assert events[0]["detail"]["role"] == "admin"
    # PII を平文で audit に残さない (hash のみ)
    assert "audit@example.com" not in str(events[0]["detail"])
    assert "email_hash" in events[0]["detail"]


def test_ac3_role_normalized_to_lower(client):
    """AC-3: role は lowercase 化されて保存."""
    r = client.post(
        "/api/workspaces/3/invitations",
        json={"email": "norm@example.com", "role": "ADMIN",
               "invited_by": "alice"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_ac3_email_normalized_to_lower(client):
    r = client.post(
        "/api/workspaces/3/invitations",
        json={"email": "Mixed@Example.COM", "role": "viewer",
               "invited_by": "alice"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "mixed@example.com"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_workspace_id_rejected(client, _fake_ws):
    before = len(_fake_ws["invitations"])
    r = client.post(
        "/api/workspaces/0/invitations",
        json={"email": "x@example.com", "invited_by": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.invalid_id"
    after = len(_fake_ws["invitations"])
    assert after == before


def test_ac4_empty_email_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "  ", "invited_by": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_email"


def test_ac4_invalid_email_format_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "no-at-sign", "invited_by": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_email"


def test_ac4_long_email_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "x" * 250 + "@y.zz", "invited_by": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.email_too_long"


def test_ac4_invalid_role_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "x@example.com", "role": "bogus",
               "invited_by": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_role"


def test_ac4_empty_invited_by_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "x@example.com", "invited_by": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invitations.unauthorized"


def test_ac4_expires_in_days_zero_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "x@example.com", "invited_by": "alice",
               "expires_in_days": 0},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_expires_in_days"


def test_ac4_expires_in_days_too_long_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "x@example.com", "invited_by": "alice",
               "expires_in_days": 91},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_expires_in_days"


def test_ac4_service_failure_returns_500_structured(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "force-error@example.com", "invited_by": "alice"},
    )
    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "invitations.create_failed"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_ws):
    """AC-4 UNWANTED: rejected で audit emit / service 呼び出しなし."""
    client.post("/api/workspaces/0/invitations",
                 json={"email": "x@e.co", "invited_by": "a"})
    client.post("/api/workspaces/1/invitations",
                 json={"email": "bad-format", "invited_by": "a"})
    events = [e for e in _capture_audit
              if e["event_type"] == "workspaces.invitation.created"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        {"email": "  ", "invited_by": "a"},
        {"email": "no-at", "invited_by": "a"},
        {"email": "x@e.co", "role": "bogus", "invited_by": "a"},
        {"email": "x@e.co", "invited_by": "  "},
        {"email": "x@e.co", "invited_by": "a", "expires_in_days": 0},
        {"email": "x@e.co", "invited_by": "a", "expires_in_days": 100},
    ]
    for payload in cases:
        r = client.post("/api/workspaces/1/invitations", json=payload)
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
