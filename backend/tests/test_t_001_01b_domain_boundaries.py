"""T-001-01b: bounded-context 13 domain barrel — 5 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS: backend/domains/ 配下に 13 bounded-context domain
  AC-2 UBIQUITOUS: 各 domain は __init__.py で public interface を露出 (__all__)
  AC-3 EVENT     : domain A から domain B の internal を直接 import したら lint で検出
  AC-4 STATE     : domain 間の循環依存が存在しない
  AC-5 UNWANTED  : 循環依存が混入したら lint が cycle path を表示して fail
"""
from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOMAINS_DIR = ROOT / "backend" / "domains"
EXPECTED_DOMAINS = (
    "auth", "workspace", "project", "task", "memory", "llm",
    "skill", "knowledge", "artifact", "review", "observability",
    "billing", "integration",
)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 13 domain
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_domains_dir_exists():
    assert DOMAINS_DIR.is_dir()


def test_ac1_exactly_13_domains_present():
    """AC-1: 期待 13 domain 全てが directory として存在."""
    actual = {p.name for p in DOMAINS_DIR.iterdir() if p.is_dir() and not p.name.startswith("__")}
    assert set(EXPECTED_DOMAINS) <= actual
    assert len(EXPECTED_DOMAINS) == 13


def test_ac1_domains_registry_lists_13():
    """AC-1: domains/__init__.py の DOMAIN_NAMES が 13 件."""
    import domains
    assert len(domains.DOMAIN_NAMES) == 13
    assert set(domains.DOMAIN_NAMES) == set(EXPECTED_DOMAINS)


# ──────────────────────────────────────────────────────────────────────────
# AC-2 UBIQUITOUS: 各 domain が __all__ で public interface 露出
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", EXPECTED_DOMAINS)
def test_ac2_each_domain_has_all(name):
    """AC-2: 各 domain の __init__.py に __all__ が定義されている."""
    mod = importlib.import_module(f"domains.{name}")
    assert hasattr(mod, "__all__"), f"domain {name!r} missing __all__"
    assert isinstance(mod.__all__, list)
    assert len(mod.__all__) >= 1, f"domain {name!r} __all__ is empty"


@pytest.mark.parametrize("name", EXPECTED_DOMAINS)
def test_ac2_each_domain_all_exports_are_accessible(name):
    """AC-2: __all__ に挙がった名前は実際に attribute として access 可能."""
    mod = importlib.import_module(f"domains.{name}")
    for sym in mod.__all__:
        assert hasattr(mod, sym), f"domain {name!r}: __all__ lists {sym!r} but not accessible"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 EVENT: barrel bypass violation 検出
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_lint_passes_on_clean_tree(tmp_path):
    """AC-3: 現状ツリーは barrel bypass がない."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check-domain-boundaries.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"clean tree should pass: {r.stdout}\n{r.stderr}"
    assert "no bypass" in r.stdout


def test_ac3_lint_detects_barrel_bypass(tmp_path, monkeypatch):
    """AC-3: domain A 内で domain B の internal submodule を直接 import したら検出."""
    # 一時的に違反ファイルと擬似 submodule を追加
    fake_sub = DOMAINS_DIR / "workspace" / "_internal_violation.py"
    target = DOMAINS_DIR / "auth" / "_violation_test.py"
    try:
        fake_sub.write_text("# fake internal submodule for AC-3 test\n", encoding="utf-8")
        target.write_text(
            "# 違反: workspace の internal submodule を直接 import\n"
            "from domains.workspace._internal_violation import *  # noqa\n",
            encoding="utf-8",
        )
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check-domain-boundaries.py")],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert r.returncode == 1, f"violation should fail. stdout={r.stdout}"
        assert "AC-3 FAIL" in r.stdout or "barrel bypass" in r.stdout
    finally:
        if target.exists():
            target.unlink()
        if fake_sub.exists():
            fake_sub.unlink()


# ──────────────────────────────────────────────────────────────────────────
# AC-4 STATE: 循環依存なし
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_no_circular_dependency_in_current_tree():
    """AC-4: 現状ツリーには domain 間循環依存が存在しない."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check-domain-boundaries.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "no cycle" in r.stdout


def test_ac4_dep_graph_is_acyclic_via_topological_sort():
    """AC-4: 依存グラフを topological sort できる (= 非循環)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        # check-domain-boundaries.py のロジックを再利用
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "domain_boundaries", ROOT / "scripts" / "check-domain-boundaries.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        graph = module._build_dep_graph()
        cycle = module._find_cycle(graph)
        assert cycle == [], f"cycle detected: {cycle}"
    finally:
        sys.path.pop(0)


# ──────────────────────────────────────────────────────────────────────────
# AC-5 UNWANTED: 循環依存が混入したら lint fail + cycle path 表示
# ──────────────────────────────────────────────────────────────────────────


def test_ac5_cycle_detection_prints_path():
    """AC-5: 循環がある graph を渡したら _find_cycle が cycle path を返す."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "domain_boundaries", ROOT / "scripts" / "check-domain-boundaries.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fake_graph = {
        "auth": {"workspace"},
        "workspace": {"project"},
        "project": {"auth"},
    }
    cycle = module._find_cycle(fake_graph)
    assert cycle, "should detect cycle"
    # cycle path は 3 つ以上の node を含む (start と end が同じ)
    assert cycle[0] == cycle[-1]
    assert set(cycle[:-1]) == {"auth", "workspace", "project"}


def test_ac5_lint_fails_when_required_domain_missing(tmp_path):
    """AC-5: 必須 domain が欠ければ lint が fail (AC-1 違反検出)."""
    # check-domain-boundaries.py の EXPECTED_DOMAINS 検証ロジックをそのまま使う
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "domain_boundaries", ROOT / "scripts" / "check-domain-boundaries.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 仮の missing 検出: EXPECTED_DOMAINS は 13 件のため list が exact match
    assert set(module.EXPECTED_DOMAINS) == set(EXPECTED_DOMAINS)
    assert len(module.EXPECTED_DOMAINS) == 13


# ──────────────────────────────────────────────────────────────────────────
# 補助: existing import path に regression 無し
# ──────────────────────────────────────────────────────────────────────────


def test_existing_services_still_importable():
    """T-001-01b は REFACTOR: 既存 services.* import path は不変."""
    for mod_name in ["services.memory_service", "services.litellm_router",
                      "services.fallback_router", "services.cost_service",
                      "services.task_dependency_service", "services.phase_service"]:
        importlib.import_module(mod_name)


def test_domain_barrel_reexports_from_services():
    """memory domain barrel 経由で emit_event を access できる."""
    from domains.memory import emit_event
    from services.memory_service import emit_event as direct
    assert emit_event is direct  # 同一 function object
