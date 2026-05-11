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


# ---------------------------------------------------------------------------
# T-021-03 AC 全網羅 (DB / git worktree / Subagent 全 mock)
# ---------------------------------------------------------------------------

import sys
import types
from pathlib import Path
from typing import Any

from services.swarm import orchestrator as orc
from services.swarm.models import SwarmCell, SwarmPool
from services.swarm.worktree import is_inside_cell_worktree, worktree_path


@pytest.fixture
def mock_swarm_db(monkeypatch):
    """orchestrator.* / models.* / worktree.* の DB / git 呼び出しを差し替え."""
    state: dict[str, Any] = {
        "pools": {},
        "cells": {},
        "redlines": [],
        "next_pool_id": 1,
        "next_cell_id": 1,
        "worktrees_created": [],
        "worktrees_removed": [],
    }

    async def fake_insert_pool(pool: SwarmPool) -> int:
        pid = state["next_pool_id"]
        state["next_pool_id"] += 1
        pool.id = pid
        state["pools"][pid] = pool
        return pid

    async def fake_insert_cell(cell: SwarmCell) -> int:
        cid = state["next_cell_id"]
        state["next_cell_id"] += 1
        cell.id = cid
        state["cells"][cid] = cell
        return cid

    async def fake_update_pool_status(pool_id, status, *, started=False, completed=False, stats=None):
        p = state["pools"].get(pool_id)
        if p:
            p.status = status

    async def fake_update_cell_status(cell_id, status, *, started=False, completed=False,
                                       exit_code=None, error_msg=None, session_id=None):
        c = state["cells"].get(cell_id)
        if c:
            c.status = status
            if exit_code is not None:
                c.exit_code = exit_code
            if error_msg is not None:
                c.error_msg = error_msg
            if session_id is not None:
                c.session_id = session_id

    async def fake_fetch_cells(pool_id):
        return [c for c in state["cells"].values() if c.pool_id == pool_id]

    async def fake_fetch_pool(pool_id):
        return state["pools"].get(pool_id)

    async def fake_emit_redline(pool_id, cell_id, event_type, detail=None):
        state["redlines"].append({
            "pool_id": pool_id, "cell_id": cell_id,
            "event_type": event_type, "detail": detail,
        })

    async def fake_create_worktree(pool_id, cell_index, base_branch="main"):
        p = worktree_path(pool_id, cell_index)
        state["worktrees_created"].append(str(p))
        return p

    async def fake_remove_worktree(pool_id, cell_index, *, force=False):
        state["worktrees_removed"].append((pool_id, cell_index))

    # orchestrator が import している名前を全て差し替え
    monkeypatch.setattr(orc, "insert_pool", fake_insert_pool)
    monkeypatch.setattr(orc, "insert_cell", fake_insert_cell)
    monkeypatch.setattr(orc, "update_pool_status", fake_update_pool_status)
    monkeypatch.setattr(orc, "update_cell_status", fake_update_cell_status)
    monkeypatch.setattr(orc, "fetch_cells", fake_fetch_cells)
    monkeypatch.setattr(orc, "fetch_pool", fake_fetch_pool)
    monkeypatch.setattr(orc, "emit_redline", fake_emit_redline)
    monkeypatch.setattr(orc, "create_worktree", fake_create_worktree)
    monkeypatch.setattr(orc, "remove_worktree", fake_remove_worktree)

    return state


def _install_runner_stub_returning_done():
    """ClaudeAgentRunner を stub 化 (AC-1 Subagent 経路)."""
    mod = types.ModuleType("integrations.claude_agent_runner")

    class _Rec:
        id = 999
        status = "done"
        crash_reason = None

    class ClaudeAgentRunner:
        async def run_task(self, **kw: Any) -> Any:
            return _Rec()

    mod.ClaudeAgentRunner = ClaudeAgentRunner
    sys.modules["integrations.claude_agent_runner"] = mod


