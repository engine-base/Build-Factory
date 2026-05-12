"""T-S0-03: license-check.yml (AGPL 防御 + ADR-010 機械的ガード CI 実効化).

AC マッピング (1:1 テスト):
  AC-1 UBIQUITOUS    : workflow が PR + push に動き AGPL/ADR-010 違反で fail.
                       detection ロジックは既存 scripts に委譲 (REUSE).
  AC-2 EVENT-DRIVEN  : 5 lint-mock invocation + 1 validate-tickets を順番に実行.
  AC-3 STATE-DRIVEN  : workflow は read-only (state mutate しない).
  AC-4 UNWANTED      : AGPL 検出 / LangGraph import / tickets issues > 0 で fail.

本テストは workflow yaml の **構造** を検証する (実行は GitHub Actions が担う).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "license-check.yml"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_yaml(workflow_text):
    return yaml.safe_load(workflow_text)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: workflow が存在し PR + push に動く / detection は委譲
# ══════════════════════════════════════════════════════════════════════


def test_ac1_workflow_file_exists():
    assert WORKFLOW_PATH.exists(), f"missing: {WORKFLOW_PATH}"


def test_ac1_workflow_valid_yaml(workflow_yaml):
    assert isinstance(workflow_yaml, dict)
    assert "name" in workflow_yaml
    # PyYAML は YAML の `on:` キーを True (boolean) としてパースする (バグ的仕様)
    # GitHub Actions では "on" として動く. どちらの key 名でも存在を確認.
    assert ("on" in workflow_yaml) or (True in workflow_yaml)


def _get_on(wf):
    """PyYAML は `on:` を True にパースするので両対応."""
    return wf.get("on", wf.get(True))


def test_ac1_workflow_triggers_on_pull_request_to_main(workflow_yaml):
    on = _get_on(workflow_yaml)
    assert "pull_request" in on
    assert "main" in on["pull_request"]["branches"]


def test_ac1_workflow_triggers_on_push_to_main(workflow_yaml):
    on = _get_on(workflow_yaml)
    assert "push" in on
    assert "main" in on["push"]["branches"]


def test_ac1_workflow_supports_manual_dispatch(workflow_yaml):
    """workflow_dispatch で手動実行可能 (緊急時 / debugging)."""
    on = _get_on(workflow_yaml)
    assert "workflow_dispatch" in on


def test_ac1_workflow_name_describes_purpose(workflow_yaml):
    assert "license-check" in workflow_yaml["name"]


def test_ac1_detection_logic_delegated_to_existing_scripts(workflow_text):
    """workflow が detection ロジックを再実装していないことを確認 (REUSE)."""
    # 既存 script を呼ぶこと
    assert "scripts/lint-mock.sh" in workflow_text
    assert "scripts/validate-tickets.py" in workflow_text
    # workflow 内で inline grep / pip license 検査ロジックを書いていないこと
    # (これらは scripts/ 内で行われる)
    assert "pip-licenses" not in workflow_text
    assert "license-checker" not in workflow_text


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 5 lint-mock + 1 validate-tickets 実行
# ══════════════════════════════════════════════════════════════════════


def _get_steps(workflow_yaml):
    jobs = workflow_yaml["jobs"]
    assert len(jobs) >= 1
    main_job = next(iter(jobs.values()))
    return main_job["steps"]


def test_ac2_workflow_has_jobs(workflow_yaml):
    assert "jobs" in workflow_yaml
    assert len(workflow_yaml["jobs"]) >= 1


def test_ac2_main_job_runs_ubuntu(workflow_yaml):
    main_job = next(iter(workflow_yaml["jobs"].values()))
    assert "ubuntu" in main_job["runs-on"]


def test_ac2_main_job_has_timeout(workflow_yaml):
    """5 lint + 1 validate で 5 分以内が妥当."""
    main_job = next(iter(workflow_yaml["jobs"].values()))
    assert "timeout-minutes" in main_job
    assert main_job["timeout-minutes"] <= 10


def test_ac2_workflow_uses_python_311(workflow_yaml):
    steps = _get_steps(workflow_yaml)
    setup_py = next((s for s in steps if "setup-python" in str(s.get("uses", ""))), None)
    assert setup_py is not None, "actions/setup-python missing"
    assert setup_py["with"]["python-version"] == "3.11"


def test_ac2_workflow_uses_checkout_v4(workflow_yaml):
    steps = _get_steps(workflow_yaml)
    checkout = next((s for s in steps if "checkout" in str(s.get("uses", ""))), None)
    assert checkout is not None, "actions/checkout missing"
    assert "@v4" in checkout["uses"]


def test_ac2_all_5_lint_mock_invocations_present(workflow_text):
    """AC-2 EVENT-DRIVEN: --agpl / --no-langgraph / --emoji / --secrets / --archive"""
    required_flags = ["--agpl", "--no-langgraph", "--emoji", "--secrets", "--archive"]
    for flag in required_flags:
        assert f"lint-mock.sh {flag}" in workflow_text, (
            f"missing lint-mock.sh {flag} invocation in workflow"
        )


def test_ac2_validate_tickets_invocation_present(workflow_text):
    assert "validate-tickets.py" in workflow_text


def test_ac2_invocations_in_declared_order(workflow_yaml):
    """AC-2 spec: in sequence: --agpl, --no-langgraph, --emoji, --secrets, --archive
    + validate-tickets. parsed steps から actual run command を抽出して順序確認.
    (workflow_text を full-text search すると header comment にも引っかかるため)
    """
    steps = _get_steps(workflow_yaml)
    expected = ["--agpl", "--no-langgraph", "--emoji", "--secrets", "--archive",
                "validate-tickets.py"]
    found_positions: dict[str, int] = {}
    for idx, step in enumerate(steps):
        run = step.get("run", "")
        for token in expected:
            if token in run and token not in found_positions:
                found_positions[token] = idx
    for token in expected:
        assert token in found_positions, f"missing step for: {token}"
    actual_order = [t for t, _ in sorted(found_positions.items(), key=lambda x: x[1])]
    assert actual_order == expected, (
        f"step order mismatch:\n  expected: {expected}\n  actual:   {actual_order}"
    )


# ══════════════════════════════════════════════════════════════════════
# Follow-up (T-025-01 #145 / T-025-02 #146): EARS AC JSON Schema validator step
# ══════════════════════════════════════════════════════════════════════


def test_followup_workflow_runs_validate_ears_ac(workflow_yaml):
    """EARS AC JSON Schema validation step が workflow に追加されている."""
    steps = _get_steps(workflow_yaml)
    runs = [s.get("run", "") for s in steps if "run" in s]
    assert any("validate-ears-ac.py" in r for r in runs), (
        "license-check.yml must run scripts/validate-ears-ac.py "
        "(T-S0-03 follow-up after T-025-01)"
    )


def test_followup_installs_jsonschema_before_validation(workflow_yaml):
    """jsonschema install step が validate-ears-ac.py の前にある."""
    steps = _get_steps(workflow_yaml)
    install_idx = next(
        (i for i, s in enumerate(steps)
         if "pip install" in s.get("run", "") and "jsonschema" in s.get("run", "")),
        -1,
    )
    validate_idx = next(
        (i for i, s in enumerate(steps)
         if "validate-ears-ac.py" in s.get("run", "")),
        -1,
    )
    assert install_idx >= 0, "jsonschema install step missing"
    assert validate_idx >= 0, "validate-ears-ac.py step missing"
    assert install_idx < validate_idx, "jsonschema must be installed BEFORE validation"


def test_followup_summary_includes_ears_outcome():
    """Summary step が EARS schema 結果に言及."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    summary_section = text.split("name: Summary")[1] if "name: Summary" in text else ""
    assert "EARS" in summary_section or "ears" in summary_section


