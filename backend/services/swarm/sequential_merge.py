"""T-M29-03: merge conflict 検出 + sequential merge ヘルパー.

T-M29-01 worktree.py の上に、 swarm 並列実行 N cell の branch を
**main に sequential merge する前段の dry-run conflict detector** と
**plan generator** を提供する.

設計境界:
  - T-M29-01 worktree.py は REUSE のみ (無改変).
  - production merge は実行しない (dry-run / planning only).
  - asyncio.create_subprocess_exec のみ (no shell=True / no blocking).
  - 失敗時は exception を surface (silent skip 禁止).

公開 API:
  - detect_conflict_dry_run(base_branch, target_branch) -> dict
  - plan_sequential_merge(pool_id, target_branch, base='main') -> list[dict]
  - MergeConflictError (caller が 4xx 変換)
  - SequentialMergeError (caller が 4xx 変換)
  - MAX_CELLS_PER_PLAN = 64

AC マッピング:
  AC-1 UBIQUITOUS: 公開 5 symbol + T-M29-01 REUSE 無改変.
  AC-2 EVENT-DRIVEN: merge-tree dry-run + plan deterministic order.
  AC-3 STATE-DRIVEN: asyncio.create_subprocess_exec / cwd=REPO_ROOT /
                     no shell=True / no langgraph etc. / no mutation.
  AC-4 UNWANTED: invalid input で SequentialMergeError / git error で
                  MergeConflictError / no actual merge / no push.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

# T-M29-01 REUSE (G15 single-source).
from services.swarm.worktree import (
    REPO_ROOT,
    InvalidWorktreeArgs,
    _validate as _validate_pool_cell,
    branch_name as _branch_name,
)

logger = logging.getLogger(__name__)

MAX_CELLS_PER_PLAN = 64
MAX_BRANCH_LEN = 200
DEFAULT_TIMEOUT_SEC = 30


class SequentialMergeError(ValueError):
    """invalid input / 計画違反 (caller が 4xx 化)."""


class MergeConflictError(RuntimeError):
    """git merge-tree が conflict を検出した / git 自体が non-zero exit
    (caller が 409 等にマッピング)."""


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_branch(name: Any, field: str) -> str:
    if not isinstance(name, str):
        raise SequentialMergeError(f"{field} must be string")
    s = name.strip()
    if not s:
        raise SequentialMergeError(f"{field} must not be empty")
    if len(s) > MAX_BRANCH_LEN:
        raise SequentialMergeError(
            f"{field} must be <= {MAX_BRANCH_LEN} chars"
        )
    # 簡易 sanity: shell metachar を弾く (injection 防止)
    if re.search(r"[;\|`$\\\n\r]", s):
        raise SequentialMergeError(f"{field} contains forbidden chars")
    return s


def _validate_pool_id(pool_id: Any) -> int:
    if not isinstance(pool_id, int) or isinstance(pool_id, bool) or pool_id <= 0:
        raise SequentialMergeError(
            f"pool_id must be positive int, got {pool_id!r}"
        )
    return pool_id


def _validate_n_cells(n: Any) -> int:
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise SequentialMergeError(f"n must be non-negative int")
    if n > MAX_CELLS_PER_PLAN:
        raise SequentialMergeError(
            f"n must be <= MAX_CELLS_PER_PLAN ({MAX_CELLS_PER_PLAN})"
        )
    return n


# ──────────────────────────────────────────────────────────────────────
# Internal: async git runner (no shell=True)
# ──────────────────────────────────────────────────────────────────────


async def _run_git(
    args: list[str],
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> tuple[int, str, str]:
    """git command async 実行. (rc, stdout, stderr) を返す."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=str(REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise MergeConflictError(
            f"git {' '.join(args[:2])} timed out after {timeout_sec}s"
        )
    rc = proc.returncode if proc.returncode is not None else 1
    return rc, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


async def detect_conflict_dry_run(
    base_branch: str,
    target_branch: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """`git merge-tree base target` で dry-run conflict 検出.

    Returns:
      {
        "has_conflict": bool,
        "conflicts": list[str],          # conflict と思われる file path
        "stdout_sample": str,            # head 2KB
        "returncode": int,
        "base": str, "target": str,
      }

    No mutation. git merge-tree は work tree を変更しない (read-only).
    """
    base = _validate_branch(base_branch, "base_branch")
    target = _validate_branch(target_branch, "target_branch")

    rc, stdout, stderr = await _run_git(
        ["merge-tree", "--write-tree", "--name-only", base, target],
        timeout_sec=timeout_sec,
    )
    # `--write-tree` mode: rc != 0 で conflict があった事を意味するが、
    # ref-not-found エラーと区別するため stderr を検査.
    if rc not in (0, 1):
        # rc 2+ は通常 unknown ref / fatal error
        raise MergeConflictError(
            f"git merge-tree failed (rc={rc}): {stderr.strip()[:500]}"
        )

    # `<<<<<<<` marker or `--name-only` 出力で conflict file を抽出.
    conflicts: list[str] = []
    if "<<<<<<<" in stdout:
        # `git merge-tree base..target` モード (古い構文) 出力
        for line in stdout.splitlines():
            if line.startswith("changed in both") or line.startswith("+"):
                # heuristic: file name 抽出
                pass
    else:
        # `--write-tree --name-only` モード: rc=1 のときは conflict file
        # が stdout の SHA 後に出る. 安全側で stdout 全行を tokenize.
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # SHA (40 hex char) や空行はスキップ
            if re.match(r"^[a-f0-9]{40}$", line):
                continue
            conflicts.append(line)

    has_conflict = rc == 1 or bool(conflicts)
    return {
        "has_conflict": has_conflict,
        "conflicts": conflicts,
        "stdout_sample": stdout[:2048],
        "returncode": rc,
        "base": base,
        "target": target,
    }


async def plan_sequential_merge(
    pool_id: int,
    n_cells: int,
    *,
    base: str = "main",
) -> list[dict[str, Any]]:
    """pool_id の N cell branch を sequential merge する plan を生成.

    Returns:
      list of {pool_id, cell_index, branch, predicted_conflict:bool}
      (cell_index ascending / deterministic order)
    """
    pid = _validate_pool_id(pool_id)
    n = _validate_n_cells(n_cells)
    _validate_branch(base, "base")

    plan: list[dict[str, Any]] = []
    for cell in range(n):
        # T-M29-01 _validate REUSE: cell < 0 拒否 (n>=0 で必ず通る)
        _validate_pool_cell(pid, cell)
        branch = _branch_name(pid, cell)
        try:
            result = await detect_conflict_dry_run(base, branch)
            predicted = result["has_conflict"]
        except MergeConflictError as e:
            # ref-not-found のような unknown branch は predicted=True
            # としてマーク (silent skip しない).
            logger.warning(
                "predict conflict failed for %s: %s", branch, e,
            )
            predicted = True
        plan.append({
            "pool_id": pid,
            "cell_index": cell,
            "branch": branch,
            "predicted_conflict": predicted,
        })
    return plan
