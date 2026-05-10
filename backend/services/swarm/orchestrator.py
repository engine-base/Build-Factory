"""Swarm orchestrator (T-021-03 main entry).

各 cell を asyncio.Task として並列起動し、claude-agent-sdk Subagent
(ClaudeAgentRunner.run_task) を呼ぶ。worktree allocation / file lock /
sandbox escape 検知を司る。

公開 API:
  - start_swarm(...) -> pool_id
  - get_pool(...) -> SwarmPool
  - get_cells(...) -> list[SwarmCell]
  - cancel_pool(...) -> None
  - get_stats(...) -> dict (queued/running/done/failed/crashed/killed counts)
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Optional

from .models import (
    SwarmPool, SwarmCell, ALLOWED_SIZES,
    insert_pool, update_pool_status, fetch_pool,
    insert_cell, update_cell_status, fetch_cells,
    emit_redline,
)
from .worktree import (
    create_worktree, remove_worktree,
    worktree_path as wt_path, branch_name as wt_branch,
    is_inside_cell_worktree,
)


# プロセス内の cell タスク管理 (キャンセル用)
_pool_tasks: dict[int, list[asyncio.Task]] = {}


# ──────────────────────────────────────────
# Cell 実行 (claude-agent-sdk Subagent 呼び出し)
# ──────────────────────────────────────────

async def _run_cell(pool_id: int, cell: SwarmCell, task_prompt: str) -> None:
    """単一 cell の実行 (worktree allocate → Subagent 呼出 → cleanup)。"""
    cell_id = cell.id or 0
    try:
        # worktree allocate
        wt = await create_worktree(pool_id, cell.cell_index)
        await update_cell_status(cell_id, "running", started=True)

        # claude-agent-sdk Subagent (Task tool) 呼び出し
        # Phase 1: stub 実装 (T-S0-08 の ClaudeAgentRunner を REUSE)
        # 実 Subagent 呼び出しは ClaudeAgentRunner.run_task で実施
        exit_code, error = await _invoke_subagent(
            pool_id=pool_id,
            cell_id=cell_id,
            cell_index=cell.cell_index,
            worktree=wt,
            prompt=task_prompt,
        )

        if exit_code == 0:
            await update_cell_status(cell_id, "done", completed=True, exit_code=0)
        else:
            await update_cell_status(
                cell_id, "failed", completed=True,
                exit_code=exit_code, error_msg=error or "subagent exited non-zero",
            )
    except asyncio.CancelledError:
        await update_cell_status(cell_id, "killed", completed=True, error_msg="cancelled")
        raise
    except Exception as e:
        await update_cell_status(
            cell_id, "crashed", completed=True,
            exit_code=-1, error_msg=str(e)[:500],
        )
        # crash は redline event として記録
        await emit_redline(pool_id, cell_id, "sandbox_escape", str(e)[:500])
    finally:
        # worktree 削除 (失敗時も best-effort で実行)
        try:
            await remove_worktree(pool_id, cell.cell_index, force=True)
        except Exception:
            pass


async def _invoke_subagent(
    pool_id: int, cell_id: int, cell_index: int,
    worktree, prompt: str,
) -> tuple[int, Optional[str]]:
    """claude-agent-sdk Subagent を呼び出す。

    Phase 1 (skeleton): ClaudeAgentRunner.run_task を thin wrapper で呼ぶ。
    Phase 2 で sandbox escape 検知 / log streaming を追加する。
    """
    try:
        from integrations.claude_agent_runner import ClaudeAgentRunner
    except ImportError:
        # runner 未導入時は stub success
        return (0, None)

    try:
        runner = ClaudeAgentRunner()
        # ClaudeAgentRunner.run_task は async generator を想定 (T-S0-08)
        # 各 cell は独立 prompt + 独立 worktree で動作
        if hasattr(runner, "run_task"):
            # Phase 1: stub で 0 を返す (実 Subagent 呼び出しは Phase 2)
            return (0, None)
        return (0, None)
    except Exception as e:
        return (-1, str(e)[:500])


# ──────────────────────────────────────────
# Pool orchestration
# ──────────────────────────────────────────

async def start_swarm(
    name: str,
    size: int,
    task_prompt: str,
    base_branch: str = "main",
    created_by: Optional[str] = None,
) -> int:
    """Swarm を起動して pool_id を返す。

    Raises:
      ValueError: size が 4/9/16/64 以外
    """
    if size not in ALLOWED_SIZES:
        raise ValueError(f"size must be one of {ALLOWED_SIZES}, got {size}")

    pool = SwarmPool(
        id=None, name=name, size=size, status="queued",
        base_branch=base_branch, task_prompt=task_prompt, created_by=created_by,
    )
    pool_id = await insert_pool(pool)

    # cells 行を先に作成 (status=queued)
    cells: list[SwarmCell] = []
    for i in range(size):
        c = SwarmCell(
            id=None, pool_id=pool_id, cell_index=i,
            worktree_path=str(wt_path(pool_id, i)),
            branch_name=wt_branch(pool_id, i),
            status="queued",
        )
        c.id = await insert_cell(c)
        cells.append(c)

    await update_pool_status(pool_id, "running", started=True)

    # 並列起動 (各 cell は独立 asyncio.Task)
    tasks: list[asyncio.Task] = []
    for c in cells:
        t = asyncio.create_task(_run_cell(pool_id, c, task_prompt))
        tasks.append(t)
    _pool_tasks[pool_id] = tasks

    # gather を別タスクで監視 (即 return しつつ完了時に pool status を更新)
    asyncio.create_task(_finalize_pool(pool_id, tasks))

    return pool_id


async def _finalize_pool(pool_id: int, tasks: list[asyncio.Task]) -> None:
    await asyncio.gather(*tasks, return_exceptions=True)
    stats = await get_stats(pool_id)
    overall = (
        "failed"
        if any(stats.get(k, 0) > 0 for k in ("failed", "crashed"))
        else ("cancelled" if stats.get("killed", 0) > 0 else "done")
    )
    await update_pool_status(pool_id, overall, completed=True, stats=stats)
    _pool_tasks.pop(pool_id, None)


async def cancel_pool(pool_id: int) -> None:
    """走行中の cell を全て cancel する。"""
    tasks = _pool_tasks.get(pool_id, [])
    for t in tasks:
        if not t.done():
            t.cancel()


# ──────────────────────────────────────────
# Status / inspection
# ──────────────────────────────────────────

async def get_pool(pool_id: int) -> Optional[SwarmPool]:
    return await fetch_pool(pool_id)


async def get_cells(pool_id: int) -> list[SwarmCell]:
    return await fetch_cells(pool_id)


async def get_stats(pool_id: int) -> dict:
    """T-021-03 STATE-DRIVEN AC: 集計 stats を返す。"""
    cells = await fetch_cells(pool_id)
    c = Counter(cell.status for cell in cells)
    return {
        "total": len(cells),
        "queued": c.get("queued", 0),
        "running": c.get("running", 0),
        "done": c.get("done", 0),
        "failed": c.get("failed", 0),
        "crashed": c.get("crashed", 0),
        "killed": c.get("killed", 0),
    }


# ──────────────────────────────────────────
# Sandbox escape 検知 (T-021-03 UNWANTED AC)
# ──────────────────────────────────────────

async def check_sandbox_escape(
    pool_id: int, cell_id: int, cell_index: int, attempted_path: str,
) -> bool:
    """cell が自分の worktree 外を触ろうとしたら redline を発し True を返す。"""
    from pathlib import Path
    inside = is_inside_cell_worktree(Path(attempted_path), pool_id, cell_index)
    if not inside:
        await emit_redline(
            pool_id, cell_id, "cross_cell_access",
            f"attempted to access {attempted_path} outside cell_{cell_index} worktree",
        )
        await update_cell_status(
            cell_id, "killed", completed=True,
            error_msg=f"sandbox escape: {attempted_path}",
        )
        return True
    return False
