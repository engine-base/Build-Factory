"""T-021-03: Swarm 並列実行の smoke test.

minimal scope:
  - size 検証 (ALLOWED_SIZES 4/9/16/64 のみ受理、それ以外は ValueError)
  - worktree path / branch name の命名規則
  - SwarmPool / SwarmCell dataclass の整合性
"""
from __future__ import annotations

import asyncio

import pytest

from services.swarm import ALLOWED_SIZES, start_swarm
from services.swarm.models import SwarmPool, SwarmCell, RedlineEvent
from services.swarm.worktree import worktree_path, branch_name


def test_allowed_sizes_constant() -> None:
    assert ALLOWED_SIZES == (4, 9, 16, 64)


def test_worktree_path_and_branch_naming() -> None:
    p = worktree_path(pool_id=42, cell_index=3)
    assert str(p).endswith(".worktrees/swarm_42/cell_3")
    assert branch_name(pool_id=42, cell_index=3) == "swarm/42/cell-3"


def test_swarm_pool_dataclass_defaults() -> None:
    p = SwarmPool(id=None, name="t", size=4, status="queued")
    assert p.base_branch == "main"
    assert p.task_prompt is None
    assert p.stats() == {}


def test_swarm_cell_dataclass_defaults() -> None:
    c = SwarmCell(
        id=None, pool_id=1, cell_index=0,
        worktree_path="x", branch_name="b", status="queued",
    )
    assert c.session_id is None
    assert c.exit_code is None


def test_redline_event_dataclass() -> None:
    e = RedlineEvent(id=None, pool_id=1, cell_id=1, event_type="sandbox_escape")
    assert e.detail is None


def test_start_swarm_rejects_invalid_size() -> None:
    with pytest.raises(ValueError, match="size must be one of"):
        asyncio.run(start_swarm(name="x", size=5, task_prompt="noop"))


def test_start_swarm_rejects_zero_size() -> None:
    with pytest.raises(ValueError):
        asyncio.run(start_swarm(name="x", size=0, task_prompt="noop"))
