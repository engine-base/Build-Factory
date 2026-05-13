"""T-010d-02: swarm_grid UI — 4 AC.

NEW FE タスク. Python 静的解析で TSX を検査.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : SwarmGrid.tsx + page.tsx / props signature / 4 size
                       preset / REUSE SwarmSessionStatus from sessions.ts.
  AC-2 EVENT-DRIVEN  : onCellClick callback / size > 16 で windowing.
  AC-3 STATE-DRIVEN  : 4 status palette (border-eb-500/700/rose-500/amber-500)
                       SwarmSessionDetail と一致 / no emoji / status enum
                       再定義禁止.
  AC-4 UNWANTED      : cells > size で graceful slice / invalid size で 16
                       fallback / no fetch in component / no langgraph etc.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT = REPO_ROOT / "frontend" / "src" / "components" / "swarm" / "SwarmGrid.tsx"
PAGE = REPO_ROOT / "frontend" / "src" / "app" / "dashboard" / "swarm" / "page.tsx"
SESSIONS_API = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "sessions.ts"
DETAIL_COMPONENT = REPO_ROOT / "frontend" / "src" / "components" / "sessions" / "SwarmSessionDetail.tsx"


EMOJI = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
)


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — files + props + 4 size + REUSE status type
# ══════════════════════════════════════════════════════════════════════


def test_ac1_component_file_exists():
    assert COMPONENT.exists()


def test_ac1_page_file_exists():
    assert PAGE.exists()


def test_ac1_component_default_and_named_exports():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "export function SwarmGrid" in src
    assert "export default SwarmGrid" in src


def test_ac1_component_exports_swarm_grid_size_type():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"export\s+type\s+SwarmGridSize", src)
    # literal union '4' | '9' | '16' | '64'
    assert '"4"' in src and '"9"' in src and '"16"' in src and '"64"' in src


def test_ac1_component_exports_swarm_cell_interface():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"export\s+interface\s+SwarmCell", src)
    # 必須 fields
    for field in ("session_id", "status", "pool_id", "cell_index"):
        assert field in src


def test_ac1_component_imports_status_type_from_sessions():
    """REUSE: SwarmSessionStatus を sessions.ts から import (再定義禁止)."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "@/lib/api/sessions" in src
    assert "SwarmSessionStatus" in src


def test_ac1_status_type_not_redefined_in_component():
    """G15: SwarmSessionStatus を SwarmGrid.tsx で再定義しない."""
    src = COMPONENT.read_text(encoding="utf-8")
    code = _strip_js_comments(src)
    # `export type SwarmSessionStatus = ...` のような再定義禁止
    assert not re.search(
        r"(?:export\s+)?type\s+SwarmSessionStatus\s*=",
        code,
    ), "SwarmSessionStatus must NOT be redefined (G15)"


def test_ac1_page_uses_component():
    src = PAGE.read_text(encoding="utf-8")
    assert "SwarmGrid" in src
    assert "@/components/swarm/SwarmGrid" in src


def test_ac1_props_signature():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"cells:\s*SwarmCell\[\]", src)
    assert "size?" in src or "size:" in src
    assert "onCellClick" in src
    assert "className" in src


def test_ac1_page_in_dashboard_swarm_route():
    parts = PAGE.parts
    assert "dashboard" in parts
    assert "swarm" in parts


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — onCellClick + virtualization
# ══════════════════════════════════════════════════════════════════════


def test_ac2_on_cell_click_invocation():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"onCellClick\??\.\(", src)


def test_ac2_useCallback_for_click_handler():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "useCallback" in src


def test_ac2_virtualization_threshold_constant():
    """size > 16 で windowing logic がある."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "VIRTUALIZATION_THRESHOLD" in src
    assert "WINDOW_PAGE" in src


def test_ac2_windowing_uses_slice():
    """visible cells = clipped.slice(windowStart, windowStart + WINDOW_PAGE)."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"\.slice\(\s*windowStart", src)


def test_ac2_useMemo_for_visible_cells():
    """re-render 最小化に useMemo を使う."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "useMemo" in src


def test_ac2_window_controls_for_virtualized():
    """size 64 で prev/next ボタン表示."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "swarm-grid-window-controls" in src
    assert "prev" in src.lower() and "next" in src.lower()


def test_ac2_page_routes_on_cell_click():
    """page の onCellClick が /sessions/[id] へ遷移."""
    src = PAGE.read_text(encoding="utf-8")
    assert "useRouter" in src
    assert "/sessions/" in src
    assert "router.push" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — palette consistency + Lucide-only + no enum redef
# ══════════════════════════════════════════════════════════════════════


def test_ac3_status_border_4_keys():
    src = COMPONENT.read_text(encoding="utf-8")
    # STATUS_BORDER に 4 status 全て
    for st in ("running", "done", "crashed", "paused"):
        assert re.search(rf"{st}\s*:\s*\"border-", src), (
            f"STATUS_BORDER missing: {st}"
        )


def test_ac3_running_uses_eb_500():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'running\s*:\s*"border-eb-500"', src)


