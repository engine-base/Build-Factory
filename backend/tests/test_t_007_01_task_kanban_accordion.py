"""T-007-01: task_kanban accordion (existing TaskKanban.tsx REFACTOR / CLAUDE.md §5.5).

TS module を Python から構造検証 (node 環境なし).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : TaskKanbanAccordion.tsx 存在 / 既存 TaskKanban.tsx 無改変.
  AC-2 EVENT-DRIVEN  : useMemo で recompute / onTaskClick callback / __testing__ export.
  AC-3 STATE-DRIVEN  : 進行中の機能 default 展開 / 完了済み default 折り畳み /
                       eb-* palette / Lucide icons / 絵文字なし.
  AC-4 UNWANTED      : null/non-array tasks で empty fallback / eb-* 外の hex なし.
"""
from __future__ import annotations

import json as _json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ACCORDION = REPO_ROOT / "frontend" / "src" / "components" / "tasks" / "TaskKanbanAccordion.tsx"
EXISTING_KANBAN = REPO_ROOT / "frontend" / "src" / "components" / "tasks" / "TaskKanban.tsx"


@pytest.fixture(scope="module")
def src() -> str:
    return ACCORDION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_accordion_exists():
    assert ACCORDION.exists()


def test_ac1_existing_kanban_exists():
    assert EXISTING_KANBAN.exists()


def test_ac1_existing_kanban_unchanged():
    """既存 TaskKanban.tsx に TaskKanbanAccordion への依存を入れていない (REUSE)."""
    src = EXISTING_KANBAN.read_text(encoding="utf-8")
    assert "TaskKanbanAccordion" not in src
    assert "from \"./TaskKanbanAccordion\"" not in src


def test_ac1_required_exports_present(src):
    for name in (
        "TaskKanbanAccordion",
        "AccordionTask",
        "TaskKanbanAccordionProps",
        "statusToColumnId",
        "isFeatureInProgress",
        "isFeatureCompleted",
        "__testing__",
    ):
        assert name in src, f"missing export: {name}"


def test_ac1_four_columns_defined(src):
    """4 列定義 (Todo/In Progress/Review/Done) が含まれる."""
    assert "FOUR_COLUMNS" in src
    assert "VALID_COLUMN_IDS" in src
    for col_id in ("todo", "in_progress", "review", "done"):
        assert f'"{col_id}"' in src, f"column {col_id} missing"


def test_ac1_documents_claude_md_5_5(src):
    """CLAUDE.md §5.5 への明示的言及."""
    assert "5.5" in src or "§5.5" in src or "S-027" in src
    assert "アコーディオン" in src or "accordion" in src.lower()


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: useMemo + onTaskClick + helpers
# ══════════════════════════════════════════════════════════════════════


def test_ac2_uses_useMemo(src):
    """props 変更時に再計算 (useMemo)."""
    assert "React.useMemo" in src


def test_ac2_invokes_on_task_click(src):
    assert "onTaskClick" in src
    # callback 呼出
    assert "onTaskClick?.(task)" in src or "onTaskClick && onTaskClick(task)" in src


def test_ac2_pure_helpers_exported_via_testing(src):
    """__testing__ object 経由で pure helpers が export."""
    assert "__testing__" in src
    assert "statusToColumnId" in src
    assert "isFeatureInProgress" in src
    assert "isFeatureCompleted" in src


def test_ac2_status_to_column_id_mapping(src):
    """statusToColumnId の mapping 文書化."""
    # 各 status → column id
    mappings = [
        ("pending", "todo"),
        ("in_progress", "in_progress"),
        ("review_needed", "review"),
        ("completed", "done"),
    ]
    for status, col in mappings:
        assert f'"{status}"' in src
        assert f'"{col}"' in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: default expand rule + eb palette + Lucide
# ══════════════════════════════════════════════════════════════════════


def test_ac3_default_expand_rule_in_source(src):
    """進行中の機能のみ default 展開 / 完了済みは折り畳み."""
    assert "isFeatureInProgress" in src
    assert "isFeatureCompleted" in src
    # default 展開判定ロジック
    assert "defaultOpen" in src


def test_ac3_uses_eb_palette_only(src):
    """border / bg は eb-* class のみ."""
    assert "border-eb-500" in src
    assert "border-eb-400" in src
    assert "border-eb-200" in src
    assert "bg-eb-50" in src


def test_ac3_no_hardcoded_color_outside_eb(src):
    """eb-* palette 以外の hex literal なし."""
    code = _strip_comments(src)
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
    matches = [m for m in hex_pattern.findall(code) if m.lower() != "#1a6648"]
    assert not matches, f"non-eb hex colors: {matches}"


def test_ac3_lucide_icons_only(src):
    """Lucide のみ (Clock / CheckCircle / AlertCircle / ChevronDown / Folder)."""
    assert 'from "lucide-react"' in src
    for icon in ("Clock", "CheckCircle", "AlertCircle", "ChevronDown", "Folder"):
        assert icon in src, f"missing Lucide icon: {icon}"


def test_ac3_no_emoji_in_source():
    """source に絵文字 literal なし (lint script 経由検証)."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"emoji baseline broken: {r.stdout}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_tasks_fallback(src):
    """tasks 空で fallback 表示."""
    assert 'data-testid="kanban-accordion-empty"' in src
    assert "features.length === 0" in src


def test_ac4_null_tasks_safety(src):
    """null / non-array tasks で crash しない."""
    assert "Array.isArray(tasks)" in src


def test_ac4_no_secret_keywords(src):
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code


def _strip_comments(src: str) -> str:
    """簡易 TS comment stripper."""
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


def test_tickets_t_007_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-007-01"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-007-01",
        "While refactoring for T-007-01 is in progress",
        "If invalid input or unauthorized actor is detected during T-007-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-007-01 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "TaskKanbanAccordion.tsx" in full
    assert "CLAUDE.md §5.5" in full
    assert "4 列" in full or "Todo/In Progress" in full


def test_tickets_t_007_01_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-007-01"), None)
    assert t.get("adr_link") is not None
