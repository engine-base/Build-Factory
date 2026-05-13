"""T-S0-02: GitHub Actions ci.yml (pytest + coverage + pre-commit-check + smoke 統合).

AC マッピング (1:1 テスト):
  AC-1 UBIQUITOUS    : workflow が PR + push に動き 4 jobs 並列実行 / 1 つでも
                       fail で build fail. detection は既存 scripts に委譲 (REUSE).
  AC-2 EVENT-DRIVEN  : 4 ステップ (pre-commit / pytest / smoke / summary) を実行,
                       coverage.xml を artifact として upload.
  AC-3 STATE-DRIVEN  : workflow は read-only (state mutate しない) /
                       baseline 維持 (>= 2823 passing tests excluding deselect).
  AC-4 UNWANTED      : pytest / pre-commit / smoke fail で workflow fail /
                       continue-on-error: true 禁止.

T-S0-03 (license-check.yml) との役割分担:
  - license-check.yml : 構造 lint + 機械的ガード (5 分以内 / 軽量)
  - ci.yml (本 PR)    : pytest + coverage + smoke + 統合 (15 分上限 / 重め)

両 workflow が独立して動くこと, 役割重複しないことをテストで verify.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_yaml(workflow_text):
    return yaml.safe_load(workflow_text)


def _get_on(wf):
    """PyYAML は `on:` を True にパースするので両対応."""
    return wf.get("on", wf.get(True))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: workflow が PR + push に動き 4 jobs 並列 / REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac1_workflow_file_exists():
    assert WORKFLOW_PATH.exists(), f"missing: {WORKFLOW_PATH}"


def test_ac1_workflow_valid_yaml(workflow_yaml):
    assert isinstance(workflow_yaml, dict)
    assert "name" in workflow_yaml


def test_ac1_workflow_name_is_ci(workflow_yaml):
    assert workflow_yaml["name"] == "ci"


def test_ac1_workflow_triggers_on_pull_request_to_main(workflow_yaml):
    on = _get_on(workflow_yaml)
    assert "pull_request" in on
    assert "main" in on["pull_request"]["branches"]


def test_ac1_workflow_triggers_on_push_to_main(workflow_yaml):
    on = _get_on(workflow_yaml)
    assert "push" in on
    assert "main" in on["push"]["branches"]


def test_ac1_workflow_supports_manual_dispatch(workflow_yaml):
    on = _get_on(workflow_yaml)
    assert "workflow_dispatch" in on


def test_ac1_workflow_has_4_jobs(workflow_yaml):
    """AC-1: 4 jobs (pre-commit-check / backend-pytest / backend-smoke / summary)."""
    jobs = workflow_yaml["jobs"]
    assert len(jobs) == 4
    expected = {"pre-commit-check", "backend-pytest", "backend-smoke", "summary"}
    assert set(jobs.keys()) == expected


def test_ac1_detection_logic_delegated_to_existing_scripts(workflow_text):
    """workflow が detection ロジックを再実装していないことを確認 (REUSE)."""
    # 既存 script を呼ぶこと
    assert "scripts/pre-commit-check.sh" in workflow_text
    # workflow 内で inline ruff / pyright 実装は無いこと
    # (pytest は標準ツールなのでそのまま. 構造 lint は pre-commit-check に委譲)
    assert "ruff check" not in workflow_text  # 直接ではなく pre-commit-check 経由
    assert "pyright" not in workflow_text     # 同上


def test_ac1_no_role_overlap_with_license_check():
    """T-S0-03 license-check.yml と役割が重複しないこと.
    ci.yml は pytest + coverage / license-check.yml は lint scripts.
    """
    license_path = REPO_ROOT / ".github" / "workflows" / "license-check.yml"
    if not license_path.exists():
        pytest.skip("license-check.yml not yet present (T-S0-03 未マージ)")
    license_text = license_path.read_text(encoding="utf-8")
    ci_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    # license-check.yml: pytest を呼ばない
    assert "python3 -m pytest" not in license_text
    # ci.yml: lint-mock.sh の個別フラグを呼ばない (pre-commit-check 経由のみ)
    for flag in ("--agpl ", "--no-langgraph ", "--emoji "):
        assert f"lint-mock.sh {flag}" not in ci_text, (
            f"ci.yml duplicates license-check.yml: {flag}"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 4 ステップ + coverage artifact upload
# ══════════════════════════════════════════════════════════════════════


def _get_job_steps(workflow_yaml, job_name):
    return workflow_yaml["jobs"][job_name]["steps"]


def test_ac2_pre_commit_job_runs_quick_mode(workflow_yaml):
    """pre-commit-check.sh --quick (frontend tsc skip)."""
    steps = _get_job_steps(workflow_yaml, "pre-commit-check")
    cmds = [s.get("run", "") for s in steps]
    pre_commit_step = next((c for c in cmds if "pre-commit-check.sh" in c), None)
    assert pre_commit_step is not None
    assert "--quick" in pre_commit_step


def test_ac2_pytest_job_uses_coverage(workflow_yaml):
    """pytest が --cov + --cov-report で coverage 取得."""
    steps = _get_job_steps(workflow_yaml, "backend-pytest")
    pytest_step = next((s for s in steps if "pytest" in s.get("run", "")), None)
    assert pytest_step is not None
    cmd = pytest_step["run"]
    assert "--cov" in cmd
    assert "--cov-report=xml" in cmd
    assert "--cov-report=term" in cmd


def test_ac2_pytest_deselect_known_numpy_compat_failure(workflow_yaml):
    """既存 numpy compat fail を deselect (CLAUDE.md 既知)."""
    steps = _get_job_steps(workflow_yaml, "backend-pytest")
    pytest_step = next((s for s in steps if "pytest" in s.get("run", "")), None)
    assert pytest_step is not None
    cmd = pytest_step["run"]
    assert "--deselect" in cmd
    assert "test_vector_score_for_returns_0_when_embedding_unavailable" in cmd


def test_ac2_coverage_artifact_uploaded(workflow_yaml):
    """coverage.xml を artifact として upload."""
    steps = _get_job_steps(workflow_yaml, "backend-pytest")
    upload_step = next((s for s in steps if "upload-artifact" in str(s.get("uses", ""))), None)
    assert upload_step is not None
    assert "@v4" in upload_step["uses"]
    assert upload_step["with"]["path"] == "backend/coverage.xml"
    assert upload_step["with"]["retention-days"] == 7


def test_ac2_smoke_job_imports_main_app(workflow_yaml):
    """backend-smoke が main:app を import."""
    steps = _get_job_steps(workflow_yaml, "backend-smoke")
    cmds = " ".join(s.get("run", "") for s in steps)
    assert "from main import app" in cmds


def test_ac2_summary_job_aggregates_results(workflow_yaml):
    """summary job が 3 jobs の結果を集約."""
    summary = workflow_yaml["jobs"]["summary"]
    assert summary.get("if") == "always()"
    needs = summary.get("needs", [])
    assert "pre-commit-check" in needs
    assert "backend-pytest" in needs
    assert "backend-smoke" in needs


def test_ac2_workflow_uses_python_311(workflow_yaml):
    """全 job が python 3.11 を使用."""
    for job_name in ("pre-commit-check", "backend-pytest", "backend-smoke"):
        steps = _get_job_steps(workflow_yaml, job_name)
        setup_py = next((s for s in steps if "setup-python" in str(s.get("uses", ""))), None)
        assert setup_py is not None, f"job {job_name} missing setup-python"
        assert setup_py["with"]["python-version"] == "3.11"


def test_ac2_workflow_uses_pip_cache(workflow_yaml):
    """setup-python が pip cache を使用 (CI 高速化)."""
    for job_name in ("pre-commit-check", "backend-pytest", "backend-smoke"):
        steps = _get_job_steps(workflow_yaml, job_name)
        setup_py = next((s for s in steps if "setup-python" in str(s.get("uses", ""))), None)
        assert setup_py["with"].get("cache") == "pip"


def test_ac2_workflow_uses_checkout_v4(workflow_yaml):
    for job_name in ("pre-commit-check", "backend-pytest", "backend-smoke"):
        steps = _get_job_steps(workflow_yaml, job_name)
        checkout = next((s for s in steps if "checkout" in str(s.get("uses", ""))), None)
        assert checkout is not None, f"job {job_name} missing checkout"
        assert "@v4" in checkout["uses"]


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only / baseline 維持
# ══════════════════════════════════════════════════════════════════════


def test_ac3_workflow_has_read_only_permissions(workflow_yaml):
    perms = workflow_yaml.get("permissions", {})
    assert perms.get("contents") == "read"


def test_ac3_workflow_does_not_mutate_repo(workflow_text):
    mutating = [
        "git push",
        "git commit",
        "git-auto-commit",
        "create-pull-request",
    ]
    for action in mutating:
        assert action not in workflow_text, f"must not contain mutating: {action}"


def test_ac3_workflow_no_db_writes(workflow_text):
    assert "psql" not in workflow_text
    assert "alembic upgrade" not in workflow_text
    assert "INSERT INTO" not in workflow_text


def test_ac3_concurrency_control_present(workflow_yaml):
    conc = workflow_yaml.get("concurrency", {})
    assert "group" in conc
    assert conc.get("cancel-in-progress") is True


def test_ac3_all_jobs_have_timeout(workflow_yaml):
    """全 job が timeout-minutes 持つ (無限 hang 防止)."""
    for job_name, job in workflow_yaml["jobs"].items():
        if job_name == "summary":
            continue  # summary は他 job 待ちなので timeout 不要
        assert "timeout-minutes" in job, f"job {job_name} missing timeout"
        assert job["timeout-minutes"] <= 20


def test_ac3_pytest_disables_background_workers(workflow_yaml):
    """DISABLE_BACKGROUND_WORKERS=1 で scheduler を起動させない (CI 環境保護)."""
    steps = _get_job_steps(workflow_yaml, "backend-pytest")
    pytest_step = next((s for s in steps if "pytest" in s.get("run", "")), None)
    assert pytest_step.get("env", {}).get("DISABLE_BACKGROUND_WORKERS") == "1"

    smoke_steps = _get_job_steps(workflow_yaml, "backend-smoke")
    smoke_step = next((s for s in smoke_steps if "from main import app" in s.get("run", "")), None)
    assert smoke_step is not None
    assert smoke_step.get("env", {}).get("DISABLE_BACKGROUND_WORKERS") == "1"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: fail propagation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_no_continue_on_error_in_steps(workflow_yaml):
    """continue-on-error: true 禁止 (deselect 以外で fail を吸わない).
    yaml の parsed step を見て確認 (header comment の言及は除外)."""
    for job_name, job in workflow_yaml["jobs"].items():
        for step in job.get("steps", []):
            assert step.get("continue-on-error") is not True, (
                f"job {job_name} step {step.get('name','?')} has continue-on-error=true"
            )
        # job level
        assert job.get("continue-on-error") is not True, (
            f"job {job_name} has continue-on-error=true"
        )


def test_ac4_summary_fails_if_any_job_fails(workflow_yaml):
    """summary job が 1 つでも success != なら exit 1."""
    summary_steps = _get_job_steps(workflow_yaml, "summary")
    cmds = " ".join(s.get("run", "") for s in summary_steps)
    assert "exit 1" in cmds, "summary job must fail if any dep job fails"


def test_ac4_local_pre_commit_check_quick_passes():
    r = subprocess.run(
        ["bash", "scripts/pre-commit-check.sh", "--quick"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"pre-commit-check --quick broken: {r.stdout}\n{r.stderr}"


def test_ac4_pytest_cli_accepts_deselect_flag():
    """pytest CLI が --deselect フラグを受け付ける (構文 verify).

    本 test 内でフルテスト走らせると無限再帰になるため、
    --collect-only で deselect 構文の有効性のみ verify する.
    ローカル baseline は full suite 実行 (PR description) で別途確認.
    """
    r = subprocess.run(
        [
            "python3", "-m", "pytest", "tests/test_t_s0_02_ci_yml.py",
            "--collect-only", "-q",
            "--deselect",
            "tests/test_chat_search.py::test_vector_score_for_returns_0_when_embedding_unavailable",
        ],
        cwd=REPO_ROOT / "backend",
        capture_output=True, text=True, timeout=30,
        env={**__import__("os").environ, "DISABLE_BACKGROUND_WORKERS": "1"},
    )
    # collect-only + 自分自身指定 + valid deselect → exit 0
    assert r.returncode == 0, f"pytest --deselect syntax broken: {r.stdout[-500:]}\n{r.stderr[-500:]}"
    # 自分のテストが collect できる
    assert "test_t_s0_02_ci_yml" in r.stdout


# ══════════════════════════════════════════════════════════════════════
# REUSE 検証 + docstring
# ══════════════════════════════════════════════════════════════════════


def test_workflow_documents_role_division_with_license_check(workflow_text):
    """ci.yml と license-check.yml の役割分担が header に記載."""
    head = workflow_text.split("name: ci")[0]
    assert "license-check.yml" in head, "header must reference T-S0-03 license-check.yml"
    assert "T-S0-03" in head or "T-S0-02" in head


def test_workflow_documents_known_deselect(workflow_text):
    """既存 numpy compat fail の deselect 理由が header に記載."""
    head = workflow_text.split("name: ci")[0]
    assert "numpy" in head.lower() or "deselect" in head.lower()
    assert "test_chat_search" in head or "test_vector_score" in head


def test_workflow_explicit_python_version_pinned(workflow_yaml):
    """python-version は文字列 '3.11' に pin."""
    for job_name in ("pre-commit-check", "backend-pytest", "backend-smoke"):
        steps = _get_job_steps(workflow_yaml, job_name)
        setup_py = next((s for s in steps if "setup-python" in str(s.get("uses", ""))), None)
        version = setup_py["with"]["python-version"]
        assert version == "3.11", f"job {job_name}: python {version} (must be 3.11)"


def test_workflow_has_summary_aggregation():
    """summary job で全 result を log 出力 (監査 trail)."""
    summary_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "CI Summary" in summary_text
    assert "pre-commit-check" in summary_text
    assert "backend-pytest" in summary_text
    assert "backend-smoke" in summary_text


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_02_ac_concretized():
    """tickets.json T-S0-02 AC が generic でないことを確認 (PR #134 と同じパターン)."""
    import json
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-02"), None)
    assert t is not None, "T-S0-02 missing in tickets.json"
    generic_phrases = [
        "as specified by feature",
        "implementation step for T-S0-02 is triggered",
        "shall record an audit entry capturing the action and timestamp",
        "shall apply Row Level Security and audit_logs as per CLAUDE.md",
    ]
    for ac in t["acceptance_criteria"]:
        text = ac["text"]
        for phrase in generic_phrases:
            assert phrase not in text, (
                f"T-S0-02 AC still contains generic phrase: {phrase!r} in {ac['type']}"
            )
    # 具体的キーワードを含むこと
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "pre-commit-check.sh" in full
    assert "pytest" in full
    assert "coverage" in full


def test_tickets_t_s0_02_has_adr_link():
    """tickets.json T-S0-02 に adr_link がある."""
    import json
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-02"), None)
    assert t.get("adr_link") is not None
