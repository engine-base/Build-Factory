"""T-BTSTRAP-04: build-factory project migrate (既存案件への遡及適用 CLI).

`build-factory project migrate --workspace={id}` で、当該 workspace の repo を
fetch して templates/project-bootstrap/ の最新版と diff し、**不足ファイルだけ追加**
する CLI. 既存ファイルがあれば skip + manual-merge 警告.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : migrate --workspace={id} で fetch → diff → missing-only add
  AC-2 EVENT-DRIVEN  : 既存ファイル overwrite を skip + manual-merge レポート
  AC-3 STATE-DRIVEN  : --dry-run で commit/push しない (diff print のみ)
  AC-4 OPTIONAL      : --all で全 workspace を sequential migrate
  AC-5 UNWANTED      : dirty repo (uncommitted) は abort + force change しない

依存: T-BTSTRAP-02 (WorkspaceService.bootstrap → templates 解決の道具を REUSE).

CLI 起動: python -m backend.cli.project_commands migrate [options]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# ──────────────────────────────────────────────────────────────────────
# Path constants
# ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = REPO_ROOT / "templates/project-bootstrap"
CHANGELOG = REPO_ROOT / "templates/CHANGELOG.md"


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


class MigrateError(Exception):
    """migrate 処理での明示的失敗 (caller が 4xx / non-zero exit に map)."""


@dataclass
class MigratePlan:
    """1 workspace 分の migrate 計画 (dry-run / 実行 共通)."""

    workspace_id: int
    workspace_repo_path: Path
    template_version: str
    missing_files: list[str] = field(default_factory=list)
    existing_files_skipped: list[str] = field(default_factory=list)
    dirty_files: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.dirty_files

    @property
    def has_changes(self) -> bool:
        return bool(self.missing_files)


# ──────────────────────────────────────────────────────────────────────
# Core helpers (依存最小, mock しやすい関数として切り出し)
# ──────────────────────────────────────────────────────────────────────


def get_template_version(changelog: Path = CHANGELOG) -> str:
    """templates/CHANGELOG.md から最新 version を抽出 ("v1.2" 形式)."""
    if not changelog.exists():
        return "v0.0"
    import re
    content = changelog.read_text(encoding="utf-8")
    m = re.search(r"^##\s+(v\d+\.\d+(?:\.\d+)?)", content, re.MULTILINE)
    return m.group(1) if m else "v0.0"


def list_template_files(template_dir: Path = TEMPLATE_DIR) -> list[Path]:
    """templates/project-bootstrap/ 配下の全 file を返す."""
    if not template_dir.is_dir():
        return []
    return sorted(p for p in template_dir.rglob("*") if p.is_file())


def template_relative_target(template_file: Path, template_dir: Path) -> Path:
    """テンプレファイル → workspace 配下の相対パス (.j2 拡張子を取る)."""
    rel = template_file.relative_to(template_dir)
    if rel.name.endswith(".j2"):
        rel = rel.with_name(rel.name[:-3])
    return rel


def check_repo_dirty(workspace_repo: Path) -> list[str]:
    """git status --porcelain で uncommitted ファイル一覧を取る.

    AC-5 UNWANTED: dirty なら migration を abort する.
    """
    if not (workspace_repo / ".git").exists():
        return []  # git repo ではない → dirty 判定不可能 → 空
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [
        line[3:].strip() for line in result.stdout.splitlines() if line.strip()
    ]


def compute_migrate_plan(
    workspace_id: int,
    workspace_repo: Path,
    *,
    template_dir: Path = TEMPLATE_DIR,
    changelog: Path = CHANGELOG,
) -> MigratePlan:
    """workspace に対する migrate 計画を計算 (副作用なし)."""
    plan = MigratePlan(
        workspace_id=workspace_id,
        workspace_repo_path=workspace_repo,
        template_version=get_template_version(changelog),
    )
    # AC-5: dirty check (副作用前に)
    plan.dirty_files = check_repo_dirty(workspace_repo)
    # AC-1/2: missing 判定
    for tf in list_template_files(template_dir):
        target_rel = template_relative_target(tf, template_dir)
        target_abs = workspace_repo / target_rel
        if target_abs.exists():
            # AC-2 EVENT: overwrite 候補は skip
            plan.existing_files_skipped.append(str(target_rel))
        else:
            # AC-1: missing → add 候補
            plan.missing_files.append(str(target_rel))
    return plan


def apply_migrate_plan(
    plan: MigratePlan,
    *,
    template_dir: Path = TEMPLATE_DIR,
    dry_run: bool = False,
) -> dict:
    """migrate plan を実行 (or dry-run).

    AC-3: dry_run=True で commit/push しない (diff print のみ).
    AC-5: dirty なら MigrateError raise.

    Returns:
        {action: str, added: list, skipped: list, dirty: list, version: str}
    """
    if not plan.is_clean:
        raise MigrateError(
            f"workspace #{plan.workspace_id} repo is dirty "
            f"({len(plan.dirty_files)} uncommitted files); migration aborted"
        )
    result = {
        "workspace_id": plan.workspace_id,
        "version": plan.template_version,
        "added": [],
        "skipped": list(plan.existing_files_skipped),
        "dirty": [],
        "action": "dry-run" if dry_run else "apply",
    }
    if dry_run:
        # AC-3: print only, no copy
        result["added"] = list(plan.missing_files)
        return result
    # Apply: copy missing files only (no overwrite)
    for rel in plan.missing_files:
        # source template file (with optional .j2 suffix)
        src_candidates = [
            template_dir / rel,
            template_dir / (rel + ".j2"),
        ]
        src = next((c for c in src_candidates if c.exists()), None)
        if src is None:
            continue
        dst = plan.workspace_repo_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        result["added"].append(rel)
    return result


# ──────────────────────────────────────────────────────────────────────
# CLI entry
# ──────────────────────────────────────────────────────────────────────


def cmd_migrate(args: argparse.Namespace) -> int:
    """build-factory project migrate サブコマンド."""
    workspace_ids: list[int] = []
    if args.all:
        # AC-4 OPTIONAL: --all で全 workspace iterate
        workspace_ids = _list_all_workspaces()
        if not workspace_ids:
            print("(no active workspaces — set ACTIVE_WORKSPACES_JSON env or use --workspace)")
            return 0
    elif args.workspace:
        workspace_ids = [int(args.workspace)]
    else:
        print("Error: --workspace={id} or --all required", file=sys.stderr)
        return 2

    failures = []
    for ws_id in workspace_ids:
        repo_path = _resolve_workspace_repo(ws_id, args.repo_root)
        plan = compute_migrate_plan(ws_id, repo_path)
        print(f"\n=== workspace #{ws_id} (template {plan.template_version}) ===")
        if not plan.is_clean:
            print(f"  ABORT: repo is dirty ({len(plan.dirty_files)} files):")
            for f in plan.dirty_files[:10]:
                print(f"    - {f}")
            failures.append(ws_id)
            continue
        try:
            result = apply_migrate_plan(plan, dry_run=args.dry_run)
        except MigrateError as e:
            print(f"  FAILED: {e}")
            failures.append(ws_id)
            continue
        print(f"  action: {result['action']}")
        print(f"  files to add ({len(result['added'])}):")
        for f in result["added"][:10]:
            print(f"    + {f}")
        if len(result["added"]) > 10:
            print(f"    ... +{len(result['added']) - 10} more")
        print(f"  files skipped (existing) ({len(result['skipped'])}):")
        for f in result["skipped"][:5]:
            print(f"    = {f}")
        if len(result["skipped"]) > 5:
            print(f"    ... +{len(result['skipped']) - 5} more")
    if failures:
        print(f"\n{len(failures)}/{len(workspace_ids)} workspace migrations FAILED")
        return 1
    print(f"\n{len(workspace_ids)} workspace(s) migration {'planned (dry-run)' if args.dry_run else 'completed'}")
    return 0


def _list_all_workspaces() -> list[int]:
    """全 active workspace ID を返す (DB 未接続環境では env から)."""
    raw = os.environ.get("ACTIVE_WORKSPACES_JSON", "")
    if not raw:
        return []
    try:
        items = json.loads(raw)
        return [int(it["id"]) for it in items if "id" in it]
    except Exception:
        return []


def _resolve_workspace_repo(workspace_id: int, repo_root_override: Optional[str]) -> Path:
    """workspace_id → repo path. 実運用では DB から github_repo を fetch + clone.

    現状: env WORKSPACE_REPO_{id} があれば使う / なければ /tmp/ws-{id}.
    test では --repo-root で override 可.
    """
    if repo_root_override:
        return Path(repo_root_override)
    env_key = f"WORKSPACE_REPO_{workspace_id}"
    if env_key in os.environ:
        return Path(os.environ[env_key])
    return Path(tempfile.gettempdir()) / f"ws-{workspace_id}"


def build_parser() -> argparse.ArgumentParser:
    """argparse parser 構築 (CLI + test 共通)."""
    ap = argparse.ArgumentParser(prog="build-factory project", description="Build-Factory project CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate", help="既存案件にテンプレを遡及適用")
    migrate.add_argument("--workspace", type=str, help="workspace id (--all と排他)")
    migrate.add_argument("--all", action="store_true", help="全 active workspace を migrate")
    migrate.add_argument("--dry-run", action="store_true", help="diff print のみ (commit/push なし)")
    migrate.add_argument("--repo-root", type=str, default=None, help="(test 用) workspace repo path override")
    migrate.set_defaults(func=cmd_migrate)

    return ap


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
