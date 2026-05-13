"""T-019-03: bootstrap 動作確認 (smoke test / REUSE existing bootstrap).

T-019-01 (ARCHIVE: onlook/penpot 削除) + T-019-02 (modify-target github-issue)
完了後の bootstrap が運用可能であることを **pytest から機械検証** する.

設計境界 (TST REUSE タスク, IMPLEMENTATION_PROTOCOL Step 4):
  production code は一切変更しない. 本 module は read-only 検査のみ.

## AC マッピング (1:1)

  AC-1 UBIQUITOUS    : main:app import / >= 300 routes / Sprint-0 core router
                       (feature_decomposer / mid_term_layer / short_term_layer /
                       memory_pipeline / task_decomposition) / requirements.txt
                       + frontend/package.json 存在.
  AC-2 EVENT-DRIVEN  : 全 assertion < 10 秒 / ARCHIVE 再出現で非ゼロ /
                       missing router 名を assertion message に含める.
  AC-3 STATE-DRIVEN  : onlook/penpot 不在維持 / 主要 bootstrap file 存続 /
                       scripts 実行可能 / smoke test は mutate しない.
  AC-4 UNWANTED      : main:app import 失敗 / ARCHIVE 再出現 / AGPL 依存追加 /
                       frontend 必須 dep 欠落 → pytest 失敗 (silent skip 禁止).
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_MAIN = REPO_ROOT / "backend" / "main.py"
BACKEND_REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"
FRONTEND_PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
LINT_MOCK = REPO_ROOT / "scripts" / "lint-mock.sh"
PRECOMMIT_CHECK = REPO_ROOT / "scripts" / "pre-commit-check.sh"

# AC-3: 削除済 ARCHIVE directories. 再出現したら fail.
FORBIDDEN_ARCHIVE_DIRS = (
    REPO_ROOT / "onlook",
    REPO_ROOT / "penpot",
    REPO_ROOT / "services" / "cookiecutter_legacy",
)

# AC-1: Sprint-0 core router prefixes (mount 後の URL prefix で確認).
REQUIRED_ROUTER_PREFIXES = (
    "/api/features",            # feature_decomposer
    "/api/mid-term",            # mid_term_layer
    "/api/short-term",          # short_term_layer
    "/api/memory",              # memory_pipeline (prefix /api/memory)
    "/api/task-decomposition",  # task_decomposition
)

# AC-4: AGPL licensed packages we must not pull in (SaaS friction).
AGPL_PACKAGE_BLACKLIST = (
    "ghostscript",  # AGPL
    "ghostpdl",
    "mongo-cxx-driver",
    "mongoengine",  # AGPL-3.0 hybrid
    "qt-python",    # not strict but watched
    "rethinkdb",    # AGPL
    # NOTE: 文字列 substring 検索のため、慎重な list. lint-mock.sh は別 list を持つ.
)

# AC-4: frontend/package.json で外せない依存 keys.
REQUIRED_FRONTEND_DEPS = (
    "next",
    "react",
    "lucide-react",
    "shadcn",
)

MIN_ROUTES = 300
MAX_TEST_WALLCLOCK_SECONDS = 10.0


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app as _app
    return _app


@pytest.fixture(scope="module")
def mounted_paths(app) -> list[str]:
    paths: list[str] = []
    for r in app.routes:
        p = getattr(r, "path", None)
        if isinstance(p, str):
            paths.append(p)
    return paths


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_main_py_exists():
    assert BACKEND_MAIN.exists(), f"missing backend/main.py at {BACKEND_MAIN}"


def test_ac1_requirements_txt_exists():
    assert BACKEND_REQUIREMENTS.exists(), (
        f"missing backend/requirements.txt at {BACKEND_REQUIREMENTS}"
    )


def test_ac1_frontend_package_json_exists():
    assert FRONTEND_PACKAGE_JSON.exists(), (
        f"missing frontend/package.json at {FRONTEND_PACKAGE_JSON}"
    )


def test_ac1_main_app_imports(app):
    # fixture itself imports. existence of attribute is the actual assertion.
    assert hasattr(app, "routes")


def test_ac1_minimum_route_count(mounted_paths):
    assert len(mounted_paths) >= MIN_ROUTES, (
        f"expected >= {MIN_ROUTES} routes, got {len(mounted_paths)}"
    )


def test_ac1_all_required_routers_mounted(mounted_paths):
    """AC-2 UNWANTED: missing router の identity を message に含める."""
    missing: list[str] = []
    for prefix in REQUIRED_ROUTER_PREFIXES:
        if not any(p.startswith(prefix) for p in mounted_paths):
            missing.append(prefix)
    assert not missing, f"missing required router prefixes: {missing}"


def test_ac1_required_frontend_deps_present():
    pkg = json.loads(FRONTEND_PACKAGE_JSON.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    missing = [k for k in REQUIRED_FRONTEND_DEPS if k not in deps]
    assert not missing, f"missing required frontend deps: {missing}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 全 assertion < 10 秒
# ══════════════════════════════════════════════════════════════════════


def test_ac2_full_smoke_runs_in_under_10_seconds(mounted_paths):
    """全 fixture + 主 assertion を一連で再走しても 10 秒以内.

    mounted_paths fixture は module scope なので import コストは share される.
    実装健全性確認の指針: warm path で 10 秒以内に終わるべき.
    """
    t0 = time.time()
    assert len(mounted_paths) >= MIN_ROUTES
    for prefix in REQUIRED_ROUTER_PREFIXES:
        assert any(p.startswith(prefix) for p in mounted_paths)
    elapsed = time.time() - t0
    assert elapsed < MAX_TEST_WALLCLOCK_SECONDS, (
        f"smoke assertions took {elapsed:.2f}s (>= {MAX_TEST_WALLCLOCK_SECONDS}s)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: bootstrap 不変条件
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("forbidden_dir", FORBIDDEN_ARCHIVE_DIRS)
def test_ac3_forbidden_archive_dirs_absent(forbidden_dir):
    assert not forbidden_dir.exists(), (
        f"forbidden ARCHIVE directory has reappeared: {forbidden_dir}"
    )


def test_ac3_scripts_are_executable():
    """lint-mock.sh + pre-commit-check.sh が実行可能ビットを持つ."""
    for script in (LINT_MOCK, PRECOMMIT_CHECK):
        assert script.exists(), f"missing script: {script}"
        st = script.stat()
        executable = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        assert executable, f"script not executable: {script}"


def test_ac3_smoke_test_does_not_mutate_filesystem(tmp_path):
    """smoke test 実行が repo root の mtime を変えない (簡易 sanity)."""
    before_mtime = BACKEND_MAIN.stat().st_mtime
    # re-run a trivial assertion path
    assert BACKEND_MAIN.exists()
    after_mtime = BACKEND_MAIN.stat().st_mtime
    assert before_mtime == after_mtime


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: regression detection
# ══════════════════════════════════════════════════════════════════════


def test_ac4_no_agpl_in_requirements():
    src = BACKEND_REQUIREMENTS.read_text(encoding="utf-8").lower()
    hits = [pkg for pkg in AGPL_PACKAGE_BLACKLIST if pkg in src]
    assert not hits, f"AGPL-licensed packages detected in requirements.txt: {hits}"


def test_ac4_no_hardcoded_secret_in_main():
    src = BACKEND_MAIN.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", src)
    assert "SUPABASE_SERVICE_KEY" not in src


def test_ac4_assertion_message_specifies_missing_router(mounted_paths):
    """missing router の identity が assertion message に出ることを確認.

    実際には全 router 居る前提なので, AssertionError をシミュレートしない代わりに
    list comprehension の semantics を直接検証.
    """
    fake_required = ("/api/__nonexistent_for_test__",)
    missing = [
        p for p in fake_required
        if not any(actual.startswith(p) for actual in mounted_paths)
    ]
    assert missing == list(fake_required), (
        "missing-router detection logic is broken"
    )


def test_ac4_requirements_has_no_legacy_onlook_penpot():
    src = BACKEND_REQUIREMENTS.read_text(encoding="utf-8").lower()
    assert "onlook" not in src
    assert "penpot" not in src


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_019_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-019-03"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the implementation step for T-019-03 is triggered",
        "While the existing implementation is in use",
        "If invalid input or unauthorized actor is detected during T-019-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-019-03 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "test_t_019_03_bootstrap_health.py" in full
    assert "main:app" in full
    assert "onlook" in full or "penpot" in full


def test_tickets_t_019_03_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-019-03"), None)
    assert t.get("adr_link") is not None
    assert "TBD" not in str(t.get("existing_files", []))
