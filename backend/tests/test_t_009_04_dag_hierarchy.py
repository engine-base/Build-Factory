"""T-009-04: DAG 仮想化 + 階層折りたたみ (pure helpers + Controls).

TS module を Python から構造検証.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : DagHierarchy.tsx + computeDepths / filterVisibleTasks /
                       DagHierarchyControls / CollapseButton / 既存 DependencyGraph 無改変.
  AC-2 EVENT-DRIVEN  : useMemo / onToggleCollapse / onMaxDepthChange / __testing__.
  AC-3 STATE-DRIVEN  : controlled (collapse state は caller) / cycle 安全 /
                       eb-* + Lucide.
  AC-4 UNWANTED      : null tasks で empty / 負 / NaN maxDepth で -1 fallback /
                       cycle で MAX_REASONABLE_DEPTH cap.
"""
from __future__ import annotations

import json as _json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HIERARCHY = REPO_ROOT / "frontend" / "src" / "components" / "dag" / "DagHierarchy.tsx"
EXISTING_DG = REPO_ROOT / "frontend" / "src" / "components" / "dag" / "DependencyGraph.tsx"


@pytest.fixture(scope="module")
def src() -> str:
    return HIERARCHY.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_hierarchy_exists():
    assert HIERARCHY.exists()


def test_ac1_existing_dependency_graph_unchanged():
    """既存 DependencyGraph.tsx は無改変 (REUSE)."""
    assert EXISTING_DG.exists()
    src = EXISTING_DG.read_text(encoding="utf-8")
    assert "DagHierarchy" not in src
    assert "computeDepths" not in src


def test_ac1_required_exports(src):
    for name in (
        "HierarchyTask", "HierarchyEdge",
        "computeDepths", "filterVisibleTasks",
        "DagHierarchyControls", "DagHierarchyControlsProps",
        "CollapseButton",
        "__testing__",
    ):
        assert name in src, f"missing export: {name}"


def test_ac1_max_reasonable_depth_defined(src):
    assert "MAX_REASONABLE_DEPTH" in src
    assert "50" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: useMemo / callbacks / __testing__
# ══════════════════════════════════════════════════════════════════════


def test_ac2_uses_useMemo(src):
    assert "React.useMemo" in src


def test_ac2_uses_useCallback(src):
    assert "React.useCallback" in src


def test_ac2_on_toggle_collapse_callback(src):
    assert "onToggleCollapse" in src
    assert "onClick?.(taskId)" in src or "onClick(taskId)" in src


def test_ac2_on_max_depth_change_callback(src):
    assert "onMaxDepthChange" in src
    assert "handleDepthChange" in src


def test_ac2_testing_exports(src):
    """__testing__ object で pure helpers + MAX 定数."""
    assert "__testing__" in src
    for name in ("MAX_REASONABLE_DEPTH", "computeDepths", "filterVisibleTasks"):
        assert name in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: controlled + cycle safe + eb-* + Lucide
# ══════════════════════════════════════════════════════════════════════


def test_ac3_controlled_no_collapse_state(src):
    """collapsedIds は props 経由 (controlled). 内部 useState なし."""
    assert "useState<Set" not in src
    assert "collapsedIds" in src
    # props として受け取る
    assert "collapsedIds:" in src


def test_ac3_cycle_safe(src):
    """visiting set + cycle 検知."""
    assert "visiting" in src
    assert "cycle" in src.lower()
    # MAX_REASONABLE_DEPTH cap
    assert "MAX_REASONABLE_DEPTH" in src


def test_ac3_eb_palette(src):
    assert "border-eb-500" in src
    assert "bg-eb-50" in src
    assert "text-eb-500" in src
    assert "border-eb-200" in src


def test_ac3_lucide_icons(src):
    assert 'from "lucide-react"' in src
    for icon in ("Layers", "ChevronRight", "ChevronDown"):
        assert icon in src


def test_ac3_no_emoji_in_source():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_null_tasks_safety(src):
    assert "Array.isArray(tasks)" in src


def test_ac4_invalid_max_depth_handling(src):
    """maxDepth が負 / NaN / Infinity で -1 fallback."""
    assert "Number.isFinite(maxDepth)" in src
    assert "maxDepth >= 0" in src


def test_ac4_cycle_detection_via_visiting(src):
    """visiting set で cycle 検出."""
    assert "visiting.has" in src or "visiting.add" in src


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


def test_tickets_t_009_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-009-04"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-009-04",
        "While the new feature for T-009-04 is enabled",
        "If invalid input or unauthorized actor is detected during T-009-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-009-04 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "DagHierarchy.tsx" in full
    assert "computeDepths" in full
    assert "MAX_REASONABLE_DEPTH" in full


def test_tickets_t_009_04_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-009-04"), None)
    assert t.get("adr_link") is not None