def _install_runner_stub_returning_crashed():
    mod = types.ModuleType("integrations.claude_agent_runner")

    class _Rec:
        id = 1000
        status = "crashed"
        crash_reason = "sandbox_violation"

    class ClaudeAgentRunner:
        async def run_task(self, **kw: Any) -> Any:
            return _Rec()

    mod.ClaudeAgentRunner = ClaudeAgentRunner
    sys.modules["integrations.claude_agent_runner"] = mod


@pytest.mark.parametrize("size", [4, 9, 16, 64])
def test_start_swarm_spawns_each_allowed_size(size, mock_swarm_db):
    """AC-1 UBIQUITOUS: 4/9/16/64 全 size で N cells 作成 + 並列起動."""
    _install_runner_stub_returning_done()
    pool_id = asyncio.run(start_swarm(name=f"pool{size}", size=size, task_prompt="noop"))
    # cells が size 個作られた
    assert len([c for c in mock_swarm_db["cells"].values() if c.pool_id == pool_id]) == size
    # _finalize_pool は別タスクで動くので明示的に await
    async def _wait():
        await asyncio.sleep(0.05)
    asyncio.run(_wait())
    sys.modules.pop("integrations.claude_agent_runner", None)


def test_worktree_allocated_under_swarm_pool_subdir(mock_swarm_db):
    """AC-2 EVENT: worktree は .worktrees/swarm_{pool_id}/cell_{n}."""
    _install_runner_stub_returning_done()
    pool_id = asyncio.run(start_swarm(name="x", size=4, task_prompt="noop"))
    asyncio.run(asyncio.sleep(0.05))
    for path in mock_swarm_db["worktrees_created"]:
        assert f"swarm_{pool_id}" in path
        assert "cell_" in path
    sys.modules.pop("integrations.claude_agent_runner", None)


def test_get_stats_aggregates_by_status(mock_swarm_db):
    """AC-3 STATE: queued/running/done/failed/crashed/killed の集計."""
    _install_runner_stub_returning_done()
    pool_id = asyncio.run(start_swarm(name="x", size=4, task_prompt="noop"))
    asyncio.run(asyncio.sleep(0.05))
    stats = asyncio.run(orc.get_stats(pool_id))
    assert stats["total"] == 4
    # 全 cell が done (stub) か少なくとも terminal 状態
    assert sum(stats[k] for k in ("done", "failed", "crashed", "killed", "running", "queued")) == 4
    sys.modules.pop("integrations.claude_agent_runner", None)


def test_get_pool_returns_inserted_pool(mock_swarm_db):
    _install_runner_stub_returning_done()
    pool_id = asyncio.run(start_swarm(name="px", size=4, task_prompt="noop"))
    asyncio.run(asyncio.sleep(0.05))
    p = asyncio.run(orc.get_pool(pool_id))
    assert p is not None
    assert p.size == 4
    sys.modules.pop("integrations.claude_agent_runner", None)


def test_get_cells_returns_n_cells(mock_swarm_db):
    _install_runner_stub_returning_done()
    pool_id = asyncio.run(start_swarm(name="x", size=9, task_prompt="noop"))
    asyncio.run(asyncio.sleep(0.05))
    cells = asyncio.run(orc.get_cells(pool_id))
    assert len(cells) == 9
    sys.modules.pop("integrations.claude_agent_runner", None)


def test_subagent_crash_propagates_to_cell_status(mock_swarm_db):
    """Subagent が crashed を返したら cell.status = failed."""
    _install_runner_stub_returning_crashed()
    pool_id = asyncio.run(start_swarm(name="x", size=4, task_prompt="noop"))
    asyncio.run(asyncio.sleep(0.05))
    cells = [c for c in mock_swarm_db["cells"].values() if c.pool_id == pool_id]
    # crashed (rc=-1) 経由で cell.status = failed
    assert all(c.status == "failed" for c in cells), [c.status for c in cells]
    sys.modules.pop("integrations.claude_agent_runner", None)


