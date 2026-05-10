"""git worktree manager (T-021-03 EVENT-DRIVEN AC).

各 cell に専用 worktree を割り当て、cell 完了時に削除する。
worktree path: <repo>/.worktrees/swarm_{pool_id}/cell_{n}
branch name : swarm/{pool_id}/cell-{n}
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional


# repo root はこのファイル基準 (backend/services/swarm/worktree.py → repo root)
REPO_ROOT: Path = Path(__file__).resolve().parents[3]
WORKTREES_BASE: Path = REPO_ROOT / ".worktrees"


def worktree_path(pool_id: int, cell_index: int) -> Path:
    return WORKTREES_BASE / f"swarm_{pool_id}" / f"cell_{cell_index}"


def branch_name(pool_id: int, cell_index: int) -> str:
    return f"swarm/{pool_id}/cell-{cell_index}"


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


async def create_worktree(pool_id: int, cell_index: int, base_branch: str = "main") -> Path:
    """指定 cell 用の worktree + branch を作成して path を返す。

    既存 worktree があれば一度削除して再作成 (冪等性確保)。
    """
    wt = worktree_path(pool_id, cell_index)
    br = branch_name(pool_id, cell_index)

    # 既存 worktree があれば prune
    if wt.exists():
        await remove_worktree(pool_id, cell_index, force=True)

    wt.parent.mkdir(parents=True, exist_ok=True)

    # branch を base から切る → 既存なら削除して再作成
    await _run_git(["branch", "-D", br])  # exit 0 or 1 (どちらでも OK)

    rc, _, err = await _run_git(["worktree", "add", "-b", br, str(wt), base_branch])
    if rc != 0:
        raise RuntimeError(f"git worktree add failed (rc={rc}): {err}")
    return wt


async def remove_worktree(pool_id: int, cell_index: int, *, force: bool = False) -> None:
    """worktree を削除。force=True なら未コミット変更も破棄。"""
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
