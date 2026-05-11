"""T-S0-08: claude-agent-sdk runner pytest (7 AC 全網羅)

claude-agent-sdk は実 install 不要 — sys.modules に fake を差し込んで検証。

AC マッピング:
  AC-1 UBIQUITOUS: claude-agent-sdk が使われる (NOT LangGraph)
  AC-2 UBIQUITOUS: ClaudeAgentOptions に resume=sdk_session_id が渡る
  AC-3 EVENT:      store.create_session + append_log がストリーミングされる
  AC-4 STATE:      cost_hook.record に cache_read/write_tokens が記録される
  AC-5 STATE:      SummaryHook.persist API が存在 (compressed_summary 永続化)
  AC-6 EVENT:      handle_resume の 4-choice + invalid raise
  AC-7 UNWANTED:   runner module に langgraph/langchain import が一切ない
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from integrations.claude_agent_runner import (
    ClaudeAgentRunner,
    CostHook,
    CostRecord,
    InMemorySessionStore,
    SessionRecord,
    SessionStore,
    SummaryHook,
    NoopSummaryHook,
    NoopCostHook,
    VALID_RESUME_CHOICES,
)


# ---------------------------------------------------------------------------
# fake claude-agent-sdk (sys.modules 差し込み)
# ---------------------------------------------------------------------------


def _install_fake_sdk(usage: dict[str, int] | None = None, raise_on_query: bool = False) -> dict[str, Any]:
    """fake claude_agent_sdk を sys.modules に登録。状態を返す (assert で参照)。"""
    state: dict[str, Any] = {"opts": None, "queries": []}

    class _FakeMsg:
        pass

    class AssistantMessage(_FakeMsg):
        def __init__(self, text: str) -> None:
            class _Block:
                pass
            blk = _Block()
            blk.text = text
            self.content = [blk]

    class SystemMessage(_FakeMsg):
        def __init__(self, sdk_id: str) -> None:
            self.data = {"session_id": sdk_id}
            self.content = None

    class ResultMessage(_FakeMsg):
        def __init__(self, usage: dict[str, int]) -> None:
            self.usage = usage
            self.total_cost_usd = 0.001234
            self.content = None

    class ClaudeAgentOptions:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            state["opts"] = kwargs

    class ClaudeSDKClient:
        def __init__(self, *, options: ClaudeAgentOptions) -> None:
            self.options = options

        async def __aenter__(self) -> "ClaudeSDKClient":
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def query(self, prompt: str) -> None:
            state["queries"].append(prompt)
            if raise_on_query:
                raise RuntimeError("simulated subprocess crash")

        async def receive_response(self):
            yield SystemMessage("sdk_session_xyz")
            yield AssistantMessage("hello")
            yield ResultMessage(usage or {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 80,
                "cache_creation_input_tokens": 20,
            })

    mod = types.ModuleType("claude_agent_sdk")
    mod.ClaudeAgentOptions = ClaudeAgentOptions
    mod.ClaudeSDKClient = ClaudeSDKClient
    mod.AssistantMessage = AssistantMessage
    mod.ResultMessage = ResultMessage
    mod.SystemMessage = SystemMessage
    sys.modules["claude_agent_sdk"] = mod
    return state


@pytest.fixture(autouse=True)
def _cleanup_fake_sdk():
    yield
    sys.modules.pop("claude_agent_sdk", None)


# ---------------------------------------------------------------------------
# AC-1 / AC-2 / AC-3 / AC-4 — happy path
# ---------------------------------------------------------------------------


class _RecordingCostHook(CostHook):
    def __init__(self) -> None:
        self.records: list[CostRecord] = []

    async def record(self, cost: CostRecord) -> None:
        self.records.append(cost)


def test_run_task_resume_keeps_supplied_sdk_session_id() -> None:
    """AC-2: resume 指定時は SystemMessage の id で上書きせず維持."""
    state = _install_fake_sdk()
    store = InMemorySessionStore()
    cost_hook = _RecordingCostHook()
    runner = ClaudeAgentRunner(store=store, cost_hook=cost_hook)

    rec = asyncio.run(
        runner.run_task(
            prompt="hello",
            sdk_session_id="resume_me",
            workspace_id=42,
            agent_persona="mary",
            model="claude-sonnet-4-6",
        )
    )
    assert state["opts"]["resume"] == "resume_me"
    assert state["opts"]["model"] == "claude-sonnet-4-6"
    assert state["queries"] == ["hello"]
    assert rec.status == "done"
    assert rec.id is not None
    assert len(store._logs[rec.id]) == 3
    # resume 時は与えた id を維持
    assert rec.sdk_session_id == "resume_me"
    # AC-4: cost_hook に cache_read/write が記録
    assert len(cost_hook.records) == 1
    cr = cost_hook.records[0]
    assert cr.cache_read_tokens == 80
    assert cr.cache_write_tokens == 20
    assert cr.input_tokens == 100
    assert cr.output_tokens == 50
    assert cr.workspace_id == 42


def test_run_task_new_session_records_sdk_session_id_from_system_message() -> None:
    """AC-2: 新規 (resume=None) の場合 SystemMessage の session_id が記録される."""
    state = _install_fake_sdk()
    store = InMemorySessionStore()
    runner = ClaudeAgentRunner(store=store)
    rec = asyncio.run(runner.run_task(prompt="hi"))
    assert state["opts"]["resume"] is None
    assert rec.sdk_session_id == "sdk_session_xyz"
    # update_sdk_session_id 経由で store にも反映
    stored = store._sessions[rec.id]
    assert stored.sdk_session_id == "sdk_session_xyz"


def test_run_task_passes_cwd_for_swarm_worktree() -> None:
    """T-021-03 連携: cwd を指定すると SDK options に渡る。"""
    state = _install_fake_sdk()
    runner = ClaudeAgentRunner()
    asyncio.run(runner.run_task(prompt="x", cwd="/tmp/worktree/cell_1"))
    assert state["opts"]["cwd"] == "/tmp/worktree/cell_1"


def test_run_task_omits_cwd_when_not_given() -> None:
    state = _install_fake_sdk()
    runner = ClaudeAgentRunner()
    asyncio.run(runner.run_task(prompt="x"))
    assert "cwd" not in state["opts"]


# ---------------------------------------------------------------------------
# AC-3 / AC-6 — crash path
# ---------------------------------------------------------------------------


def test_run_task_crash_marks_status_crashed_with_reason() -> None:
    """AC-6 EVENT: subprocess crash → status=crashed + crash_reason."""
    _install_fake_sdk(raise_on_query=True)
    store = InMemorySessionStore()
    runner = ClaudeAgentRunner(store=store)
    rec = asyncio.run(runner.run_task(prompt="boom"))
    assert rec.status == "crashed"
    assert rec.crash_reason is not None
    assert "RuntimeError" in rec.crash_reason
    assert rec.completed_at is not None


# ---------------------------------------------------------------------------
# AC-6 — handle_resume 4-choice
# ---------------------------------------------------------------------------


def test_valid_resume_choices_constant_matches_db_check() -> None:
    """AC-6: migration の CHECK 制約と一致。"""
    assert set(VALID_RESUME_CHOICES) == {
        "from_checkpoint",
        "rerun_full",
        "manual_fix",
        "cancel",
    }


def test_handle_resume_invalid_choice_raises() -> None:
    runner = ClaudeAgentRunner()
    with pytest.raises(ValueError, match="invalid resume choice"):
        asyncio.run(runner.handle_resume(1, "garbage"))


def test_handle_resume_unknown_session_raises() -> None:
    _install_fake_sdk()
    runner = ClaudeAgentRunner()
    with pytest.raises(LookupError, match="session not found"):
        asyncio.run(runner.handle_resume(999, "cancel"))


def test_handle_resume_cancel_marks_cancelled() -> None:
    _install_fake_sdk()
    store = InMemorySessionStore()
    runner = ClaudeAgentRunner(store=store)
    rec = asyncio.run(runner.run_task(prompt="x"))
    out = asyncio.run(runner.handle_resume(rec.id, "cancel"))
    assert out.status == "cancelled"
    assert out.resume_choice == "cancel"


def test_handle_resume_manual_fix_marks_paused() -> None:
    _install_fake_sdk()
    store = InMemorySessionStore()
    runner = ClaudeAgentRunner(store=store)
    rec = asyncio.run(runner.run_task(prompt="x"))
    out = asyncio.run(runner.handle_resume(rec.id, "manual_fix"))
    assert out.status == "paused"
    assert out.resume_choice == "manual_fix"


def test_handle_resume_from_checkpoint_passes_sdk_session_id() -> None:
    state = _install_fake_sdk()
    store = InMemorySessionStore()
    runner = ClaudeAgentRunner(store=store)
    first = asyncio.run(runner.run_task(prompt="x"))
    assert first.sdk_session_id == "sdk_session_xyz"
    state["opts"] = None
    asyncio.run(runner.handle_resume(first.id, "from_checkpoint"))
    # 2 度目の SDK 起動で resume 引数が確定 sdk_session_id になっている
    assert state["opts"]["resume"] == "sdk_session_xyz"


def test_handle_resume_rerun_full_starts_new_session() -> None:
    state = _install_fake_sdk()
    store = InMemorySessionStore()
    runner = ClaudeAgentRunner(store=store)
    first = asyncio.run(runner.run_task(prompt="x"))
    state["opts"] = None
    second = asyncio.run(runner.handle_resume(first.id, "rerun_full"))
    # 新規セッションなので resume=None
    assert state["opts"]["resume"] is None
    assert second.id != first.id


# ---------------------------------------------------------------------------
# AC-5 — SummaryHook API 存在検証
# ---------------------------------------------------------------------------


def test_summary_hook_persist_api_exists() -> None:
    """AC-5: SummaryHook.persist が thread_id + summary dict を受け取る。"""
    hook = NoopSummaryHook()
    asyncio.run(hook.persist(thread_id=1, summary={"section1": "..."}))
    # NoopSummaryHook は何もせず None を返す
    base = SummaryHook()
    with pytest.raises(NotImplementedError):
        asyncio.run(base.persist(thread_id=1, summary={}))


def test_session_store_abstract_raises_not_implemented() -> None:
    base = SessionStore()
    with pytest.raises(NotImplementedError):
        asyncio.run(base.create_session(SessionRecord()))
    with pytest.raises(NotImplementedError):
        asyncio.run(base.append_log(1, "x"))


def test_noop_cost_hook_returns_none() -> None:
    h = NoopCostHook()
    out = asyncio.run(h.record(CostRecord(session_id=1)))
    assert out is None


# ---------------------------------------------------------------------------
# AC-7 — runner module に LangGraph / LangChain import が一切ない
# ---------------------------------------------------------------------------


def test_runner_module_has_no_langgraph_or_langchain_imports() -> None:
    """AC-7 UNWANTED: ADR-010 で禁止された import が runner ファイルに存在しないこと.

    lint-mock.sh --no-langgraph と等価の検証を pytest 側でも担保。
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    runner_path = repo_root / "backend" / "integrations" / "claude_agent_runner.py"
    text = runner_path.read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("from langgraph"), f"line {line_no}: {line}"
        assert not stripped.startswith("import langgraph"), f"line {line_no}: {line}"
        assert not stripped.startswith("from langchain"), f"line {line_no}: {line}"
        assert not stripped.startswith("import langchain"), f"line {line_no}: {line}"


