#!/usr/bin/env python3
"""T-M30-03 AC-4 UNWANTED / T-M28-04 UNWANTED 連動:
9-section structured summary の SECTION_KEYS は ADR-010 で
"SDK auto-compaction 経路のみが生成する" と定められている.

このスクリプトは, application code が 9 section の keys を **新規に**
tuple/list literal で定義していないかを検出する.

許容:
- services/mid_term_layer.py        SECTION_KEYS owner (G10)
- services/tier2_cache.py           KNOWN_SUMMARY_SECTIONS legacy alias
- tests/                            (動作検証で 9-section を直書きしてよい)
- docs/                             (仕様書記載)
- scripts/                          (本スクリプト含む)

ALL_9 すべてを含む tuple/list literal を ALLOWED 外で検出したら FAIL.

Exit code:
  0 — clean
  1 — 9-section reimplementation detected
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SECTION_NAMES = frozenset((
    "context",
    "goals",
    "decisions",
    "open_questions",
    "actions",
    "blockers",
    "facts",
    "preferences",
    "next_steps",
))

ALLOWED_FILES = frozenset((
    "backend/services/mid_term_layer.py",
    "backend/services/tier2_cache.py",
))


def _str_literals_in(node: ast.AST) -> set[str]:
    """node が tuple/list/set literal なら, その中の str リテラルを集合で返す."""
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return set()
    out: set[str] = set()
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.add(elt.value)
    return out


def _file_defines_9_sections(path: Path) -> tuple[bool, int]:
    """与えられた .py が 9 section keys 全てを含む tuple/list/set literal を
    トップレベル定義していれば (True, lineno) を返す."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return (False, 0)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            lits = _str_literals_in(node)
            if SECTION_NAMES.issubset(lits):
                return (True, getattr(node, "lineno", 0))
    return (False, 0)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    backend = repo_root / "backend"
    if not backend.exists():
        print("OK: no backend/ — skipping 9-section lint", flush=True)
        return 0

    violations: list[tuple[str, int]] = []
    for path in backend.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(repo_root))
        if rel in ALLOWED_FILES:
            continue
        # tests/ は許容 (動作検証用に直書きあり)
        if "/tests/" in rel or rel.startswith("backend/tests/"):
            continue
        defines, lineno = _file_defines_9_sections(path)
        if defines:
            violations.append((rel, lineno))

    if violations:
        print("FAIL: 9-section SECTION_KEYS re-defined outside allowed files:")
        for rel, lineno in violations:
            print(f"  - {rel}:{lineno}")
        print()
        print("Allowed defining files (ADR-010 / T-M30-03 AC-4):")
        for f in sorted(ALLOWED_FILES):
            print(f"  - {f}")
        print()
        print("If you actually need to reference the 9-section keys, import")
        print("them from services.mid_term_layer (SECTION_KEYS) instead.")
        return 1

    print(f"OK: 9-section SECTION_KEYS unique to {len(ALLOWED_FILES)} allowed files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
