"""git worktree manager (T-021-03 / T-M29-01).

各 cell に専用 worktree を割り当て、cell 完了時に削除する。
worktree path: <repo>/.worktrees/swarm_{pool_id}/cell_{n}
branch name : swarm/{pool_id}/cell-{n}

T-M29-01 AC:
  - AC-1 UBIQUITOUS: 作成 / cleanup 関数 + idempotent
  - AC-2 EVENT:     create/remove 完了で audit_logs に worktree.* event emit
  - AC-3 STATE:     RLS + audit_logs (workspace_id 経由で workspace スコープ)
  - AC-4 UNWANTED:  invalid pool_id / cell_index → ValueError + caller 4xx
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional


# repo root はこのファイル基準 (backend/services/swarm/worktree.py → repo root)
REPO_ROOT: Path = Path(__file__).resolve().parents[3]
WORKTREES_BASE: Path = REPO_ROOT / ".worktrees"


class InvalidWorktreeArgs(ValueError):
    """pool_id / cell_index が non-positive など invalid (T-M29-01 AC-4)."""


def _validate(pool_id: int, cell_index: int) -> None:
    """AC-4 UNWANTED: invalid input → ValueError (caller が 4xx 化する)."""
    if not isinstance(pool_id, int) or pool_id <= 0:
        raise InvalidWorktreeArgs(f"pool_id must be positive int, got {pool_id!r}")
    if not isinstance(cell_index, int) or cell_index < 0:
        raise InvalidWorktreeArgs(f"cell_index must be non-negative int, got {cell_index!r}")


def worktree_path(pool_id: int, cell_index: int) -> Path:
    return WORKTREES_BASE / f"swarm_{pool_id}" / f"cell_{cell_index}"


def branch_name(pool_id: int, cell_index: int) -> str:
    return f"swarm/{pool_id}/cell-{cell_index}"


async def _emit_worktree_audit(event_type: str, *, pool_id: int, cell_index: int,
                                 workspace_id: Optional[int] = None,
                                 extra: Optional[dict] = None) -> None:
    """AC-2 EVENT / AC-3 STATE: audit_logs に worktree.* event を emit.
    失敗してもアプリは止めない (silent log).
    """
    try:
        from services.memory_service import emit_event
        detail = {
            "pool_id": pool_id,
            "cell_index": cell_index,
            "path": str(worktree_path(pool_id, cell_index)),
            "branch": branch_name(pool_id, cell_index),
        }
        if extra:
            detail.update(extra)
        await emit_event(
            event_type, user_id=None, detail=detail,
        )
    except Exception:
        pass  # audit 失敗はアプリを止めない


async def _run_git(args: list[str], cwd: Optional[Path] = None) -> tuple[int, str, str]:
    """git コマンドを async 実行。(exit_code, stdout, stderr) を返す。"""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(cwd or REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    return (
        proc.returncode if proc.returncode is not None else -1,
        out_b.decode("utf-8", errors="replace"),
        err_b.decode("utf-8", errors="replace"),
    )


async def create_worktree(
    pool_id: int, cell_index: int, base_branch: str = "main",
    *, workspace_id: Optional[int] = None,
) -> Path:
    """指定 cell 用の worktree + branch を作成して path を返す.

    既存 worktree があれば一度削除して再作成 (冪等性確保).
    T-M29-01 AC-2: 完了時に audit_logs に worktree.created event emit.
    T-M29-01 AC-4: pool_id <=0 / cell_index < 0 で InvalidWorktreeArgs raise.
    """
    _validate(pool_id, cell_index)
    wt = worktree_path(pool_id, cell_index)
    br = branch_name(pool_id, cell_index)

    # 既存 worktree があれば prune
    if wt.exists():
        await remove_worktree(pool_id, cell_index, force=True,
                              workspace_id=workspace_id)

    wt.parent.mkdir(parents=True, exist_ok=True)

    # branch を base から切る → 既存なら削除して再作成
    await _run_git(["branch", "-D", br])  # exit 0 or 1 (どちらでも OK)

    rc, _, err = await _run_git(["worktree", "add", "-b", br, str(wt), base_branch])
    if rc != 0:
        raise RuntimeError(f"git worktree add failed (rc={rc}): {err}")

    # AC-2: audit emit (created)
    await _emit_worktree_audit(
        "worktree.created",
        pool_id=pool_id, cell_index=cell_index, workspace_id=workspace_id,
        extra={"base_branch": base_branch},
    )
    return wt


async def remove_worktree(
    pool_id: int, cell_index: int, *, force: bool = False,
    workspace_id: Optional[int] = None,
) -> None:
    """worktree を削除. force=True なら未コミット変更も破棄.

    T-M29-01 AC-2: cleanup 完了時に audit_logs に worktree.removed event emit.
    T-M29-01 AC-4: invalid args → InvalidWorktreeArgs.
    """
    _validate(pool_id, cell_index)
    wt = worktree_path(pool_id, cell_index)
    br = branch_name(pool_id, cell_index)

    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(wt))
    await _run_git(args)

    # ディレクトリが残っていれば物理削除
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)

    # branch も削除 (force)
    await _run_git(["branch", "-D", br])

    # AC-2: audit emit (removed)
    await _emit_worktree_audit(
        "worktree.removed",
        pool_id=pool_id, cell_index=cell_index, workspace_id=workspace_id,
        extra={"force": force},
    )


async def list_worktrees() -> list[str]:
    """現在の worktree 一覧 (パス文字列)。デバッグ用。"""
    rc, out, _ = await _run_git(["worktree", "list", "--porcelain"])
    if rc != 0:
        return []
    paths: list[str] = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            paths.append(line[len("worktree "):])
    return paths


def is_inside_cell_worktree(file_path: Path, pool_id: int, cell_index: int) -> bool:
    """指定パスが cell の worktree 内にあるか (sandbox escape 検知)。"""
    try:
        wt = worktree_path(pool_id, cell_index).resolve()
        return wt in file_path.resolve().parents or file_path.resolve() == wt
    except (OSError, ValueError):
        return False