def test_runner_module_carries_no_langgraph_sentinel_comment() -> None:
    """ADR-010 の意図を文書化する sentinel コメント (# NO_LANGGRAPH_IN_RUNNER)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    runner_path = repo_root / "backend" / "integrations" / "claude_agent_runner.py"
    assert "NO_LANGGRAPH_IN_RUNNER" in runner_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# DB-backed store classes — import + SQL shape smoke (実 DB 接続不要)
# ---------------------------------------------------------------------------


def test_db_store_classes_are_importable_and_subclass_abstracts() -> None:
    """DbSessionStore / DbCostHook / DbSummaryHook が抽象を継承しているか."""
    from integrations.claude_agent_runner import (
        DbCostHook,
        DbSessionStore,
        DbSummaryHook,
    )
    assert issubclass(DbSessionStore, SessionStore)
    assert issubclass(DbCostHook, CostHook)
    assert issubclass(DbSummaryHook, SummaryHook)


def test_db_session_store_uses_correct_tables_in_sql() -> None:
    """DB 永続化 SQL が migration の 5 テーブルを参照していること."""
    runner_path = Path(__file__).resolve().parent.parent / "integrations" / "claude_agent_runner.py"
    text = runner_path.read_text(encoding="utf-8")
    assert "INSERT INTO sessions" in text
    assert "INSERT INTO session_logs" in text
    assert "INSERT INTO cost_logs" in text
    assert "chat_messages" in text and "compressed_summary" in text
    # CHECK 制約と一致する 5 status 値が SQL 内で使われる前提の status 列更新
    assert "UPDATE sessions" in text
    # AC-4: cache_read/write_tokens 列が cost_logs INSERT に含まれる
    assert "cache_read_tokens" in text
    assert "cache_write_tokens" in text
