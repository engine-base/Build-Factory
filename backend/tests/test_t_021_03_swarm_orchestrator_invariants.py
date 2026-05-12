"""T-021-03: Swarm 並列実行 (Subagent + git worktree) — 5 AC.

Production artifact 完成済
(backend/services/swarm/{__init__,orchestrator,models,worktree,file_lock}.py
+ backend/routers/swarm.py).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : __init__ re-export + ALLOWED_SIZES (4/9/16/64) /
                       start_swarm signature + ValueError on bad size /
                       _invoke_subagent → ClaudeAgentRunner.run_task
                       (ADR-010 claude-agent-sdk main path).
  AC-2 EVENT-DRIVEN  : insert_pool 'queued' / insert_cell with
                       worktree_path + branch_name / update to 'running'
                       / asyncio.create_task per cell / create_worktree
                       'worktree.created' audit.
  AC-3 STATE-DRIVEN  : get_stats returns 7-key dict /
                       _finalize_pool aggregates failed > cancelled >
                       done.
  AC-4 OPTIONAL      : file_lock async context manager + in-proc
                       asyncio.Lock + swarm_file_locks INSERT /
                       cancel_pool iterates _pool_tasks.
  AC-5 UNWANTED      : check_sandbox_escape → 'cross_cell_access'
                       redline + cell 'killed' / _run_cell crash →
                       'sandbox_escape' redline / no langgraph / no
                       hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SWARM_INIT = REPO_ROOT / "backend" / "services" / "swarm" / "__init__.py"
SWARM_ORCH = REPO_ROOT / "backend" / "services" / "swarm" / "orchestrator.py"
SWARM_MODELS = REPO_ROOT / "backend" / "services" / "swarm" / "models.py"
SWARM_WORKTREE = REPO_ROOT / "backend" / "services" / "swarm" / "worktree.py"
SWARM_FILELOCK = REPO_ROOT / "backend" / "services" / "swarm" / "file_lock.py"
SWARM_ROUTER = REPO_ROOT / "backend" / "routers" / "swarm.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — barrel re-export + ALLOWED_SIZES + start_swarm sig
# ══════════════════════════════════════════════════════════════════════


def test_ac1_swarm_package_module_exists():
    assert SWARM_INIT.exists()
    assert SWARM_ORCH.exists()
    assert SWARM_MODELS.exists()
    assert SWARM_WORKTREE.exists()
    assert SWARM_FILELOCK.exists()


def test_ac1_swarm_barrel_reexports():
    from services import swarm
    for sym in (
        "start_swarm", "get_pool", "get_cells", "cancel_pool", "get_stats",
        "SwarmPool", "SwarmCell", "RedlineEvent", "ALLOWED_SIZES",
    ):
        assert hasattr(swarm, sym), f"services.swarm missing {sym}"
    # __all__ にも含まれる
    for sym in (
        "start_swarm", "get_pool", "ALLOWED_SIZES", "SwarmPool",
    ):
        assert sym in swarm.__all__


def test_ac1_allowed_sizes_4_9_16_64():
    from services.swarm import ALLOWED_SIZES
    assert ALLOWED_SIZES == (4, 9, 16, 64)


def test_ac1_start_swarm_signature():
    from services.swarm import start_swarm
    sig = inspect.signature(start_swarm)
    params = sig.parameters
    for name in ("name", "size", "task_prompt"):
        assert name in params
    # base_branch default
    assert params.get("base_branch") and params["base_branch"].default == "main"
    # created_by Optional default None
    assert params.get("created_by") and params["created_by"].default is None


@pytest.mark.asyncio
async def test_ac1_start_swarm_rejects_bad_size():
    """size が ALLOWED_SIZES に含まれないなら ValueError."""
    from services.swarm import start_swarm
    with pytest.raises(ValueError) as e:
        await start_swarm(name="bad", size=5, task_prompt="x")
    assert "size" in str(e.value)


def test_ac1_invoke_subagent_uses_claude_agent_runner():
    """ADR-010: _invoke_subagent は ClaudeAgentRunner.run_task を呼ぶ."""
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def _invoke_subagent[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "ClaudeAgentRunner" in body
    assert "run_task" in body
    assert "cwd" in body  # worktree を cwd に


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — INSERT + worktree_path + create_task + audit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_start_swarm_inserts_pool_queued():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def start_swarm[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "insert_pool" in body
    assert "queued" in body


def test_ac2_cells_inserted_with_worktree_path_and_branch():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def start_swarm[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "insert_cell" in body
    assert "wt_path" in body or "worktree_path" in body
    assert "wt_branch" in body or "branch_name" in body


def test_ac2_pool_status_updated_to_running():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def start_swarm[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(
        r"update_pool_status\([\s\S]+?[\"']running[\"'][\s\S]+?started\s*=\s*True",
        body,
    )


def test_ac2_each_cell_runs_in_asyncio_create_task():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def start_swarm[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "asyncio.create_task" in body
    assert "_pool_tasks" in body


def test_ac2_create_worktree_runs_git_worktree_add_and_emits_audit():
    src = SWARM_WORKTREE.read_text(encoding="utf-8")
    m = re.search(
        r"async def create_worktree[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(
        r"\[\"worktree\",\s*\"add\",\s*\"-b\"",
        body,
    )
    assert "worktree.created" in body


def test_ac2_worktree_path_format():
    from services.swarm.worktree import worktree_path, branch_name, WORKTREES_BASE
    p = worktree_path(7, 3)
    assert "swarm_7" in str(p) and "cell_3" in str(p)
    assert str(WORKTREES_BASE) in str(p)
    assert branch_name(7, 3) == "swarm/7/cell-3"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — get_stats 7-key dict + _finalize_pool aggregation
# ══════════════════════════════════════════════════════════════════════


def test_ac3_get_stats_returns_seven_key_dict():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def get_stats[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    for key in ("total", "queued", "running", "done", "failed", "crashed", "killed"):
        assert f'"{key}"' in body, f"get_stats missing {key} key"
    assert "Counter" in body


def test_ac3_finalize_pool_aggregates_failed_cancelled_done():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def _finalize_pool[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "failed" in body
    assert "cancelled" in body or "killed" in body
    assert "done" in body
    assert "update_pool_status" in body
    assert "completed" in body


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — file_lock + asyncio.Lock + cancel_pool
# ══════════════════════════════════════════════════════════════════════


def test_ac4_file_lock_is_async_context_manager():
    src = SWARM_FILELOCK.read_text(encoding="utf-8")
    assert re.search(r"@asynccontextmanager\s*\n\s*async def file_lock", src)


def test_ac4_file_lock_uses_inproc_asyncio_lock_and_db_insert():
    src = SWARM_FILELOCK.read_text(encoding="utf-8")
    m = re.search(
        r"async def file_lock[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "_get_inproc_lock" in body
    assert "_acquire_db" in body
    assert "_release_db" in body


def test_ac4_swarm_file_locks_insert_with_released_at_null():
    src = SWARM_FILELOCK.read_text(encoding="utf-8")
    assert "INSERT INTO swarm_file_locks" in src
    # release UPDATE sets released_at
    assert re.search(r"UPDATE\s+swarm_file_locks\s+SET\s+released_at\s*=", src)


def test_ac4_cancel_pool_iterates_pool_tasks():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def cancel_pool[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "_pool_tasks" in body
    assert ".cancel()" in body
    assert "t.done()" in body or "not t.done" in body


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — sandbox escape + crash → redline / no langgraph / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_check_sandbox_escape_emits_cross_cell_redline():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def check_sandbox_escape[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "emit_redline" in body
    assert "cross_cell_access" in body
    # cell → 'killed'
    assert re.search(
        r"update_cell_status\([^)]*[\"']killed[\"']",
        body,
    )


def test_ac5_run_cell_crash_emits_sandbox_escape_redline():
    src = SWARM_ORCH.read_text(encoding="utf-8")
    m = re.search(
        r"async def _run_cell[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # generic Exception 経路で 'crashed' + emit_redline 'sandbox_escape'
    assert "crashed" in body
    assert "emit_redline" in body
    assert "sandbox_escape" in body


def test_ac5_no_langgraph_langchain_litellm():
    for path in (
        SWARM_INIT, SWARM_ORCH, SWARM_MODELS, SWARM_WORKTREE, SWARM_FILELOCK,
        SWARM_ROUTER,
    ):
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8").lower()
        for bad in ("langgraph", "langchain", "litellm"):
            assert bad not in src, f"{path.name} imports {bad}"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (
        SWARM_INIT, SWARM_ORCH, SWARM_MODELS, SWARM_WORKTREE, SWARM_FILELOCK,
        SWARM_ROUTER,
    ):
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_021_03_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-03"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), f"non-canonical EARS type: {ty}"
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_021_03_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-03"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/swarm/orchestrator.py" in files
    assert "backend/services/swarm/worktree.py" in files
    assert "backend/services/swarm/file_lock.py" in files


def test_tickets_t_021_03_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-021-03"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "start_swarm",
        "ALLOWED_SIZES",
        "ClaudeAgentRunner",
        "run_task",
        "swarm_cells",
        "swarm_pools",
        "swarm/{pool_id}/cell-{n}",
        "asyncio.create_task",
        "_pool_tasks",
        "get_stats",
        "file_lock",
        "swarm_file_locks",
        "check_sandbox_escape",
        "cross_cell_access",
        "sandbox_escape",
        "ADR-010",
    ):
        assert sym in full, f"T-021-03 AC missing: {sym}"
