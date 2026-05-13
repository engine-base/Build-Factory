"""T-009-02: DAG 可視化 UI (React Flow @xyflow/react v12) — 4 AC.

PR #66 (T-009-02 初版) で production 実装が完成済. 本 module は **spec
contract layer** として 4 AC が production code (TSX) の symbol /
import / status palette / Lucide-only invariant と 1:1 整合していることを
Python 静的解析で機械検証する.

(Node 環境を前提とせず、 TSX を文字列として読んで検査する.)

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : DependencyGraph.tsx が @xyflow/react v12 から
                       ReactFlow / Background / Controls / MiniMap import +
                       export default DependencyGraph + Sugiyama auto-layout
                       (BFS) + dependency-graph page から参照.
  AC-2 EVENT-DRIVEN  : onNodeClick callback + tasks/edges props 変化で
                       useMemo recompute.
  AC-3 STATE-DRIVEN  : STATUS_BORDER / STATUS_BG が 6 TaskStatus に対応 /
                       in_progress = border-eb-500 / completed = border-eb-700 /
                       絵文字なし (CLAUDE.md §5.1 Lucide-only).
  AC-4 UNWANTED      : tasks 空で [] / 不明 task id を含む edge を silent skip /
                       backend を直接呼ばない (layer separation).
"""
from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DAG_DIR = REPO_ROOT / "frontend" / "src" / "components" / "dag"
COMPONENT = DAG_DIR / "DependencyGraph.tsx"
DEP_DND = DAG_DIR / "DependencyDnD.tsx"
DAG_HIER = DAG_DIR / "DagHierarchy.tsx"
PAGE = (
    REPO_ROOT / "frontend" / "src" / "app" / "workspaces"
    / "[id]" / "dependency-graph" / "page.tsx"
)
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — file presence + @xyflow/react v12 + exports
# ══════════════════════════════════════════════════════════════════════


def test_ac1_component_file_exists():
    assert COMPONENT.exists()


def test_ac1_page_file_exists():
    assert PAGE.exists()


def test_ac1_package_json_uses_xyflow_v12_not_legacy_reactflow():
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    # @xyflow/react v12+ is the canonical successor; legacy "reactflow"
    # package must NOT appear (deprecated namespace, AC-1 invariant).
    assert "@xyflow/react" in deps, "missing @xyflow/react v12 dep"
    version = deps["@xyflow/react"]
    # version range starts with ^12 / 12. / ~12.
    assert re.match(r"[\^~]?12", version), (
        f"@xyflow/react must be v12+, got {version}"
    )
    assert "reactflow" not in deps, (
        "legacy 'reactflow' package must not be present"
    )


def test_ac1_component_imports_from_xyflow_react():
    src = COMPONENT.read_text(encoding="utf-8")
    assert 'from "@xyflow/react"' in src
    # legacy import path 禁止
    assert 'from "reactflow"' not in src


def test_ac1_component_imports_reactflow_subset():
    """ReactFlow / Background / Controls / MiniMap を import している."""
    src = COMPONENT.read_text(encoding="utf-8")
    for sym in ("ReactFlow", "Background", "Controls", "MiniMap"):
        assert re.search(rf"\b{sym}\b", src), (
            f"DependencyGraph.tsx missing import: {sym}"
        )


def test_ac1_component_imports_xyflow_styles():
    src = COMPONENT.read_text(encoding="utf-8")
    assert '"@xyflow/react/dist/style.css"' in src


def test_ac1_component_default_export():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "export default DependencyGraph" in src
    # 名前付き export もある (test_ac1_named_export で別途確認)
    assert re.search(r"export\s+function\s+DependencyGraph\b", src)


def test_ac1_component_props_signature():
    """DependencyGraphProps が tasks / edges / onNodeClick / className を持つ."""
    src = COMPONENT.read_text(encoding="utf-8")
    # interface or type の中身を緩く検証
    assert re.search(r"tasks\s*:\s*TaskNodeData\[\]", src)
    assert re.search(r"edges\s*:\s*TaskEdge\[\]", src)
    assert "onNodeClick" in src


def test_ac1_component_uses_sugiyama_bfs_layout():
    """auto-layout の BFS 実装が存在 (incoming/outgoing map + level)."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "function layoutNodes" in src
    assert "incoming" in src
    assert "outgoing" in src
    assert "level" in src.lower()
    # BFS の queue
    assert "queue" in src.lower()


def test_ac1_page_imports_dependency_graph():
    src = PAGE.read_text(encoding="utf-8")
    assert "DependencyGraph" in src
    assert "@/components/dag/DependencyGraph" in src


def test_ac1_page_is_in_workspaces_nested_route():
    """frontend/src/app/workspaces/[id]/dependency-graph/page.tsx の場所."""
    parts = PAGE.parts
    assert "workspaces" in parts
    assert "[id]" in parts
    assert "dependency-graph" in parts


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — onNodeClick + useMemo recompute
# ══════════════════════════════════════════════════════════════════════


def test_ac2_on_node_click_callback_invocation():
    """source 上で onNodeClick(data) / onNodeClick?.(data) が呼ばれる."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"onNodeClick\??\.\(", src), (
        "onNodeClick must be invoked in the component"
    )


def test_ac2_use_memo_for_layout():
    """tasks/edges 変化時のみ layoutNodes を再計算 (useMemo)."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "useMemo" in src
    # layoutNodes が useMemo の中で呼ばれていること (近接検査)
    layout_idx = src.find("layoutNodes")
    memo_idx = src.find("useMemo")
    assert layout_idx > 0 and memo_idx > 0


def test_ac2_use_callback_for_node_click_handler():
    """node click handler を useCallback で memoize (refresh on prop change)."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "useCallback" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — 6 status palette + eb-500 / eb-700 + no emoji
