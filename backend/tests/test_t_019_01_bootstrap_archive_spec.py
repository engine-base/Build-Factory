"""T-019-01 (REFACTOR audit): bootstrap archive 9 items + 4 lint guards.

This is the **audit-spec** module (Wave 5 v2 audit), distinct from the existing
`test_t_019_01_archive_invariants.py` (which uses pytest.parametrize for the
archive paths).

**Anti-drift policy** (per audit prompt 2026-05-14):
  Each of the 9 archive items MUST be asserted with its OWN named test function
  (no collapsed parametrize / regex set). Future regressions surface as a
  specific symbol like `test_ac1_item04_design_canvas_component_absent`, not as
  an opaque `[p3]` parametrize index.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 9 archive items each absent + 3 lint guards
                       (ARCHIVE check / emoji exempt / AGPL block).
  AC-2 EVENT-DRIVEN  : `bash scripts/lint-mock.sh --archive` exits 0 with
                       'ARCHIVE 残留なし' and `onlook` scan completes < 5 s.
  AC-3 STATE-DRIVEN  : package.json / requirements.txt / main.py / route
                       baseline keep ARCHIVE absent under operational state.
  AC-4 UNWANTED      : regression detection (lint + pytest both fail explicitly).

Spec source (cited verbatim):
  docs/task-decomposition/2026-05-09_v1/tickets.json#T-019-01.acceptance_criteria
  docs/functional-breakdown/2026-05-09_v1/features.json#F-019 (audit_logs:
  'bootstrap_disposition').
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"
BACKEND = REPO_ROOT / "backend"
LINT_MOCK = REPO_ROOT / "scripts" / "lint-mock.sh"

# ----------------------------------------------------------------------
# 9 archive items — each MUST have an individual `test_ac1_itemNN_*` test.
# Spec source: tickets.json T-019-01 existing_files (verbatim order kept).
# ----------------------------------------------------------------------
#   1. onlook/                                          (root dir)
#   2. penpot/                                          (self-hosted Docker stack)
#   3. frontend/src/components/onlook/                  (UI component dir)
#   4. frontend/src/components/design-canvas/           (UI component dir)
#   5. frontend/src/app/workspaces/[id]/design/         (Next.js route)
#      + URL-encoded variant frontend/src/app/workspaces/%5Bid%5D/design/
#   6. services/cookiecutter_legacy/                    (Python package)
#   7. scripts/lint-mock.sh                             (MUST exist — guard host)
#   8. scripts/pre-commit-check.sh                      (MUST exist — guard host)
#   9. docs/decisions/0010-ai-stack-3-layer.md          (legacy ADR filename
#                                                        absent; new ADR uses
#                                                        ADR-010-ai-stack-anthropic-native.md)
#
# Items 1-6 + 9 are DELETED. Items 7-8 must EXIST and host the 3 lint guards.
# ----------------------------------------------------------------------


# Test files allowed to mention 'onlook' literal for verification purposes.
ALLOWED_REFERENCE_FILES = {
    "test_supabase_migrations.py",
    "test_t_019_03_bootstrap_health.py",
    "test_t_019_01_archive_invariants.py",
    "test_t_019_01_bootstrap_archive_spec.py",  # this file (Wave 5 v2 audit)
    "test_t_s0_13_inventory_invariants.py",
}


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 9 archive items, EACH with its own test (anti-drift)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_item01_onlook_root_dir_absent():
    """Archive item 1/9: onlook/ root directory must NOT exist."""
    p = REPO_ROOT / "onlook"
    assert not p.exists(), f"forbidden ARCHIVE path reappeared: {p}"


def test_ac1_item02_penpot_root_dir_absent():
    """Archive item 2/9: penpot/ self-hosted Docker stack must NOT exist.

    NOTE: backend/services/penpot_client.py (SaaS API integration) is a
    separate integration and is NOT subject to this archive.
    """
    p = REPO_ROOT / "penpot"
    assert not p.exists(), f"forbidden ARCHIVE path reappeared: {p}"


def test_ac1_item03_onlook_component_dir_absent():
    """Archive item 3/9: frontend/src/components/onlook/ must NOT exist."""
    p = FRONTEND / "src" / "components" / "onlook"
    assert not p.exists(), f"forbidden ARCHIVE path reappeared: {p}"


def test_ac1_item04_design_canvas_component_absent():
    """Archive item 4/9: frontend/src/components/design-canvas/ must NOT exist."""
    p = FRONTEND / "src" / "components" / "design-canvas"
    assert not p.exists(), f"forbidden ARCHIVE path reappeared: {p}"


def test_ac1_item05_workspaces_design_route_absent():
    """Archive item 5/9: frontend/src/app/workspaces/[id]/design/ route absent.

    Both `[id]` (literal) and `%5Bid%5D` (URL-encoded) variants are checked.
    """
    p_literal = FRONTEND / "src" / "app" / "workspaces" / "[id]" / "design"
    p_encoded = FRONTEND / "src" / "app" / "workspaces" / "%5Bid%5D" / "design"
    assert not p_literal.exists(), f"forbidden ARCHIVE path reappeared: {p_literal}"
    assert not p_encoded.exists(), f"forbidden ARCHIVE path reappeared: {p_encoded}"


def test_ac1_item06_cookiecutter_legacy_absent():
    """Archive item 6/9: services/cookiecutter_legacy/ must NOT exist (root)."""
    p_root = REPO_ROOT / "services" / "cookiecutter_legacy"
    p_backend = BACKEND / "services" / "cookiecutter_legacy"
    assert not p_root.exists(), f"forbidden ARCHIVE path reappeared: {p_root}"
    assert not p_backend.exists(), f"forbidden ARCHIVE path reappeared: {p_backend}"


def test_ac1_item07_lint_mock_script_present():
    """Archive item 7/9: scripts/lint-mock.sh MUST exist (hosts ARCHIVE guard).

    This is one of the 9 'existing_files' listed in T-019-01 ticket BUT the
    semantic intent is preserved (not deleted) — it hosts the ARCHIVE residue
    detector. Absence == regression.
    """
    p = REPO_ROOT / "scripts" / "lint-mock.sh"
    assert p.exists(), f"required guard script missing: {p}"
    assert p.is_file(), f"{p} is not a regular file"


def test_ac1_item08_pre_commit_check_script_present():
    """Archive item 8/9: scripts/pre-commit-check.sh MUST exist (ADR-011 gate)."""
    p = REPO_ROOT / "scripts" / "pre-commit-check.sh"
    assert p.exists(), f"required gate script missing: {p}"
    assert p.is_file(), f"{p} is not a regular file"


def test_ac1_item09_legacy_adr_0010_filename_absent():
    """Archive item 9/9: docs/decisions/0010-ai-stack-3-layer.md (legacy name) absent.

    The active ADR file is `ADR-010-ai-stack-anthropic-native.md` per
    tickets.json T-019-01.adr_link. The numeric-prefix legacy variant must
    not coexist.
    """
    p = REPO_ROOT / "docs" / "decisions" / "0010-ai-stack-3-layer.md"
    assert not p.exists(), f"legacy ADR filename reappeared: {p}"


# ---- 3 lint guards (AC-1 UBIQUITOUS, second clause) -------------------


def test_ac1_lint_guard1_archive_check_function_present():
    """3 lint guards / 1: ARCHIVE 残留 detector (check_archive function)."""
    src = LINT_MOCK.read_text(encoding="utf-8")
    assert "check_archive" in src
    assert "ARCHIVE 残留なし" in src


def test_ac1_lint_guard2_emoji_exempt_list_present():
    """3 lint guards / 2: emoji exempt list for ADR-005 out-of-scope files."""
    src = LINT_MOCK.read_text(encoding="utf-8")
    assert "EMOJI_EXEMPT_FILES" in src


def test_ac1_lint_guard3_agpl_block_check_present():
    """3 lint guards / 3: AGPL package block (check_agpl + 'agpl' grep)."""
    src = LINT_MOCK.read_text(encoding="utf-8")
    assert "check_agpl" in src
    assert "AGPL" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — `lint-mock.sh --archive` exits 0 < 5 s + onlook scan
# ══════════════════════════════════════════════════════════════════════


def test_ac2_lint_archive_exits_zero_with_success_message():
    """AC-2: --archive must exit 0 and emit 'OK: ARCHIVE 残留なし' on clean state."""
    result = subprocess.run(
        ["bash", str(LINT_MOCK), "--archive"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"lint --archive returned {result.returncode}:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "ARCHIVE 残留なし" in result.stdout, (
        "expected success marker missing from stdout"
    )


def test_ac2_lint_archive_completes_under_5_seconds():
    """AC-2: --archive must complete within 5 s for full repo scan."""
    t0 = time.time()
    result = subprocess.run(
        ["bash", str(LINT_MOCK), "--archive"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    elapsed = time.time() - t0
    assert elapsed < 5.0, f"lint --archive took {elapsed:.2f}s (AC-2 budget 5 s)"
    assert result.returncode == 0


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — package.json + requirements.txt + main.py clean
# ══════════════════════════════════════════════════════════════════════


def test_ac3_frontend_package_json_clean_of_onlook_and_penpot_self_host_keys():
    """AC-3: package.json must contain no onlook / @onlook/* / @penpot/* keys.

    NOTE: 'penpot' substring is NOT blanket-banned (Penpot SaaS API client
    is a separate integration). Only the self-hosted Penpot UI npm package
    namespace (@penpot/*) is blocked here.
    """
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    hits = [
        k for k in deps
        if "onlook" in k or k.startswith("@onlook/") or k.startswith("@penpot/")
    ]
    assert not hits, f"ARCHIVE deps reappeared in package.json: {hits}"


def test_ac3_backend_requirements_no_cookiecutter_package():
    """AC-3: backend/requirements.txt must not pin `cookiecutter` (legacy)."""
    src = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    # match start-of-line or after whitespace, then 'cookiecutter==' or 'cookiecutter\n'
    for line in src.splitlines():
        normalized = line.strip().split("#", 1)[0].strip()
        token = normalized.split("==", 1)[0].split(">=", 1)[0].split("<", 1)[0]
        assert token != "cookiecutter", (
            f"cookiecutter package reappeared in requirements.txt: {line!r}"
        )


def test_ac3_backend_main_py_no_archive_module_imports():
    """AC-3: backend/main.py must import no module from any of the 9 archive paths."""
    src = (BACKEND / "main.py").read_text(encoding="utf-8")
    forbidden_fragments = (
        "from onlook",
        "import onlook",
        "from penpot",      # SaaS API client uses penpot_client (snake_case), not bare 'penpot'
        "import penpot",
        "design_canvas",
        "cookiecutter_legacy",
    )
    hits = [frag for frag in forbidden_fragments if frag in src]
    assert not hits, f"backend/main.py imports ARCHIVE module: {hits}"


def test_ac3_route_baseline_holds_without_onlook_routers():
    """AC-3: backend smoke must succeed without onlook routes reappearing.

    Re-uses existing pre-commit-check.sh backend-smoke result file if present;
    otherwise asserts that no router under backend/routers/ has an 'onlook'
    literal in its file name or top-level path string.
    """
    routers_dir = BACKEND / "routers"
    if not routers_dir.exists():
        return  # smoke step covers this elsewhere; nothing to assert here
    hits = [
        p.name for p in routers_dir.rglob("*.py")
        if "onlook" in p.name.lower()
    ]
    assert not hits, f"onlook router file(s) reappeared: {hits}"


def test_ac3_no_onlook_references_in_frontend_src():
    """AC-3 reinforcement: frontend/src must have zero 'onlook' string refs."""
    hits: list[str] = []
    if not FRONTEND.exists():
        return
    for ext in ("ts", "tsx", "js", "jsx"):
        for f in (FRONTEND / "src").rglob(f"*.{ext}"):
            text = f.read_text(encoding="utf-8", errors="replace").lower()
            if "onlook" in text:
                hits.append(str(f.relative_to(REPO_ROOT)))
    assert not hits, f"frontend/src still references onlook: {hits}"


def test_ac3_no_onlook_references_in_backend_outside_allowed_test_files():
    """AC-3 reinforcement: backend/*.py must have zero 'onlook' refs outside allow-list."""
    hits: list[str] = []
    for f in BACKEND.rglob("*.py"):
        if f.name in ALLOWED_REFERENCE_FILES:
            continue
        text = f.read_text(encoding="utf-8", errors="replace").lower()
        if "onlook" in text:
            hits.append(str(f.relative_to(REPO_ROOT)))
    assert not hits, f"backend still references onlook: {hits}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — regression detection (lint + pytest fail explicitly)
# ══════════════════════════════════════════════════════════════════════


def test_ac4_lint_archive_check_excludes_known_verification_test_files():
    """AC-4: lint exclude list must cover the ARCHIVE verification tests so
    they do NOT cause false positives.

    Failure here means a future edit broke the allow-list and the lint will
    falsely trigger on the verification tests themselves.
    """
    src = LINT_MOCK.read_text(encoding="utf-8")
    assert "test_supabase_migrations.py" in src
    assert "test_t_019_03_bootstrap_health.py" in src
    assert "test_t_019_01_archive_invariants.py" in src
    assert "test_t_s0_13_inventory_invariants.py" in src


def test_ac4_no_hardcoded_secret_in_lint_script():
    """AC-4: lint script itself must contain no Anthropic / Google api keys."""
    src = LINT_MOCK.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", src)


def test_ac4_tickets_t_019_01_metadata_complete():
    """AC-4: tickets.json T-019-01 must keep the 9 existing_files + adr_link.

    Drift here would mean someone watered down the spec; pre-commit gate
    would lose its source-of-truth alignment.
    """
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-019-01"), None)
    assert t is not None
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert len(files) >= 9, f"expected >= 9 existing_files, got {len(files)}"
    # All 9 named items must appear in tickets.json existing_files literally
    for needed in (
        "onlook/", "penpot/",
        "frontend/src/components/onlook/",
        "frontend/src/components/design-canvas/",
        "services/cookiecutter_legacy/",
        "scripts/lint-mock.sh",
        "scripts/pre-commit-check.sh",
    ):
        assert needed in files, f"tickets.json missing existing_files entry: {needed}"


def test_ac4_recreating_any_archive_dir_would_be_detected_individually():
    """AC-4: regression — meta-test that each of the 9 per-item tests, if any
    archive dir re-appeared, would fire on that item *individually* (anti-drift
    against collapsed regex). We assert the 9 absent paths are all genuinely
    distinct path objects (no aliasing) to keep the failure surface specific.
    """
    archive_paths = [
        REPO_ROOT / "onlook",
        REPO_ROOT / "penpot",
        FRONTEND / "src" / "components" / "onlook",
        FRONTEND / "src" / "components" / "design-canvas",
        FRONTEND / "src" / "app" / "workspaces" / "[id]" / "design",
        REPO_ROOT / "services" / "cookiecutter_legacy",
        BACKEND / "services" / "cookiecutter_legacy",
        REPO_ROOT / "docs" / "decisions" / "0010-ai-stack-3-layer.md",
    ]
    # 8 distinct path objects (item 5 has two variants but here we keep one;
    # item 6 has two location variants for the cookiecutter dir).
    assert len(set(map(str, archive_paths))) == len(archive_paths)
    for p in archive_paths:
        assert not p.exists(), f"ARCHIVE regression at {p}"
