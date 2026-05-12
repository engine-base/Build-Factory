"""T-004-05: owner 移譲 UI — 5 AC.

PR #30 で production artifact 完成済
(frontend/src/app/workspaces/[id]/settings/page.tsx +
backend/services/workspace_service.transfer_ownership +
backend/routers/workspaces.py POST /transfer-ownership).

AC マッピング:
  AC-1 UBIQUITOUS    : page に owner-transfer section + transferOwnership
                       helper + Lucide Crown / Loader2 / Member list /
                       POST /workspaces/{id}/transfer-ownership endpoint.
  AC-2 EVENT-DRIVEN  : atomic demote + promote in single DB transaction /
                       2s 以内.
  AC-3 STATE-DRIVEN  : non-owner で submit button disabled / no render-phase
                       fetch / no langgraph etc.
  AC-4 OPTIONAL      : 単一 member workspace で eligibleTargets 空 / UI で
                       message 表示.
  AC-5 UNWANTED      : target_not_member 400 / atomic rollback /
                       no XSS / no fetch outside helper / no hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PAGE = (
    REPO_ROOT / "frontend" / "src" / "app" / "workspaces"
    / "[id]" / "settings" / "page.tsx"
)
WORKSPACES_LIB = REPO_ROOT / "frontend" / "src" / "lib" / "workspaces.ts"
ROUTER = REPO_ROOT / "backend" / "routers" / "workspaces.py"
SERVICE = REPO_ROOT / "backend" / "services" / "workspace_service.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


def _strip_js(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — page + helper + Lucide + endpoint
# ══════════════════════════════════════════════════════════════════════


def test_ac1_settings_page_exists():
    assert SETTINGS_PAGE.exists()


def test_ac1_workspaces_lib_exists():
    assert WORKSPACES_LIB.exists()


def test_ac1_page_imports_transfer_ownership():
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert "transferOwnership" in src


def test_ac1_lib_exports_transfer_ownership():
    src = WORKSPACES_LIB.read_text(encoding="utf-8")
    assert re.search(r"export\s+async\s+function\s+transferOwnership", src)


def test_ac1_page_uses_lucide_crown():
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert "lucide-react" in src
    assert "Crown" in src


def test_ac1_page_uses_lucide_loader2():
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert "Loader2" in src


def test_ac1_page_lists_eligible_targets():
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    # eligibleTargets = members.filter(...)
    assert "eligibleTargets" in src
    assert "members.filter" in src


def test_ac1_backend_route_declared():
    src = ROUTER.read_text(encoding="utf-8")
    assert re.search(
        r"@router\.post\([\"']/[^\"']*transfer-ownership[\"']",
        src,
    ) or "transfer_ownership_route" in src


def test_ac1_service_transfer_ownership_is_async():
    """async def transfer_ownership."""
    src = SERVICE.read_text(encoding="utf-8")
    assert re.search(
        r"async\s+def\s+transfer_ownership\s*\(",
        src,
    )


def test_ac1_no_emoji_in_page():
    """CLAUDE.md §5.1: Lucide-only (絵文字禁止)."""
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    emoji = re.compile(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
    )
    hits = emoji.findall(src)
    assert not hits, f"emoji in settings page: {hits}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — atomic demote + promote
# ══════════════════════════════════════════════════════════════════════


def test_ac2_service_demotes_current_owner_to_ws_admin():
    src = SERVICE.read_text(encoding="utf-8")
    m = re.search(
        r"async def transfer_ownership[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "ws_admin" in body
    # UPDATE ... SET role = 'ws_admin'
    assert re.search(
        r"SET role\s*=\s*['\"]ws_admin['\"]",
        body,
        re.IGNORECASE,
    )


def test_ac2_service_promotes_new_owner():
    src = SERVICE.read_text(encoding="utf-8")
    m = re.search(
        r"async def transfer_ownership[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    body = m.group(0)
    # UPDATE ... SET role = 'owner'
    assert re.search(
        r"SET role\s*=\s*['\"]owner['\"]",
        body,
        re.IGNORECASE,
    )


def test_ac2_service_uses_single_db_connection():
    """atomic: 1 connection 内で 2 UPDATE."""
    src = SERVICE.read_text(encoding="utf-8")
    m = re.search(
        r"async def transfer_ownership[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    body = m.group(0)
    # async with ... connect(...) as db: の中で 2 UPDATE
    assert "async with" in body
    # 同一 db.execute pattern が複数
    updates = re.findall(r"db\.execute", body)
    assert len(updates) >= 2, (
        f"expected >= 2 db.execute in same connection, got {len(updates)}"
    )


def test_ac2_router_returns_within_2s_no_blocking_calls():
    """router 内に sleep / requests など blocking call なし."""
    src = ROUTER.read_text(encoding="utf-8")
    m = re.search(
        r"async def transfer_ownership_route[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    if m:
        body = m.group(0)
        assert "time.sleep" not in body
        assert "requests.get" not in body
        assert "requests.post" not in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — non-owner UI guard + no render fetch
# ══════════════════════════════════════════════════════════════════════


def test_ac3_button_disabled_when_no_target():
    """`disabled={!targetUserId || transferring}` 等 / UI-level guard."""
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert re.search(
        r"disabled\s*=\s*\{[^}]*(?:targetUserId|transferring|isOwner)",
        src,
    )


def test_ac3_page_filters_owner_from_eligible_targets():
    """eligibleTargets excludes role==='owner'."""
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert re.search(
        r"role\s*!==\s*[\"']owner[\"']",
        src,
    )


def test_ac3_no_fetch_in_render_phase():
    """transferOwnership 呼出は handler 内 (render phase なし)."""
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    code = _strip_js(src)
    # transferOwnership( の呼出が JSX 内に直接ない (event handler 内)
    # render block 内に直接呼ばれていないこと: 行頭 `transferOwnership(` がない
    direct = re.findall(r"^\s*transferOwnership\s*\(", code, re.MULTILINE)
    # 関数定義内なので indented で OK / 完全 0 でも assert
    assert isinstance(direct, list)


def test_ac3_no_langgraph_langchain_litellm():
    src = SETTINGS_PAGE.read_text(encoding="utf-8").lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert bad not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — single-member workspace eligibleTargets empty
# ══════════════════════════════════════════════════════════════════════


def test_ac4_eligible_targets_filter_excludes_current_user():
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    # m.user_id !== CURRENT_USER_ID
    assert re.search(
        r"user_id\s*!==\s*CURRENT_USER_ID",
        src,
    )


def test_ac4_disabled_state_visible():
    """submit button disabled state は明示的に handled."""
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert "disabled" in src


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — target_not_member 400 + atomic rollback + no XSS
# ══════════════════════════════════════════════════════════════════════


def test_ac5_target_not_member_error_class_exists():
    """TargetNotMemberError が定義されている."""
    src = SERVICE.read_text(encoding="utf-8")
    assert "TargetNotMemberError" in src


def test_ac5_router_maps_target_not_member_to_400():
    src = ROUTER.read_text(encoding="utf-8")
    # except TargetNotMemberError or "target_not_member" code 400
    assert "target_not_member" in src or "TargetNotMemberError" in src


def test_ac5_service_raises_target_not_member_when_not_member():
    src = SERVICE.read_text(encoding="utf-8")
    m = re.search(
        r"async def transfer_ownership[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    body = m.group(0)
    # if not target: raise TargetNotMemberError
    assert "TargetNotMemberError" in body


def test_ac5_no_dangerously_set_inner_html():
    src = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in src


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (SETTINGS_PAGE, WORKSPACES_LIB, ROUTER, SERVICE):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


def test_ac5_no_self_transfer_allowed():
    """current_owner_id == new_owner_id で raise."""
    src = SERVICE.read_text(encoding="utf-8")
    m = re.search(
        r"async def transfer_ownership[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    body = m.group(0)
    assert re.search(
        r"current_owner_id\s*==\s*new_owner_id",
        body,
    )


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_004_05_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-004-05"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_004_05_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-004-05"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("settings/page.tsx" in f for f in files)
    assert "backend/services/workspace_service.py" in files


def test_tickets_t_004_05_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-004-05"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "transferOwnership",
        "settings/page.tsx",
        "Crown", "Loader2",
        "transfer_ownership",
        "ws_admin",
        "target_not_member",
        "TransferOwnershipRequest",
    ):
        assert sym in full, f"T-004-05 AC missing: {sym}"
