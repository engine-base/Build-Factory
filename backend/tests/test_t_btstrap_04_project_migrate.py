"""T-BTSTRAP-04: build-factory project migrate (既存案件への遡及適用) 1:1 spec test.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : migrate --workspace={id} で fetch → diff → missing-only add
  AC-2 EVENT-DRIVEN  : 既存ファイル overwrite を skip + manual-merge レポート
  AC-3 STATE-DRIVEN  : --dry-run で commit/push しない (diff print のみ)
  AC-4 OPTIONAL      : --all で全 workspace を sequential migrate
  AC-5 UNWANTED      : dirty repo (uncommitted) は abort + force change しない

実装ファイル: backend/cli/project_commands.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_SCRIPT = REPO_ROOT / "backend/cli/project_commands.py"


@pytest.fixture
def fake_workspace_repo(tmp_path):
    """空の workspace repo (CLAUDE.md だけ既存) を tmp に作る."""
    ws = tmp_path / "ws-fake"
    ws.mkdir()
    # 既存ファイル (= overwrite skip 対象)
    (ws / "CLAUDE.md").write_text("# existing project CLAUDE.md\n")
    return ws


@pytest.fixture
def fake_workspace_repo_with_git(tmp_path):
    """git init 済み workspace repo (test env で sign 必須をbypass)."""
    ws = tmp_path / "ws-git"
    ws.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=ws, check=False)
    # test 環境で sign 要求を回避
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=ws, check=False)
    subprocess.run(["git", "config", "tag.gpgsign", "false"], cwd=ws, check=False)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=ws, check=False)
    subprocess.run(["git", "config", "user.name", "test"], cwd=ws, check=False)
    (ws / "README.md").write_text("# ws-git\n")
    subprocess.run(["git", "add", "."], cwd=ws, check=False)
    # commit 失敗時は staged 状態のままになる→そこから手動で clean に持っていく
    commit = subprocess.run(
        ["git", "commit", "-q", "-m", "init", "--no-gpg-sign"],
        cwd=ws, capture_output=True, text=True,
    )
    if commit.returncode != 0:
        # 署名サーバ等で fail した場合: working tree 状態を clean に reset
        # (test は dirty 検出のために後で意図的に dirty にするので、初期は clean が必要)
        subprocess.run(["git", "rm", "--cached", "-r", "."], cwd=ws, capture_output=True)
        # ↑ index を空に → status はファイル untracked になる
        # untracked も dirty 扱いなので、untracked を .gitignore に追加する手も…
        # 簡単な手: README.md を消す (= dirty 元を除去)
        (ws / "README.md").unlink(missing_ok=True)
    return ws


# ════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: missing-only add
# ════════════════════════════════════════════════════════════════════


def test_ac1_cli_script_exists():
    assert CLI_SCRIPT.exists()


def test_ac1_compute_migrate_plan_returns_missing_files(fake_workspace_repo):
    """既存 CLAUDE.md は skip、他 template files は missing として detect."""
    from cli.project_commands import compute_migrate_plan
    plan = compute_migrate_plan(workspace_id=1, workspace_repo=fake_workspace_repo)
    # 既存 CLAUDE.md は skip リストにある
    assert "CLAUDE.md" in plan.existing_files_skipped
    # 他に template files が複数 missing
    assert len(plan.missing_files) >= 3, f"only {len(plan.missing_files)} missing"


def test_ac1_apply_adds_missing_files_only(fake_workspace_repo):
    """apply 後 missing files が新規追加され、既存ファイル無変更."""
    from cli.project_commands import compute_migrate_plan, apply_migrate_plan
    plan = compute_migrate_plan(workspace_id=1, workspace_repo=fake_workspace_repo)
    original_claude_md = (fake_workspace_repo / "CLAUDE.md").read_text()
    result = apply_migrate_plan(plan, dry_run=False)
    assert result["action"] == "apply"
    assert len(result["added"]) >= 1
    # CLAUDE.md は変わってない (existing skipped)
    assert (fake_workspace_repo / "CLAUDE.md").read_text() == original_claude_md
    # missing file が実際に作られた
    for added_rel in result["added"]:
        assert (fake_workspace_repo / added_rel).exists()


# ════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: overwrite skip + report
# ════════════════════════════════════════════════════════════════════


def test_ac2_existing_file_skipped_in_plan(fake_workspace_repo):
    """既存 CLAUDE.md は existing_files_skipped に入り、missing_files には入らない."""
    from cli.project_commands import compute_migrate_plan
    plan = compute_migrate_plan(workspace_id=1, workspace_repo=fake_workspace_repo)
    assert "CLAUDE.md" in plan.existing_files_skipped
    assert "CLAUDE.md" not in plan.missing_files


def test_ac2_apply_reports_skipped_count(fake_workspace_repo):
    """apply 結果に skipped 件数が含まれる."""
    from cli.project_commands import compute_migrate_plan, apply_migrate_plan
    plan = compute_migrate_plan(workspace_id=1, workspace_repo=fake_workspace_repo)
    result = apply_migrate_plan(plan, dry_run=True)
    assert "skipped" in result
    assert isinstance(result["skipped"], list)
    assert len(result["skipped"]) >= 1


# ════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: --dry-run is read-only
# ════════════════════════════════════════════════════════════════════


def test_ac3_dry_run_does_not_create_files(fake_workspace_repo):
    """dry_run=True なら新規 file は作られない."""
    from cli.project_commands import compute_migrate_plan, apply_migrate_plan
    before_files = {p.relative_to(fake_workspace_repo) for p in fake_workspace_repo.rglob("*") if p.is_file()}
    plan = compute_migrate_plan(workspace_id=1, workspace_repo=fake_workspace_repo)
    result = apply_migrate_plan(plan, dry_run=True)
    after_files = {p.relative_to(fake_workspace_repo) for p in fake_workspace_repo.rglob("*") if p.is_file()}
    assert before_files == after_files, "dry-run should not change file system"
    assert result["action"] == "dry-run"


def test_ac3_dry_run_cli_returns_diff_only(fake_workspace_repo):
    """CLI --dry-run の stdout に added/skipped が含まれる."""
    result = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "migrate", "--workspace", "1", "--dry-run", "--repo-root", str(fake_workspace_repo)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert "dry-run" in result.stdout.lower() or "dry_run" in result.stdout.lower()


# ════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL: --all で全 workspace
# ════════════════════════════════════════════════════════════════════


def test_ac4_cli_supports_all_flag():
    """--all フラグが parser に登録されている."""
    from cli.project_commands import build_parser
    parser = build_parser()
    # parse_args で --all を受け付ける
    ns = parser.parse_args(["migrate", "--all", "--dry-run"])
    assert getattr(ns, "all", False) is True


def test_ac4_all_uses_active_workspaces_env(fake_workspace_repo):
    """--all + ACTIVE_WORKSPACES_JSON env で iterate."""
    env = os.environ.copy()
    env["ACTIVE_WORKSPACES_JSON"] = json.dumps([{"id": 101}])
    env[f"WORKSPACE_REPO_101"] = str(fake_workspace_repo)
    result = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "migrate", "--all", "--dry-run"],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert result.returncode == 0
    assert "#101" in result.stdout or "workspace #101" in result.stdout


def test_ac4_all_empty_returns_zero_no_error():
    """ACTIVE_WORKSPACES_JSON 空でも --all はエラー無しで 0."""
    env = os.environ.copy()
    env.pop("ACTIVE_WORKSPACES_JSON", None)
    result = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "migrate", "--all", "--dry-run"],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert result.returncode == 0


# ════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED: dirty repo abort
# ════════════════════════════════════════════════════════════════════


def test_ac5_check_repo_dirty_detects_uncommitted(fake_workspace_repo_with_git):
    """git status --porcelain で uncommitted を検出."""
    from cli.project_commands import check_repo_dirty
    # 何も変更してない状態
    assert check_repo_dirty(fake_workspace_repo_with_git) == []
    # 変更を加える
    (fake_workspace_repo_with_git / "foo.txt").write_text("dirty content")
    dirty = check_repo_dirty(fake_workspace_repo_with_git)
    assert len(dirty) >= 1
    assert any("foo.txt" in f for f in dirty)


def test_ac5_apply_aborts_when_dirty(fake_workspace_repo_with_git):
    """dirty repo に対して apply_migrate_plan が MigrateError raise."""
    from cli.project_commands import compute_migrate_plan, apply_migrate_plan, MigrateError
    # わざと dirty にする
    (fake_workspace_repo_with_git / "dirty.txt").write_text("uncommitted")
    plan = compute_migrate_plan(workspace_id=2, workspace_repo=fake_workspace_repo_with_git)
    assert not plan.is_clean
    with pytest.raises(MigrateError) as exc_info:
        apply_migrate_plan(plan, dry_run=False)
    assert "dirty" in str(exc_info.value).lower()


def test_ac5_cli_aborts_with_nonzero_exit_when_dirty(fake_workspace_repo_with_git):
    """CLI も dirty 検出時 exit 1 を返す (force change なし)."""
    (fake_workspace_repo_with_git / "uncommitted.txt").write_text("x")
    result = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "migrate", "--workspace", "2", "--repo-root", str(fake_workspace_repo_with_git)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0, "CLI should exit non-zero when dirty"
    assert "dirty" in result.stdout.lower() or "abort" in result.stdout.lower()
    # AC-5: force change なし → file 一覧変わってない (uncommitted.txt 以外)
    files_after = sorted(p.name for p in fake_workspace_repo_with_git.iterdir() if p.is_file())
    assert "README.md" in files_after  # 既存
    assert "uncommitted.txt" in files_after  # 元から dirty 状態のまま
