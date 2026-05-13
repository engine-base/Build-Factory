"""T-007-03: task_dag_view (existing DependencyGraph.tsx REUSE wrapper).

TS module を Python から構造検証.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : TaskDagView.tsx 存在 / 既存 DependencyGraph.tsx 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : useMemo / onTaskClick / __testing__ で pure helpers export.
  AC-3 STATE-DRIVEN  : eb-* palette + Lucide / controlled / status normalize.
  AC-4 UNWANTED      : null/non-array tasks で empty fallback / invalid edges filter /
                       hardcoded color なし.
"""
from __future__ import annotations

import json as _json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DAG_VIEW = REPO_ROOT / "frontend" / "src" / "components" / "tasks" / "TaskDagView.tsx"
EXISTING_DG = REPO_ROOT / "frontend" / "src" / "components" / "dag" / "DependencyGraph.tsx"


@pytest.fixture(scope="module")
def src() -> str:
    return DAG_VIEW.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_dag_view_exists():
    assert DAG_VIEW.exists()


def test_ac1_existing_dependency_graph_unchanged():
    """既存 DependencyGraph.tsx に TaskDagView 依存なし (REUSE)."""
    assert EXISTING_DG.exists()
    src = EXISTING_DG.read_text(encoding="utf-8")
    assert "TaskDagView" not in src
    assert 'from "@/components/tasks/TaskDagView"' not in src


def test_ac1_imports_dependency_graph(src):
    """DependencyGraph を import している (REUSE)."""
    assert "DependencyGraph" in src
    assert 'from "@/components/dag/DependencyGraph"' in src


def test_ac1_required_exports(src):
    for name in (
        "TaskDagView",
        "DagTask",
        "DagDependency",
        "TaskDagViewProps",
        "normalizeStatus",
        "tasksToNodes",
        "dependenciesToEdges",
        "__testing__",
    ):
        assert name in src, f"missing export: {name}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_uses_useMemo(src):
    """tasks/dependencies の変換は useMemo で再計算."""
    assert "React.useMemo" in src


def test_ac2_uses_useCallback(src):
    """onNodeClick handler は useCallback で memoize."""
    assert "React.useCallback" in src


def test_ac2_locates_original_task(src):
    """node click 時に元 DagTask を id で逆引き."""
    assert "validTasks.find" in src
    assert "t.id === taskData.id" in src


def test_ac2_pure_helpers_exported_via_testing(src):
    assert "__testing__" in src
    for helper in ("normalizeStatus", "tasksToNodes",
                   "dependenciesToEdges", "VALID_STATUSES"):
        assert helper in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: eb-* + Lucide + controlled
# ══════════════════════════════════════════════════════════════════════


def test_ac3_eb_palette_color_used(src):
    """fallback message で eb-500 色使用."""
    assert "text-eb-500" in src


def test_ac3_lucide_icon_used(src):
    """Workflow icon (Lucide)."""
    assert 'from "lucide-react"' in src
    assert "Workflow" in src


def test_ac3_no_emoji_in_source():
    """source に絵文字 literal なし (lint-mock 経由)."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0


def test_ac3_status_normalization_logic(src):
    """unknown status → mapping rules."""
    assert 'review_needed' in src or '"review_needed"' in src
    assert "cancelled" in src
    assert "pending" in src
    # default fallback
    assert 'return "pending"' in src or "return 'pending'" in src


def test_ac3_no_internal_state(src):
    """controlled component (no useState for tasks)."""
    # useState で tasks を保持していない
    assert "useState<DagTask" not in src
    assert "useState<TaskNodeData" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_fallback(src):
    """tasks 空で fallback render."""
    assert 'data-testid="task-dag-empty"' in src
    assert "nodes.length === 0" in src


def test_ac4_array_isarray_safety(src):
    """null / non-array tasks で graceful."""
    assert "Array.isArray(tasks)" in src
    assert "Array.isArray(deps)" in src


def test_ac4_filters_invalid_task_id(src):
    """id が非 positive int の task は filter."""
    assert 'typeof t.id === "number"' in src
    assert "t.id > 0" in src


def test_ac4_filters_self_edge(src):
    """source==target edge は filter."""
    assert "d.source !== d.target" in src


def test_ac4_no_hardcoded_color_outside_eb(src):
    """eb-* 以外の hex literal なし."""
    code = _strip_comments(src)
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
    matches = [m for m in hex_pattern.findall(code) if m.lower() != "#1a6648"]
    assert not matches, f"non-eb hex: {matches}"


def test_ac4_no_secret_in_source(src):
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


def test_tickets_t_007_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-007-03"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-007-03",
        "While the existing implementation is in use",
        "If invalid input or unauthorized actor is detected during T-007-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-007-03 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "TaskDagView.tsx" in full
    assert "DependencyGraph" in full


def test_tickets_t_007_03_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-007-03"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert files and not any("TBD" in f for f in files)
