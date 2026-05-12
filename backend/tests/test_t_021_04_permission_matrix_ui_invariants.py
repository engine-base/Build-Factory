"""T-021-04: permission matrix UI grid — 5 AC.

Production artifact 完成済 (frontend/src/app/workspaces/[id]/members/page.tsx +
frontend/src/lib/workspace-api.ts).
本 module は **spec contract layer** (静的 source 解析).

AC マッピング:
  AC-1 UBIQUITOUS    : 6 ROLE_KEYS + SUMMARY_COLUMNS (>= 7) +
                       lucide-react ShieldCheck/Eye/Hammer/UserCog/
                       Briefcase/Activity/Mail/Loader2 + eb-500 / no emoji.
  AC-2 EVENT-DRIVEN  : updateMemberRole PATCH / addMember POST /
                       invalidateQueries 'ws-members' / no blocking I/O.
  AC-3 STATE-DRIVEN  : Loader2 spinner / empty-state msg /
                       per-row saving disable (no global lock).
  AC-4 OPTIONAL      : renderCell 'configurable' / 'limited_*' amber pill /
                       fallback 'x' slate-300.
  AC-5 UNWANTED      : 409 self_strip_blocked / owner_protected →
                       formatBackendError JA msg / no langgraph / no XSS /
                       no hardcoded secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_TSX = (
    REPO_ROOT / "frontend" / "src" / "app" / "workspaces"
    / "[id]" / "members" / "page.tsx"
)
API_LIB = REPO_ROOT / "frontend" / "src" / "lib" / "workspace-api.ts"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


def _strip_js(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — page + 6 ROLE_KEYS + 7 cols + Lucide + eb-500 + no emoji
# ══════════════════════════════════════════════════════════════════════


def test_ac1_page_exists():
    assert PAGE_TSX.exists()


def test_ac1_workspace_api_lib_exists():
    assert API_LIB.exists()


def test_ac1_role_keys_six_canonical():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # ROLE_KEYS: RoleKey[] = ["owner", "ws_admin", "contributor", "viewer", "client", "monitor"];
    m = re.search(r"ROLE_KEYS\s*:\s*RoleKey\[\]\s*=\s*\[([^\]]+)\]", src)
    assert m, "ROLE_KEYS declaration not found"
    body = m.group(1)
    for role in ("owner", "ws_admin", "contributor", "viewer", "client", "monitor"):
        assert role in body, f"ROLE_KEYS missing {role}"


def test_ac1_summary_columns_at_least_seven():
    src = PAGE_TSX.read_text(encoding="utf-8")
    m = re.search(r"SUMMARY_COLUMNS\s*=\s*\[([\s\S]+?)\];", src)
    assert m, "SUMMARY_COLUMNS not found"
    body = m.group(1)
    # count `{ key: ...` entries
    entries = re.findall(r"\{\s*key:", body)
    assert len(entries) >= 7, f"SUMMARY_COLUMNS has {len(entries)} cols (need >= 7)"


def test_ac1_uses_lucide_react():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "lucide-react" in src
    # 必須 icon
    for icon in (
        "ShieldCheck", "Eye", "Hammer", "UserCog", "Briefcase",
        "Activity", "UserPlus", "Trash2", "Loader2", "Mail",
    ):
        assert icon in src, f"lucide icon missing: {icon}"


def test_ac1_uses_eb_500_primary_color():
    """CLAUDE.md §5.2: ENGINE BASE green (eb-500) を主色."""
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "bg-eb-500" in src or "bg-eb-600" in src


def test_ac1_no_emoji_in_page():
    """CLAUDE.md §5.1: Lucide-only (絵文字禁止)."""
    src = PAGE_TSX.read_text(encoding="utf-8")
    emoji = re.compile(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
    )
    hits = emoji.findall(src)
    assert not hits, f"emoji in members page: {hits}"


def test_ac1_fetch_permission_matrix_endpoint():
    src = API_LIB.read_text(encoding="utf-8")
    assert "/api/workspaces/permissions/matrix" in src
    assert re.search(
        r"export\s+async\s+function\s+fetchPermissionMatrix",
        src,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — PATCH / POST + invalidateQueries
# ══════════════════════════════════════════════════════════════════════


def test_ac2_update_member_role_uses_patch():
    src = API_LIB.read_text(encoding="utf-8")
    m = re.search(
        r"export\s+async\s+function\s+updateMemberRole[\s\S]+?(?=\nexport |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "method: \"PATCH\"" in body or "method: 'PATCH'" in body
    assert "/api/workspaces/" in body
    assert "/members/" in body
    assert "actor_user_id" in body


def test_ac2_add_member_uses_post():
    src = API_LIB.read_text(encoding="utf-8")
    m = re.search(
        r"export\s+async\s+function\s+addMember[\s\S]+?(?=\nexport |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "method: \"POST\"" in body or "method: 'POST'" in body
    assert "/api/workspaces/" in body
    assert "/members" in body


def test_ac2_page_invalidates_ws_members_query():
    """role / add / remove mutation の onSuccess で invalidateQueries(['ws-members', id])."""
    src = PAGE_TSX.read_text(encoding="utf-8")
    # invalidateQueries({ queryKey: ["ws-members", id] })
    matches = re.findall(
        r"invalidateQueries\(\s*\{\s*queryKey:\s*\[\s*\"ws-members\"",
        src,
    )
    assert len(matches) >= 2, (
        f"expected >= 2 invalidateQueries(ws-members), got {len(matches)}"
    )


def test_ac2_no_blocking_python_imports():
    """frontend に backend stdlib import が混入していない."""
    src = PAGE_TSX.read_text(encoding="utf-8")
    for bad in ("import time", "import requests"):
        assert bad not in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — loader + empty-state + per-row disable
# ══════════════════════════════════════════════════════════════════════


def test_ac3_loader_shown_while_loading():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "membersQ.isLoading" in src
    assert "Loader2" in src
    # 読み込み中… message
    assert re.search(r"読み込み中", src)


def test_ac3_empty_state_message():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # empty state Japanese msg
    assert re.search(r"メンバーがいません", src)


def test_ac3_per_row_saving_disable():
    """saving={roleMut.isPending && roleMut.variables?.userId === m.user_id}."""
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert re.search(
        r"roleMut\.variables\??\.userId\s*===\s*m\.user_id",
        src,
    )
    # MemberRow に saving prop が渡って disabled に使われる
    assert "disabled={saving}" in src


def test_ac3_no_langgraph_langchain_litellm():
    src = PAGE_TSX.read_text(encoding="utf-8").lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert bad not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — configurable / limited_ amber pill + fallback x
# ══════════════════════════════════════════════════════════════════════


def test_ac4_render_cell_function_exists():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert re.search(r"function\s+renderCell\s*\(", src)


def test_ac4_render_cell_handles_true_false():
    src = PAGE_TSX.read_text(encoding="utf-8")
    m = re.search(
        r"function\s+renderCell[\s\S]+?\n\}",
        src,
    )
    assert m
    body = m.group(0)
    assert "v === true" in body
    assert "v === false" in body or "false ||" in body
    # string variant → amber pill
    assert "amber" in body


def test_ac4_render_cell_string_replace_underscore():
    """'limited_by_tab' → 'limited by tab' display via replace(/_/g, ' ')."""
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert re.search(r"replace\(\s*/_/g\s*,\s*[\"'] [\"']\s*\)", src)


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — 409 codes mapped to JA msg / no XSS / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_format_backend_error_self_strip():
    src = PAGE_TSX.read_text(encoding="utf-8")
    m = re.search(
        r"function\s+formatBackendError[\s\S]+?\n\}",
        src,
    )
    assert m
    body = m.group(0)
    assert "self_strip_blocked" in body
    assert "owner_protected" in body
    # Japanese msg
    assert re.search(r"ブロック|降格|削除", body)


def test_ac5_no_dangerously_set_inner_html():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in src


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (PAGE_TSX, API_LIB):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


def test_ac5_no_inline_token_or_password():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # token= 'aaa...' / password = 'bbb...' 等が無い
    hardcoded = re.findall(
        r'(?:token|password|api_key)\s*[:=]\s*["\'][A-Za-z0-9_-]{20,}["\']',
        src,
        re.IGNORECASE,
    )
    assert not hardcoded, f"hardcoded credential: {hardcoded}"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_021_04_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-04"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_021_04_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-04"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert any("members/page.tsx" in f for f in files)
    assert any("workspace-api.ts" in f for f in files)


def test_tickets_t_021_04_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-04"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "ROLE_KEYS",
        "fetchPermissionMatrix",
        "updateMemberRole",
        "addMember",
        "lucide-react",
        "ShieldCheck",
        "Loader2",
        "ws-members",
        "self_strip_blocked",
        "owner_protected",
        "formatBackendError",
        "ADR-010",
    ):
        assert sym in full, f"T-021-04 AC missing: {sym}"
