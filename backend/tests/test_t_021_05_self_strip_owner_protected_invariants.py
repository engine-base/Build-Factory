"""T-021-05: self-strip block + owner 保護 — 5 AC.

Production artifact 完成済
(backend/services/workspace_service.py SelfStripError + OwnerProtectedError
+ _count_role + update_member_role / remove_member guards +
backend/routers/workspaces.py PATCH/DELETE 409 mapping).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : SelfStripError + OwnerProtectedError ValueError
                       subclass / _count_role helper / {detail: {code,
                       message}} response shape.
  AC-2 EVENT-DRIVEN  : PATCH 409 self_strip_blocked + owner_protected /
                       DELETE 409 同上 / guard precedes UPDATE/DELETE.
  AC-3 STATE-DRIVEN  : actor != target → no guard / count > 1 → demote
                       OK.
  AC-4 OPTIONAL      : actor_user_id None → skip self-strip / role None
                       → skip self-strip.
  AC-5 UNWANTED      : SelfStripError raised pre-DB / no langgraph /
                       no hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PY = REPO_ROOT / "backend" / "services" / "workspace_service.py"
ROUTER_PY = REPO_ROOT / "backend" / "routers" / "workspaces.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — error classes + _count_role + response shape
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_and_router_exist():
    assert SERVICE_PY.exists()
    assert ROUTER_PY.exists()


def test_ac1_self_strip_error_is_value_error_subclass():
    from services.workspace_service import SelfStripError
    assert issubclass(SelfStripError, ValueError)


def test_ac1_owner_protected_error_is_value_error_subclass():
    from services.workspace_service import OwnerProtectedError
    assert issubclass(OwnerProtectedError, ValueError)


def test_ac1_count_role_helper_exists():
    src = SERVICE_PY.read_text(encoding="utf-8")
    assert re.search(r"async def _count_role\s*\(", src)
    # COUNT(*) WHERE workspace_id = ? AND role = ?
    assert re.search(
        r"SELECT\s+COUNT\(\*\)\s+FROM\s+workspace_members\s+WHERE\s+workspace_id\s*=\s*\?\s+AND\s+role\s*=\s*\?",
        src,
        re.IGNORECASE,
    )


def test_ac1_response_shape_detail_code_message():
    src = ROUTER_PY.read_text(encoding="utf-8")
    # detail={"code": "...", "message": str(e)}
    matches = re.findall(
        r"detail\s*=\s*\{\s*[\"']code[\"']\s*:\s*[\"'][a-z_]+[\"']\s*,\s*[\"']message[\"']\s*:\s*str\(e\)",
        src,
    )
    # PATCH + DELETE で 2 つ以上 ({code: self_strip_blocked, ...} と {code: owner_protected, ...})
    assert len(matches) >= 4, f"expected >= 4 detail {{code,message}} matches, got {len(matches)}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — PATCH/DELETE 409 mapping + guard pre-DB
# ══════════════════════════════════════════════════════════════════════


def test_ac2_patch_maps_self_strip_to_409():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def update_member[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "SelfStripError" in body
    assert re.search(
        r"status_code\s*=\s*409[\s\S]+?self_strip_blocked",
        body,
    )


def test_ac2_patch_maps_owner_protected_to_409():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def update_member[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "OwnerProtectedError" in body
    assert re.search(
        r"status_code\s*=\s*409[\s\S]+?owner_protected",
        body,
    )


def test_ac2_delete_maps_self_strip_and_owner_protected():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def remove_member[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "SelfStripError" in body
    assert "OwnerProtectedError" in body
    # 409 が 2 回 (each error)
    assert len(re.findall(r"status_code\s*=\s*409", body)) >= 2


def test_ac2_guard_precedes_update_sql_in_service():
    """update_member_role: SelfStripError raise が UPDATE SQL より前."""
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def update_member_role[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    self_strip_idx = body.find("SelfStripError")
    update_sql_idx = body.find("UPDATE workspace_members")
    assert self_strip_idx >= 0 and update_sql_idx >= 0
    assert self_strip_idx < update_sql_idx


def test_ac2_remove_member_guard_precedes_delete():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def remove_member[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    self_strip_idx = body.find("SelfStripError")
    # DELETE FROM workspace_members in remove_member
    delete_idx = body.find("DELETE FROM workspace_members")
    assert self_strip_idx >= 0
    # delete_idx may be -1 if DELETE is in inline SQL; check for delete-like statement
    if delete_idx < 0:
        # may use db.execute with 'DELETE ...'
        delete_idx = body.find("DELETE")
    assert delete_idx >= 0
    assert self_strip_idx < delete_idx


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — actor != target / count > 1 demote OK
# ══════════════════════════════════════════════════════════════════════


def test_ac3_guard_only_when_actor_equals_target():
    """update_member_role の self-strip guard 条件: actor_user_id == user_id."""
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def update_member_role[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(
        r"actor_user_id\s+is\s+not\s+None\s+and\s+actor_user_id\s*==\s*user_id",
        body,
    )


def test_ac3_owner_protect_only_when_count_le_1():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def update_member_role[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(
        r"_count_role\([^)]*workspace_id[^)]*,\s*[\"']owner[\"']\s*\)\s*<=\s*1",
        body,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — actor None → skip / role None → skip
# ══════════════════════════════════════════════════════════════════════


def test_ac4_actor_none_skips_self_strip():
    """actor_user_id is None なら self-strip guard はスキップ."""
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def update_member_role[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # guard が `actor_user_id is not None and ...` パターン
    assert re.search(
        r"if\s+actor_user_id\s+is\s+not\s+None",
        body,
    )


def test_ac4_role_none_skips_self_strip():
    """role が None (custom_permissions のみ) なら self-strip guard はスキップ."""
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def update_member_role[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # guard が `... and role is not None` を含む
    assert re.search(
        r"role\s+is\s+not\s+None",
        body,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — SelfStripError pre-DB / no langgraph / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_self_strip_message_contains_blocked_keyword():
    src = SERVICE_PY.read_text(encoding="utf-8")
    # raise SelfStripError("cannot ... self-strip blocked")
    assert re.search(
        r"raise\s+SelfStripError\(\s*[\"'][^\"']*self-strip blocked",
        src,
    )


def test_ac5_no_langgraph_langchain_litellm():
    for path in (SERVICE_PY, ROUTER_PY):
        src = path.read_text(encoding="utf-8").lower()
        for bad in ("langgraph", "langchain", "litellm"):
            assert bad not in src, f"{path.name} imports {bad}"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (SERVICE_PY, ROUTER_PY):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_021_05_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-05"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_021_05_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-05"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/workspace_service.py" in files
    assert "backend/routers/workspaces.py" in files


def test_tickets_t_021_05_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-05"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "SelfStripError",
        "OwnerProtectedError",
        "_count_role",
        "update_member_role",
        "remove_member",
        "self_strip_blocked",
        "owner_protected",
        "HTTPException(409",
        "ADR-010",
    ):
        assert sym in full, f"T-021-05 AC missing: {sym}"
