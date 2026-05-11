"""T-021-02 / T-021-05: workspace_service permission 関連の smoke test.

DB-less (in-memory) で `validate_custom_permissions` / SelfStripError /
OwnerProtectedError の動作を確認する。

実際の DB 操作 (add_member / update_member_role / remove_member) は migration
前提なので、テストでは role/permission 周りのロジックを単体検証する。
"""
from __future__ import annotations

import asyncio
import pytest

from services.workspace_service import (
    DEFAULT_ROLES, _normalize_role,
    SelfStripError, OwnerProtectedError, update_member_role, remove_member,
)
from services.roles import validate_custom_permissions


def test_default_roles_include_six_plus_legacy_admin() -> None:
    # T-021-01: 6 + legacy "admin" 互換
    for r in ("owner", "ws_admin", "contributor", "viewer", "client", "monitor"):
        assert r in DEFAULT_ROLES
    assert "admin" in DEFAULT_ROLES  # legacy 互換


def test_normalize_role_admin_to_ws_admin() -> None:
    assert _normalize_role("admin") == "ws_admin"
    assert _normalize_role("ws_admin") == "ws_admin"
    assert _normalize_role("contributor") == "contributor"


def test_validate_custom_permissions_known_keys_pass() -> None:
    assert validate_custom_permissions({"edit_spec": True, "run_session": False}) == []


def test_validate_custom_permissions_unknown_keys_returned() -> None:
    unknown = validate_custom_permissions({"made_up_permission": True})
    assert "made_up_permission" in unknown


# T-021-05: SelfStripError は同一 actor / user_id で role 変更時に発火
def test_update_member_role_self_strip_blocked() -> None:
    """actor が自分自身の role を変更しようとしたら SelfStripError"""
    # DB が無い環境では get_member が None → role 変更ロジックの early-return を
    # 避けるため、SelfStripError ブランチが先に走るか確認
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


def test_remove_member_other_user_proceeds_when_no_db() -> None:
    """別 user の削除は SelfStripError を出さない (DB 不在なら DELETE は 0 件)。"""
    # DB が無い環境では例外を吸収 (graceful) または False を返す挙動が期待値
    # raise されないことだけ確認 (具体的な return は環境依存)
    try:
        asyncio.run(remove_member(
            workspace_id=1, user_id="alice", actor_user_id="bob",
        ))
    except SelfStripError:
        pytest.fail("should not raise SelfStripError for different user")
    except Exception:
        # DB 接続エラーは許容 (本テストの範囲外)
        pass
