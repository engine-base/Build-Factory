"""T-009-02: DAG 可視化 UI (React Flow) AC 検証 (frontend 静的解析).

AC マッピング:
  AC-1 UBIQUITOUS: DependencyGraph component + page + @xyflow/react dep
  AC-2 EVENT:     onNodeClick → router.push / fetch /api/workspaces/{id}/dependency-graph
  AC-3 STATE:     RLS (workspace_id 経由) は backend layer (本 task は frontend)
  AC-4 UNWANTED:  4xx fetch → {detail: {code, message}} を parse して friendly alert
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"
COMPONENT = FE / "src/components/dag/DependencyGraph.tsx"
PAGE = FE / "src/app/workspaces/[id]/dependency-graph/page.tsx"
PACKAGE_JSON = FE / "package.json"


@pytest.fixture(scope="module")
def comp_text() -> str:
    return COMPONENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: component + page + dep
# ──────────────────────────────────────────────────────────────────────────


def test_dependency_graph_component_exists() -> None:
    assert COMPONENT.exists()


def test_dependency_graph_page_exists() -> None:
    assert PAGE.exists()


def test_xyflow_react_dependency_in_package_json() -> None:
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    assert "@xyflow/react" in deps, "@xyflow/react dep missing (React Flow v12)"


def test_component_imports_reactflow_primitives(comp_text: str) -> None:
    """ReactFlow / Background / Controls / MiniMap を import (S-017 mock 準拠)."""
    assert 'from "@xyflow/react"' in comp_text
    for symbol in ("ReactFlow", "Background", "Controls", "MiniMap"):
        assert re.search(rf"\b{symbol}\b", comp_text), f"{symbol} not imported"


def test_component_imports_xyflow_css(comp_text: str) -> None:
    """React Flow v12 は CSS import 必須."""
    assert '"@xyflow/react/dist/style.css"' in comp_text


def test_component_exports_task_node_data_and_edge_types(comp_text: str) -> None:
    """型 TaskNodeData + TaskEdge を export (caller が import 可能)."""
    assert re.search(r"export\s+interface\s+TaskNodeData", comp_text)
    assert re.search(r"export\s+interface\s+TaskEdge", comp_text)


def test_component_exports_default_dependency_graph(comp_text: str) -> None:
    """default export + named export 両方."""
    assert "export default DependencyGraph" in comp_text
    assert re.search(r"export\s+function\s+DependencyGraph", comp_text)


def test_component_supports_6_task_statuses(comp_text: str) -> None:
    """6 status (pending/in_progress/completed/blocked_question/blocked_dependency/failed)
    の border/bg class 定義あり."""
    for status in (
        "pending", "in_progress", "completed",
        "blocked_question", "blocked_dependency", "failed",
    ):
        assert f'"{status}"' in comp_text, f"status {status!r} missing"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT: onNodeClick → router.push / fetch backend endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_component_accepts_on_node_click_prop(comp_text: str) -> None:
    assert "onNodeClick" in comp_text
    # NodeMouseHandler 型を使う
    assert "NodeMouseHandler" in comp_text


def test_page_fetches_dependency_graph_endpoint(page_text: str) -> None:
    """page は GET /api/workspaces/{id}/dependency-graph を叩く."""
    assert "/api/workspaces/" in page_text
    assert "/dependency-graph" in page_text


def test_page_navigates_to_task_on_node_click(page_text: str) -> None:
    """node click → router.push でタスク詳細へ."""
    assert "router.push" in page_text
    assert "taskId=" in page_text or "/tasks?" in page_text


def test_page_uses_use_router_for_navigation(page_text: str) -> None:
    """Next.js 16 の useRouter (next/navigation)."""
    assert 'from "next/navigation"' in page_text
    assert "useRouter" in page_text


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: workspace スコープ (useParams で workspace_id を取得)
# ──────────────────────────────────────────────────────────────────────────


def test_page_extracts_workspace_id_from_params(page_text: str) -> None:
    """useParams() で動的 route segment を取得 → workspace scope を確立."""
    assert "useParams" in page_text
    assert "workspaceId" in page_text


def test_page_passes_workspace_id_to_api(page_text: str) -> None:
    """fetch URL に workspaceId を含める."""
    assert "${workspaceId}" in page_text or "{workspaceId}" in page_text


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx fetch → friendly error + {detail: {code, message}} parse
# ──────────────────────────────────────────────────────────────────────────


def test_page_handles_4xx_response_with_friendly_message(page_text: str) -> None:
    """4xx 時に detail.message を抽出してユーザに表示."""
    assert re.search(r"res\.status\s*>=\s*400", page_text)
    assert re.search(r"detail.*message", page_text, re.DOTALL)


def test_page_shows_alert_role_on_error(page_text: str) -> None:
    """エラー UI に role=alert (a11y)."""
    assert 'role="alert"' in page_text


def test_page_falls_back_to_demo_data_on_failure(page_text: str) -> None:
    """backend 未接続 / fetch 失敗時に demo data fallback (Phase 1)."""
    assert "DEMO" in page_text or "demo" in page_text.lower()


def test_page_uses_lucide_icons_only(page_text: str) -> None:
    """page で使う icon は lucide-react のみ (CLAUDE.md §5.1)."""
    assert 'from "lucide-react"' in page_text
    # 他 icon lib を import していないこと
    for forbidden in ("react-icons", "@heroicons", "phosphor-icons"):
        assert forbidden not in page_text


# ──────────────────────────────────────────────────────────────────────────
# Layout algorithm + a11y
# ──────────────────────────────────────────────────────────────────────────


def test_component_uses_bfs_layout_function(comp_text: str) -> None:
    """auto-layout 関数 layoutNodes が定義されている."""
    assert "function layoutNodes" in comp_text
    # BFS / level 計算ロジック
    assert "incoming" in comp_text or "level" in comp_text


def test_component_uses_aria_region_for_a11y(comp_text: str) -> None:
    """grpah container に role=region + aria-label (a11y)."""
    assert 'role="region"' in comp_text
    assert 'aria-label="dependency graph"' in comp_text


def test_component_distinguishes_hard_and_soft_edges(comp_text: str) -> None:
    """hard / soft edge を視覚的に区別 (animated / strokeDasharray)."""
    assert '"hard"' in comp_text
    assert '"soft"' in comp_text
    assert "strokeDasharray" in comp_text or "animated" in comp_text


def test_component_uses_eb_palette_for_in_progress(comp_text: str) -> None:
    """ENGINE BASE green (eb-500) を in_progress に使用."""
    assert "border-eb-500" in comp_text
    assert "bg-eb-50" in comp_text or "bg-eb-100" in comp_text


# ──────────────────────────────────────────────────────────────────────────
# No emoji / AGPL check
# ──────────────────────────────────────────────────────────────────────────


def test_component_has_no_emoji() -> None:
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    text = COMPONENT.read_text(encoding="utf-8")
    assert not emoji_re.findall(text)


def test_page_has_no_emoji() -> None:
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    text = PAGE.read_text(encoding="utf-8")
    assert not emoji_re.findall(text)


def test_xyflow_react_is_mit_licensed() -> None:
    """@xyflow/react は MIT (AGPL ではない)."""
    license_file = FE / "node_modules" / "@xyflow" / "react" / "LICENSE"
    if license_file.exists():
        text = license_file.read_text(encoding="utf-8")
        assert "MIT" in text, f"@xyflow/react license is not MIT: {text[:100]}"
    else:
        # node_modules absent in some CI env → skip
        pytest.skip("LICENSE file not in node_modules")


def test_component_uses_pro_options_hide_attribution(comp_text: str) -> None:
    """商用利用時の attribution 非表示 (React Flow Pro option)."""
    assert "hideAttribution" in comp_text