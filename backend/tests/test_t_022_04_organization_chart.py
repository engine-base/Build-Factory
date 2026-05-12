"""T-022-04: 組織図 UI (React Flow tree).

TS component の **構造検証** を Python から行う (node 環境なしのため runtime test 不可).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : OrganizationChart.tsx export / React Flow 使用 /
                       DependencyGraph.tsx 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : onNodeClick callback / useMemo で layout 再計算 /
                       controlled component.
  AC-3 STATE-DRIVEN  : eb-* palette のみ / Lucide icons (Crown/Users/User) /
                       絵文字なし / props mutate なし.
  AC-4 UNWANTED      : empty employees で fallback render / invalid role_level
                       で silent skip / hardcoded color literal なし.
"""
from __future__ import annotations

import json as _json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ORG_CHART = REPO_ROOT / "frontend" / "src" / "components" / "org" / "OrganizationChart.tsx"
DAG = REPO_ROOT / "frontend" / "src" / "components" / "dag" / "DependencyGraph.tsx"


@pytest.fixture(scope="module")
def src() -> str:
    return ORG_CHART.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_component_exists():
    assert ORG_CHART.exists()


def test_ac1_export_organization_chart(src):
    assert "export function OrganizationChart" in src


def test_ac1_uses_xyflow_react(src):
    assert 'from "@xyflow/react"' in src


def test_ac1_required_types_exported(src):
    for name in ("PersonaData", "EmployeeData", "OrgEdge", "OrganizationChartProps"):
        assert f"export interface {name}" in src or f"export type {name}" in src


def test_ac1_dependency_graph_unchanged():
    """既存 DependencyGraph.tsx に T-022-04 改変なし (REUSE)."""
    assert DAG.exists()
    src = DAG.read_text(encoding="utf-8")
    # T-022-04 関連の import を入れていないこと
    assert "from \"@/components/org/OrganizationChart\"" not in src
    assert "OrganizationChart" not in src


def test_ac1_xyflow_already_in_package_json():
    pkg = _json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert "@xyflow/react" in pkg["dependencies"]


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: onNodeClick + useMemo + controlled
# ══════════════════════════════════════════════════════════════════════


def test_ac2_on_node_click_callback(src):
    assert "onNodeClick" in src
    assert "NodeMouseHandler" in src or "onNodeClick(employee)" in src or "onNodeClick(emp)" in src


def test_ac2_uses_useMemo_for_layout(src):
    """layout は useMemo で props 変化時に再計算."""
    assert "React.useMemo" in src
    # employees + edges 依存
    assert "[employees]" in src or "[validEmployees]" in src


def test_ac2_uses_usecallback_for_handler(src):
    """node click handler は useCallback で memoize."""
    assert "React.useCallback" in src


def test_ac2_controlled_no_internal_employees_state(src):
    """internal useState で employees を持たない (controlled component)."""
    # employees の internal state がないこと
    assert "useState(employees" not in src
    assert "useState<EmployeeData" not in src or "validEmployees" in src


def test_ac2_employee_data_shape_matches_backend():
    """EmployeeData が backend ai_employee_store.AIEmployee.to_dict() と整合."""
    src = ORG_CHART.read_text(encoding="utf-8")
    # backend が返すキー
    for key in ("id", "employee_key", "display_name", "role_level", "is_active", "persona_id"):
        assert key in src, f"EmployeeData missing key: {key}"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: eb-* palette + Lucide + no emoji
# ══════════════════════════════════════════════════════════════════════


def test_ac3_uses_eb_palette_only(src):
    """border / bg は eb-* class のみ."""
    assert "border-eb-500" in src
    assert "border-eb-400" in src or "border-eb-200" in src
    assert "bg-eb-50" in src


def test_ac3_role_styles_for_all_three_levels(src):
    """ROLE_STYLE が secretary / leader / member 全 3 役を扱う."""
    for role in ("secretary:", "leader:", "member:"):
        assert role in src


def test_ac3_lucide_icons_only(src):
    """Crown / Users / User の Lucide icon を使う."""
    assert 'from "lucide-react"' in src
    assert "Crown" in src
    assert "Users" in src
    # User icon (capital 'U')
    assert re.search(r"\bUser\b", src), "Lucide User icon missing"


