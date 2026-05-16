"""T-V3-B-06 (F-004): Workspace member role + invitation revocation.

3-tier AC mapping (Tier 2 Functional, per docs/audit/2026-05-16_v3/T-V3-B-06.md):
  AC-F3  : DELETE /workspaces/{id}/members/{user_id} last-admin → 409 (delegated to
           T-021-05 existing impl; we assert that update_member_role surface returns
           409 when last-owner would be demoted)
  AC-F7  : PUT /workspaces/{id}/members/{user_id}/role valid → 2xx {role, updated_at}
  AC-F8  : PUT /workspaces/{id}/members/{user_id}/role no auth → 401
  AC-F9  : PUT /workspaces/{id}/members/{user_id}/role invalid body → 422
  AC-F10 : DELETE /workspaces/{id}/invitations/{token} valid → 2xx {revoked_at}
  AC-F11 : DELETE /workspaces/{id}/invitations/{token} no auth → 401

Implementation strategy: monkey-patch the workspace_service service-layer DB ops
to an in-memory fake. This mirrors the test_t_v3_b_05_accounts.py strategy and
keeps tests independent of the SQLite filesystem.
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    # supabase env-vars must already be set; tests session config handles this.
    from main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append(
            {
                "event_type": event_type,
                "user_id": user_id,
                "detail": detail or {},
            }
        )

    import services.memory_service as ms

    monkeypatch.setattr(ms, "emit_event", fake_emit)
    return captured


@pytest.fixture
def _fake_ws(monkeypatch):
    """Fake workspace_service service-layer ops for T-V3-B-06.

    State layout:
      - members: dict[(workspace_id, user_id)] -> {role, custom_permissions, updated_at}
      - invitations: dict[token] -> {workspace_id, id, status, role, email}
    """
    import services.workspace_service as ws

    state: dict[str, Any] = {
        "members": {
            (1, "alice"): {
                "workspace_id": 1,
                "user_id": "alice",
                "role": "owner",
                "updated_at": "2026-05-16T10:00:00",
            },
            (1, "bob"): {
                "workspace_id": 1,
                "user_id": "bob",
                "role": "ws_admin",
                "updated_at": "2026-05-16T10:00:00",
            },
            (1, "carol"): {
                "workspace_id": 1,
                "user_id": "carol",
                "role": "contributor",
                "updated_at": "2026-05-16T10:00:00",
            },
        },
        "invitations": {
            "tok_pending_xxxxxxxxxxxxxxxx": {
                "id": 100,
                "workspace_id": 1,
                "token": "tok_pending_xxxxxxxxxxxxxxxx",
                "status": "pending",
                "role": "contributor",
                "email": "newbie@example.com",
            },
            "tok_accepted_xxxxxxxxxxxxxxxx": {
                "id": 101,
                "workspace_id": 1,
                "token": "tok_accepted_xxxxxxxxxxxxxxxx",
                "status": "accepted",
                "role": "contributor",
                "email": "already-joined@example.com",
            },
            "tok_revoked_xxxxxxxxxxxxxxxx": {
                "id": 102,
                "workspace_id": 1,
                "token": "tok_revoked_xxxxxxxxxxxxxxxx",
                "status": "revoked",
                "role": "contributor",
                "email": "kicked@example.com",
            },
            "tok_cross_ws_xxxxxxxxxxxxxxxx": {
                "id": 200,
                "workspace_id": 2,  # different workspace
                "token": "tok_cross_ws_xxxxxxxxxxxxxxxx",
                "status": "pending",
                "role": "contributor",
                "email": "other-ws@example.com",
            },
        },
        "audit_events": [],
    }

    async def fake_get_member(workspace_id, user_id):
        return state["members"].get((int(workspace_id), user_id))

    async def fake_count_role(workspace_id, role):
        return sum(
            1
            for (wid, _uid), m in state["members"].items()
            if int(wid) == int(workspace_id) and m.get("role") == role
        )

    async def fake_update_member_role(
        workspace_id, user_id, *, role=None, custom_permissions=None, actor_user_id=None
    ):
        # mirror real service: self-strip / owner protection
        if actor_user_id is not None and actor_user_id == user_id and role is not None:
            raise ws.SelfStripError("cannot change your own role (self-strip blocked)")
        current = state["members"].get((int(workspace_id), user_id))
        if not current:
            return {}
        if current.get("role") == "owner" and role and role != "owner":
            owners = await fake_count_role(workspace_id, "owner")
            if owners <= 1:
                raise ws.OwnerProtectedError("cannot demote the last owner")
        normalized = "ws_admin" if role == "admin" else role
        if role:
            current["role"] = normalized
        current["updated_at"] = "2026-05-16T14:30:00"
        return dict(current)

    async def fake_revoke_invitation(workspace_id, token, *, actor_user_id=None):
        inv = state["invitations"].get(token)
        if not inv:
            raise ws.InvitationNotFoundError(
                f"invitation not found for token (workspace_id={workspace_id})"
            )
        if int(inv["workspace_id"]) != int(workspace_id):
            raise ws.InvitationNotFoundError(
                f"invitation not found in workspace {workspace_id}"
            )
        if inv["status"] != "pending":
            raise ws.InvitationRevokedError(
                f"invitation already in state '{inv['status']}' (cannot revoke)"
            )
        inv["status"] = "revoked"
        return {
            "workspace_id": workspace_id,
            "token_prefix": token[:8],
            "revoked_at": "2026-05-16T14:31:00",
        }

    monkeypatch.setattr(ws, "get_member", fake_get_member)
    monkeypatch.setattr(ws, "_count_role", fake_count_role)
    monkeypatch.setattr(ws, "update_member_role", fake_update_member_role)
    monkeypatch.setattr(ws, "revoke_invitation", fake_revoke_invitation)
    return state


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 / AC-F7: PUT role happy path
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f7_update_role_valid_returns_200_with_contract(
    client, _fake_ws, _capture_audit
):
    r = client.put(
        "/api/workspaces/1/members/carol/role",
        json={"role": "viewer"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # F-004 contract: { role, updated_at }
    assert body["role"] == "viewer"
    assert "updated_at" in body and body["updated_at"]


def test_ac_f7_update_role_alias_admin_normalized_to_ws_admin(
    client, _fake_ws, _capture_audit
):
    r = client.put(
        "/api/workspaces/1/members/carol/role",
        json={"role": "admin"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # service-layer normalizes admin → ws_admin
    assert body["role"] == "ws_admin"


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 / AC-F9: invalid body → 422 (Pydantic field-level error map)
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f9_update_role_missing_role_returns_422(client, _fake_ws):
    r = client.put("/api/workspaces/1/members/carol/role", json={})
    assert r.status_code == 422
    detail = r.json()["detail"]
    # Pydantic returns a list-of-errors structure (field-level)
    assert isinstance(detail, list)
    assert any("role" in (e.get("loc") or []) for e in detail)


def test_ac_f9_update_role_invalid_enum_returns_422(client, _fake_ws):
    r = client.put(
        "/api/workspaces/1/members/carol/role",
        json={"role": "super-duper-admin"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list)
    assert any("role" in (e.get("loc") or []) for e in detail)


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 / AC-F3 indirect: owner-protected → 409
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f3_update_role_last_owner_demote_returns_409(client, _fake_ws):
    # alice is the only owner — demoting her must 409
    r = client.put(
        "/api/workspaces/1/members/alice/role",
        json={"role": "viewer", "actor_user_id": "bob"},
    )
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["code"] == "workspaces.owner_protected"
    assert "last owner" in body["detail"]["message"]


def test_self_strip_blocked_returns_409(client, _fake_ws):
    # bob tries to demote himself
    r = client.put(
        "/api/workspaces/1/members/bob/role",
        json={"role": "viewer", "actor_user_id": "bob"},
    )
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["code"] == "workspaces.self_strip_blocked"


def test_update_role_unknown_member_returns_404(client, _fake_ws):
    r = client.put(
        "/api/workspaces/1/members/nobody/role",
        json={"role": "viewer"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "workspaces.member_not_found"


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 / AC-F8: no auth → 401
# ──────────────────────────────────────────────────────────────────────────


def _client_no_auth_bypass(monkeypatch):
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import importlib

    import services.auth_middleware as am

    importlib.reload(am)
    from main import app

    return TestClient(app, raise_server_exceptions=False)


def test_ac_f8_update_role_no_auth_returns_401(monkeypatch, _fake_ws):
    try:
        c = _client_no_auth_bypass(monkeypatch)
        r = c.put(
            "/api/workspaces/1/members/carol/role",
            json={"role": "viewer"},
        )
        assert r.status_code == 401
    finally:
        monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
        import importlib

        import services.auth_middleware as am

        importlib.reload(am)


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 / AC-F10: DELETE invitation happy path
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f10_revoke_invitation_valid_returns_200_with_revoked_at(
    client, _fake_ws, _capture_audit
):
    r = client.delete(
        "/api/workspaces/1/invitations/tok_pending_xxxxxxxxxxxxxxxx"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # F-004 contract: { revoked_at } (plus token_prefix / workspace_id for cross-ref)
    assert "revoked_at" in body and body["revoked_at"]
    # state must reflect status -> revoked
    assert _fake_ws["invitations"]["tok_pending_xxxxxxxxxxxxxxxx"]["status"] == "revoked"


def test_revoke_invitation_unknown_token_returns_404(client, _fake_ws):
    r = client.delete(
        "/api/workspaces/1/invitations/tok_unknown_xxxxxxxxxxxxxxxx"
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "invitations.not_found"


def test_revoke_invitation_cross_workspace_returns_404(client, _fake_ws):
    # token exists but belongs to workspace 2
    r = client.delete(
        "/api/workspaces/1/invitations/tok_cross_ws_xxxxxxxxxxxxxxxx"
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "invitations.not_found"


def test_revoke_invitation_already_accepted_returns_409(client, _fake_ws):
    r = client.delete(
        "/api/workspaces/1/invitations/tok_accepted_xxxxxxxxxxxxxxxx"
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "invitations.already_finalized"


def test_revoke_invitation_already_revoked_returns_409(client, _fake_ws):
    r = client.delete(
        "/api/workspaces/1/invitations/tok_revoked_xxxxxxxxxxxxxxxx"
    )
    assert r.status_code == 409


def test_revoke_invitation_empty_token_returns_400(client, _fake_ws):
    # FastAPI path-param non-empty constraint: empty string becomes 404 from
    # the framework. Use a too-short token that hits our validator.
    r = client.delete("/api/workspaces/1/invitations/short")
    assert r.status_code == 400
    assert "invalid_token" in r.json()["detail"]["code"]


def test_revoke_invitation_bad_workspace_id_returns_400(client, _fake_ws):
    r = client.delete(
        "/api/workspaces/0/invitations/tok_pending_xxxxxxxxxxxxxxxx"
    )
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 / AC-F11: no auth → 401 for DELETE invitation
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f11_revoke_invitation_no_auth_returns_401(monkeypatch, _fake_ws):
    try:
        c = _client_no_auth_bypass(monkeypatch)
        r = c.delete(
            "/api/workspaces/1/invitations/tok_pending_xxxxxxxxxxxxxxxx"
        )
        assert r.status_code == 401
    finally:
        monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
        import importlib

        import services.auth_middleware as am

        importlib.reload(am)


# ──────────────────────────────────────────────────────────────────────────
# Audit emit assertions
# ──────────────────────────────────────────────────────────────────────────


def test_audit_emitted_on_role_update(client, _fake_ws, _capture_audit):
    client.put(
        "/api/workspaces/1/members/carol/role",
        json={"role": "viewer"},
    )
    events = [e["event_type"] for e in _capture_audit]
    assert any("role_updated" in e or "member.updated" in e for e in events), (
        f"no role_updated audit emitted: {events}"
    )


# ──────────────────────────────────────────────────────────────────────────
# Service-layer unit tests (workspace_service.revoke_invitation contract)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_revoke_invitation_rejects_empty_token():
    import services.workspace_service as ws

    with pytest.raises(ws.InvitationNotFoundError):
        await ws.revoke_invitation(1, "", actor_user_id="alice")


@pytest.mark.asyncio
async def test_service_revoke_invitation_rejects_bad_workspace_id():
    import services.workspace_service as ws

    with pytest.raises(ws.InvitationNotFoundError):
        await ws.revoke_invitation(0, "tok_some_test_xxxxxxx", actor_user_id="alice")
