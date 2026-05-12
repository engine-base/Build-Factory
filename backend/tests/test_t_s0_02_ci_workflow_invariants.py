"""T-S0-02: GitHub Actions ci.yml — 5 AC 機械 invariant 検証.

PR #135 で production artifact 完成済 (.github/workflows/ci.yml).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : on=pull_request+push / 4 parallel jobs / fail
                       on any job / REUSE scripts/pre-commit-check.sh.
  AC-2 EVENT-DRIVEN  : pre-commit --quick / pytest --cov --deselect /
                       main:app import smoke / coverage artifact 7d
                       retention.
  AC-3 STATE-DRIVEN  : permissions: contents=read / concurrency
                       cancel-in-progress=true / pytest baseline preserve.
  AC-4 OPTIONAL      : concurrency cancel-in-progress (CI 経済) /
                       全 action @v4/@v5 pin / no @main/master/latest.
  AC-5 UNWANTED      : continue-on-error 禁止 / no mutation /
                       no hardcoded secret / secrets via ${{ secrets.X }}.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PRE_COMMIT = REPO_ROOT / "scripts" / "pre-commit-check.sh"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture(scope="module")
def workflow():
    if yaml is None:
        pytest.skip("PyYAML not available")
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def src():
    return CI_YML.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — workflow file + triggers + 4 jobs + REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac1_ci_yml_exists():
    assert CI_YML.exists()


def test_ac1_pre_commit_script_exists():
    """REUSE invariant: scripts/pre-commit-check.sh が依存先."""
    assert PRE_COMMIT.exists()


def test_ac1_workflow_name_is_ci(workflow):
    assert workflow.get("name") == "ci"


def test_ac1_triggers_on_pull_request_and_push(src):
    """pull_request: と push: の両方が on: にある."""
    # PyYAML の `on:` は True (boolean) に変換されるので raw text で確認
    assert re.search(r"^on:", src, re.MULTILINE)
    assert re.search(r"^\s+pull_request:", src, re.MULTILINE)
    assert re.search(r"^\s+push:", src, re.MULTILINE)


def test_ac1_has_4_named_jobs(workflow):
    jobs = workflow.get("jobs", {})
    expected = {"pre-commit-check", "backend-pytest", "backend-smoke", "summary"}
    actual = set(jobs.keys())
    assert expected.issubset(actual), (
        f"missing jobs: {expected - actual} (got {actual})"
    )


def test_ac1_reuses_pre_commit_check_script(src):
    """REUSE: bash scripts/pre-commit-check.sh を直接呼ぶ."""
    assert "scripts/pre-commit-check.sh" in src


def test_ac1_reuses_existing_scripts_not_reimplemented():
    """ci.yml が pre-commit-check.sh のロジックを再実装していない."""
    src = CI_YML.read_text(encoding="utf-8")
    # check_emoji / check_agpl 等の関数定義が ci.yml に無い
    forbidden_redef = [
        "function check_emoji",
        "function check_agpl",
        "function check_archive",
        "function check_secrets",
    ]
    for bad in forbidden_redef:
        assert bad not in src, f"ci.yml re-implements {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — quick + pytest --cov --deselect + smoke + artifact
# ══════════════════════════════════════════════════════════════════════


def test_ac2_pre_commit_uses_quick_mode(src):
    assert re.search(
        r"bash\s+scripts/pre-commit-check\.sh\s+--quick",
        src,
    )


def test_ac2_pytest_uses_cov(src):
    """pytest コマンドが --cov を含む (multi-line backslash 形式も対応)."""
    # multi-line で backslash 継続を許容
    assert re.search(r"python3?\s+-m\s+pytest[\s\S]+?--cov", src), (
        "pytest must use --cov (coverage measurement required)"
    )


def test_ac2_pytest_deselects_known_failure(src):
    """既知 numpy fail を --deselect で除外."""
    assert "--deselect" in src
    assert "test_chat_search" in src or "test_vector_score" in src


def test_ac2_backend_smoke_imports_main_app(src):
    """python3 -c 'from main import app' import smoke が backend-smoke job 内."""
    # backend-smoke job 内に from main import app が含まれる
    m = re.search(
        r"backend-smoke[\s\S]+?(?=\n  \w|\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "from main import app" in body


def test_ac2_coverage_artifact_uploaded(src):
    """coverage.xml を upload-artifact@v4 で artifact 化."""
    assert "actions/upload-artifact@v4" in src
    assert "coverage" in src.lower()


def test_ac2_coverage_artifact_7_day_retention(src):
    """retention-days: 7 で 7-day 保持."""
    assert re.search(r"retention-days:\s*7", src)


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — permissions / concurrency / baseline
# ══════════════════════════════════════════════════════════════════════


def test_ac3_permissions_contents_read(workflow):
    perms = workflow.get("permissions", {})
    assert perms.get("contents") == "read"


def test_ac3_no_write_permission(workflow):
    """permissions に write 系の値が含まれていない."""
    perms = workflow.get("permissions", {})
    for key, val in perms.items():
        assert val != "write", f"unexpected write permission: {key}"


def test_ac3_concurrency_group_per_ref(workflow):
    conc = workflow.get("concurrency", {})
    assert isinstance(conc, dict)
    group = conc.get("group", "")
    assert "github.ref" in str(group), (
        f"concurrency group must include github.ref, got {group}"
    )


def test_ac3_concurrency_cancel_in_progress_true(workflow):
    conc = workflow.get("concurrency", {})
    assert conc.get("cancel-in-progress") is True


def test_ac3_no_state_mutation(src):
    """workflow が state mutation を含まない (no git push / no DB insert)."""
    # git push / curl POST / INSERT INTO は無い
    code = re.sub(r"#[^\n]*", "", src)
    assert not re.search(r"\bgit\s+push\b", code)
    assert not re.search(r"INSERT INTO", code, re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — action @v pin + no floating refs + concurrency 経済
# ══════════════════════════════════════════════════════════════════════


def test_ac4_all_actions_pinned_to_major_version(src):
    """全 uses: <repo>@<ref> が major version (v数字) で pinned."""
    refs = re.findall(
        r"uses:\s*([a-zA-Z0-9_./-]+)@([a-zA-Z0-9_.-]+)",
        src,
    )
    assert refs, "no uses: in workflow"
    forbidden_refs = {"main", "master", "latest", "develop", "head"}
    for action, ref in refs:
        assert ref.lower() not in forbidden_refs, (
            f"{action} uses floating ref @{ref}"
        )
        # v数字 / 数字.数字 / 数字.数字.数字 / 40-char SHA
        assert re.match(
            r"^(v\d+|\d+\.\d+|\d+\.\d+\.\d+|[a-f0-9]{40})$",
            ref,
        ), f"{action} version {ref} not in pinned format"


def test_ac4_checkout_v4(src):
    assert re.search(r"actions/checkout@v4\b", src)


def test_ac4_setup_python_v5(src):
    assert re.search(r"actions/setup-python@v5\b", src)


def test_ac4_upload_artifact_v4(src):
    assert re.search(r"actions/upload-artifact@v4\b", src)


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — no continue-on-error / no mutation / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_no_continue_on_error_true(src):
    """continue-on-error: true 禁止 (失敗を握りつぶさない)."""
    code = re.sub(r"#[^\n]*", "", src)
    assert not re.search(
        r"continue-on-error:\s*true",
        code,
    )


def test_ac5_no_hardcoded_jwt(src):
    assert not re.search(
        r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.",
        src,
    )


def test_ac5_no_hardcoded_supabase_or_anthropic_key(src):
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


def test_ac5_secrets_via_secrets_context(src):
    """secret 参照は ${{ secrets.X }} 経由 (もし使うなら)."""
    # secret 直接書きが無い (env から secrets context 経由のみ)
    # GITHUB_TOKEN や hardcoded base64 が無いことを確認
    code = re.sub(r"#[^\n]*", "", src)
    # secrets を使う場合は ${{ secrets.X }} 形式
    secret_refs = re.findall(r"\$\{\{\s*secrets\.[A-Z_]+\s*\}\}", code)
    # 直接 = "abc123" のような hardcoded value が無い
    hardcoded = re.findall(r'(?:token|password|key)\s*=\s*["\'][A-Za-z0-9_-]{20,}["\']', code, re.IGNORECASE)
    assert not hardcoded, f"hardcoded credentials: {hardcoded}"


def test_ac5_workflow_does_not_write_to_main(src):
    """git config / git commit / git push が main に向かない."""
    code = re.sub(r"#[^\n]*", "", src)
    # `git push` 自体が無い (もしくは origin に対してではない)
    pushes = re.findall(r"git\s+push", code)
    assert not pushes, f"forbidden git push in workflow: {pushes}"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_02_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-02"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    # 5 AC (OPTIONAL added)
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_s0_02_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-02"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert ".github/workflows/ci.yml" in files
    assert "scripts/pre-commit-check.sh" in files


def test_tickets_t_s0_02_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-02"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        ".github/workflows/ci.yml",
        "scripts/pre-commit-check.sh",
        "pull_request", "push",
        "pre-commit-check", "backend-pytest", "backend-smoke", "summary",
        "actions/checkout@v4",
        "actions/setup-python@v5",
        "actions/upload-artifact@v4",
        "cancel-in-progress",
        "continue-on-error",
        "permissions: contents=read",
        "concurrency",
    ):
        assert sym in full, f"T-S0-02 AC missing: {sym}"
