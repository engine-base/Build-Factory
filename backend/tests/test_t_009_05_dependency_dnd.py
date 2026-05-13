"""T-009-05: 依存追加/削除 drag&drop (pure validation + DnDPanel).

TS module を Python から構造検証.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : DependencyDnD.tsx 存在 / 8 helpers + Panel /
                       既存 DependencyGraph.tsx 無改変.
  AC-2 EVENT-DRIVEN  : useMemo / onUndo / onConfirm / __testing__.
  AC-3 STATE-DRIVEN  : controlled pending / eb-* palette / Lucide icons.
  AC-4 UNWANTED      : 5 validation rules (type/value/self/duplicate/cycle) /
                       hardcoded color/secret なし.
"""
from __future__ import annotations

import json as _json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DND = REPO_ROOT / "frontend" / "src" / "components" / "dag" / "DependencyDnD.tsx"
EXISTING_DG = REPO_ROOT / "frontend" / "src" / "components" / "dag" / "DependencyGraph.tsx"


@pytest.fixture(scope="module")
def src() -> str:
    return DND.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_dnd_exists():
    assert DND.exists()


def test_ac1_existing_dependency_graph_unchanged():
    """既存 DependencyGraph.tsx に DependencyDnD 依存なし (REUSE)."""
    assert EXISTING_DG.exists()
    src = EXISTING_DG.read_text(encoding="utf-8")
    assert "DependencyDnD" not in src
    assert "validateNewDependency" not in src


def test_ac1_required_exports(src):
    for name in (
        "DependencyEdge", "DependencyChange", "DependencyChangeKind",
        "ValidationResult",
        "validateNewDependency", "proposeAddEdge", "proposeRemoveEdge",
        "applyPending",
        "DependencyDnDPanel", "DependencyDnDPanelProps",
        "__testing__",
    ):
        assert name in src, f"missing export: {name}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: useMemo + callbacks + __testing__
# ══════════════════════════════════════════════════════════════════════


def test_ac2_uses_useMemo(src):
    assert "React.useMemo" in src


def test_ac2_propose_add_returns_change_or_error(src):
    """proposeAddEdge は valid なら DependencyChange, invalid なら {error: ...}."""
    assert "proposeAddEdge" in src
    assert "{ error: result }" in src or "{ error:" in src


def test_ac2_callbacks_present(src):
    for cb in ("onUndo", "onConfirm", "onCancel"):
        assert cb in src


def test_ac2_testing_exports(src):
    assert "__testing__" in src
    for name in ("validateNewDependency", "proposeAddEdge",
                 "proposeRemoveEdge", "applyPending"):
        assert name in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: controlled + eb-* + Lucide
# ══════════════════════════════════════════════════════════════════════


def test_ac3_controlled_pending(src):
    """pending は props 経由. 内部 useState なし."""
    assert "useState<DependencyChange" not in src
    assert "pending:" in src


def test_ac3_eb_palette(src):
    """eb-* class 使用."""
    assert "border-eb-500" in src
    assert "border-eb-200" in src
    assert "bg-eb-50" in src or "bg-eb-500" in src
    assert "text-eb-500" in src


def test_ac3_lucide_icons(src):
    assert 'from "lucide-react"' in src
    for icon in ("Plus", "Trash2", "Undo2", "AlertCircle"):
        assert icon in src


def test_ac3_no_emoji_in_source():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: 5 validation rules
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_type_check(src):
    """source/target が number でない場合 reject."""
    assert "dep.invalid_type" in src
    assert 'typeof source !== "number"' in src


def test_ac4_invalid_value_check(src):
    """source/target <= 0 で reject."""
    assert "dep.invalid_value" in src
    assert "source <= 0" in src or "target <= 0" in src


def test_ac4_self_edge_check(src):
    """source === target で reject."""
    assert "dep.self_edge" in src
    assert "source === target" in src


def test_ac4_duplicate_check(src):
    """既存 edge と重複で reject."""
    assert "dep.duplicate" in src


def test_ac4_cycle_check(src):
    """BFS で cycle 検出."""
    assert "dep.cycle" in src
    assert "would create cycle" in src or "queue" in src


def test_ac4_integer_check(src):
    """Number.isInteger or Number.isFinite check."""
    assert "Number.isInteger" in src or "Number.isFinite" in src


def test_ac4_no_hardcoded_color_outside_eb(src):
    code = _strip_comments(src)
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}")
    matches = [m for m in hex_pattern.findall(code) if m.lower() != "#1a6648"]
    assert not matches


def test_ac4_no_secret(src):
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)


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


def test_tickets_t_009_05_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-009-05"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-009-05",
        "While the new feature for T-009-05 is enabled",
        "If invalid input or unauthorized actor is detected during T-009-05",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-009-05 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "DependencyDnD.tsx" in full
    assert "validateNewDependency" in full
    assert "dep.cycle" in full or "cycle" in full


def test_tickets_t_009_05_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-009-05"), None)
    assert t.get("adr_link") is not None
