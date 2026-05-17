"""T-V3-B-05 (F-004): Account-level endpoints — transfer-owner / invitations / member removal.

3-tier AC マッピング (Tier 2 Functional):
  AC-F1  : POST /accounts/{id}/transfer-owner non-member → 409
  AC-F2  : POST /accounts/{id}/invitations > 20/hour → 429
  AC-F4  : POST /accounts/{id}/transfer-owner valid → 2xx (old_owner_id)
  AC-F5  : POST /accounts/{id}/transfer-owner no auth → 401
  AC-F6  : POST /accounts/{id}/transfer-owner invalid body → 422
  AC-F7  : POST /accounts/{id}/invitations valid → 2xx (invitation_token)
  AC-F8  : POST /accounts/{id}/invitations no auth → 401
  AC-F9  : POST /accounts/{id}/invitations invalid body → 422
  AC-F10 : POST /accounts/{id}/invitations rate-limit → 429
  AC-F11 : DELETE /accounts/{id}/members/{user_id} valid → 2xx (removed_at)
  AC-F12 : DELETE /accounts/{id}/members/{user_id} no auth → 401

実装方針: workspace_service の既存パターンに従い fastapi.testclient + service-level
fake/monkeypatch で対象 endpoint の入出力契約を検証する。

DB I/O は monkeypatch で in-memory fake に差し替え, audit emit は capture する.
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # auth はテスト時 dev bypass で常に DEV_USER (masato) を返す
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
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

    # services.memory_service.emit_event を fake (account_service._emit_audit 経由)
    import services.memory_service as ms

    monkeypatch.setattr(ms, "emit_event", fake_emit)
    return captured


@pytest.fixture
def _fake_account(monkeypatch):
    """account_service の DB 層を fake する.

    - get_account: 指定 id だけ存在 (1=existing, 999=missing)
    - get_account_member: dict-based 判定 (account_id, user_id) → role
    - transfer_owner / create_account_invitation / remove_account_member の
      下流 DB ops は別途 mock せず、それぞれを直接 fake する。
    """
    import services.account_service as acc

    state: dict[str, Any] = {
        "accounts": {
            1: {
                "id": 1,
                "name": "Test Account",
                "owner_user_id": "alice",
                "plan": "free",
                "is_active": 1,
            },
        },
        "members": {
            (1, "alice"): {"role": "owner", "user_id": "alice"},
            (1, "bob"): {"role": "admin", "user_id": "bob"},
            (1, "carol"): {"role": "member", "user_id": "carol"},
        },
        "invitations": [],
        "removed_members": [],
        "ownership_transfers": [],
    }

    async def fake_get_account(account_id: int):
        return state["accounts"].get(int(account_id))

    async def fake_get_member(account_id: int, user_id: str):
        return state["members"].get((int(account_id), user_id))

    async def fake_transfer_owner(account_id, *, new_owner_user_id, actor_user_id=None):
        a = state["accounts"].get(int(account_id))
        if not a:
            raise acc.AccountNotFoundError(f"account {account_id} not found")
        if not state["members"].get((int(account_id), new_owner_user_id)):
            raise acc.TargetNotAccountMemberError(
                f"{new_owner_user_id} not a member of {account_id}"
            )
        old = a.get("owner_user_id")
        if old == new_owner_user_id:
            raise ValueError("already owner")
        state["ownership_transfers"].append(
            {"account_id": account_id, "old": old, "new": new_owner_user_id}
        )
        a["owner_user_id"] = new_owner_user_id
        # Mirror real account_service.transfer_owner audit emit so audit-assertion
        # tests see the event.
        await acc._emit_audit(
            "accounts.owner_transferred",
            user_id=actor_user_id or old,
            detail={
                "account_id": int(account_id),
                "old_owner_id": old,
                "new_owner_id": new_owner_user_id,
            },
        )
        return {
            "old_owner_id": old,
            "new_owner_id": new_owner_user_id,
            "transferred_at": "2026-05-16T14:00:00",
        }

    async def fake_create_invitation(
        account_id, *, email, role, invited_by, expires_in_days
    ):
        a = state["accounts"].get(int(account_id))
        if not a:
            raise acc.AccountNotFoundError(f"account {account_id} not found")
        token = f"tok_{len(state['invitations']) + 1:04d}_xxxxxxx"
        inv = {
            "account_id": int(account_id),
            "email": email,
            "role": role,
            "invitation_token": token,
            "expires_at": "2026-05-23T14:00:00",
        }
        state["invitations"].append(inv)
        return inv

    async def fake_remove_member(account_id, user_id, *, actor_user_id=None):
        a = state["accounts"].get(int(account_id))
        if not a:
            raise acc.AccountNotFoundError(f"account {account_id} not found")
        m = state["members"].get((int(account_id), user_id))
        if not m:
            raise acc.AccountNotFoundError(
                f"member {user_id} not found in {account_id}"
            )
        if m.get("role") == "owner" or a.get("owner_user_id") == user_id:
            raise acc.CannotRemoveAccountOwnerError(
                f"cannot remove owner {user_id}"
            )
        state["members"].pop((int(account_id), user_id), None)
        state["removed_members"].append({"account_id": account_id, "user_id": user_id})
        return {
            "removed_at": "2026-05-16T14:01:00",
            "account_id": account_id,
            "user_id": user_id,
        }

    monkeypatch.setattr(acc, "get_account", fake_get_account)
    monkeypatch.setattr(acc, "get_account_member", fake_get_member)
    monkeypatch.setattr(acc, "transfer_owner", fake_transfer_owner)
    monkeypatch.setattr(acc, "create_account_invitation", fake_create_invitation)
    monkeypatch.setattr(acc, "remove_account_member", fake_remove_member)
    return state


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from services import invitation_service as inv

    inv.reset_rate_limit()
    inv.configure_rate_limit(max_requests=20, window_seconds=3600.0)
    yield
    inv.reset_rate_limit()
    inv.configure_rate_limit(max_requests=20, window_seconds=3600.0)


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F4 / AC-F1: transfer-owner happy path & non-member
# ════════════════════════════════════════════════════════════════════════


def test_ac_f4_transfer_owner_valid_returns_201_with_contract(
    client, _fake_account, _capture_audit
):
    r = client.post(
        "/api/accounts/1/transfer-owner",
        json={"new_owner_user_id": "bob"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # F-004 contract: old_owner_id / new_owner_id / transferred_at
    assert "old_owner_id" in body
    assert body["new_owner_id"] == "bob"
    assert "transferred_at" in body
    assert body["old_owner_id"] == "alice"


def test_ac_f1_transfer_owner_non_member_returns_409(client, _fake_account):
    r = client.post(
        "/api/accounts/1/transfer-owner",
        json={"new_owner_user_id": "nobody-here"},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["code"] == "accounts.target_not_member"
    assert "message" in body["detail"]


def test_ac_f1_transfer_owner_unknown_account_returns_404(client, _fake_account):
    r = client.post(
        "/api/accounts/999/transfer-owner",
        json={"new_owner_user_id": "bob"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "accounts.not_found"


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F5: 401 when no auth (BUILD_FACTORY_DEV_BYPASS_AUTH=0)
# ════════════════════════════════════════════════════════════════════════


def test_ac_f5_transfer_owner_no_auth_returns_401(_fake_account, monkeypatch):
    # 強制で dev bypass を切ってクライアントを作成
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import importlib
    import services.auth_middleware as am

    importlib.reload(am)
    # auth_middleware の DEV_BYPASS は import 時 evaluate されるので reload
    try:
        from main import app

        c = TestClient(app, raise_server_exceptions=False)
        r = c.post(
            "/api/accounts/1/transfer-owner",
            json={"new_owner_user_id": "bob"},
        )
        assert r.status_code == 401
    finally:
        # 元に戻す
        monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
        importlib.reload(am)


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F6: 422 for invalid request body
# ════════════════════════════════════════════════════════════════════════


def test_ac_f6_transfer_owner_missing_new_owner_returns_422(client, _fake_account):
    r = client.post("/api/accounts/1/transfer-owner", json={})
    assert r.status_code == 422


def test_ac_f6_transfer_owner_empty_new_owner_returns_422(client, _fake_account):
    # Pydantic min_length=1 が空文字列を 422 で reject
    r = client.post(
        "/api/accounts/1/transfer-owner",
        json={"new_owner_user_id": ""},
    )
    assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F7: create invitation happy path
# ════════════════════════════════════════════════════════════════════════


def test_ac_f7_create_invitation_valid_returns_201_with_token(
    client, _fake_account, _capture_audit
):
    r = client.post(
        "/api/accounts/1/invitations",
        json={"email": "newbie@example.com", "role": "member"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "invitation_token" in body
    assert body["email"] == "newbie@example.com"
    assert body["role"] == "member"
    assert "expires_at" in body


def test_ac_f7_email_lowercase_normalized(client, _fake_account):
    r = client.post(
        "/api/accounts/1/invitations",
        json={"email": "MIXED@Example.COM", "role": "viewer"},
    )
    assert r.status_code == 201
    assert r.json()["email"] == "mixed@example.com"


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F9: 422 for invalid email / role
# ════════════════════════════════════════════════════════════════════════


def test_ac_f9_invalid_email_returns_422(client, _fake_account):
    r = client.post(
        "/api/accounts/1/invitations",
        json={"email": "not-an-email", "role": "member"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invitations.invalid_email"


def test_ac_f9_invalid_role_returns_422(client, _fake_account):
    r = client.post(
        "/api/accounts/1/invitations",
        json={"email": "ok@example.com", "role": "super-admin"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invitations.invalid_role"


def test_ac_f9_invalid_expires_in_days_returns_422(client, _fake_account):
    r = client.post(
        "/api/accounts/1/invitations",
        json={"email": "x@example.com", "role": "member", "expires_in_days": 0},
    )
    assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F2 + AC-F10: rate-limit 20/hour/account → 429
# ════════════════════════════════════════════════════════════════════════


def test_ac_f2_invitation_rate_limit_returns_429(client, _fake_account):
    from services import invitation_service as inv

    inv.configure_rate_limit(max_requests=3, window_seconds=3600.0)
    inv.reset_rate_limit()

    for i in range(3):
        r = client.post(
            "/api/accounts/1/invitations",
            json={"email": f"u{i}@example.com", "role": "member"},
        )
        assert r.status_code == 201, f"call {i} unexpected: {r.text}"

    r = client.post(
        "/api/accounts/1/invitations",
        json={"email": "blocked@example.com", "role": "member"},
    )
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "invitations.rate_limited"


def test_ac_f10_rate_limit_resets_after_window():
    from services import invitation_service as inv

    inv.configure_rate_limit(max_requests=2, window_seconds=0.001)
    inv.reset_rate_limit()

    assert inv.check_invitation_rate_limit(42)[0] is True
    assert inv.check_invitation_rate_limit(42)[0] is True
    assert inv.check_invitation_rate_limit(42)[0] is False
    # window expired → reset (sleep > 1ms)
    import time

    time.sleep(0.01)
    assert inv.check_invitation_rate_limit(42)[0] is True


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F11: member removal happy path
# ════════════════════════════════════════════════════════════════════════


def test_ac_f11_remove_member_valid_returns_200_with_removed_at(
    client, _fake_account
):
    r = client.delete("/api/accounts/1/members/carol")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "removed_at" in body
    assert body["user_id"] == "carol"


def test_ac_f11_remove_owner_returns_409(client, _fake_account):
    """AC-F1 系 (cannot_remove_owner)."""
    r = client.delete("/api/accounts/1/members/alice")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "accounts.cannot_remove_owner"


def test_ac_f11_remove_unknown_member_returns_404(client, _fake_account):
    r = client.delete("/api/accounts/1/members/ghost-user")
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════
# Tier 2 / AC-F8 / AC-F12: 401 no-auth (再利用 fixture / 簡略版)
# ════════════════════════════════════════════════════════════════════════


def _client_no_auth_bypass(monkeypatch):
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import importlib
    import services.auth_middleware as am

    importlib.reload(am)
    from main import app

    return TestClient(app, raise_server_exceptions=False)


def test_ac_f8_create_invitation_no_auth_returns_401(monkeypatch, _fake_account):
    try:
        c = _client_no_auth_bypass(monkeypatch)
        r = c.post(
            "/api/accounts/1/invitations",
            json={"email": "x@example.com", "role": "member"},
        )
        assert r.status_code == 401
    finally:
        monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
        import importlib
        import services.auth_middleware as am

        importlib.reload(am)


def test_ac_f12_remove_member_no_auth_returns_401(monkeypatch, _fake_account):
    try:
        c = _client_no_auth_bypass(monkeypatch)
        r = c.delete("/api/accounts/1/members/carol")
        assert r.status_code == 401
    finally:
        monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
        import importlib
        import services.auth_middleware as am

        importlib.reload(am)


# ════════════════════════════════════════════════════════════════════════
# Audit emit assertions (AC-F4 / AC-F7 / AC-F11 audit_logs)
# ════════════════════════════════════════════════════════════════════════


def test_audit_emitted_on_transfer_owner(client, _fake_account, _capture_audit):
    client.post(
        "/api/accounts/1/transfer-owner",
        json={"new_owner_user_id": "bob"},
    )
    # owner_transferred 系の event が 1 件以上
    events = [e["event_type"] for e in _capture_audit]
    assert any("owner" in e for e in events), f"no owner audit emitted: {events}"


def test_audit_emitted_on_invitation_create(client, _fake_account, _capture_audit):
    client.post(
        "/api/accounts/1/invitations",
        json={"email": "audit@example.com", "role": "member"},
    )
    events = [e["event_type"] for e in _capture_audit]
    assert any("invitation" in e for e in events), f"no invitation audit: {events}"