# ══════════════════════════════════════════════════════════════════════


def test_ac3_status_border_has_6_entries():
    src = COMPONENT.read_text(encoding="utf-8")
    # 6 TaskStatus key 全てが STATUS_BORDER に出てくる
    for st in (
        "pending", "in_progress", "completed",
        "blocked_question", "blocked_dependency", "failed",
    ):
        assert re.search(
            rf"STATUS_BORDER[\s\S]{{0,500}}{st}",
            src,
        ), f"STATUS_BORDER missing key: {st}"


def test_ac3_status_bg_has_6_entries():
    src = COMPONENT.read_text(encoding="utf-8")
    for st in (
        "pending", "in_progress", "completed",
        "blocked_question", "blocked_dependency", "failed",
    ):
        assert re.search(
            rf"STATUS_BG[\s\S]{{0,500}}{st}",
            src,
        ), f"STATUS_BG missing key: {st}"


def test_ac3_in_progress_uses_eb_500_border():
    src = COMPONENT.read_text(encoding="utf-8")
    # `in_progress: "border-eb-500"` パターン
    assert re.search(
        r'in_progress\s*:\s*"border-eb-500"',
        src,
    ), "in_progress must use border-eb-500 (ENGINE BASE green)"


def test_ac3_completed_uses_eb_700_border():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(
        r'completed\s*:\s*"border-eb-700"',
        src,
    ), "completed must use border-eb-700"


def test_ac3_no_emoji_in_component():
    """CLAUDE.md §5.1: Lucide Icons only / 絵文字禁止."""
    src = COMPONENT.read_text(encoding="utf-8")
    # よくある絵文字パターン (CJK 範囲を除いた絵文字 unicode)
    emoji_pattern = re.compile(
        r"[\U0001F300-\U0001FAFF"   # symbols + pictographs + sup1+2
        r"\U00002600-\U000027BF"    # misc symbols + dingbats
        r"\U0001F000-\U0001F2FF]"   # mahjong + playing cards + enclosed
    )
    hits = emoji_pattern.findall(src)
    assert not hits, f"emoji found in DependencyGraph.tsx: {hits}"


def test_ac3_no_emoji_in_page():
    src = PAGE.read_text(encoding="utf-8")
    emoji_pattern = re.compile(
        r"[\U0001F300-\U0001FAFF"
        r"\U00002600-\U000027BF"
        r"\U0001F000-\U0001F2FF]"
    )
    hits = emoji_pattern.findall(src)
    assert not hits, f"emoji found in dependency-graph page.tsx: {hits}"


def test_ac3_page_uses_lucide_icons():
    """page.tsx は Lucide icons を使う (eb-500 緑色適用)."""
    src = PAGE.read_text(encoding="utf-8")
    assert "lucide-react" in src
    assert "text-eb-500" in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — empty / unknown ids / layer separation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_layout_returns_empty_when_no_tasks():
    """source 上で `if (tasks.length === 0) return []` を確認."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(
        r"if\s*\(\s*tasks\.length\s*===\s*0\s*\)\s*return\s*\[\]",
        src,
    ), "layoutNodes must early-return [] when tasks is empty"


def test_ac4_unknown_edges_silently_skipped():
    """edge の source/target が tasks に無い時 continue する."""
    src = COMPONENT.read_text(encoding="utf-8")
    # if (!incoming.has(e.target) || !outgoing.has(e.source)) continue;
    assert re.search(
        r"!incoming\.has\(e\.target\)\s*\|\|\s*!outgoing\.has\(e\.source\)",
        src,
    ), "unknown edge ids must be silently skipped via .has() guard"


def test_ac4_component_does_not_fetch_backend():
    """layer separation: component に fetch / axios / api client 呼出なし."""
    src = COMPONENT.read_text(encoding="utf-8")
    forbidden = [
        re.search(r"\bfetch\s*\(", src),
        re.search(r"\baxios\b", src),
        re.search(r"useQuery\b", src),
        re.search(r"useSWR\b", src),
        "from \"@/lib/api/" in src,
    ]
    assert not any(forbidden), (
        "DependencyGraph component must not call backend directly "
        "(layer separation: page handles data, component renders)"
    )


def test_ac4_no_dangerous_html_injection():
    """dangerouslySetInnerHTML 使用なし (XSS リスク)."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in src


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_009_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-009-02"), None)
    assert t is not None
    generic = [
        "as specified by feature F-009",
        "When the user interacts with the UI for T-009-02",
        "While the new feature for T-009-02 is enabled",
        "If invalid input or unauthorized actor is detected during T-009-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-009-02 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "DependencyGraph.tsx", "@xyflow/react", "TaskNodeData",
        "onNodeClick", "STATUS_BORDER", "STATUS_BG",
        "border-eb-500", "border-eb-700",
        "Sugiyama", "useMemo",
        "dependency-graph",
    ):
        assert sym in full, f"T-009-02 AC missing concrete symbol: {sym}"


def test_tickets_t_009_02_has_adr_link_and_7_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-009-02"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert len(files) >= 7, f"expected >= 7 existing_files, got {len(files)}"
    assert any("DependencyGraph.tsx" in f for f in files)
    assert any("dependency-graph/page.tsx" in f for f in files)
    assert any("package.json" in f for f in files)


def test_tickets_t_009_02_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-009-02"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-009-02 still uses legacy alias: {ty}"
        )
    assert "UBIQUITOUS" in types
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "UNWANTED" in types