# ---------------------------------------------------------------------------
# AC-5 UNWANTED: sandbox escape detection
# ---------------------------------------------------------------------------


def test_check_sandbox_escape_kills_cell_and_emits_redline(mock_swarm_db):
    """cell が自分の worktree 外を触ろうとしたら kill + redline."""
    # cell を直接生成
    cell = SwarmCell(
        id=1, pool_id=1, cell_index=0,
        worktree_path=".worktrees/swarm_1/cell_0",
        branch_name="swarm/1/cell-0", status="running",
    )
    mock_swarm_db["cells"][1] = cell
    escaped = asyncio.run(
        orc.check_sandbox_escape(
            pool_id=1, cell_id=1, cell_index=0,
            attempted_path="/etc/passwd",
        )
    )
    assert escaped is True
    assert mock_swarm_db["cells"][1].status == "killed"
    assert any(r["event_type"] == "cross_cell_access" for r in mock_swarm_db["redlines"])


def test_check_sandbox_escape_allows_inside_path(mock_swarm_db):
    """worktree 内のパスは escape にならない."""
    inside = str(worktree_path(99, 0)) + "/some_file.py"
    escaped = asyncio.run(
        orc.check_sandbox_escape(
            pool_id=99, cell_id=42, cell_index=0,
            attempted_path=inside,
        )
    )
    assert escaped is False
    assert not any(r["pool_id"] == 99 for r in mock_swarm_db["redlines"])


def test_is_inside_cell_worktree_for_root_path() -> None:
    """worktree 自体のパスは inside 判定."""
    p = worktree_path(7, 2)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.mkdir(exist_ok=True)
    try:
        assert is_inside_cell_worktree(p, 7, 2) is True
        assert is_inside_cell_worktree(Path("/etc"), 7, 2) is False
    finally:
        import shutil
        shutil.rmtree(p.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC-4 OPTIONAL: file lock (in-proc 部分のみ実 DB なし検証)
# ---------------------------------------------------------------------------


def test_file_lock_inproc_serializes_concurrent_acquirers(monkeypatch):
    """同じ file_path に対する 2 つの取得は順番待ちで serialize される."""
    from services.swarm import file_lock as fl

    async def fake_acquire(pool_id, cell_id, file_path):
        return 1

    async def fake_release(lock_id):
        return None

    monkeypatch.setattr(fl, "_acquire_db", fake_acquire)
    monkeypatch.setattr(fl, "_release_db", fake_release)

    order: list[str] = []

    async def worker(name: str, delay: float):
        async with fl.file_lock(1, 1, "/x/y"):
            order.append(f"{name}-enter")
            await asyncio.sleep(delay)
            order.append(f"{name}-exit")

    async def runner():
        await asyncio.gather(worker("A", 0.02), worker("B", 0.0))

    asyncio.run(runner())
    # A が先に enter→exit してから B (順序不問だが入れ子にはならない)
    assert order in (
        ["A-enter", "A-exit", "B-enter", "B-exit"],
        ["B-enter", "B-exit", "A-enter", "A-exit"],
    )


def test_file_lock_yields_lock_id(monkeypatch):
    from services.swarm import file_lock as fl

    async def fake_acquire(pool_id, cell_id, file_path):
        return 42

    async def fake_release(lock_id):
        return None

    monkeypatch.setattr(fl, "_acquire_db", fake_acquire)
    monkeypatch.setattr(fl, "_release_db", fake_release)

    async def runner():
        async with fl.file_lock(1, 1, "/foo") as lid:
            return lid

    assert asyncio.run(runner()) == 42


# ---------------------------------------------------------------------------
# cancel_pool (cancellable)
# ---------------------------------------------------------------------------


def test_cancel_pool_within_same_event_loop(mock_swarm_db):
    """cancel_pool は registered tasks に対して呼ぶだけ (smoke).

    実際の cancel 伝播は asyncio.Task の race に依存するので
    ここでは「呼び出しがエラーなく完走」と「pool_id が記録された」を確認."""
    _install_runner_stub_returning_done()

    async def _run():
        pid = await start_swarm(name="x", size=4, task_prompt="noop")
        assert pid in orc._pool_tasks
        await orc.cancel_pool(pid)
        # cancel 後、 全タスクが destroy される前に finalize させる
        for t in list(orc._pool_tasks.get(pid, [])):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        return pid

    asyncio.run(_run())
    sys.modules.pop("integrations.claude_agent_runner", None)


def test_cancel_pool_with_unknown_id_is_noop(mock_swarm_db):
    """存在しない pool_id への cancel は例外を出さない."""
    asyncio.run(orc.cancel_pool(99999))


# ---------------------------------------------------------------------------
# worktree.py: subprocess を mock して create / remove / list / _run_git
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, rc: int = 0, out: bytes = b"", err: bytes = b"") -> None:
        self.returncode = rc
        self._out = out
        self._err = err

    async def communicate(self):
        return (self._out, self._err)


