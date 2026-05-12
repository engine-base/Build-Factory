"""T-007-04: 仮想スクロール VirtualList (react-window wrapper).

TS module を Python から構造検証.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : VirtualList.tsx + 4 normalizers + 4 constants /
                       react-window dep / @types/react-window devDep.
  AC-2 EVENT-DRIVEN  : useMemo / onScroll callback / renderItem call /
                       data-testid='vlist-row-{index}'.
  AC-3 STATE-DRIVEN  : react-window 内蔵 virtualization / eb-* palette /
                       Lucide Inbox icon / controlled (items props).
  AC-4 UNWANTED      : null items で empty / invalid itemSize/height で default fallback /
                       MAX cap / hardcoded color/secret なし.
"""
from __future__ import annotations

import json as _json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMP = REPO_ROOT / "frontend" / "src" / "components" / "common" / "VirtualList.tsx"


@pytest.fixture(scope="module")
def src() -> str:
    return COMP.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_component_exists():
    assert COMP.exists()


def test_ac1_required_exports(src):
    for name in (
        "VirtualList", "VirtualListProps",
        "DEFAULT_ITEM_SIZE", "DEFAULT_HEIGHT",
        "DEFAULT_OVERSCAN_COUNT", "MAX_REASONABLE_ITEM_SIZE",
        "normalizeItemSize", "normalizeHeight", "normalizeOverscan",
        "__testing__",
    ):
        assert name in src, f"missing export: {name}"


def test_ac1_constants_correct_values(src):
    """DEFAULT 値が docstring と一致."""
    assert "DEFAULT_ITEM_SIZE = 48" in src
    assert "DEFAULT_HEIGHT = 480" in src
    assert "DEFAULT_OVERSCAN_COUNT = 5" in src
    assert "MAX_REASONABLE_ITEM_SIZE = 1000" in src


def test_ac1_uses_react_window(src):
    assert 'from "react-window"' in src
    assert "FixedSizeList" in src


def test_ac1_react_window_dep_added():
    pkg = _json.loads(
        (REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    assert "react-window" in pkg["dependencies"]
    assert "@types/react-window" in pkg["devDependencies"]


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_uses_useMemo(src):
    assert "React.useMemo" in src


def test_ac2_uses_useCallback(src):
    assert "React.useCallback" in src


def test_ac2_on_scroll_callback(src):
    assert "onScroll" in src
    assert "scrollOffset" in src


def test_ac2_renderItem_invocation(src):
    assert "renderItem(item, index)" in src


def test_ac2_row_test_id(src):
    """各 row が data-testid='vlist-row-{index}'."""
    assert "vlist-row-" in src
    assert "data-testid={`vlist-row-${index}`}" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_uses_react_window_virtualization(src):
    """FixedSizeList が built-in virtualization を提供."""
    assert "<FixedSizeList" in src
    assert "itemCount" in src
    assert "overscanCount" in src


def test_ac3_eb_palette_only(src):
    assert "border-eb-200" in src
    assert "text-eb-500" in src


def test_ac3_lucide_icon_inbox(src):
    assert 'from "lucide-react"' in src
    assert "Inbox" in src


def test_ac3_no_emoji_in_source():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0


def test_ac3_no_internal_items_state(src):
    """items は props のみ (controlled)."""
    assert "useState<T[]" not in src
    assert "useState<T>" not in src or "useState<T>(items" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_array_isarray_safety(src):
    """items が null/non-array で fallback."""
    assert "Array.isArray(items)" in src


def test_ac4_empty_fallback(src):
    assert 'data-testid="vlist-empty"' in src
    assert "validItems.length === 0" in src


def test_ac4_invalid_itemSize_fallback(src):
    """itemSize <= 0 / NaN で DEFAULT fallback."""
    assert "Number.isFinite(value)" in src
    assert "value <= 0" in src or "value < 0" in src
    assert "DEFAULT_ITEM_SIZE" in src


def test_ac4_max_cap_for_itemSize(src):
    """itemSize > MAX_REASONABLE で DEFAULT fallback."""
    assert "MAX_REASONABLE_ITEM_SIZE" in src
    assert "value > MAX_REASONABLE_ITEM_SIZE" in src


def test_ac4_normalize_overscan_non_negative(src):
    """overscanCount < 0 で 0 fallback."""
    assert "value < 0" in src
    assert "return 0" in src


def test_ac4_no_hardcoded_color_outside_eb(src):
    code = _strip_comments(src)
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
    matches = [m for m in hex_pattern.findall(code) if m.lower() != "#1a6648"]
    assert not matches


def test_ac4_no_secret(src):
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


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


def test_tickets_t_007_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-007-04"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-007-04",
        "While the new feature for T-007-04 is enabled",
        "If invalid input or unauthorized actor is detected during T-007-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-007-04 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "VirtualList.tsx" in full
    assert "react-window" in full
    assert "DEFAULT_ITEM_SIZE" in full or "DEFAULT_HEIGHT" in full


def test_tickets_t_007_04_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-007-04"), None)
    assert t.get("adr_link") is not None
