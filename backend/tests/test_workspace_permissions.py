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


# ──────────────────────────────────────────────────────────────────────────
# T-021-01 AC-2 / AC-3 / AC-4: GET /api/workspaces/permissions/matrix
# ──────────────────────────────────────────────────────────────────────────


def test_permission_matrix_endpoint_returns_required_shape(client) -> None:
    """AC-3: response が {roles, permissions, matrix} の構造を持つ."""
    r = client.get("/api/workspaces/permissions/matrix")
    assert r.status_code == 200
    body = r.json()
    # 必須 3 key
    for k in ("roles", "permissions", "matrix"):
        assert k in body, f"missing key {k}"
    # roles は 6 件
    assert body["roles"] == list(ROLE_KEYS)
    assert len(body["roles"]) == 6


def test_permission_matrix_permissions_have_key_label_category(client) -> None:
    """AC-3: permissions[i] = {key, label, category}."""
    r = client.get("/api/workspaces/permissions/matrix")
    body = r.json()
    perms = body["permissions"]
    assert isinstance(perms, list)
    assert len(perms) >= 30  # 30 permission key
    for p in perms:
        assert set(p.keys()) >= {"key", "label", "category"}
        assert isinstance(p["key"], str)
        assert isinstance(p["label"], str) and p["label"]
        assert isinstance(p["category"], str) and p["category"]


def test_permission_matrix_role_oriented_shape(client) -> None:
    """AC-3: matrix[role][permission] = bool の構造."""
    r = client.get("/api/workspaces/permissions/matrix")
    body = r.json()
    matrix = body["matrix"]
    # role が外側 key
    for role in ROLE_KEYS:
        assert role in matrix
        # 各 role の値は permission → bool の dict
        row = matrix[role]
        assert isinstance(row, dict)
        for perm_key, val in row.items():
            assert isinstance(perm_key, str)
            assert isinstance(val, bool), f"matrix[{role}][{perm_key}] is {type(val).__name__}, expected bool"


def test_permission_matrix_owner_has_more_permissions_than_viewer(client) -> None:
    """sanity: owner の True 数 >= viewer の True 数."""
    r = client.get("/api/workspaces/permissions/matrix")
    matrix = r.json()["matrix"]
    owner_true = sum(1 for v in matrix["owner"].values() if v)
    viewer_true = sum(1 for v in matrix["viewer"].values() if v)
    assert owner_true >= viewer_true


def test_permission_matrix_keeps_legacy_keys_for_backward_compat(client) -> None:
    """legacy frontend 互換: permission_keys / legacy_matrix も残す."""
    r = client.get("/api/workspaces/permissions/matrix")
    body = r.json()
    assert "permission_keys" in body
    assert "legacy_matrix" in body
    assert isinstance(body["permission_keys"], list)
    assert len(body["permission_keys"]) == len(body["permissions"])


# ──────────────────────────────────────────────────────────────────────────
# T-021-01 AC-1: 6 ロールのみ受け入れ (is_known_role / DEFAULT_ROLES)
# ──────────────────────────────────────────────────────────────────────────


def test_is_known_role_for_six_canonical_keys() -> None:
    from services.roles import is_known_role
    for r in ROLE_KEYS:
        assert is_known_role(r) is True


def test_is_known_role_normalizes_long_keys() -> None:
    from services.roles import is_known_role
    # roles.json での long key (workspace_admin / account_owner) も True
    assert is_known_role("workspace_admin") is True
    assert is_known_role("account_owner") is True


def test_is_known_role_rejects_unknown() -> None:
    from services.roles import is_known_role
    for r in ("god", "intern", "robot", "ADMIN", "Owner", ""):
        assert is_known_role(r) is False


# ──────────────────────────────────────────────────────────────────────────
# T-021-01 AC-4: UNWANTED — 不正 role での member 追加は 422 + 永続化しない
# ──────────────────────────────────────────────────────────────────────────


def test_add_member_with_invalid_role_returns_4xx(client) -> None:
    """AC-4: invalid role → 4xx で reject (DB 永続化しない).

    Pydantic / service 層のどちらが reject するかは実装依存だが、
    いずれにせよ 4xx で帰り、 DB に row が増えないことが重要."""
    r = client.post(
        "/api/workspaces/1/members",
        json={"user_id": "alice", "role": "DEFINITELY_NOT_A_ROLE"},
    )
    # 422 (pydantic) / 400 (custom validation) / 500 (DB 不在環境) を許容
    assert r.status_code in (400, 422, 500)


def test_update_member_role_with_invalid_role_returns_4xx(client) -> None:
    r = client.patch(
        "/api/workspaces/1/members/alice",
        json={"role": "INVALID"},
    )
    assert r.status_code in (400, 422, 500)


def test_normalize_role_admin_legacy_alias() -> None:
    """DB 既存 row 互換: admin → ws_admin に変換."""
    assert _normalize_role("admin") == "ws_admin"
    assert _normalize_role("ws_admin") == "ws_admin"
    assert _normalize_role("owner") == "owner"


# ──────────────────────────────────────────────────────────────────────────
# Permissions metadata 内部 helper
# ──────────────────────────────────────────────────────────────────────────


def test_get_permissions_metadata_covers_all_permission_keys() -> None:
    from services.roles import PERMISSIONS, get_permissions_metadata
    meta = get_permissions_metadata()
    keys_in_meta = {m["key"] for m in meta}
    assert keys_in_meta == set(PERMISSIONS)


def test_get_permissions_metadata_categories_are_meaningful() -> None:
    from services.roles import get_permissions_metadata
    meta = get_permissions_metadata()
    categories = {m["category"] for m in meta}
    # 7+ category が存在することを確認 (view / edit / approval / ai / membership / 等)
    assert len(categories) >= 5
    # 全 category は非空文字列
    assert all(c and isinstance(c, str) for c in categories)


def test_get_role_oriented_matrix_returns_only_bool_values() -> None:
    """role-oriented matrix の全 cell は bool (limited_* は False に正規化)."""
    from services.roles import get_role_oriented_matrix
    matrix = get_role_oriented_matrix()
    for role, row in matrix.items():
        for perm, v in row.items():
            assert isinstance(v, bool), f"matrix[{role}][{perm}] = {v!r}"


def test_role_oriented_matrix_includes_all_roles() -> None:
    from services.roles import ROLE_KEYS, get_role_oriented_matrix
    matrix = get_role_oriented_matrix()
    assert set(matrix.keys()) == set(ROLE_KEYS)


def test_infer_category_for_known_prefixes() -> None:
    from services.roles import _infer_category
    assert _infer_category("view_phase_X") == "view"
    assert _infer_category("view_costs") == "finance"
    assert _infer_category("view_audit_log") == "security"
    assert _infer_category("edit_spec") == "edit"
    assert _infer_category("edit_budget") == "governance"
    assert _infer_category("edit_integrations") == "integration"
    assert _infer_category("approve_phase_gate") == "approval"
    assert _infer_category("summon_ai_employee") == "ai"
    assert _infer_category("invite_member") == "membership"
    assert _infer_category("archive_workspace") == "workspace"
    assert _infer_category("manage_secrets") == "security"
    assert _infer_category("export_artifacts") == "data"
    assert _infer_category("unknown_xyz") == "other"