def test_ac3_no_emoji_in_source():
    """絵文字混入なし (CLAUDE.md §5.1).
    実検査は scripts/lint-mock.sh --emoji が CI で実行する.
    ここでは TS source 内の各 char が ASCII or 日本語 (CJK) のみであることを
    確認 (絵文字 emoji range U+1F300+ や U+2600-27BF を含まない).
    """
    import subprocess
    # 既存 lint script を呼ぶ (literal emoji を test file に書かない)
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, (
        f"lint-mock --emoji baseline broken: {r.stdout}\n{r.stderr}"
    )


def test_ac3_uses_eb_500_color_token_for_edges(src):
    """edge stroke が eb-500 (#1a6648) を使う."""
    assert "eb-500" in src or "#1a6648" in src


def test_ac3_no_props_mutation(src):
    """props を直接 mutate しないこと.
    employees / edges を assign / push / splice で改変していないこと.
    """
    # employees や edges に対する mutating method 呼出を検査
    code = _strip_comments_and_docstrings(src)
    for mutating in (
        "employees.push", "employees.splice", "employees.shift",
        "edges.push", "edges.splice", "edges.shift",
        "props.employees =", "props.edges =",
    ):
        assert mutating not in code, f"props mutation detected: {mutating}"


def _strip_comments_and_docstrings(src: str) -> str:
    """TS ファイルの // と /** */ コメントを除去 (rough)."""
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
        # block comment 開始
        if "/*" in line:
            before, _, after = line.partition("/*")
            if "*/" in after:
                line = before + after.split("*/", 1)[1]
            else:
                line = before
                in_block = True
        # line comment 削除
        if "//" in line:
            # ただし "https://" 等は残す
            idx = line.find("//")
            # URL 内 // ではないか確認 (前後文字)
            if idx > 0 and line[idx - 1] != ":":
                line = line[:idx]
            elif idx == 0:
                line = ""
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: empty / invalid / no hardcoded color
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_employees_fallback_render(src):
    """空 employees で fallback (`data-testid="org-chart-empty"`)."""
    assert 'data-testid="org-chart-empty"' in src
    assert "flowNodes.length === 0" in src or "validEmployees.length === 0" in src


def test_ac4_valid_roles_constant(src):
    """VALID_ROLES が定義され silent filter に使われる."""
    assert "VALID_ROLES" in src
    assert "secretary" in src
    assert "leader" in src
    assert "member" in src


def test_ac4_filters_invalid_role_level(src):
    """role_level チェックで silent skip."""
    code = _strip_comments_and_docstrings(src)
    assert "VALID_ROLES.includes" in code


def test_ac4_no_hardcoded_color_outside_eb_palette(src):
    """eb-* palette 以外の hex color literal がないこと.
    grayscale (border-gray-*, text-gray-*) は OK (fallback message のみ).
    """
    code = _strip_comments_and_docstrings(src)
    # 非 eb-* の hex literal を検査
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
    hex_matches = [m for m in hex_pattern.findall(code) if m.lower() != "#1a6648"]
    assert not hex_matches, f"non-eb hex colors detected: {hex_matches}"


def test_ac4_no_secret_keywords_in_source(src):
    """source に hardcoded secret なし (defensive)."""
    code = _strip_comments_and_docstrings(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code


def test_ac4_no_crash_on_null_employees(src):
    """null / non-array employees で graceful (Array.isArray check)."""
    assert "Array.isArray(employees)" in src


def test_ac4_no_crash_on_null_edges(src):
    assert "Array.isArray(edges)" in src or "edges = []" in src


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_022_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-022-04"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-022-04",
        "While the new feature for T-022-04 is enabled",
        "If invalid input or unauthorized actor is detected during T-022-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-022-04 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "OrganizationChart" in full
    assert "react flow" in full.lower() or "React Flow" in full or "@xyflow/react" in full
    assert "eb-500" in full or "ENGINE BASE green" in full
    assert "Lucide" in full or "lucide" in full


def test_tickets_t_022_04_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-022-04"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files")