def test_create_worktree_runs_git_branch_and_worktree_add(monkeypatch, tmp_path):
    """AC-1/AC-2: create_worktree は git branch -D → git worktree add を呼ぶ."""
    from services.swarm import worktree as wt

    calls: list[list[str]] = []

    async def fake_exec(*args, **kw):
        calls.append(list(args))
        return _FakeProc(rc=0)

    monkeypatch.setattr(wt.asyncio, "create_subprocess_exec", fake_exec)
    # WORKTREES_BASE を tmp に差し替えて FS 副作用を局所化
    monkeypatch.setattr(wt, "WORKTREES_BASE", tmp_path / ".worktrees")
    monkeypatch.setattr(
        wt, "worktree_path",
        lambda pid, ci: tmp_path / ".worktrees" / f"swarm_{pid}" / f"cell_{ci}",
    )

    p = asyncio.run(wt.create_worktree(pool_id=5, cell_index=2))
    assert p.parent.exists()
    # git branch -D + git worktree add の 2 呼び出し
    assert any("branch" in c and "-D" in c for c in calls)
    assert any("worktree" in c and "add" in c for c in calls)


def test_create_worktree_raises_runtime_error_on_git_failure(monkeypatch, tmp_path):
    from services.swarm import worktree as wt

    call_idx = {"i": 0}

    async def fake_exec(*args, **kw):
        call_idx["i"] += 1
        # 1 回目 (branch -D) は exit 1 (既存無し OK), 2 回目 (worktree add) も fail
        if "worktree" in args and "add" in args:
            return _FakeProc(rc=128, err=b"already exists")
        return _FakeProc(rc=0)

    monkeypatch.setattr(wt.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(wt, "WORKTREES_BASE", tmp_path / ".worktrees")
    monkeypatch.setattr(
        wt, "worktree_path",
        lambda pid, ci: tmp_path / ".worktrees" / f"swarm_{pid}" / f"cell_{ci}",
    )

    with pytest.raises(RuntimeError, match="git worktree add failed"):
        asyncio.run(wt.create_worktree(pool_id=1, cell_index=0))


def test_remove_worktree_runs_git_remove_and_branch_delete(monkeypatch, tmp_path):
    from services.swarm import worktree as wt

    calls: list[list[str]] = []

    async def fake_exec(*args, **kw):
        calls.append(list(args))
        return _FakeProc(rc=0)

    monkeypatch.setattr(wt.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(wt, "WORKTREES_BASE", tmp_path / ".worktrees")
    monkeypatch.setattr(
        wt, "worktree_path",
        lambda pid, ci: tmp_path / ".worktrees" / f"swarm_{pid}" / f"cell_{ci}",
    )
    asyncio.run(wt.remove_worktree(pool_id=3, cell_index=1, force=True))
    assert any("worktree" in c and "remove" in c and "--force" in c for c in calls)
    assert any("branch" in c and "-D" in c for c in calls)


def test_list_worktrees_parses_porcelain_output(monkeypatch):
    from services.swarm import worktree as wt

    sample = b"worktree /path/a\nHEAD abc\n\nworktree /path/b\nHEAD def\n"

    async def fake_exec(*args, **kw):
        return _FakeProc(rc=0, out=sample)

    monkeypatch.setattr(wt.asyncio, "create_subprocess_exec", fake_exec)
    out = asyncio.run(wt.list_worktrees())
    assert out == ["/path/a", "/path/b"]


def test_list_worktrees_returns_empty_on_git_failure(monkeypatch):
    from services.swarm import worktree as wt

    async def fake_exec(*args, **kw):
        return _FakeProc(rc=1)

    monkeypatch.setattr(wt.asyncio, "create_subprocess_exec", fake_exec)
    assert asyncio.run(wt.list_worktrees()) == []


def test_run_git_decodes_output(monkeypatch):
    from services.swarm import worktree as wt

    async def fake_exec(*args, **kw):
        return _FakeProc(rc=0, out=b"hello", err=b"warn")

    monkeypatch.setattr(wt.asyncio, "create_subprocess_exec", fake_exec)
    rc, out, err = asyncio.run(wt._run_git(["status"]))
    assert (rc, out, err) == (0, "hello", "warn")


# ---------------------------------------------------------------------------
# models.py: DB connect を mock して CRUD ops
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows: list[Any] | None = None, lastrowid: int = 0) -> None:
        self._rows = rows or []
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, *, cursor: _FakeCursor | None = None) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._cursor = cursor or _FakeCursor()

    async def execute(self, sql: str, params: tuple = ()):
        self.executed.append((sql, params))
        return self._cursor

    async def commit(self) -> None:
        return None

    async def __aenter__(self) -> "_FakeDB":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _patch_models_db(monkeypatch, *, cursor: _FakeCursor | None = None) -> _FakeDB:
    from services.swarm import models as m
    fake = _FakeDB(cursor=cursor)
    # row_factory 代入を受け流す (no-op)
    fake.row_factory = None  # type: ignore[attr-defined]

    fake_db_module = types.SimpleNamespace(
        connect=lambda _path: fake,
        Row=dict,  # fetch_pool 内 `db.row_factory = _db().Row` を吸収
    )
    monkeypatch.setattr(m, "_db", lambda: fake_db_module)
    monkeypatch.setattr(m, "_db_path", lambda: ":memory:")
    return fake


