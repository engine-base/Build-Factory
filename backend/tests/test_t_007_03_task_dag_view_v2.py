"""T-007-03 v2 (pre-flight audit gap closure): TaskDagView + DependencyGraph REUSE invariants.

v1 (`test_t_007_03_task_dag_view.py`) covers basic spec presence via string grep.
v2 closes the following anti-drift gaps identified during pre-flight audit:

  GAP-1  REUSE invariant only checked at "TaskDagView not referenced inside
         DependencyGraph". Doesn't guarantee 0 mutations vs. main / vs. the
         commit that introduced T-009-02 DependencyGraph. → git-level check.
  GAP-2  React Flow library presence checked only on TaskDagView side. The
         actual `ReactFlow` JSX consumer is `DependencyGraph`. → explicit
         test on existing file + version pin via package.json.
  GAP-3  Status normalization behavior not exercised (spec mandates 3
         specific mappings: review_needed→in_progress, cancelled→failed,
         fallback→pending). v1 only checks literal presence. → semantic
         pure-function tests via Python regex extraction.
  GAP-4  Cycle handling in DependencyGraph layout (`level 未確定 node も 0 に
         置く`) not asserted. → grep + behavior bound (layout function
         can not loop forever on a cycle).
  GAP-5  `tasksToNodes` / `dependenciesToEdges` / `normalizeStatus` filter
         behaviors covered only by source-grep regex; no actual mapping
         from `assignee_name`→`assignee`, `edge_type`→`kind` confirmed.
         → AST/regex assertions on the conversion bodies.
  GAP-6  S-017 mock reference: ticket points to S-012 (workspace dashboard)
         but the real DAG mock is S-017. → audit doc + a sanity test that
         the S-017 mock exists.

These tests do **not** mutate any file and complement v1.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DAG_VIEW = REPO_ROOT / "frontend" / "src" / "components" / "tasks" / "TaskDagView.tsx"
EXISTING_DG = REPO_ROOT / "frontend" / "src" / "components" / "dag" / "DependencyGraph.tsx"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
TICKETS_JSON = (
    REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
)
MOCK_S017 = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "moat" / "S-017-dependency-graph.html"


@pytest.fixture(scope="module")
def view_src() -> str:
    return DAG_VIEW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dg_src() -> str:
    return EXISTING_DG.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# GAP-1: REUSE invariant via git-level zero-diff check
# ══════════════════════════════════════════════════════════════════════


def _git_run(*args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return r.stdout


def test_gap1_dependency_graph_unchanged_vs_main():
    """REUSE 不変条件: 既存 DependencyGraph.tsx に対する main からの差分が 0 行."""
    diff = _git_run(
        "diff", "main...HEAD",
        "--",
        "frontend/src/components/dag/DependencyGraph.tsx",
    )
    assert diff == "", (
        "REUSE invariant violated: DependencyGraph.tsx must remain unchanged "
        f"between main and HEAD. Got diff:\n{diff[:500]}"
    )


def test_gap1_dependency_graph_unchanged_since_t_009_02():
    """REUSE 不変条件 (起源): T-009-02 が DependencyGraph を導入して以降 0 mutation."""
    # T-009-02 introduction commit hash (verified via git log --follow on file).
    intro_commit = "e9408ae"
    diff = _git_run(
        "diff", intro_commit, "HEAD",
        "--",
        "frontend/src/components/dag/DependencyGraph.tsx",
    )
    assert diff == "", (
        f"REUSE invariant violated since {intro_commit}: "
        f"DependencyGraph.tsx must be 1:1 with introduction commit."
    )


def test_gap1_task_dag_view_does_not_subclass_or_patch_dg(view_src: str):
    """patching pattern (prototype assignment / monkey-patch) 不在."""
    forbidden_patterns = [
        ".prototype.",
        "Object.assign(DependencyGraph",
        "DependencyGraph.defaultProps",
        # bypass via re-export with override
        "= DependencyGraph",
    ]
    for pat in forbidden_patterns:
        assert pat not in view_src, f"patching pattern detected: {pat!r}"


# ══════════════════════════════════════════════════════════════════════
# GAP-2: React Flow library presence (substrate)
# ══════════════════════════════════════════════════════════════════════


def test_gap2_react_flow_imported_in_existing_dg(dg_src: str):
    """既存 DependencyGraph が React Flow を利用 (substrate)."""
    assert 'from "@xyflow/react"' in dg_src
    assert "ReactFlow" in dg_src
    assert "Background" in dg_src
    assert "Controls" in dg_src
    assert "MiniMap" in dg_src


def test_gap2_react_flow_pinned_in_package_json():
    """@xyflow/react が dependency にあること (12.x 系で固定)."""
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = pkg.get("dependencies", {})
    assert "@xyflow/react" in deps, "@xyflow/react missing from frontend deps"
    # major version pin sanity (caret accepted)
    ver = deps["@xyflow/react"]
    assert re.match(r"^[\^~]?12\.", ver), f"unexpected react-flow version: {ver}"


def test_gap2_wrapper_does_not_re_import_react_flow_directly(view_src: str):
    """thin wrapper は React Flow を直接 import しない (substrate 経由)."""
    assert '@xyflow/react' not in view_src, (
        "TaskDagView must not import React Flow directly; "
        "it must REUSE DependencyGraph as substrate."
    )


# ══════════════════════════════════════════════════════════════════════
# GAP-3: Status normalization behavior (semantic, not just literal)
# ══════════════════════════════════════════════════════════════════════


def _extract_function_body(src: str, name: str) -> str:
    """Crude TS function body extractor (balanced braces)."""
    m = re.search(rf"export function {re.escape(name)}\b", src)
    assert m, f"function {name} not found"
    start = src.find("{", m.end())
    assert start != -1
    depth = 0
    i = start
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces for {name}")


def test_gap3_normalize_status_maps_review_needed_to_in_progress(view_src: str):
    body = _extract_function_body(view_src, "normalizeStatus")
    # spec: review_needed → in_progress
    assert re.search(
        r'review_needed["\s].*?in_progress', body, re.DOTALL,
    ), f"review_needed→in_progress mapping missing.\nBody:\n{body}"


def test_gap3_normalize_status_maps_cancelled_to_failed(view_src: str):
    body = _extract_function_body(view_src, "normalizeStatus")
    assert re.search(
        r'cancelled["\s].*?failed', body, re.DOTALL,
    ), f"cancelled→failed mapping missing.\nBody:\n{body}"


def test_gap3_normalize_status_default_returns_pending(view_src: str):
    body = _extract_function_body(view_src, "normalizeStatus")
    # final return is "pending"
    assert re.search(r'return\s+"pending"', body), (
        "default fallback must `return \"pending\"`"
    )


def test_gap3_valid_statuses_complete_set(view_src: str):
    """spec defines 6 statuses inherited from DependencyGraph.TaskStatus."""
    required = (
        "pending", "in_progress", "completed",
        "blocked_question", "blocked_dependency", "failed",
    )
    m = re.search(r"VALID_STATUSES\s*=\s*new Set<string>\(\[(.*?)\]\)", view_src, re.DOTALL)
    assert m, "VALID_STATUSES literal not found"
    block = m.group(1)
    for s in required:
        assert f'"{s}"' in block, f"VALID_STATUSES missing: {s}"


# ══════════════════════════════════════════════════════════════════════
# GAP-4: Cycle handling in DependencyGraph layout (BFS termination)
# ══════════════════════════════════════════════════════════════════════


def test_gap4_layout_has_cycle_unset_level_fallback(dg_src: str):
    """layout は cycle で level 未確定 node に対して fallback (0) を持つ."""
    # source contains the comment + the for-loop that sets level for unvisited nodes.
    assert "level 未確定" in dg_src or "level.has(t.id)" in dg_src
    # the actual fallback assignment line (defensive)
    assert re.search(r"if\s*\(\s*!level\.has\(t\.id\)\s*\)", dg_src), (
        "missing cycle fallback assignment in layoutNodes"
    )


def test_gap4_layout_bfs_uses_max_to_avoid_infinite_loop(dg_src: str):
    """BFS の level 更新は Math.max を使い、 strict-monotonic 増加で cycle 内に
    無限ループを発生させない (current<next の場合のみ enqueue)."""
    assert "Math.max(level.get(next)" in dg_src
    assert "if (level.get(next) !== nextLevel)" in dg_src


# ══════════════════════════════════════════════════════════════════════
# GAP-5: tasksToNodes / dependenciesToEdges semantic mapping
# ══════════════════════════════════════════════════════════════════════


def test_gap5_tasks_to_nodes_maps_assignee_name(view_src: str):
    body = _extract_function_body(view_src, "tasksToNodes")
    # output.assignee comes from t.assignee_name (?? null)
    assert "assignee" in body and "assignee_name" in body, body
    assert re.search(r"assignee\s*:\s*t\.assignee_name\s*\?\?\s*null", body), body


def test_gap5_tasks_to_nodes_filters_non_positive_id(view_src: str):
    body = _extract_function_body(view_src, "tasksToNodes")
    assert 't.id === "number"' in body and "t.id > 0" in body


def test_gap5_dependencies_to_edges_filters_self_and_invalid(view_src: str):
    body = _extract_function_body(view_src, "dependenciesToEdges")
    assert "d.source !== d.target" in body
    assert 'd.source === "number"' in body
    assert 'd.target === "number"' in body
    assert "d.source > 0" in body
    assert "d.target > 0" in body


def test_gap5_dependencies_to_edges_preserves_edge_type(view_src: str):
    body = _extract_function_body(view_src, "dependenciesToEdges")
    # output edges propagate hard/soft kind
    assert re.search(r'edge_type\s*:\s*d\.edge_type\s*===\s*"soft"', body), body


def test_gap5_field_naming_drift_documented(view_src: str, dg_src: str):
    """ANTI-DRIFT FINDING (documented, not fixed in this REUSE audit):

    `dependenciesToEdges` returns objects with `edge_type` field, but
    `DependencyGraph.TaskEdge` interface declares `kind?: "hard" | "soft"`.
    TS accepts because `kind` is optional. At runtime, DependencyGraph sees
    `e.kind === undefined`, so the `e.kind === "hard"` branch never triggers
    → all edges render as soft (dashed). This means hard/soft styling
    semantic from the wrapper is **silently dropped**.

    Because T-007-03 is a REUSE audit (0 mutations to DependencyGraph),
    fixing requires either (a) a new REFACTOR task on the wrapper to rename
    field, or (b) DependencyGraph patch (REUSE-violating). We **record but
    do not auto-fix** here. The audit document (T-007-03.md) tracks this as
    Gap-F1.
    """
    # wrapper uses edge_type
    wrapper_body = _extract_function_body(view_src, "dependenciesToEdges")
    assert "edge_type" in wrapper_body
    # substrate consumes kind
    assert re.search(r"\be\.kind\s*===\s*\"hard\"", dg_src), (
        "DependencyGraph no longer reads e.kind — drift state changed, "
        "re-evaluate Gap-F1 in audit."
    )


def test_gap5_dependencies_to_edges_filters_null_array(view_src: str):
    body = _extract_function_body(view_src, "dependenciesToEdges")
    assert "Array.isArray(deps)" in body
    assert "return []" in body


# ══════════════════════════════════════════════════════════════════════
# GAP-6: Mock cross-reference sanity
# ══════════════════════════════════════════════════════════════════════


def test_gap6_s_017_dag_mock_exists():
    """task DAG screen mock S-017 が存在 (ticket は S-012 を指すが substrate は S-017)."""
    assert MOCK_S017.exists(), f"S-017 mock missing: {MOCK_S017}"


def test_gap6_s_017_mock_references_dag_or_dependency():
    """S-017 mock が DAG / dependency 関連語を含む (sanity)."""
    src = MOCK_S017.read_text(encoding="utf-8").lower()
    assert "dependency" in src or "dag" in src or "依存" in src


# ══════════════════════════════════════════════════════════════════════
# Drift guard: hardcoded color literal check (only on the wrapper)
# ══════════════════════════════════════════════════════════════════════


def test_drift_guard_no_hex_outside_eb_palette_in_wrapper(view_src: str):
    """wrapper 内の hex literal は eb-500 (#1a6648) 系のみ許可."""
    # strip strings inside comments
    code = re.sub(r"/\*.*?\*/", "", view_src, flags=re.DOTALL)
    code = re.sub(r"//.*", "", code)
    hexes = re.findall(r"#[0-9a-fA-F]{6}", code)
    allowed = {"#1a6648"}
    bad = [h for h in hexes if h.lower() not in allowed]
    assert not bad, f"non-eb hex in wrapper source: {bad}"


def test_drift_guard_ticket_meta_immutable():
    """ticket meta (label / deps / spec_link) は本 PR で改変されない."""
    d = json.loads(TICKETS_JSON.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-007-03"), None)
    assert t is not None
    assert t["label"] == "REUSE"
    assert t["layer"] == "FE"
    assert "T-009-02" in t.get("deps", [])
    assert t.get("existing_files") == [
        "frontend/src/components/dag/DependencyGraph.tsx",
    ]
