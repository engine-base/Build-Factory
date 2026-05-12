"""T-021-01: 6 ロール permission matrix — 5 AC.

PR #24 / #56 で production artifact 完成済
(backend/services/roles.py + GET /api/workspaces/permissions/matrix +
docs/functional-breakdown/2026-05-09_v1/roles.json).

AC マッピング:
  AC-1 UBIQUITOUS    : 6 normalized roles + 8 public symbol + roles.json
                       canonical (30 perm × 6 role).
  AC-2 EVENT-DRIVEN  : matrix endpoint 5-field response (roles +
                       permissions + matrix + permission_keys +
                       legacy_matrix) / deterministic.
  AC-3 STATE-DRIVEN  : @lru_cache(maxsize=1) / PERMISSION_MATRIX module-
                       level / no AI stack / no G15 violation.
  AC-4 OPTIONAL      : custom_permissions override BEFORE base role /
                       validate_custom_permissions returns warnings.
  AC-5 UNWANTED      : invalid role → 422 / missing roles.json → graceful
                       empty / no hardcoded secret.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import roles


REPO_ROOT = Path(__file__).resolve().parents[2]
ROLES_PY = REPO_ROOT / "backend" / "services" / "roles.py"
ROLES_JSON = REPO_ROOT / "docs" / "functional-breakdown" / "2026-05-09_v1" / "roles.json"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"

NORMALIZED_ROLES = ("owner", "ws_admin", "contributor", "viewer", "client", "monitor")


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 6 roles + 8 public symbols + 30 permissions
# ══════════════════════════════════════════════════════════════════════


def test_ac1_roles_py_exists():
    assert ROLES_PY.exists()


def test_ac1_roles_json_exists():
    assert ROLES_JSON.exists()


def test_ac1_roles_json_has_6_roles():
    d = json.loads(ROLES_JSON.read_text(encoding="utf-8"))
    assert len(d["roles"]) == 6


def test_ac1_roles_json_has_30_permission_keys():
    d = json.loads(ROLES_JSON.read_text(encoding="utf-8"))
    assert len(d["permission_matrix"]) == 30


@pytest.mark.parametrize("sym", [
    "_ROLES_JSON_KEY_MAP",
    "_normalize_role",
    "get_role_definitions",
    "get_permission_matrix",
    "has_permission",
    "is_known_role",
    "validate_custom_permissions",
    "get_permissions_metadata",
    "get_role_oriented_matrix",
    "PERMISSION_MATRIX",
])
def test_ac1_public_symbol(sym):
    assert hasattr(roles, sym), f"roles.py missing: {sym}"


def test_ac1_normalize_role_mapping():
    """account_owner → owner / workspace_admin → ws_admin / 残り 4 は identity."""
    assert roles._normalize_role("account_owner") == "owner"
    assert roles._normalize_role("workspace_admin") == "ws_admin"
    for r in ("contributor", "viewer", "client", "monitor"):
        assert roles._normalize_role(r) == r


def test_ac1_six_normalized_roles_present():
    """is_known_role が 6 normalized role 全件 True を返す."""
    for r in NORMALIZED_ROLES:
        assert roles.is_known_role(r), f"role {r} not recognized"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — matrix endpoint 5-field response
# ══════════════════════════════════════════════════════════════════════


def test_ac2_endpoint_returns_200(client):
    resp = client.get("/api/workspaces/permissions/matrix")
    assert resp.status_code == 200, resp.text


def test_ac2_response_has_required_fields(client):
    resp = client.get("/api/workspaces/permissions/matrix")
    body = resp.json()
    for key in ("roles", "permissions", "matrix",
                "permission_keys", "legacy_matrix"):
        assert key in body, f"response missing: {key}"


def test_ac2_response_has_6_roles(client):
    resp = client.get("/api/workspaces/permissions/matrix")
    body = resp.json()
    assert len(body["roles"]) == 6


def test_ac2_response_has_30_permission_keys(client):
    resp = client.get("/api/workspaces/permissions/matrix")
    body = resp.json()
    assert len(body["permission_keys"]) == 30
    assert len(body["permissions"]) == 30


def test_ac2_permission_metadata_has_key_label_category(client):
    resp = client.get("/api/workspaces/permissions/matrix")
    body = resp.json()
    for p in body["permissions"]:
        assert "key" in p
        assert "label" in p
        assert "category" in p


def test_ac2_matrix_is_role_oriented(client):
    """matrix[role][permission] = bool 形式."""
    resp = client.get("/api/workspaces/permissions/matrix")
    body = resp.json()
    matrix = body["matrix"]
    # 各 role が 30 permission を持つ
    for role_key in matrix:
        assert len(matrix[role_key]) == 30


def test_ac2_response_deterministic(client):
    """同じ入力で常に同じ response."""
    r1 = client.get("/api/workspaces/permissions/matrix").json()
    r2 = client.get("/api/workspaces/permissions/matrix").json()
    assert r1 == r2


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — lru_cache + module-level + no AI stack
# ══════════════════════════════════════════════════════════════════════


def test_ac3_load_roles_json_uses_lru_cache():
    src = ROLES_PY.read_text(encoding="utf-8")
    assert "@lru_cache" in src
    assert "maxsize=1" in src


def test_ac3_permission_matrix_module_level_constant():
    """import 時に PERMISSION_MATRIX が computed."""
    assert isinstance(roles.PERMISSION_MATRIX, dict)
    assert len(roles.PERMISSION_MATRIX) > 0


def test_ac3_no_langgraph_langchain_litellm():
    src = ROLES_PY.read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    code = re.sub(r"#[^\n]*", "", code).lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert bad not in code


def test_ac3_no_section_keys_review_dimensions_persona_name():
    """G15 cross-module: SECTION_KEYS / REVIEW_DIMENSIONS / PERSONA_NAME 再定義禁止."""
    src = ROLES_PY.read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    for forbidden in ("SECTION_KEYS", "REVIEW_DIMENSIONS", "PERSONA_NAME"):
        # 代入 = の左辺 only (引数 / docstring は除外)
        assert not re.search(
            rf"^{forbidden}\s*=",
            code,
            re.MULTILINE,
        ), f"G15 violation: {forbidden} redefined"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — custom_permissions override
# ══════════════════════════════════════════════════════════════════════


def test_ac4_has_permission_respects_custom_grant():
    """custom_permissions override で base role の False を True に."""
    # base contributor は view_audit_log が無いはず
    base_can = roles.has_permission(["contributor"], "view_audit_log")
    # custom_permissions で grant
    custom_can = roles.has_permission(
        ["contributor"],
        "view_audit_log",
        custom_permissions={"view_audit_log": True},
    )
    # custom grant が優先される
    if not base_can:
        assert custom_can is True


def test_ac4_custom_permissions_is_grant_only_no_revoke():
    """v2.1 OR-evaluation: custom_permissions は grant-only.

    custom_permissions[key]=False では base role の True を revoke しない
    (defense-in-depth ではなく grant-only / 仕様明示).
    """
    base_can = roles.has_permission(["owner"], "view_audit_log")
    # custom_permissions={key: False} は no-op (grant-only spec)
    still_can = roles.has_permission(
        ["owner"],
        "view_audit_log",
        custom_permissions={"view_audit_log": False},
    )
    assert still_can == base_can, (
        "custom_permissions=False must NOT revoke base role grant (grant-only spec)"
    )


def test_ac4_validate_custom_permissions_returns_list():
    """validate_custom_permissions が unknown key を warn list で返す."""
    warnings = roles.validate_custom_permissions({"unknown_perm": True})
    assert isinstance(warnings, list)
    # unknown_perm が含まれる
    assert any("unknown_perm" in w for w in warnings)


def test_ac4_validate_custom_permissions_none_returns_empty_list():
    warnings = roles.validate_custom_permissions(None)
    assert warnings == []


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — invalid role / graceful fallback / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_is_known_role_false_for_unknown():
    for bad in ("super_admin", "root", "guest", "", "unknown"):
        assert not roles.is_known_role(bad)


def test_ac5_load_roles_json_returns_empty_on_missing(tmp_path, monkeypatch):
    """roles.json が無い場合 graceful empty を返す."""
    fake_path = tmp_path / "nonexistent.json"
    # cache clear
    roles._load_roles_json.cache_clear()
    monkeypatch.setattr(roles, "_roles_json_path", lambda: fake_path)
    result = roles._load_roles_json()
    roles._load_roles_json.cache_clear()  # 後続テストに影響しない
    assert result == {"roles": [], "permission_matrix": {}}


def test_ac5_no_hardcoded_secret_in_roles():
    src = ROLES_PY.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)


def test_ac5_no_hardcoded_secret_in_roles_json():
    src = ROLES_JSON.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)


def test_ac5_unknown_role_returns_false_in_has_permission():
    """unknown role を渡しても has_permission は False (graceful)."""
    result = roles.has_permission(["super_admin"], "view_audit_log")
    assert result is False or result is None


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_021_01_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-01"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_021_01_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-01"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "backend/services/roles.py" in files
    assert "docs/functional-breakdown/2026-05-09_v1/roles.json" in files


def test_tickets_t_021_01_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-01"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "owner", "ws_admin", "contributor", "viewer", "client", "monitor",
        "_ROLES_JSON_KEY_MAP",
        "has_permission",
        "validate_custom_permissions",
        "get_permission_matrix",
        "is_known_role",
        "permission_keys",
        "legacy_matrix",
        "@lru_cache",
        "PERMISSION_MATRIX",
        "roles.json",
        "custom_permissions",
    ):
        assert sym in full, f"T-021-01 AC missing: {sym}"
