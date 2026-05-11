"""T-021-01: 6 ロール enum + permission matrix (REFACTOR)

functional-breakdown/2026-05-09_v1/roles.json を Python レイヤに取り込み、
6 ロール (owner / ws_admin / contributor / viewer / client / monitor) + 30
permission key × 6 ロールの matrix で `has_permission()` 判定を提供する。

## 公開 API

- `ROLE_KEYS`: 6 ロールの順序付きタプル
- `PERMISSIONS`: 30 permission key のリスト
- `PERMISSION_MATRIX`: dict[permission_key][role_key] = bool | str
- `has_permission(roles, permission_key, *, custom_permissions=None) -> bool`

## ロール (v2.1)

| Key | Name | Scope |
|---|---|---|
| `owner` (account_owner) | Account Owner | account |
| `ws_admin` (workspace_admin) | Workspace Admin | workspace (攻め) |
| `contributor` | Contributor | workspace |
| `viewer` | Viewer | workspace |
| `client` | Client | workspace + tab_visibility |
| `monitor` | Monitor | workspace (守り) |

## マトリクスの "limited" 値

PERMISSION_MATRIX の値が `True` / `False` 以外 (例: `"own_only"`, `"configurable"`,
`"limited_by_tab"`) の場合、本サービスは **False** として扱う (safe-by-default)。
細かい context-aware 判定は呼び出し元で `_handle_limited()` を override する。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union


ROLE_KEYS: tuple[str, ...] = (
    "owner",
    "ws_admin",
    "contributor",
    "viewer",
    "client",
    "monitor",
)

# roles.json での display key (R-XXX → short key)
_ROLES_JSON_KEY_MAP = {
    "account_owner": "owner",
    "workspace_admin": "ws_admin",
    "contributor": "contributor",
    "viewer": "viewer",
    "client": "client",
    "monitor": "monitor",
}


def _roles_json_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "functional-breakdown" / "2026-05-09_v1" / "roles.json"


@lru_cache(maxsize=1)
def _load_roles_json() -> dict:
    p = _roles_json_path()
    if not p.exists():
        return {"roles": [], "permission_matrix": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def get_role_definitions() -> list[dict]:
    """6 ロールの定義 (id / key / name / scope / description)。"""
    return _load_roles_json().get("roles", [])


def get_permission_matrix() -> dict[str, dict[str, Union[bool, str]]]:
    """permission_matrix dict (permission_key → role → bool|str)。"""
    return _load_roles_json().get("permission_matrix", {})


# モジュール load 時に展開して定数化
PERMISSION_MATRIX = get_permission_matrix()
PERMISSIONS: tuple[str, ...] = tuple(PERMISSION_MATRIX.keys())


def _normalize_role(role: str) -> str:
    """roles.json の long key (workspace_admin) を short key (ws_admin) に正規化。"""
    return _ROLES_JSON_KEY_MAP.get(role, role)


def has_permission(
    roles: Union[str, list[str]],
    permission_key: str,
    *,
    custom_permissions: Optional[dict] = None,
) -> bool:
    """ロール群が指定 permission を持つか判定する。

    判定順序 (v2.1 OR 評価):
      1. custom_permissions[permission_key] == True なら True (override)
      2. roles のいずれかが PERMISSION_MATRIX[permission_key] で True なら True
      3. "limited_*" / "*_only" / "configurable" は False (safe-by-default)
      4. その他は False
    """
    if isinstance(roles, str):
        roles = [roles]
    roles_norm = [_normalize_role(r) for r in roles]

    # 1. custom_permissions override
    if custom_permissions and custom_permissions.get(permission_key) is True:
        return True

    # 2. matrix lookup (OR 評価)
    row = PERMISSION_MATRIX.get(permission_key)
    if row is None:
        return False  # 未知の permission key は False
    for r in roles_norm:
        v = row.get(r)
        if v is True:
            return True
    return False


def is_known_role(role: str) -> bool:
    """6 ロール (短キー) のいずれかか。"""
    return _normalize_role(role) in ROLE_KEYS


def validate_custom_permissions(custom_permissions: Optional[dict]) -> list[str]:
    """custom_permissions の key が PERMISSIONS に含まれているか検証 (T-021-02 先取り)。

    Returns:
      list of unknown keys (空なら valid)
    """
    if not custom_permissions:
        return []
    unknown = [k for k in custom_permissions.keys() if k not in PERMISSIONS]
    return unknown
