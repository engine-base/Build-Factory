"""T-V3-B-28 / F-026: Constitution backend router tests.

11 AC (Tier 2 Functional) 全件 + Tier 3 regression (12 ケース) を網羅.

mock 戦略:
  services.constitution_service の 3 関数 (get_constitution / create_version /
  approve_version) を monkeypatch で fake 化し, router 層のロジック (auth /
  validation / error mapping) だけを単体テストする.
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def fake_cs(monkeypatch):
    """services.constitution_service の関数を monkeypatch."""
    from services import constitution_service as cs

    state: dict[str, Any] = {
        "active_constitution": None,           # type: ignore[var-annotated]
        "create_calls": [],
        "approve_calls": [],
        "next_version_id": "uuid-stub-0001",
        "next_version_number": 7,
        "next_approved_at": "2026-05-16T12:34:56+00:00",
        # 制御フラグ
        "raise_workspace_not_found": False,
        "raise_content_too_large": False,
        "raise_version_not_found": False,
        "raise_already_active": False,
        "get_returns_none": False,
    }

    async def fake_get(workspace_id):
        if state["raise_workspace_not_found"]:
            raise cs.WorkspaceNotFoundError(f"workspace not found: {workspace_id}")
        if state["get_returns_none"]:
            return None
        return state["active_constitution"] or {
            "content_md": "# default",
            "version": 1,
            "is_active": True,
        }

    async def fake_create(*, workspace_id, content_md, message, author):
        state["create_calls"].append({
            "workspace_id": workspace_id,
            "content_md": content_md, "message": message, "author": author,
        })
        if state["raise_workspace_not_found"]:
            raise cs.WorkspaceNotFoundError(f"workspace not found: {workspace_id}")
        if state["raise_content_too_large"]:
            raise cs.ContentTooLargeError("content_md exceeds 10240 bytes (>10KB)")
        return {
            "version_id": state["next_version_id"],
            "version_number": state["next_version_number"],
        }

    async def fake_approve(*, workspace_id, version, approver):
        state["approve_calls"].append({
            "workspace_id": workspace_id, "version": version, "approver": approver,
        })
        if state["raise_workspace_not_found"]:
            raise cs.WorkspaceNotFoundError(f"workspace not found: {workspace_id}")
        if state["raise_version_not_found"]:
            raise cs.VersionNotFoundError(f"version not found: {version}")
        if state["raise_already_active"]:
            raise cs.AlreadyActiveError(f"version already active: {version}")
        return {
            "approved_at": state["next_approved_at"],
            "active_version": version,
        }

    monkeypatch.setattr(cs, "get_constitution", fake_get)
    monkeypatch.setattr(cs, "create_version", fake_create)
    monkeypatch.setattr(cs, "approve_version", fake_approve)
    return state


# ──────────────────────────────────────────────────────────────────────────
# AC-F4: EVENT GET 2xx contract (content_md / version / is_active)
# ──────────────────────────────────────────────────────────────────────────


def test_get_constitution_returns_2xx_with_contract(client, fake_cs):
    """AC-F4."""
    fake_cs["active_constitution"] = {
        "content_md": "# Constitution v3", "version": 3, "is_active": True,
    }
    r = client.get("/api/workspaces/1/constitution", params={"user_id": "alice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"content_md": "# Constitution v3", "version": 3, "is_active": True}


# ──────────────────────────────────────────────────────────────────────────
# AC-F5: UNWANTED GET token 不在 → 401
# ──────────────────────────────────────────────────────────────────────────


def test_get_constitution_without_token_returns_401(client, fake_cs):
    """AC-F5."""
    r = client.get("/api/workspaces/1/constitution")  # user_id 未指定
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["code"] == "constitution.unauthorized"


def test_get_constitution_with_blank_token_returns_401(client, fake_cs):
    """AC-F5: 空白 user_id も 401."""
    r = client.get("/api/workspaces/1/constitution", params={"user_id": "   "})
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
# AC-F6: UNWANTED GET validation 失敗 → 422 field-level
# ──────────────────────────────────────────────────────────────────────────


def test_get_constitution_invalid_workspace_id_returns_422(client, fake_cs):
    """AC-F6: workspace_id <= 0 は 422."""
    r = client.get("/api/workspaces/0/constitution", params={"user_id": "alice"})
    assert r.status_code == 422


def test_get_constitution_not_found_returns_404(client, fake_cs):
    """active constitution が存在しないときは 404 (workspace は OK でも)."""
    fake_cs["get_returns_none"] = True
    r = client.get("/api/workspaces/77/constitution", params={"user_id": "alice"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "constitution.not_found"


def test_get_constitution_workspace_not_found_returns_404(client, fake_cs):
    fake_cs["raise_workspace_not_found"] = True
    r = client.get("/api/workspaces/9/constitution", params={"user_id": "alice"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "constitution.workspace_not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-F1 / AC-F7: EVENT POST versions → 2xx contract (version_id / version_number)
# ──────────────────────────────────────────────────────────────────────────


def test_create_version_returns_2xx_with_contract(client, fake_cs):
    """AC-F1 / AC-F7: snapshot 作成 (active 不変動) + version_id/version_number 返却."""
    r = client.post(
        "/api/workspaces/1/constitution/versions",
        params={"actor_user_id": "admin1"},
        json={"content_md": "# new version", "message": "initial draft"},
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["version_id"] == "uuid-stub-0001"
    assert body["version_number"] == 7
    # AC-F1 確認: create_version は呼ばれたが approve は呼ばれていない
    assert len(fake_cs["create_calls"]) == 1
    assert len(fake_cs["approve_calls"]) == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-F8: UNWANTED POST versions token 不在 → 401
# ──────────────────────────────────────────────────────────────────────────


def test_create_version_without_admin_token_returns_401(client, fake_cs):
    """AC-F8."""
    r = client.post(
        "/api/workspaces/1/constitution/versions",
        json={"content_md": "# x", "message": "msg"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "constitution.unauthorized"


# ──────────────────────────────────────────────────────────────────────────
# AC-F3 / AC-F9: UNWANTED content_md > 10KB → 422 / その他 validation → 422
# ──────────────────────────────────────────────────────────────────────────


def test_create_version_content_md_too_large_returns_422(client, fake_cs):
    """AC-F3: content_md 10241 byte で 422."""
    big = "a" * (10 * 1024 + 1)
    r = client.post(
        "/api/workspaces/1/constitution/versions",
        params={"actor_user_id": "admin1"},
        json={"content_md": big, "message": "too big"},
    )
    assert r.status_code == 422
    # Pydantic validation error が field-level に出ること
    body = r.json()
    assert "detail" in body


def test_create_version_content_md_too_large_service_path_returns_422(client, fake_cs):
    """AC-F3 service path: schema を通り抜けても service が 422 を返す safety."""
    fake_cs["raise_content_too_large"] = True
    r = client.post(
        "/api/workspaces/1/constitution/versions",
        params={"actor_user_id": "admin1"},
        json={"content_md": "# normal", "message": "msg"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "constitution.content_too_large"


def test_create_version_empty_content_md_returns_422(client, fake_cs):
    """AC-F9: 空 content_md は schema validation で 422."""
    r = client.post(
        "/api/workspaces/1/constitution/versions",
        params={"actor_user_id": "admin1"},
        json={"content_md": "", "message": "m"},
    )
    assert r.status_code == 422


def test_create_version_missing_message_returns_422(client, fake_cs):
    """AC-F9: required body field 欠如は 422 (field-level error)."""
    r = client.post(
        "/api/workspaces/1/constitution/versions",
        params={"actor_user_id": "admin1"},
        json={"content_md": "# ok"},
    )
    assert r.status_code == 422


def test_create_version_workspace_not_found_returns_404(client, fake_cs):
    fake_cs["raise_workspace_not_found"] = True
    r = client.post(
        "/api/workspaces/999/constitution/versions",
        params={"actor_user_id": "admin1"},
        json={"content_md": "# x", "message": "m"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "constitution.workspace_not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-F2 / AC-F10: EVENT POST approve → 2xx contract + active 化
# ──────────────────────────────────────────────────────────────────────────


def test_approve_version_returns_2xx_with_contract(client, fake_cs):
    """AC-F2 / AC-F10."""
    r = client.post(
        "/api/workspaces/1/constitution/versions/5/approve",
        params={"actor_user_id": "admin1"},
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["approved_at"] == "2026-05-16T12:34:56+00:00"
    assert body["active_version"] == 5
    assert len(fake_cs["approve_calls"]) == 1
    assert fake_cs["approve_calls"][0]["version"] == 5


# ──────────────────────────────────────────────────────────────────────────
# AC-F11: UNWANTED POST approve token 不在 → 401
# ──────────────────────────────────────────────────────────────────────────


def test_approve_version_without_admin_token_returns_401(client, fake_cs):
    """AC-F11."""
    r = client.post("/api/workspaces/1/constitution/versions/5/approve")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "constitution.unauthorized"


def test_approve_version_invalid_version_returns_422(client, fake_cs):
    """AC-F6 / AC-F9 (approve path): version <= 0 は 422."""
    r = client.post(
        "/api/workspaces/1/constitution/versions/0/approve",
        params={"actor_user_id": "admin1"},
    )
    assert r.status_code == 422


def test_approve_version_not_found_returns_404(client, fake_cs):
    fake_cs["raise_version_not_found"] = True
    r = client.post(
        "/api/workspaces/1/constitution/versions/99/approve",
        params={"actor_user_id": "admin1"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "constitution.version_not_found"


def test_approve_version_already_active_returns_409(client, fake_cs):
    """openapi 409 (already active) 経路."""
    fake_cs["raise_already_active"] = True
    r = client.post(
        "/api/workspaces/1/constitution/versions/3/approve",
        params={"actor_user_id": "admin1"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "constitution.already_active"


def test_approve_version_workspace_not_found_returns_404(client, fake_cs):
    fake_cs["raise_workspace_not_found"] = True
    r = client.post(
        "/api/workspaces/9999/constitution/versions/1/approve",
        params={"actor_user_id": "admin1"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "constitution.workspace_not_found"