def test_models_insert_pool_runs_insert_and_returns_id(monkeypatch):
    from services.swarm.models import insert_pool, SwarmPool
    fake = _patch_models_db(monkeypatch, cursor=_FakeCursor(lastrowid=7))
    pid = asyncio.run(insert_pool(SwarmPool(id=None, name="x", size=4, status="queued")))
    assert pid == 7
    assert any("INSERT INTO swarm_pools" in sql for sql, _ in fake.executed)


def test_models_insert_cell_runs_insert_and_returns_id(monkeypatch):
    from services.swarm.models import insert_cell, SwarmCell
    fake = _patch_models_db(monkeypatch, cursor=_FakeCursor(lastrowid=42))
    cid = asyncio.run(
        insert_cell(SwarmCell(
            id=None, pool_id=1, cell_index=0,
            worktree_path="/x", branch_name="b", status="queued",
        ))
    )
    assert cid == 42
    assert any("INSERT INTO swarm_cells" in sql for sql, _ in fake.executed)


def test_models_update_pool_status_with_started_and_completed(monkeypatch):
    from services.swarm.models import update_pool_status
    fake = _patch_models_db(monkeypatch)
    asyncio.run(update_pool_status(1, "running", started=True))
    asyncio.run(update_pool_status(1, "done", completed=True, stats={"done": 4}))
    sqls = [s for s, _ in fake.executed]
    assert any("UPDATE swarm_pools" in s for s in sqls)
    assert any("started_at" in s for s in sqls)
    assert any("completed_at" in s for s in sqls)


