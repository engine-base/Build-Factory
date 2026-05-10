"""T-021-03: Swarm 並列実行基盤

claude-agent-sdk Subagent (Task tool) + git worktree で 4/9/16/64 cell の並列
セッションを起動する。各 cell は独立した worktree + branch を持ち、file-level
lock で衝突を防止する。

公開 API:
  - orchestrator.start_swarm(pool_size, task_prompt, base_branch) -> pool_id
  - orchestrator.get_pool(pool_id) -> SwarmPool
  - orchestrator.get_cells(pool_id) -> list[SwarmCell]
  - orchestrator.cancel_pool(pool_id) -> None
"""

from .models import SwarmPool, SwarmCell, RedlineEvent, ALLOWED_SIZES
from .orchestrator import start_swarm, get_pool, get_cells, cancel_pool, get_stats

__all__ = [
    "SwarmPool",
    "SwarmCell",
    "RedlineEvent",
    "ALLOWED_SIZES",
    "start_swarm",
    "get_pool",
    "get_cells",
    "cancel_pool",
    "get_stats",
]
