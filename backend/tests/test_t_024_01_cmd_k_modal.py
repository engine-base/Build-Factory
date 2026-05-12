"""T-024-01: Cmd+K UI modal (cmdk + shadcn/ui Dialog).

TS module を Python から構造検証.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : command.tsx (shadcn wrapper) + CommandKModal.tsx (modal) /
                       cmdk dep 既存活用 (REUSE).
  AC-2 EVENT-DRIVEN  : Cmd+K (macOS) / Ctrl+K (others) で open / Escape で close /
                       __testing__ で pure helpers export.
  AC-3 STATE-DRIVEN  : focus trap (Dialog default) / eb-* palette / Lucide icons /
                       絵文字なし / unmount で keydown listener detach.
  AC-4 UNWANTED      : null/non-array items で empty / disableGlobalShortcut で
                       binding なし / eb-* 外の hex なし.
"""
from __future__ import annotations

import json as _json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_UI = REPO_ROOT / "frontend" / "src" / "components" / "ui" / "command.tsx"
MODAL = REPO_ROOT / "frontend" / "src" / "components" / "global" / "CommandKModal.tsx"
EXISTING_DIALOG = REPO_ROOT / "frontend" / "src" / "components" / "ui" / "dialog.tsx"


@pytest.fixture(scope="module")
def modal_src() -> str:
    return MODAL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def command_src() -> str:
    return COMMAND_UI.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_command_ui_exists():
    assert COMMAND_UI.exists()


def test_ac1_modal_exists():
    assert MODAL.exists()


def test_ac1_command_ui_exports_required(command_src):
    """shadcn-style 7 exports."""
    for name in (
        "Command", "CommandInput", "CommandList", "CommandEmpty",
        "CommandGroup", "CommandItem", "CommandSeparator",
    ):
        assert f"export const {name}" in command_src, f"missing export: {name}"


def test_ac1_modal_exports_required(modal_src):
    for name in ("CommandKModal", "CommandKItem", "CommandKModalProps", "__testing__"):
        assert name in modal_src, f"missing export: {name}"


def test_ac1_uses_cmdk_dep(command_src):
    assert 'from "cmdk"' in command_src


def test_ac1_cmdk_dep_in_package_json():
    pkg = _json.loads(
        (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    assert "cmdk" in pkg["dependencies"]


def test_ac1_reuses_existing_dialog(modal_src):
    """既存 dialog.tsx を import (REUSE)."""
    assert EXISTING_DIALOG.exists()
    assert 'from "@/components/ui/dialog"' in modal_src
    assert "Dialog" in modal_src
    assert "DialogContent" in modal_src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: keyboard + onSelect + __testing__
# ══════════════════════════════════════════════════════════════════════


def test_ac2_global_cmd_k_binding(modal_src):
    """Cmd+K / Ctrl+K detection logic."""
    assert "isCommandKEvent" in modal_src
    assert "metaKey" in modal_src
    assert "ctrlKey" in modal_src
    assert '"k"' in modal_src or '"K"' in modal_src


def test_ac2_window_keydown_listener(modal_src):
    """window.addEventListener('keydown') + removeEventListener."""
    assert 'addEventListener("keydown"' in modal_src
    assert 'removeEventListener("keydown"' in modal_src


def test_ac2_prevent_default(modal_src):
    """Cmd+K で preventDefault (browser default 阻止)."""
    assert "preventDefault" in modal_src


def test_ac2_testing_exports(modal_src):
    """__testing__ object で pure helpers export."""
    assert "__testing__" in modal_src
    assert "isCommandKEvent" in modal_src
    assert "groupItems" in modal_src


def test_ac2_on_select_callback(modal_src):
    """onSelect callback + item.onSelect."""
    assert "item.onSelect" in modal_src
    assert "onSelect?.(item)" in modal_src or "onSelect(item)" in modal_src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: focus trap + eb-* + Lucide + 絵文字なし
# ══════════════════════════════════════════════════════════════════════


def test_ac3_uses_dialog_for_focus_trap(modal_src):
    """shadcn/ui Dialog (Radix) が focus trap を提供."""
    assert "<Dialog" in modal_src
    assert "DialogContent" in modal_src


def test_ac3_aria_role_dialog(modal_src):
    """role='dialog' + aria-label."""
    assert 'role="dialog"' in modal_src
    assert "aria-label" in modal_src


def test_ac3_uses_eb_palette_only(command_src, modal_src):
    """border / bg / text は eb-* class のみ."""
    for src in (command_src, modal_src):
        assert "eb-" in src, "eb-* palette missing"
    # 主要 eb-* class
    assert "border-eb-500" in modal_src
    assert "border-eb-200" in command_src
    assert "text-eb-500" in command_src or "text-eb-500" in modal_src


def test_ac3_no_hardcoded_color_outside_eb(command_src, modal_src):
    """eb-* 以外の hex literal なし."""
    code1 = _strip_comments(command_src)
    code2 = _strip_comments(modal_src)
    for code in (code1, code2):
        hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
        matches = [m for m in hex_pattern.findall(code) if m.lower() != "#1a6648"]
        assert not matches, f"non-eb hex: {matches}"


def test_ac3_lucide_icons_only(command_src, modal_src):
    for src in (command_src, modal_src):
        assert 'from "lucide-react"' in src
        assert "Search" in src


def test_ac3_no_emoji_in_source():
    """source に絵文字 literal なし (lint script)."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"emoji baseline broken: {r.stdout}"


def test_ac3_keydown_listener_cleanup(modal_src):
    """useEffect cleanup で removeEventListener."""
    # cleanup function pattern
    assert "return () =>" in modal_src
    # or similar removal pattern
    assert "removeEventListener" in modal_src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_null_items_safety(modal_src):
    """null / non-array items で graceful."""
    assert "Array.isArray(items)" in modal_src


def test_ac4_empty_items_fallback(modal_src):
    """items 空で CommandEmpty 表示."""
    assert "validItems.length === 0" in modal_src
    assert "CommandEmpty" in modal_src


def test_ac4_disable_global_shortcut_flag(modal_src):
    """disableGlobalShortcut=true で keydown listener attach せず."""
    assert "disableGlobalShortcut" in modal_src
    # if (disableGlobalShortcut) return; pattern
    assert "if (disableGlobalShortcut)" in modal_src


def test_ac4_no_secret_in_source(command_src, modal_src):
    for src in (command_src, modal_src):
        code = _strip_comments(src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
        assert "SUPABASE_SERVICE_KEY" not in code
        assert "Bearer " not in code


def _strip_comments(src: str) -> str:
    out_lines = []
    in_block = False
    for raw in src.splitlines():
        line = raw
        if in_block:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block = False
            else:
                continue
        if "/*" in line:
            before, _, after = line.partition("/*")
            if "*/" in after:
                line = before + after.split("*/", 1)[1]
            else:
                line = before
                in_block = True
        if "//" in line:
            idx = line.find("//")
            if idx > 0 and line[idx - 1] != ":":
                line = line[:idx]
            elif idx == 0:
                line = ""
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_024_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-01"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-024-01",
        "While the new feature for T-024-01 is enabled",
        "If invalid input or unauthorized actor is detected during T-024-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-024-01 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "CommandKModal" in full
    assert "command.tsx" in full
    assert "cmdk" in full


def test_tickets_t_024_01_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-01"), None)
    assert t.get("adr_link") is not None