def test_models_update_cell_status_with_all_kwargs(monkeypatch):
    from services.swarm.models import update_cell_status
    fake = _patch_models_db(monkeypatch)
    asyncio.run(update_cell_status(
        1, "done", completed=True, exit_code=0, error_msg=None, session_id=99,
    ))
    asyncio.run(update_cell_status(2, "running", started=True))
    sqls = [s for s, _ in fake.executed]
    assert any("UPDATE swarm_cells" in s for s in sqls)


def test_models_fetch_pool_returns_dataclass(monkeypatch):
    from services.swarm.models import fetch_pool
    row = {
        "id": 1, "name": "x", "size": 4, "status": "done",
        "base_branch": "main", "task_prompt": "noop", "created_by": None,
        "created_at": None, "started_at": None, "completed_at": None,
        "stats_json": '{"done": 4}',
    }
    _patch_models_db(monkeypatch, cursor=_FakeCursor(rows=[row]))
    p = asyncio.run(fetch_pool(1))
    assert p is not None and p.size == 4 and p.stats() == {"done": 4}


def test_models_fetch_pool_returns_none_when_missing(monkeypatch):
    from services.swarm.models import fetch_pool
    _patch_models_db(monkeypatch, cursor=_FakeCursor(rows=[]))
    assert asyncio.run(fetch_pool(999)) is None


def test_models_fetch_cells_returns_list(monkeypatch):
    from services.swarm.models import fetch_cells
    rows = [
        {
            "id": 1, "pool_id": 1, "cell_index": 0,
            "worktree_path": "/x", "branch_name": "b", "status": "done",
            "session_id": 10, "exit_code": 0, "error_msg": None,
            "log_path": None, "started_at": None, "completed_at": None,
        },
    ]
    _patch_models_db(monkeypatch, cursor=_FakeCursor(rows=rows))
    cells = asyncio.run(fetch_cells(1))
    assert len(cells) == 1 and cells[0].status == "done"


def test_models_emit_redline_inserts_redline(monkeypatch):
    from services.swarm.models import emit_redline
    fake = _patch_models_db(monkeypatch)
    asyncio.run(emit_redline(1, 2, "sandbox_escape", "detail"))
    assert any("INSERT INTO swarm_redline_events" in s for s, _ in fake.executed)


# ---------------------------------------------------------------------------
# file_lock.py: DB ops を mock
# ---------------------------------------------------------------------------


def test_file_lock_acquire_release_db_mocked(monkeypatch):
    from services.swarm import file_lock as fl
    fake = _FakeDB(cursor=_FakeCursor(lastrowid=7))
    fake_db_module = types.SimpleNamespace(connect=lambda _path: fake)
    monkeypatch.setattr(fl, "_db", lambda: fake_db_module)
    monkeypatch.setattr(fl, "_db_path", lambda: ":memory:")

    lock_id = asyncio.run(fl._acquire_db(1, 2, "/foo"))
    assert lock_id == 7
    asyncio.run(fl._release_db(lock_id))
    sqls = [s for s, _ in fake.executed]
    assert any("INSERT INTO swarm_file_locks" in s for s in sqls)
    assert any("UPDATE swarm_file_locks" in s for s in sqls)


def test_file_lock_active_locks_for_returns_count(monkeypatch):
    from services.swarm import file_lock as fl
    fake = _FakeDB(cursor=_FakeCursor(rows=[(3,)]))
    fake_db_module = types.SimpleNamespace(connect=lambda _path: fake)
    monkeypatch.setattr(fl, "_db", lambda: fake_db_module)
    monkeypatch.setattr(fl, "_db_path", lambda: ":memory:")
    n = asyncio.run(fl.active_locks_for("/foo"))
    assert n == 3
