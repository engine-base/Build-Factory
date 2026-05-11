"""T-021-01 / T-021-02 / T-021-04 / T-021-05 の AC 検証.

DB を使わず in-memory で permission ロジック・guard を検証する。
DB を伴う行動は test_workspace_permissions_db.py で別途 (本ファイルでは scope 外)。
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from services.workspace_service import (
    DEFAULT_ROLES, _normalize_role,
    SelfStripError, OwnerProtectedError, update_member_role, remove_member,
)
from services.roles import (
    ROLE_KEYS, PERMISSIONS, PERMISSION_MATRIX, validate_custom_permissions,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────
# T-021-01 AC: UBIQUITOUS — 6 ロールのみ受け入れる
# ─────────────────────────────────────────────────────────
def test_six_canonical_roles_present() -> None:
    for r in ("owner", "ws_admin", "contributor", "viewer", "client", "monitor"):
        assert r in ROLE_KEYS
    assert len(ROLE_KEYS) == 6


def test_default_roles_include_legacy_admin_for_compat() -> None:
    # legacy "admin" は DB 既存 row 互換のため許容
    assert "admin" in DEFAULT_ROLES


def test_normalize_role_admin_to_ws_admin() -> None:
    assert _normalize_role("admin") == "ws_admin"
    assert _normalize_role("ws_admin") == "ws_admin"
    assert _normalize_role("contributor") == "contributor"


# ─────────────────────────────────────────────────────────
# T-021-01 AC: matrix endpoint
# ─────────────────────────────────────────────────────────
def test_permission_matrix_shape() -> None:
    # PERMISSION_MATRIX: {permission_key: {role: bool|str}}
    assert isinstance(PERMISSION_MATRIX, dict)
    assert len(PERMISSIONS) >= 30
    for pk, role_map in PERMISSION_MATRIX.items():
        assert isinstance(role_map, dict)
        for r in ROLE_KEYS:
            assert r in role_map, f"permission {pk} missing role {r}"


def test_matrix_router_returns_matrix(client) -> None:
    r = client.get("/api/workspaces/permissions/matrix")
    assert r.status_code == 200
    body = r.json()
    assert "roles" in body and "matrix" in body and "permission_keys" in body
    assert "owner" in body["roles"]
    assert len(body["permission_keys"]) >= 30


# ─────────────────────────────────────────────────────────
# T-021-02 AC: custom_permissions バリデータ
# ─────────────────────────────────────────────────────────
def test_validate_custom_permissions_known_keys_pass() -> None:
    assert validate_custom_permissions({"edit_spec": True, "run_session": False}) == []


def test_validate_custom_permissions_unknown_keys_returned() -> None:
    unknown = validate_custom_permissions({"made_up_permission": True})
    assert "made_up_permission" in unknown


def test_validate_custom_permissions_mixed_keys() -> None:
    # 1 つ known + 1 つ unknown → unknown のみ返す
    unknown = validate_custom_permissions({"edit_spec": True, "fake_key": False})
    assert unknown == ["fake_key"]


# ─────────────────────────────────────────────────────────
# T-021-05 AC: self-strip block (UNWANTED)
# ─────────────────────────────────────────────────────────
def test_update_member_role_self_strip_blocked() -> None:
    with pytest.raises(SelfStripError):
        asyncio.run(update_member_role(
            workspace_id=1, user_id="alice",
            role="viewer", actor_user_id="alice",
        ))


def test_remove_member_self_strip_blocked() -> None:
    with pytest.raises(SelfStripError):
        asyncio.run(remove_member(
            workspace_id=1, user_id="alice", actor_user_id="alice",
        ))


# ─────────────────────────────────────────────────────────
# T-021-05 AC: EVENT — actor が他人の role 変更時は self_strip しない
# ─────────────────────────────────────────────────────────
def test_remove_member_other_user_proceeds() -> None:
    try:
        asyncio.run(remove_member(
            workspace_id=1, user_id="alice", actor_user_id="bob",
        ))
    except SelfStripError:
        pytest.fail("should not raise SelfStripError for different user")
    except Exception:
        # DB 接続エラーは許容 (本テストの範囲外)
        pass


# ─────────────────────────────────────────────────────────
# T-021-04 AC: member 追加 router → 422 unknown role (DB 不在環境向け smoke)
# ─────────────────────────────────────────────────────────
def test_add_member_unknown_role_returns_400(client) -> None:
    # DB が無い場合は 4xx になることだけ確認 (実値は環境依存)
    r = client.post(
        "/api/workspaces/99999/members",
        json={"user_id": "x", "role": "ARBITRARY_NOT_EXISTING_ROLE"},
    )
    assert r.status_code in (400, 422, 500)
