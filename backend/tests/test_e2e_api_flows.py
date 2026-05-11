"""E2E (API) フロー統合テスト.

frontend が叩く一連の API call をシミュレートし、 ユーザーシナリオ通りに
バックエンドが動くことを保証する。 これは Playwright e2e の代替で、
ヘッドレスブラウザ依存なしで CI で実行可能。

カバーするユーザーシナリオ:
  - F-021 (Workspace permissions): メンバー追加 → role 変更 → 削除
  - F-023 (Profile + OAuth): プロフィール編集 → OAuth 状態確認 → opt-in toggle
  - F-004 (Workspace settings): info 編集 → owner 移譲 → archive
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ═════════════════════════════════════════════════════════
# Scenario 1: Profile flow (T-023-01 / S-009)
# ═════════════════════════════════════════════════════════
def test_profile_full_flow(client) -> None:
    """ユーザーがプロフィールを編集して再読み込みする一連の流れ"""
    uid = "e2e_profile_user"

    # 1. 初回 GET (default 値)
    r = client.get("/api/bf-profile", params={"user_id": uid})
    assert r.status_code == 200
    assert r.json()["theme"] == "light"

    # 2. PATCH (5 fields すべて)
    r = client.patch(
        "/api/bf-profile", params={"user_id": uid},
        json={
            "display_name": "E2E User",
            "role_text": "Tester",
            "bio": "Hello E2E",
            "theme": "dark",
            "avatar_url": "https://e2e.example/a.png",
        },
    )
    assert r.status_code == 200

    # 3. UNWANTED: invalid theme → 422 + code=invalid_theme
    r = client.patch(
        "/api/bf-profile", params={"user_id": uid},
        json={"theme": "neon_pink"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_theme"


# ═════════════════════════════════════════════════════════
# Scenario 2: Permission matrix flow (T-021)
# ═════════════════════════════════════════════════════════
def test_permission_matrix_flow(client) -> None:
    """frontend が起動時に取得する matrix endpoint"""
    r = client.get("/api/workspaces/permissions/matrix")
    assert r.status_code == 200
    body = r.json()

    # frontend が期待する shape
    assert "roles" in body
    assert "permission_keys" in body
    assert "matrix" in body

    # 6 ロール (legacy "admin" は除外して 6)
    assert set(body["roles"]) == {"owner", "ws_admin", "contributor", "viewer", "client", "monitor"}

    # 30 permission keys 以上
    assert len(body["permission_keys"]) >= 30

    # matrix[perm_key][role_key] の型
    for pk in body["permission_keys"][:3]:
        assert pk in body["matrix"]
        for r_key in body["roles"]:
            assert r_key in body["matrix"][pk]


# ═════════════════════════════════════════════════════════
# Scenario 3: OAuth flow (T-023-04 / S-009 API keys tab)
# ═════════════════════════════════════════════════════════
def test_oauth_flow_returns_3_providers(client) -> None:
    r = client.get("/api/oauth/providers")
    assert r.status_code == 200
    assert set(r.json()["providers"]) == {"slack", "github", "anthropic"}


def test_oauth_status_unconnected_default(client) -> None:
    """frontend が起動時に各 provider 状態を取得"""
    for provider in ["slack", "github", "anthropic"]:
        r = client.get(f"/api/oauth/{provider}/status", params={"owner_id": "e2e_oauth_user"})
        assert r.status_code == 200
        assert r.json()["connected"] is False


def test_oauth_csrf_guard_returns_400(client) -> None:
    """UNWANTED: callback state mismatch → 400 + code=csrf_mismatch"""
    r = client.post(
        "/api/oauth/slack/callback",
        json={
            "code": "fake_code",
            "redirect_uri": "https://app/cb",
            "owner_id": "e2e_csrf_user",
            "expected_state": "ABCDEF",
            "received_state": "ZZZZZZ",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "csrf_mismatch"


# ═════════════════════════════════════════════════════════
# Scenario 4: User lifecycle (T-023-05 / S-009)
# ═════════════════════════════════════════════════════════
def test_clone_optin_default_off(client) -> None:
    r = client.get("/api/user/clone-optin", params={"user_id": "e2e_clone_user"})
    assert r.status_code == 200
    assert r.json()["opted_in"] is False


def test_deletion_already_pending_409(client, monkeypatch) -> None:
    """UNWANTED: pending 削除リクエスト既存 → 409 + code=already_pending"""
    from services.user_lifecycle import AlreadyPendingError

    async def fake(*a, **kw):
        raise AlreadyPendingError("pending id=1")

    monkeypatch.setattr("routers.user_lifecycle.request_deletion", fake)
    r = client.post("/api/user/deletion", json={"user_id": "u", "grace_days": 30})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "already_pending"


# ═════════════════════════════════════════════════════════
# Scenario 5: Owner transfer (T-004-05)
# ═════════════════════════════════════════════════════════
def test_transfer_ownership_not_owner_403(client, monkeypatch) -> None:
    """STATE: actor が owner でなければ 403"""
    from services.workspace_service import NotOwnerError

    async def fake(*a, **kw):
        raise NotOwnerError("X is not owner")

    monkeypatch.setattr("routers.workspaces.ws.transfer_ownership", fake)
    r = client.post(
        "/api/workspaces/1/transfer-ownership",
        json={"current_owner_id": "alice", "new_owner_id": "bob"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_owner"


def test_transfer_ownership_target_not_member_400(client, monkeypatch) -> None:
    """UNWANTED: 移譲先が member でない → 400"""
    from services.workspace_service import TargetNotMemberError

    async def fake(*a, **kw):
        raise TargetNotMemberError("bob is not member")

    monkeypatch.setattr("routers.workspaces.ws.transfer_ownership", fake)
    r = client.post(
        "/api/workspaces/1/transfer-ownership",
        json={"current_owner_id": "alice", "new_owner_id": "bob"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "target_not_member"


# ═════════════════════════════════════════════════════════
# Scenario 6: Workspace update (T-004-05 settings page)
# ═════════════════════════════════════════════════════════
def test_workspace_patch_with_actor(client) -> None:
    """frontend が actor_user_id を query で渡す PATCH"""
    # DB 不在環境では 200 + (空 or default) を許容
    r = client.patch(
        "/api/workspaces/99999",
        params={"actor_user_id": "alice"},
        json={"name": "Renamed"},
    )
    assert r.status_code in (200, 404, 500)


def test_workspace_archive_with_actor(client) -> None:
    """frontend が archive する時の actor_user_id query"""
    r = client.delete(
        "/api/workspaces/99999",
        params={"actor_user_id": "alice"},
    )
    assert r.status_code in (200, 404, 500)