def test_followup_local_validate_ears_ac_passes():
    """ローカル baseline: validate-ears-ac.py が exit 0."""
    r = subprocess.run(
        [sys.executable, "scripts/validate-ears-ac.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, (
        f"validate-ears-ac baseline broken: {r.stdout[-1000:]}\n{r.stderr[-500:]}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only (state mutate しない)
# ══════════════════════════════════════════════════════════════════════


def test_ac3_workflow_has_read_only_permissions(workflow_yaml):
    """contents: read のみ (write 不要)."""
    perms = workflow_yaml.get("permissions", {})
    assert perms.get("contents") == "read"


def test_ac3_workflow_does_not_mutate_repo(workflow_text):
    """git push / commit / create-pull-request 等の mutating action を含まない."""
    mutating_actions = [
        "git push",
        "git commit",
        "git-auto-commit",
        "stefanzweifel/git-auto-commit-action",
        "create-pull-request",
        "peter-evans/create-pull-request",
    ]
    for action in mutating_actions:
        assert action not in workflow_text, (
            f"workflow must not contain mutating action: {action}"
        )


def test_ac3_workflow_no_db_writes_in_steps(workflow_text):
    """audit_logs / DB に書き込むコマンドを含まない (state mutate なし)."""
    assert "psql" not in workflow_text
    assert "alembic upgrade" not in workflow_text
    assert "INSERT INTO" not in workflow_text


def test_ac3_existing_scripts_referenced_unchanged():
    """workflow が参照する 3 scripts が repo に存在する (path 不変)."""
    for relpath in (
        "scripts/lint-mock.sh",
        "scripts/validate-tickets.py",
        "scripts/pre-commit-check.sh",
    ):
        assert (REPO_ROOT / relpath).exists(), f"referenced script missing: {relpath}"


def test_ac3_concurrency_control_present(workflow_yaml):
    """同一 ref への重複実行を canceled in progress で制御."""
    conc = workflow_yaml.get("concurrency", {})
    assert "group" in conc
    assert conc.get("cancel-in-progress") is True


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: AGPL / LangGraph / tickets fail で workflow fail
# ══════════════════════════════════════════════════════════════════════


def test_ac4_lint_step_failure_propagates_to_workflow():
    """各 step は default の continue-on-error なし (fail で workflow 全体 fail)."""
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "continue-on-error: true" not in text, (
        "lint steps must NOT have continue-on-error=true (AC-4 UNWANTED)"
    )


def test_ac4_local_agpl_check_passes():
    """ローカル baseline: AGPL 依存なし."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--agpl"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"local AGPL baseline broken: {r.stdout}\n{r.stderr}"


def test_ac4_local_no_langgraph_check_passes():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-langgraph"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"LangGraph leak: {r.stdout}\n{r.stderr}"


def test_ac4_local_validate_tickets_passes():
    r = subprocess.run(
        ["python3", "scripts/validate-tickets.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"tickets baseline broken: {r.stdout}\n{r.stderr}"


def test_ac4_local_archive_baseline_passes():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--archive"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"ARCHIVE residual: {r.stdout}\n{r.stderr}"


def test_ac4_local_secrets_baseline_passes():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--secrets"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"secrets leak: {r.stdout}\n{r.stderr}"


# ══════════════════════════════════════════════════════════════════════
# Docstring / ADR cross-reference (発見性)
# ══════════════════════════════════════════════════════════════════════


def test_workflow_documents_adr_010_unwanted_clauses(workflow_text):
    """workflow header comment が本セッションで散りばめた lint UNWANTED 文言を
    参照していることを確認 (発見性 + 監査 trail)."""
    for tid in ("T-M28-02", "T-M28-03", "T-M28-04",
                "T-M27-01", "T-003-02"):
        assert tid in workflow_text, f"workflow header must reference {tid}"


def test_workflow_documents_reuse_principle(workflow_text):
    """re-implement しないことを明示."""
    assert "REUSE" in workflow_text or "再実装" in workflow_text or "委譲" in workflow_text


def test_workflow_references_adr_010_or_requirements(workflow_text):
    """ADR-010 / requirements §11.6 への cross-ref."""
    assert "ADR-010" in workflow_text


# ══════════════════════════════════════════════════════════════════════
# 補助: workflow header の文書性チェック
# ══════════════════════════════════════════════════════════════════════


def test_workflow_has_header_comment(workflow_text):
    """workflow yaml 冒頭に T-S0-03 説明 comment が存在."""
    head = workflow_text.split("name:")[0]
    assert "T-S0-03" in head, "workflow header must reference task ID"


def test_workflow_explicit_python_version_pinned(workflow_yaml):
    """python-version は文字列 '3.11' (3.x の '3.x' floating ではない).
    floating version は CI 環境差で挙動が変わるため pin する.
    """
    steps = _get_steps(workflow_yaml)
    setup_py = next((s for s in steps if "setup-python" in str(s.get("uses", ""))), None)
    assert setup_py is not None
    version = setup_py["with"]["python-version"]
    assert version == "3.11" or version.startswith("3.11")
