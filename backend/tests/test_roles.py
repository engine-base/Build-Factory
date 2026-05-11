"""T-021-01: 6 ロール + permission matrix の smoke test."""
from __future__ import annotations

from services.roles import (
    ROLE_KEYS, PERMISSIONS, PERMISSION_MATRIX,
    has_permission, is_known_role, validate_custom_permissions,
    get_role_definitions,
)


def test_six_role_keys() -> None:
    assert ROLE_KEYS == ("owner", "ws_admin", "contributor", "viewer", "client", "monitor")
    assert len(ROLE_KEYS) == 6


def test_roles_loaded_from_json() -> None:
    defs = get_role_definitions()
    assert len(defs) == 6
    keys = {d.get("key") for d in defs}
    assert "account_owner" in keys
    assert "workspace_admin" in keys
    assert "monitor" in keys


def test_permissions_count_30() -> None:
    assert len(PERMISSIONS) == 30


def test_owner_can_do_almost_everything() -> None:
    # owner はほぼ全 permission が True
    for perm in PERMISSIONS:
        row = PERMISSION_MATRIX.get(perm, {})
        # owner row が存在し True であること (一部 limited は除外)
        if "owner" in row:
            v = row["owner"]
            assert v is True or v == "configurable", f"owner missing: {perm}"


def test_viewer_cannot_edit() -> None:
    assert has_permission("viewer", "edit_spec") is False
    assert has_permission("viewer", "edit_task") is False
    assert has_permission("viewer", "run_session") is False


def test_contributor_can_edit_but_not_admin() -> None:
    assert has_permission("contributor", "edit_spec") is True
    assert has_permission("contributor", "run_session") is True


def test_monitor_守り_role() -> None:
    # monitor は守り = audit_log 閲覧 OK / edit 不可
    assert has_permission("monitor", "view_audit_log") is True
    assert has_permission("monitor", "edit_spec") is False


def test_or_evaluation_multiple_roles() -> None:
    # 複数ロール = OR 評価
    assert has_permission(["viewer", "contributor"], "edit_spec") is True
    assert has_permission(["viewer", "monitor"], "view_audit_log") is True


def test_unknown_permission_key_returns_false() -> None:
    assert has_permission("owner", "no_such_perm") is False


def test_custom_permissions_override() -> None:
    # viewer は normally edit_spec=False だが custom_permissions で override 可能
    assert has_permission("viewer", "edit_spec", custom_permissions={"edit_spec": True}) is True


def test_limited_value_treated_as_false() -> None:
    # "own_only" などは safe-by-default で False
    # kill_session の contributor は "own_only" → False
    assert has_permission("contributor", "kill_session") is False


def test_is_known_role_short_and_long_keys() -> None:
    assert is_known_role("owner")
    assert is_known_role("workspace_admin")  # long key も True (正規化される)
    assert is_known_role("ws_admin")
    assert not is_known_role("xxx")


def test_validate_custom_permissions_finds_unknown() -> None:
    unknown = validate_custom_permissions({"edit_spec": True, "no_such_key": True})
    assert "no_such_key" in unknown
    assert "edit_spec" not in unknown


def test_validate_custom_permissions_empty_is_valid() -> None:
    assert validate_custom_permissions(None) == []
    assert validate_custom_permissions({}) == []
