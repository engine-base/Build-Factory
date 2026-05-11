#!/usr/bin/env python3
"""T-001-01b AC-3/4/5: bounded-context domain boundary lint.

検証内容:
  1. AC-1: backend/domains/ 配下に 13 domain が存在
  2. AC-2: 各 domain は __init__.py に __all__ を持つ
  3. AC-3 EVENT: domain A 内のファイルが domain B の internal (非 __init__) を直接 import したら違反
  4. AC-4/5 STATE/UNWANTED: domain 間の循環依存があれば fail

使い方:
  python3 scripts/check-domain-boundaries.py
  → exit 0: OK / exit 1: violation
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
DOMAINS_DIR = ROOT / "backend" / "domains"

EXPECTED_DOMAINS = (
    "auth", "workspace", "project", "task", "memory", "llm",
    "skill", "knowledge", "artifact", "review", "observability",
    "billing", "integration",
)


def _list_domain_dirs() -> list[Path]:
    if not DOMAINS_DIR.is_dir():
        return []
    return [p for p in DOMAINS_DIR.iterdir() if p.is_dir() and (p / "__init__.py").exists()]


def _domain_has_all(d: Path) -> bool:
    """__init__.py に __all__ 定義があるか確認."""
    init = d / "__init__.py"
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return True
    return False


def _imports_in_file(fp: Path) -> Iterable[str]:
    """ファイル内の import 名 (dot 表現) を yield."""
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8"))
    except Exception:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def _domain_internal_import_violations() -> list[str]:
    """AC-3: domain A → domain B の internal (非 __init__) 直接 import を検出."""
    violations: list[str] = []
    domains = {p.name for p in _list_domain_dirs()}
    for domain in domains:
        for py in (DOMAINS_DIR / domain).rglob("*.py"):
            for mod in _imports_in_file(py):
                # backend.domains.<other>.<internal> を検出 (other != self)
                # ただし backend.domains.<other> (barrel) と
                # backend.domains.<other>.__init__ は OK
                parts = mod.split(".")
                if len(parts) >= 4 and parts[0] == "backend" and parts[1] == "domains":
                    other = parts[2]
                    if other != domain and other in domains and parts[3] != "__init__":
                        violations.append(
                            f"{py.relative_to(ROOT)}: imports internal {mod} from domain {other!r}"
                        )
                elif len(parts) >= 3 and parts[0] == "domains":
                    # 相対 import: domains.<other>.<internal>
                    other = parts[1]
                    if other != domain and other in domains and parts[2] != "__init__":
                        violations.append(
                            f"{py.relative_to(ROOT)}: imports internal {mod} from domain {other!r}"
                        )
    return violations


def _build_dep_graph() -> dict[str, set[str]]:
    """domain -> {direct deps} の dict (barrel → barrel のみ)."""
    domains = {p.name for p in _list_domain_dirs()}
    graph: dict[str, set[str]] = {d: set() for d in domains}
    for domain in domains:
        init = DOMAINS_DIR / domain / "__init__.py"
        if not init.exists():
            continue
        for mod in _imports_in_file(init):
            parts = mod.split(".")
            for i, p in enumerate(parts):
                if p == "domains" and i + 1 < len(parts):
                    other = parts[i + 1]
                    if other in domains and other != domain:
                        graph[domain].add(other)
    return graph


def _find_cycle(graph: dict[str, set[str]]) -> list[str]:
    """循環依存があれば cycle path を返す (なければ空)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in graph}
    parent: dict[str, str] = {}

    def dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        for v in graph.get(u, ()):
            if color.get(v, WHITE) == GRAY:
                cycle = [v]
                cur = u
                while cur != v and cur in parent:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.append(v)
                cycle.reverse()
                return cycle
            if color.get(v, WHITE) == WHITE:
                parent[v] = u
                c = dfs(v)
                if c:
                    return c
        color[u] = BLACK
        return None

    for node in list(graph.keys()):
        if color[node] == WHITE:
            c = dfs(node)
            if c:
                return c
    return []


def main() -> int:
    errors: list[str] = []

    # AC-1: 13 domain 存在確認
    dirs = _list_domain_dirs()
    have = {p.name for p in dirs}
    missing = sorted(set(EXPECTED_DOMAINS) - have)
    if missing:
        errors.append(f"AC-1 FAIL: missing domains: {missing}")
    extra = sorted(have - set(EXPECTED_DOMAINS))
    if extra:
        errors.append(f"AC-1 WARN: unexpected domains: {extra}")

    # AC-2: 各 domain に __all__
    for d in dirs:
        if d.name not in EXPECTED_DOMAINS:
            continue
        if not _domain_has_all(d):
            errors.append(f"AC-2 FAIL: domain {d.name!r} has no __all__ in __init__.py")

    # AC-3: barrel bypass
    bypass = _domain_internal_import_violations()
    if bypass:
        errors.append(f"AC-3 FAIL: {len(bypass)} barrel bypass(es):")
        for v in bypass[:10]:
            errors.append(f"  {v}")

    # AC-4/5: circular dep
    graph = _build_dep_graph()
    cycle = _find_cycle(graph)
    if cycle:
        errors.append(f"AC-4/5 FAIL: circular dependency between domains: {' -> '.join(cycle)}")

    if errors:
        print("[domain-boundaries] FAIL")
        for e in errors:
            print(f"  {e}")
        return 1

    print(f"[domain-boundaries] OK  ({len(dirs)} domains / no bypass / no cycle)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