def test_ac3_done_uses_eb_700():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'done\s*:\s*"border-eb-700"', src)


def test_ac3_crashed_uses_rose_500():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'crashed\s*:\s*"border-rose-500"', src)


def test_ac3_paused_uses_amber_500():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'paused\s*:\s*"border-amber-500"', src)


def test_ac3_palette_matches_swarm_session_detail():
    """SwarmSessionDetail と同じ palette (cross-component 整合 / G15)."""
    grid_src = COMPONENT.read_text(encoding="utf-8")
    detail_src = DETAIL_COMPONENT.read_text(encoding="utf-8")
    # 4 status カラーが両方に出現
    for color in ("border-eb-500", "border-eb-700",
                   "border-rose-500", "border-amber-500"):
        assert color in grid_src, f"SwarmGrid missing {color}"
        assert color in detail_src, f"SwarmSessionDetail missing {color}"


def test_ac3_no_emoji_in_component():
    src = COMPONENT.read_text(encoding="utf-8")
    assert not EMOJI.findall(src)


def test_ac3_no_emoji_in_page():
    src = PAGE.read_text(encoding="utf-8")
    assert not EMOJI.findall(src)


def test_ac3_uses_lucide_icons():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "lucide-react" in src


def test_ac3_no_hardcoded_eb_hex():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "#1a6648" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — graceful slice + size fallback + layer separation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_cells_slice_to_size():
    """cells.slice(0, sizeNum) で graceful clip."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"cells\.slice\(\s*0\s*,\s*sizeNum", src)


def test_ac4_size_fallback_to_16():
    """VALID_SIZES に含まれないなら default '16'."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "VALID_SIZES" in src
    assert re.search(r"VALID_SIZES\.includes", src)
    assert '"16"' in src


def test_ac4_component_no_backend_fetch():
    """layer separation: component に fetch / axios / useQuery / useSWR なし."""
    src = COMPONENT.read_text(encoding="utf-8")
    code = _strip_js_comments(src)
    assert not re.search(r"\bfetch\s*\(", code)
    assert "axios" not in code
    assert "useQuery" not in code
    assert "useSWR" not in code
    assert "@/lib/api/" not in code or "type" in code  # type import OK


def test_ac4_no_reactflow_legacy():
    src = COMPONENT.read_text(encoding="utf-8")
    assert 'from "reactflow"' not in src
    assert "from 'reactflow'" not in src


def test_ac4_no_langgraph_langchain_litellm():
    """ADR-010 main path: block / line comments を除外して import 文を検査.

    docstring に禁止語が書かれていても OK (説明目的).
    実際の import が無いことだけを確認.
    """
    for path in (COMPONENT, PAGE):
        src = path.read_text(encoding="utf-8")
        code = _strip_js_comments(src).lower()
        for forbidden in ("langgraph", "langchain", "litellm"):
            # import 文として書かれていないこと
            assert not re.search(
                rf'from\s+["\'][^"\']*{forbidden}', code,
            ), f"forbidden import {forbidden} in {path.name}"
            assert not re.search(
                rf'import\s+[^;]*{forbidden}', code,
            ), f"forbidden import {forbidden} in {path.name}"


def test_ac4_no_dangerously_set_inner_html():
    for path in (COMPONENT, PAGE):
        src = path.read_text(encoding="utf-8")
        assert "dangerouslySetInnerHTML" not in src


def test_ac4_no_hardcoded_secret():
    for path in (COMPONENT, PAGE):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_010d_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-02"), None)
    generic = [
        "as specified by feature F-010d",
        "When the user interacts with the UI for T-010d-02",
        "While the new feature for T-010d-02 is enabled",
        "If invalid input or unauthorized actor is detected during T-010d-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"]
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "SwarmGrid.tsx", "SwarmGridSize", "SwarmCell", "onCellClick",
        "border-eb-500", "border-eb-700",
        "border-rose-500", "border-amber-500",
        "SwarmSessionStatus", "dashboard/swarm",
    ):
        assert sym in full, f"T-010d-02 AC missing: {sym}"


def test_tickets_t_010d_02_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-02"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("sessions.ts" in f for f in files)
    assert any("SwarmSessionDetail" in f for f in files)


def test_tickets_t_010d_02_canonical_ears():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-02"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
