"""T-BTSTRAP-05: テンプレ更新時に全案件へ PR 自動作成 1:1 spec test.

AC マッピング (1:1):
  AC-1 EVENT     : --dry-run mode で全 workspace の差分件数を計算
  AC-2 UBIQUITOUS: 各 workspace の "would-change file count" を report
  AC-3 EVENT     : --apply mode で各 workspace に PR 作成
  AC-4 STATE     : 同 template version の PR 重複検出 (idempotent)
  AC-5 UNWANTED  : --continue-on-error で 1 失敗時も他は継続

成果物:
  - .github/workflows/template-propagation.yml
  - scripts/propagate-template.py
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = REPO_ROOT / ".github/workflows/template-propagation.yml"
SCRIPT = REPO_ROOT / "scripts/propagate-template.py"


@pytest.fixture(scope="module")
def workflow_yaml():
    assert WORKFLOW.exists(), f"workflow missing: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script_src():
    assert SCRIPT.exists(), f"script missing: {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# AC-1 EVENT: templates/CHANGELOG.md 変更 -> dry-run trigger
# ════════════════════════════════════════════════════════════════════


def test_ac1_workflow_triggered_on_template_changelog(workflow_yaml):
    """workflow が templates/CHANGELOG.md push で発火する."""
    assert "templates/CHANGELOG.md" in workflow_yaml
    assert "templates/project-bootstrap/" in workflow_yaml or "templates/project-bootstrap/**" in workflow_yaml
    assert "branches: [main]" in workflow_yaml or "branches:\n      - main" in workflow_yaml.replace(' ','')


def test_ac1_dry_run_job_present(workflow_yaml):
    """workflow に dry-run job がある."""
    assert "dry-run:" in workflow_yaml or "dry_run:" in workflow_yaml
    assert "--dry-run" in workflow_yaml


def test_ac1_script_dry_run_command_works():
    """scripts/propagate-template.py --dry-run が exit 0 で動く."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"dry-run failed:\n{result.stdout}\n{result.stderr}"


# ════════════════════════════════════════════════════════════════════
# AC-2 UBIQUITOUS: workspace 別 diff count を report
# ════════════════════════════════════════════════════════════════════


def test_ac2_dry_run_reports_per_workspace_count(monkeypatch):
    """ACTIVE_WORKSPACES_JSON 経由で複数 workspace の diff count が出る."""
    workspaces = [
        {"id": 101, "name": "ws-a"},
        {"id": 102, "name": "ws-b"},
    ]
    env = os.environ.copy()
    env["ACTIVE_WORKSPACES_JSON"] = json.dumps(workspaces)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert result.returncode == 0
    out = result.stdout
    assert "ws #101" in out
    assert "ws #102" in out
    assert "files would change" in out


def test_ac2_dry_run_writes_summary_json():
    """dry-run が .propagation-dry-run.json を書く (post-summary 用)."""
    workspaces = [{"id": 201, "name": "test"}]
    env = os.environ.copy()
    env["ACTIVE_WORKSPACES_JSON"] = json.dumps(workspaces)
    subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        env=env, timeout=30, capture_output=True,
    )
    out = REPO_ROOT / ".propagation-dry-run.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert "version" in data
    assert "summary" in data


# ════════════════════════════════════════════════════════════════════
# AC-3 EVENT: --apply mode で PR 作成 (workflow_dispatch trigger)
# ════════════════════════════════════════════════════════════════════


def test_ac3_workflow_dispatch_with_approve_input(workflow_yaml):
    """workflow_dispatch で approve input がある."""
    assert "workflow_dispatch:" in workflow_yaml
    assert "approve:" in workflow_yaml
    assert "yes" in workflow_yaml.lower()  # default 'no'


def test_ac3_apply_job_present(workflow_yaml):
    """apply job が approve='yes' でのみ起動."""
    assert "apply:" in workflow_yaml
    assert "github.event.inputs.approve == 'yes'" in workflow_yaml or "inputs.approve == 'yes'" in workflow_yaml


def test_ac3_apply_command_in_script(script_src):
    """script に --apply mode が実装されている."""
    assert "cmd_apply" in script_src or "--apply" in script_src
    assert "create PR" in script_src or "create_pull" in script_src or "would create PR" in script_src


# ════════════════════════════════════════════════════════════════════
# AC-4 STATE: 同 template version の PR 重複しない (idempotent)
# ════════════════════════════════════════════════════════════════════


def test_ac4_pr_title_includes_version(script_src):
    """PR title に template version (v{X}) が含まれる → 重複検出可能."""
    # 'chore: migrate to template v{X}' のフォーマット
    assert re.search(r"migrate to template", script_src)
    # version は f-string で挿入される
    assert re.search(r'f["\']chore.*migrate.*\{version\}', script_src)


def test_ac4_get_template_version_function(script_src):
    """version 抽出関数がある (CHANGELOG.md パース)."""
    assert "get_template_version" in script_src or "template_version" in script_src


# ════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED: 1 workspace 失敗で abort せず continue
# ════════════════════════════════════════════════════════════════════


def test_ac5_continue_on_error_flag(script_src):
    """--continue-on-error フラグが実装されている."""
    assert "--continue-on-error" in script_src
    assert "continue_on_error" in script_src


def test_ac5_workflow_uses_continue_on_error(workflow_yaml):
    """workflow が --continue-on-error を渡している."""
    assert "--continue-on-error" in workflow_yaml


def test_ac5_failures_summary(script_src):
    """failures を集計して summary に出す."""
    assert "failures" in script_src
    assert "report failures" in script_src.lower() or "workspaces failed" in script_src
