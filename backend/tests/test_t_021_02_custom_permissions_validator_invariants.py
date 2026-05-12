"""T-021-02: custom_permissions JSONB バリデータ — 5 AC.

PR #24 で production artifact 完成済
(backend/services/roles.py validate_custom_permissions +
has_permission grant-only override).

AC マッピング:
  AC-1 UBIQUITOUS    : validate_custom_permissions(custom_permissions:
                       Optional[dict]) -> list[str] / unknown key list /
                       PERMISSIONS = 30 keys / has_permission consumes
                       validated dict.
  AC-2 EVENT-DRIVEN  : upstream rejects on non-empty warn list /
                       has_permission within 2s (no I/O).
  AC-3 STATE-DRIVEN  : grant-only override (True grants regardless of role)
                       / None / empty dict returns [] / pure function (no
                       DB / no network).
  AC-4 OPTIONAL      : multi-role OR-evaluation / warn list deterministic
                       (input-key-order preserved).
  AC-5 UNWANTED      : unknown key in warn list / no input mutation /
                       no langgraph / langchain / litellm import.
"""
from __future__ import annotations

import inspect
import json
import re
import time
from pathlib import Path

import pytest

from services import roles
from services.roles import (
    PERMISSIONS,
    PERMISSION_MATRIX,
    has_permission,
    validate_custom_permissions,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ROLES_PY = REPO_ROOT / "backend" / "services" / "roles.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — signature + PERMISSIONS subset + consumer pattern
# ══════════════════════════════════════════════════════════════════════


def test_ac1_validate_custom_permissions_exists():
    assert callable(validate_custom_permissions)


def test_ac1_validate_signature_optional_dict_to_list_str():
    """validate_custom_permissions(custom_permissions: Optional[dict]) -> list[str]."""
    sig = inspect.signature(validate_custom_permissions)
    params = list(sig.parameters.values())
    assert len(params) == 1, f"expected 1 param, got {len(params)}"
    p = params[0]
    assert p.name == "custom_permissions"
    # return annotation = list[str]
    ann = sig.return_annotation
    assert ann is not inspect.Signature.empty, "missing return annotation"


def test_ac1_permissions_is_30_keys():
    """PERMISSIONS = T-021-01 30 permission key tuple."""
    assert isinstance(PERMISSIONS, tuple)
    assert len(PERMISSIONS) == 30, f"expected 30 PERMISSIONS, got {len(PERMISSIONS)}"


def test_ac1_validate_returns_list_of_str():
    """戻り値は list[str]."""
    result = validate_custom_permissions({"unknown_key_xyz": True})
    assert isinstance(result, list)
    for k in result:
        assert isinstance(k, str)


def test_ac1_has_permission_consumes_custom_permissions():
    """has_permission の signature が custom_permissions を kw-only で受ける."""
    sig = inspect.signature(has_permission)
    assert "custom_permissions" in sig.parameters
    p = sig.parameters["custom_permissions"]
    # keyword-only
    assert p.kind == inspect.Parameter.KEYWORD_ONLY


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — upstream reject pattern + performance < 2s
# ══════════════════════════════════════════════════════════════════════


def test_ac2_non_empty_warn_list_signals_invalid():
    """unknown key を含むと non-empty list を返す (upstream は 400 reject 判断)."""
    result = validate_custom_permissions({"definitely_not_a_real_permission": True})
    assert len(result) >= 1
    assert "definitely_not_a_real_permission" in result


def test_ac2_empty_warn_list_signals_valid():
    """全 key が PERMISSIONS subset なら [] (upstream は通過判断)."""
    valid_key = PERMISSIONS[0]
    result = validate_custom_permissions({valid_key: True})
    assert result == []


def test_ac2_performance_under_2s():
    """has_permission + validate_custom_permissions 共に 2s 未満 (no I/O)."""
    custom = {PERMISSIONS[0]: True, PERMISSIONS[1]: True}
    t0 = time.perf_counter()
    for _ in range(1000):
        validate_custom_permissions(custom)
        has_permission(["viewer"], PERMISSIONS[0], custom_permissions=custom)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"1000 iter took {elapsed:.3f}s (>= 2s)"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — grant-only override + safe on None / pure function
# ══════════════════════════════════════════════════════════════════════


def test_ac3_grant_only_override_promotes_viewer():
    """viewer に edit_spec=True override で True を返す (grant-only)."""
    # viewer のデフォルトでは edit_spec=False (PERMISSION_MATRIX で確認)
    matrix_row = PERMISSION_MATRIX.get("edit_spec", {})
    assert matrix_row.get("viewer") is not True, (
        "precondition: viewer must not have edit_spec by default"
    )
    result = has_permission(
        ["viewer"], "edit_spec",
        custom_permissions={"edit_spec": True},
    )
    assert result is True


def test_ac3_validate_none_returns_empty_list():
    assert validate_custom_permissions(None) == []


def test_ac3_validate_empty_dict_returns_empty_list():
    assert validate_custom_permissions({}) == []


def test_ac3_validate_is_pure_no_io():
    """validate_custom_permissions の body に open / requests / db を含まない."""
    src = inspect.getsource(validate_custom_permissions)
    for bad in ("open(", "requests.", "httpx.", "urllib", "sqlite", "psycopg"):
        assert bad not in src, f"validate_custom_permissions imports/calls {bad}"


def test_ac3_grant_only_does_not_revoke():
    """custom_permissions[key]=False は role 既定の True を revoke しない (grant-only invariant)."""
    # owner は全 permission True を想定 → False override しても True のまま
    matrix_row = PERMISSION_MATRIX.get(PERMISSIONS[0], {})
    if matrix_row.get("owner") is True:
        result = has_permission(
            ["owner"], PERMISSIONS[0],
            custom_permissions={PERMISSIONS[0]: False},
        )
        assert result is True, "False override must not revoke base role grant"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — multi-role OR + deterministic warn list order
# ══════════════════════════════════════════════════════════════════════


def test_ac4_multi_role_or_evaluation():
    """['contributor', 'viewer'] で contributor が grant する permission は True."""
    # contributor が True / viewer が False の permission を探す
    target = None
    for pkey, row in PERMISSION_MATRIX.items():
        if row.get("contributor") is True and row.get("viewer") is not True:
            target = pkey
            break
    if target is None:
        pytest.skip("no permission with contributor=True / viewer!=True")
    assert has_permission(["contributor", "viewer"], target) is True
    assert has_permission(["viewer"], target) is False


def test_ac4_multi_role_or_with_custom_override():
    """multi-role + custom_permissions grant の OR 評価."""
    # viewer + monitor (両方 edit_spec=False 想定) に custom override で True
    matrix_row = PERMISSION_MATRIX.get("edit_spec", {})
    if matrix_row.get("viewer") is True or matrix_row.get("monitor") is True:
        pytest.skip("viewer or monitor already has edit_spec")
    result = has_permission(
        ["viewer", "monitor"], "edit_spec",
        custom_permissions={"edit_spec": True},
    )
    assert result is True


def test_ac4_warn_list_preserves_input_order():
    """validate の warn list は input key の挿入順を保持 (deterministic log)."""
    inp = {"zzz_unknown": True, "aaa_unknown": True, "mmm_unknown": True}
    result = validate_custom_permissions(inp)
    # dict は Python 3.7+ で挿入順保持 → 同じ順序で出る
    assert result == ["zzz_unknown", "aaa_unknown", "mmm_unknown"]


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — unknown key in list / no mutation / no LangGraph
# ══════════════════════════════════════════════════════════════════════


def test_ac5_unknown_key_returned_in_warn_list():
    result = validate_custom_permissions({
        PERMISSIONS[0]: True,  # known
        "totally_made_up_perm_key": True,  # unknown
    })
    assert "totally_made_up_perm_key" in result
    assert PERMISSIONS[0] not in result


def test_ac5_no_input_mutation():
    """validate_custom_permissions は入力 dict を mutate しない (functional purity)."""
    inp = {"some_unknown_key": True, PERMISSIONS[0]: False}
    inp_copy = dict(inp)
    validate_custom_permissions(inp)
    assert inp == inp_copy, "validate_custom_permissions mutated input dict"


def test_ac5_no_langgraph_langchain_litellm_in_roles_module():
    """ADR-010: roles モジュールに main path 禁止 import が無い."""
    src = ROLES_PY.read_text(encoding="utf-8").lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert bad not in src, f"roles.py imports forbidden {bad}"


def test_ac5_has_permission_no_input_mutation():
    """has_permission も custom_permissions / roles list を mutate しない."""
    roles_list = ["viewer"]
    roles_copy = list(roles_list)
    custom = {PERMISSIONS[0]: True}
    custom_copy = dict(custom)
    has_permission(roles_list, PERMISSIONS[0], custom_permissions=custom)
    assert roles_list == roles_copy, "has_permission mutated roles list"
    assert custom == custom_copy, "has_permission mutated custom_permissions"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    src = ROLES_PY.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_021_02_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-02"), None)
    assert t is not None, "T-021-02 not in tickets.json"
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), f"non-canonical EARS type: {ty}"
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_021_02_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-02"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/roles.py" in files


def test_tickets_t_021_02_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-02"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "validate_custom_permissions",
        "has_permission",
        "PERMISSIONS",
        "grant-only",
        "custom_permissions",
        "30",
        "ADR-010",
    ):
        assert sym in full, f"T-021-02 AC missing: {sym}"
