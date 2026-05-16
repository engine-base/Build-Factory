#!/usr/bin/env python3
"""pytest entrypoint for T-FOUNDATION-02 (scripts/lint-mock-impl-diff.py).

Exposes the 4 fixture cases (aligned / drifted / missing_impl / missing_meta) as
individual pytest functions plus an end-to-end CLI smoke test. Each test maps 1:1
to a Tier 2 functional AC in docs/audit/2026-05-16_v3/T-FOUNDATION-02.md.

Run:
    pytest scripts/tests/test-lint-mock-impl-diff.py -v
or:
    python3 scripts/tests/test-lint-mock-impl-diff.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

# scripts/lint-mock-impl-diff.py を import (ハイフン入りファイル名のため importlib 経由)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "lint-mock-impl-diff.py"
_spec = importlib.util.spec_from_file_location("lint_mock_impl_diff", _SCRIPT_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise RuntimeError(f"failed to load {_SCRIPT_PATH}")
_lmd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lmd)

FIXTURES = _REPO_ROOT / "scripts" / "tests" / "fixtures" / "mock-impl-diff"


def test_aligned_yields_no_drift() -> None:
    """Tier 2 AC-1: UBIQUITOUS — 5 meta fields extracted; identical -> 0 drift."""
    mock = _lmd.extract_mock_meta(FIXTURES / "mock-aligned.html")
    impl, _ = _lmd.extract_impl_meta(FIXTURES / "impl-aligned.tsx")
    assert sorted(mock.keys()) == sorted(_lmd.META_FIELDS)
    drifts = _lmd.diff_one_screen("S-901", mock, impl)
    assert drifts == []


def test_missing_impl_yields_error() -> None:
    """Tier 2 AC-2: EVENT-DRIVEN — impl file absent -> missing_in_impl error."""
    mock = _lmd.extract_mock_meta(FIXTURES / "mock-aligned.html")
    drifts = _lmd.diff_one_screen("S-901", mock, None)
    assert len(drifts) == 1
    assert drifts[0]["kind"] == "missing_in_impl"
    assert drifts[0]["severity"] == "error"


def test_value_mismatch_yields_warning() -> None:
    """Tier 2 AC-3: EVENT-DRIVEN — value differs -> warning drift entries."""
    mock = _lmd.extract_mock_meta(FIXTURES / "mock-drifted.html")
    impl, _ = _lmd.extract_impl_meta(FIXTURES / "impl-drifted.tsx")
    drifts = _lmd.diff_one_screen("S-902", mock, impl)
    value_mismatch = [d for d in drifts if d["kind"] == "value_mismatch"]
    assert len(value_mismatch) == 4
    for d in value_mismatch:
        assert d["severity"] == "warning"
        assert d["mock_value"] is not None
        assert d["impl_value"] is not None
        assert d["mock_value"] != d["impl_value"]


def test_missing_meta_in_mock_yields_error() -> None:
    """Tier 2 AC-5: UNWANTED — mock lacks required meta -> error entries."""
    impl, _ = _lmd.extract_impl_meta(FIXTURES / "impl-aligned.tsx")
    drifts = _lmd.diff_one_screen("S-901", {}, impl)
    missing_in_mock = [d for d in drifts if d["kind"] == "missing_field_in_mock"]
    assert len(missing_in_mock) == 5
    for d in missing_in_mock:
        assert d["severity"] == "error"


def test_strict_mode_exits_nonzero_on_drift(tmp_path: Path) -> None:
    """Tier 2 AC-4: OPTIONAL --strict + drift -> exit 1."""
    # Build a tiny scratch mock dir + impl dir with one drifted pair
    mock_dir = tmp_path / "mocks"
    impl_dir = tmp_path / "impl"
    (mock_dir).mkdir()
    (impl_dir / "screens").mkdir(parents=True)
    (mock_dir / "S-902.html").write_text(
        (FIXTURES / "mock-drifted.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (impl_dir / "screens" / "S-902.tsx").write_text(
        (FIXTURES / "impl-drifted.tsx").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--mock-dir",
            str(mock_dir),
            "--impl-dir",
            str(impl_dir),
            "--strict",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["drift_count"] > 0


def test_self_test_flag_runs_4_cases() -> None:
    """Tier 2 AC-6: STATE-DRIVEN --self-test verifies 4 fixtures exit 0."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(_SCRIPT_PATH), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL 4 CASES PASS" in result.stdout


if __name__ == "__main__":  # pragma: no cover
    import tempfile

    failures: list[str] = []
    test_fns = [
        test_aligned_yields_no_drift,
        test_missing_impl_yields_error,
        test_value_mismatch_yields_warning,
        test_missing_meta_in_mock_yields_error,
        test_self_test_flag_runs_4_cases,
    ]
    for fn in test_fns:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
        except AssertionError as e:
            failures.append(f"{fn.__name__}: {e}")
            print(f"[FAIL] {fn.__name__}: {e}")

    with tempfile.TemporaryDirectory() as td:
        try:
            test_strict_mode_exits_nonzero_on_drift(Path(td))
            print("[PASS] test_strict_mode_exits_nonzero_on_drift")
        except AssertionError as e:
            failures.append(f"test_strict_mode_exits_nonzero_on_drift: {e}")
            print(f"[FAIL] test_strict_mode_exits_nonzero_on_drift: {e}")

    sys.exit(1 if failures else 0)
