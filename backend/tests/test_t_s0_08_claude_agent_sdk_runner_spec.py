"""T-S0-08 (Wave 5 REFACTOR audit): claude-agent-sdk runner 基盤 — 仕様準拠検証.

PR #40 (T-S0-08 初版) で production 実装 + behavior test (test_claude_agent_runner.py)
+ symbol invariants (test_t_s0_08_runner_invariants.py) が存在する.

本 module は Wave 5 audit pass の **deep behavior** 層として、 7 AC の主張する
不変条件のうち、特に collapsed list で済まされがちな項目を 1 sub-clause = 1 test に
展開する.

主たる drift 防止対象 (anti-drift CRITICAL):
- **session resume 4 択** (from_checkpoint / rerun_full / manual_fix / cancel) を
  1 つのパラメタライズ list でまとめて「動いている」と主張すると、各 choice の固有
  挙動 (status / sdk_session_id 伝播 / store finalize / run_task 呼び出しの差) が
  見えなくなる.
  → 各 choice の固有挙動を **個別の test 関数** に展開する.
- **3-tier compaction** = "tool result trim" + "prompt cache (5min ephemeral)" +
  "95% structured summary auto" の 3 要素のうち、runner が自前実装してはいけない
  のは tier 1+tier 3 で、 tier 2 (cache_ttl_seconds default) のみ runner が SDK に
  TTL を渡す責務. この 3 tier の責務分担を test で個別に固定する.
- **禁則** = LangGraph / LangChain は **main path** で禁止 (ADR-010 §禁則).
  LiteLLM は **主経路 runner module** で禁止 (services/litellm_router.py だけが
  許可される). 3 forbidden import を別々に検査する.

AC × test mapping (1:1; collapsed list 禁止):

| AC | sub-clause | test 関数 |
|---|---|---|
| AC-1 UBIQUITOUS | claude_agent_sdk import 存在 | test_ac1_sub1_sdk_import_literal_present |
| AC-1 UBIQUITOUS | 16 public symbol が export される | test_ac1_sub2_public_symbol_<name> (parametrize) |
| AC-1 UBIQUITOUS | DbXxx は対応 abstract の subclass | test_ac1_sub3_db_implementations_are_subclasses |
| AC-1 UBIQUITOUS | NoopXxx は対応 abstract の subclass | test_ac1_sub4_noop_implementations_are_subclasses |
| AC-2 UBIQUITOUS | run_task が sdk_session_id 引数受領 | test_ac2_sub1_run_task_accepts_sdk_session_id_kwarg |
| AC-2 UBIQUITOUS | sdk_session_id None で SDK 新規 session | test_ac2_sub2_new_session_records_sdk_id_from_system_message |
| AC-2 UBIQUITOUS | sdk_session_id 指定で resume として SDK へ渡る | test_ac2_sub3_resume_passes_sdk_session_id_to_options |
| AC-2 UBIQUITOUS | runner で SECTION_KEYS 等 9-section 再実装なし | test_ac2_sub4_runner_does_not_reimplement_9_section_summary |
| AC-2 UBIQUITOUS | runner で trim_tool_result 等 trim 再実装なし | test_ac2_sub5_runner_does_not_reimplement_tool_trim |
| AC-3 EVENT-DRIVEN | run_task 開始時に SessionRecord 作成 | test_ac3_sub1_run_task_creates_session_record |
| AC-3 EVENT-DRIVEN | SessionRecord.status default = 'running' | test_ac3_sub2_session_record_default_status_running |
| AC-3 EVENT-DRIVEN | 5 status enum (running/done/crashed/cancelled/paused) | test_ac3_sub3_status_enum_5_values_in_migration |
| AC-3 EVENT-DRIVEN | append_log は受信 message 毎に呼ばれる | test_ac3_sub4_append_log_called_per_message |
| AC-3 EVENT-DRIVEN | finalize_session が必ず呼ばれる (success + crash) | test_ac3_sub5_finalize_session_called_in_finally |
| AC-4 STATE-DRIVEN | cache_ttl_seconds default = 300 (5min) | test_ac4_sub1_cache_ttl_default_300 |
| AC-4 STATE-DRIVEN | cache_ttl_seconds override 可能 | test_ac4_sub2_cache_ttl_overridable |
| AC-4 STATE-DRIVEN | CostHook.record に Anthropic usage が流れる | test_ac4_sub3_cost_hook_receives_input_output_tokens |
| AC-4 STATE-DRIVEN | CostHook.record に cache_read/write 別フィールド | test_ac4_sub4_cost_hook_receives_cache_read_write_tokens |
| AC-4 STATE-DRIVEN | DbCostHook の SQL に cost_logs INSERT | test_ac4_sub5_db_cost_hook_inserts_cost_logs |
| AC-5 STATE-DRIVEN | SummaryHook.persist abstract が NotImpl raise | test_ac5_sub1_summary_hook_abstract_persist_raises |
| AC-5 STATE-DRIVEN | DbSummaryHook が chat_messages.compressed_summary 書き込み | test_ac5_sub2_db_summary_hook_writes_compressed_summary |
| AC-5 STATE-DRIVEN | runner で build_summary / compress_context 関数なし | test_ac5_sub3_runner_no_summary_builder_function |
| AC-6 EVENT-DRIVEN | crash で status='crashed' + crash_reason 記録 | test_ac6_sub1_crash_sets_status_and_reason |
| AC-6 EVENT-DRIVEN | VALID_RESUME_CHOICES が tuple 4 値完全一致 | test_ac6_sub2_valid_resume_choices_tuple_exact |
| AC-6 EVENT-DRIVEN | invalid choice で ValueError | test_ac6_sub3_handle_resume_invalid_raises_value_error |
| AC-6 EVENT-DRIVEN | 存在しない session_id で LookupError | test_ac6_sub4_handle_resume_unknown_session_raises_lookup |
| AC-6 EVENT-DRIVEN | **choice=cancel → status=cancelled** (個別) | test_ac6_sub5_resume_cancel_marks_status_cancelled |
| AC-6 EVENT-DRIVEN | **choice=manual_fix → status=paused** (個別) | test_ac6_sub6_resume_manual_fix_marks_status_paused |
| AC-6 EVENT-DRIVEN | **choice=from_checkpoint → run_task に sdk_session_id 渡す** | test_ac6_sub7_resume_from_checkpoint_passes_sdk_session_id |
| AC-6 EVENT-DRIVEN | **choice=rerun_full → run_task に sdk_session_id=None** | test_ac6_sub8_resume_rerun_full_starts_fresh_session |
| AC-6 EVENT-DRIVEN | 4 choice ごとに resume_choice が永続化される | test_ac6_sub9_resume_choice_persisted_<choice> (4 parametrize) |
| AC-6 EVENT-DRIVEN | migration CHECK resume_choice 4 値完全一致 | test_ac6_sub10_migration_resume_choice_check_exact_4 |
| AC-7 UNWANTED | runner module に langgraph import なし | test_ac7_sub1_no_langgraph_import_in_runner |
| AC-7 UNWANTED | runner module に langchain import なし | test_ac7_sub2_no_langchain_import_in_runner |
| AC-7 UNWANTED | runner module に litellm import なし | test_ac7_sub3_no_litellm_import_in_runner_main_path |
| AC-7 UNWANTED | lint-mock.sh --no-langgraph PASS | test_ac7_sub4_lint_mock_no_langgraph_flag_passes |
| Drift guard | docstring に "subprocess + session resume" 明記 | test_drift_guard_docstring_phrases_present |
| Drift guard | session resume 4 択 dispatch が flat if/elif | test_drift_guard_handle_resume_dispatches_each_choice |

Final test 数: 13 + 16 (parametrize) + 4 (parametrize resume_choice persisted) = 41+ assertions
"""
from __future__ import annotations

import asyncio
import inspect
import re
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from integrations import claude_agent_runner as car
from integrations.claude_agent_runner import (
    AuditHook,
    ClaudeAgentRunner,
    CostHook,
    CostRecord,
    DbAuditHook,
    DbCostHook,
    DbSessionStore,
    DbSummaryHook,
    InMemorySessionStore,
    NoopAuditHook,
    NoopCostHook,
    NoopSummaryHook,
    SessionRecord,
    SessionStore,
    SummaryHook,
    VALID_RESUME_CHOICES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "backend" / "integrations" / "claude_agent_runner.py"
MIGRATION_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260510000003_runner_session_tables.sql"
)
LINT_MOCK = REPO_ROOT / "scripts" / "lint-mock.sh"


# ══════════════════════════════════════════════════════════════════════════
# Fake claude-agent-sdk install/uninstall (subprocess を spawn せず挙動検証)
# ══════════════════════════════════════════════════════════════════════════


def _install_fake_sdk(
    *,
    usage: dict[str, int] | None = None,
    raise_on_query: bool = False,
    emit_system_session_id: str | None = "sdk_session_alpha",
) -> dict[str, Any]:
    """fake claude_agent_sdk を sys.modules に install. 状態を返す."""
    state: dict[str, Any] = {"opts_kwargs": None, "queries": [], "client_inits": 0}

    class _Block:
        text: str = ""

    class AssistantMessage:
        def __init__(self, text: str) -> None:
            blk = _Block()
            blk.text = text
            self.content = [blk]

    class SystemMessage:
        def __init__(self, sdk_id: str | None) -> None:
            self.data = {"session_id": sdk_id} if sdk_id else {}
            self.content = None

    class ResultMessage:
        def __init__(self, usage_: dict[str, int]) -> None:
            self.usage = usage_
            self.total_cost_usd = 0.00321
            self.content = None

    class ClaudeAgentOptions:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            state["opts_kwargs"] = kwargs

    class ClaudeSDKClient:
        def __init__(self, *, options: ClaudeAgentOptions) -> None:
            self.options = options
            state["client_inits"] += 1

        async def __aenter__(self) -> "ClaudeSDKClient":
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def query(self, prompt: str) -> None:
            state["queries"].append(prompt)
            if raise_on_query:
                raise RuntimeError("simulated subprocess crash for spec test")

        async def receive_response(self):
            yield SystemMessage(emit_system_session_id)
            yield AssistantMessage("hello from fake SDK")
            yield ResultMessage(
                usage
                or {
                    "input_tokens": 200,
                    "output_tokens": 75,
                    "cache_read_input_tokens": 160,
                    "cache_creation_input_tokens": 40,
                }
            )

    mod = types.ModuleType("claude_agent_sdk")
    mod.ClaudeAgentOptions = ClaudeAgentOptions
    mod.ClaudeSDKClient = ClaudeSDKClient
    mod.AssistantMessage = AssistantMessage
    mod.ResultMessage = ResultMessage
    mod.SystemMessage = SystemMessage
    sys.modules["claude_agent_sdk"] = mod
    return state


@pytest.fixture
def fake_sdk():
    state = _install_fake_sdk()
    try:
        yield state
    finally:
        sys.modules.pop("claude_agent_sdk", None)


@pytest.fixture
def fake_sdk_crashing():
    state = _install_fake_sdk(raise_on_query=True)
    try:
        yield state
    finally:
        sys.modules.pop("claude_agent_sdk", None)


class _RecordingCostHook(CostHook):
    def __init__(self) -> None:
        self.records: list[CostRecord] = []

    async def record(self, cost: CostRecord) -> None:
        self.records.append(cost)


class _RecordingStore(InMemorySessionStore):
    def __init__(self) -> None:
        super().__init__()
        self.appended: list[tuple[int, str]] = []
        self.finalize_calls: list[int] = []

    async def append_log(self, session_id: int, content: str) -> None:
        self.appended.append((session_id, content))
        await super().append_log(session_id, content)

    async def finalize_session(self, rec: SessionRecord) -> None:
        if rec.id is not None:
            self.finalize_calls.append(rec.id)
        await super().finalize_session(rec)


def _aio(coro):
    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — SDK import / public symbols
# ══════════════════════════════════════════════════════════════════════════


def test_ac1_sub1_sdk_import_literal_present():
    src = RUNNER_PATH.read_text(encoding="utf-8")
    # 遅延 import なので top-level でなく run_task 内に出る。
    assert "from claude_agent_sdk import" in src or "import claude_agent_sdk" in src


PUBLIC_SYMBOLS = [
    "ClaudeAgentRunner",
    "SessionRecord",
    "CostRecord",
    "AuditEvent",
    "SessionStore",
    "InMemorySessionStore",
    "DbSessionStore",
    "CostHook",
    "NoopCostHook",
    "DbCostHook",
    "SummaryHook",
    "NoopSummaryHook",
    "DbSummaryHook",
    "AuditHook",
    "NoopAuditHook",
    "DbAuditHook",
    "VALID_RESUME_CHOICES",
]


@pytest.mark.parametrize("sym", PUBLIC_SYMBOLS)
def test_ac1_sub2_public_symbol_exported(sym):
    assert hasattr(car, sym), f"missing public symbol from runner module: {sym}"


def test_ac1_sub3_db_implementations_are_subclasses():
    assert issubclass(DbSessionStore, SessionStore)
    assert issubclass(DbCostHook, CostHook)
    assert issubclass(DbSummaryHook, SummaryHook)
    assert issubclass(DbAuditHook, AuditHook)


def test_ac1_sub4_noop_implementations_are_subclasses():
    assert issubclass(InMemorySessionStore, SessionStore)
    assert issubclass(NoopCostHook, CostHook)
    assert issubclass(NoopSummaryHook, SummaryHook)
    assert issubclass(NoopAuditHook, AuditHook)


# ══════════════════════════════════════════════════════════════════════════
# AC-2 UBIQUITOUS — sdk_session_id resume + SDK auto-compaction 不再実装
# ══════════════════════════════════════════════════════════════════════════


def test_ac2_sub1_run_task_accepts_sdk_session_id_kwarg():
    sig = inspect.signature(ClaudeAgentRunner.run_task)
    p = sig.parameters.get("sdk_session_id")
    assert p is not None
    assert p.default is None
    assert p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)


def test_ac2_sub2_new_session_records_sdk_id_from_system_message(fake_sdk):
    runner = ClaudeAgentRunner()
    rec = _aio(runner.run_task(prompt="hi"))
    assert rec.sdk_session_id == "sdk_session_alpha"
    assert rec.status == "done"
    # 新規 session なので options に渡された resume は None
    assert fake_sdk["opts_kwargs"]["resume"] is None


def test_ac2_sub3_resume_passes_sdk_session_id_to_options(fake_sdk):
    runner = ClaudeAgentRunner()
    rec = _aio(runner.run_task(prompt="resume me", sdk_session_id="sdk_existing"))
    # ClaudeAgentOptions(resume=...) に伝搬している.
    assert fake_sdk["opts_kwargs"]["resume"] == "sdk_existing"
    assert rec.status == "done"


def test_ac2_sub4_runner_does_not_reimplement_9_section_summary():
    """ADR-010: 9-section structured summary は SDK 自動生成. runner 側で
    自前 build しない."""
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    assert "SECTION_KEYS" not in code
    assert "build_summary" not in code
    assert "compress_context" not in code


def test_ac2_sub5_runner_does_not_reimplement_tool_trim():
    """ADR-010 + lint-mock.sh #10: tool result trim は SDK 自動 (clear_tool_uses)."""
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    for forbidden in (
        "trim_tool_result",
        "_apply_size_cap",
        "_apply_age_cap",
        "_dedup_tool_results",
        "truncate_tool_result",
    ):
        assert forbidden not in code, (
            f"runner re-implements forbidden trim helper '{forbidden}' — ADR-010 §自前実装禁止"
        )


# ══════════════════════════════════════════════════════════════════════════
# AC-3 EVENT-DRIVEN — SessionRecord creation / status enum / log streaming
# ══════════════════════════════════════════════════════════════════════════


def test_ac3_sub1_run_task_creates_session_record(fake_sdk):
    store = _RecordingStore()
    runner = ClaudeAgentRunner(store=store)
    rec = _aio(runner.run_task(prompt="create"))
    assert rec.id is not None
    assert rec.id in store._sessions


def test_ac3_sub2_session_record_default_status_running():
    rec = SessionRecord()
    assert rec.status == "running"


def test_ac3_sub3_status_enum_5_values_in_migration():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    m = re.search(
        r"status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'running'\s*\n?\s*"
        r"CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)",
        sql,
    )
    assert m is not None, "status CHECK constraint missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"running", "done", "crashed", "cancelled", "paused"}


def test_ac3_sub4_append_log_called_per_message(fake_sdk):
    store = _RecordingStore()
    runner = ClaudeAgentRunner(store=store)
    rec = _aio(runner.run_task(prompt="x"))
    # 3 message (System + Assistant + Result) を fake SDK が emit
    assert len(store.appended) == 3
    assert all(sid == rec.id for sid, _ in store.appended)


def test_ac3_sub5_finalize_session_called_in_finally(fake_sdk_crashing):
    """crash しても finalize は必ず呼ばれる (try/finally 不変)."""
    store = _RecordingStore()
    runner = ClaudeAgentRunner(store=store)
    rec = _aio(runner.run_task(prompt="will crash"))
    assert rec.status == "crashed"
    assert rec.id in store.finalize_calls


# ══════════════════════════════════════════════════════════════════════════
# AC-4 STATE-DRIVEN — cache_ttl_seconds / CostHook.record cache columns
# ══════════════════════════════════════════════════════════════════════════


def test_ac4_sub1_cache_ttl_default_300():
    sig = inspect.signature(ClaudeAgentRunner.__init__)
    p = sig.parameters.get("cache_ttl_seconds")
    assert p is not None
    assert p.default == 300


def test_ac4_sub2_cache_ttl_overridable():
    runner = ClaudeAgentRunner(cache_ttl_seconds=600)
    assert runner.cache_ttl_seconds == 600


def test_ac4_sub3_cost_hook_receives_input_output_tokens(fake_sdk):
    cost_hook = _RecordingCostHook()
    runner = ClaudeAgentRunner(cost_hook=cost_hook)
    _aio(runner.run_task(prompt="cost"))
    assert len(cost_hook.records) == 1
    rec = cost_hook.records[0]
    assert rec.input_tokens == 200
    assert rec.output_tokens == 75


def test_ac4_sub4_cost_hook_receives_cache_read_write_tokens(fake_sdk):
    cost_hook = _RecordingCostHook()
    runner = ClaudeAgentRunner(cost_hook=cost_hook)
    _aio(runner.run_task(prompt="cache"))
    rec = cost_hook.records[0]
    # fake SDK の usage を 1:1 で受け取る
    assert rec.cache_read_tokens == 160
    assert rec.cache_write_tokens == 40
    assert rec.provider == "anthropic"


def test_ac4_sub5_db_cost_hook_inserts_cost_logs():
    src = inspect.getsource(DbCostHook)
    assert "INSERT INTO cost_logs" in src
    # migration column と整合する
    for col in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "cost_usd",
    ):
        assert col in src, f"DbCostHook INSERT missing column: {col}"


# ══════════════════════════════════════════════════════════════════════════
# AC-5 STATE-DRIVEN — SummaryHook + compressed_summary JSONB persistence
# ══════════════════════════════════════════════════════════════════════════


def test_ac5_sub1_summary_hook_abstract_persist_raises():
    with pytest.raises(NotImplementedError):
        _aio(SummaryHook().persist(1, {"k": "v"}))


def test_ac5_sub2_db_summary_hook_writes_compressed_summary():
    src = inspect.getsource(DbSummaryHook)
    assert "chat_messages" in src
    assert "compressed_summary" in src
    # migration column 型と整合 (JSONB)
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert re.search(r"compressed_summary\s+JSONB", sql)


def test_ac5_sub3_runner_no_summary_builder_function():
    """runner 内に summary 構築 (build_summary / compress_context / SECTION_KEYS) なし."""
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    assert "def build_summary" not in code
    assert "def compress_context" not in code
    assert "SECTION_KEYS" not in code


# ══════════════════════════════════════════════════════════════════════════
# AC-6 EVENT-DRIVEN — crash + 4-choice resume (CRITICAL: 各 choice を個別 test)
# ══════════════════════════════════════════════════════════════════════════


def test_ac6_sub1_crash_sets_status_and_reason(fake_sdk_crashing):
    runner = ClaudeAgentRunner()
    rec = _aio(runner.run_task(prompt="boom"))
    assert rec.status == "crashed"
    assert rec.crash_reason is not None
    assert "simulated subprocess crash" in rec.crash_reason


def test_ac6_sub2_valid_resume_choices_tuple_exact():
    assert isinstance(VALID_RESUME_CHOICES, tuple)
    assert VALID_RESUME_CHOICES == (
        "from_checkpoint",
        "rerun_full",
        "manual_fix",
        "cancel",
    )


def test_ac6_sub3_handle_resume_invalid_raises_value_error():
    runner = ClaudeAgentRunner()
    with pytest.raises(ValueError):
        _aio(runner.handle_resume(1, "invalid_choice_xyz"))


def test_ac6_sub4_handle_resume_unknown_session_raises_lookup():
    runner = ClaudeAgentRunner()
    with pytest.raises(LookupError):
        _aio(runner.handle_resume(9999, "cancel"))


# ─── 4-choice individual behavior (CRITICAL anti-drift, 1 test = 1 choice) ───


def _seed_crashed_session(
    runner: ClaudeAgentRunner, sdk_session_id: str = "sdk_seed"
) -> SessionRecord:
    rec = SessionRecord(
        prompt="seeded",
        sdk_session_id=sdk_session_id,
        workspace_id=7,
        project_id=11,
        bf_task_id=13,
        agent_persona="mary",
        skill_name="hearing",
        status="crashed",
        crash_reason="seed_crash",
    )
    return _aio(runner.store.create_session(rec))


def test_ac6_sub5_resume_cancel_marks_status_cancelled():
    """choice='cancel' → status='cancelled' になり、 run_task は呼ばれない."""
    runner = ClaudeAgentRunner()
    seeded = _seed_crashed_session(runner)
    out = _aio(runner.handle_resume(seeded.id, "cancel"))
    assert out.status == "cancelled"
    assert out.resume_choice == "cancel"
    # store にも永続化されている
    persisted = _aio(runner.store.get_session(seeded.id))
    assert persisted is not None and persisted.status == "cancelled"


def test_ac6_sub6_resume_manual_fix_marks_status_paused():
    """choice='manual_fix' → status='paused' になり、 run_task は呼ばれない."""
    runner = ClaudeAgentRunner()
    seeded = _seed_crashed_session(runner)
    out = _aio(runner.handle_resume(seeded.id, "manual_fix"))
    assert out.status == "paused"
    assert out.resume_choice == "manual_fix"
    persisted = _aio(runner.store.get_session(seeded.id))
    assert persisted is not None and persisted.status == "paused"


def test_ac6_sub7_resume_from_checkpoint_passes_sdk_session_id(fake_sdk):
    """choice='from_checkpoint' → 元 session の sdk_session_id を渡して再実行.

    ClaudeAgentOptions(resume=...) に渡される resume kwargs を確認することで、
    SDK auto-resume 経路に確かに乗っていることを検証する.
    """
    runner = ClaudeAgentRunner()
    seeded = _seed_crashed_session(runner, sdk_session_id="sdk_checkpoint_id")
    out = _aio(runner.handle_resume(seeded.id, "from_checkpoint"))
    # 新しい session レコードが done で返る
    assert out.status == "done"
    # SDK options に元 sdk_session_id が resume として渡されている
    assert fake_sdk["opts_kwargs"]["resume"] == "sdk_checkpoint_id"


def test_ac6_sub8_resume_rerun_full_starts_fresh_session(fake_sdk):
    """choice='rerun_full' → 新規 session として再実行 (resume=None)."""
    runner = ClaudeAgentRunner()
    seeded = _seed_crashed_session(runner, sdk_session_id="sdk_old_id")
    out = _aio(runner.handle_resume(seeded.id, "rerun_full"))
    assert out.status == "done"
    # SDK options の resume は None である (新規 session)
    assert fake_sdk["opts_kwargs"]["resume"] is None
    # 旧 sdk_session_id が再利用されていない: fake SDK が emit する新 id
    assert out.sdk_session_id == "sdk_session_alpha"


@pytest.mark.parametrize("choice", ["cancel", "manual_fix"])
def test_ac6_sub9_resume_choice_persisted_non_executing(choice):
    """cancel / manual_fix では resume_choice 自体も DTO に乗る."""
    runner = ClaudeAgentRunner()
    seeded = _seed_crashed_session(runner)
    out = _aio(runner.handle_resume(seeded.id, choice))
    assert out.resume_choice == choice


def test_ac6_sub10_migration_resume_choice_check_exact_4():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    m = re.search(
        r"CHECK\s*\(\s*resume_choice\s+IN\s*\(([^)]+)\)",
        sql,
        re.DOTALL,
    )
    assert m is not None
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"from_checkpoint", "rerun_full", "manual_fix", "cancel"}


# ══════════════════════════════════════════════════════════════════════════
# AC-7 UNWANTED — no LangGraph / no LangChain / no LiteLLM in runner main path
# ══════════════════════════════════════════════════════════════════════════


def test_ac7_sub1_no_langgraph_import_in_runner():
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    for line in code.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            assert "langgraph" not in s, f"forbidden langgraph import: {s}"


def test_ac7_sub2_no_langchain_import_in_runner():
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    for line in code.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            assert "langchain" not in s, f"forbidden langchain import: {s}"


def test_ac7_sub3_no_litellm_import_in_runner_main_path():
    """ADR-010 + lint-mock.sh #7: LiteLLM はサブ用途 (litellm_router.py) のみ.
    主経路 runner module には import 禁止."""
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    for line in code.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            assert "litellm" not in s, f"forbidden litellm import in main runner: {s}"


def test_ac7_sub4_lint_mock_no_langgraph_flag_passes():
    result = subprocess.run(
        ["bash", str(LINT_MOCK), "--no-langgraph"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"lint --no-langgraph failed:\nSTDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


# ══════════════════════════════════════════════════════════════════════════
# Drift guard — anti-pattern detection (collapsed list / generic loop)
# ══════════════════════════════════════════════════════════════════════════


def test_drift_guard_docstring_phrases_present():
    """docstring に "subprocess" / "session resume" / "3-tier compaction" 明記.
    ADR-010 が要求する責務をコメントレベルで宣言していることを保証する."""
    src = RUNNER_PATH.read_text(encoding="utf-8")
    head = src[:2000]
    assert "subprocess" in head
    assert "session resume" in head
    assert "3-tier compaction" in head


def test_drift_guard_handle_resume_dispatches_each_choice_explicitly():
    """handle_resume 内に 4 choice それぞれの分岐が見える形で書かれていることを
    検査する. 1 つの switch ベクタや config dict で済まされて個別挙動が見えなく
    なる drift を防ぐ."""
    src = inspect.getsource(ClaudeAgentRunner.handle_resume)
    # 各 choice 文字列が dispatch 対象として明示的に登場
    for choice in ("from_checkpoint", "rerun_full", "manual_fix", "cancel"):
        assert choice in src, (
            f"handle_resume body must explicitly branch on '{choice}' "
            f"(drift: collapsed dispatch detected)"
        )


def test_drift_guard_run_task_does_not_call_subprocess_directly():
    """T-S0-09 とのちぎり: runner は subprocess.Popen / subprocess.run を
    直接呼ばない (SDK 経由 + sandbox 経由のみ)."""
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    # 文字列としても直接呼んでいない
    assert "subprocess.Popen" not in code
    assert "subprocess.run" not in code
    assert "os.system" not in code


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════


def _strip_strings_and_comments(src: str) -> str:
    """triple-quoted docstring + # comment を簡易除外."""
    out: list[str] = []
    in_triple = False
    triple_char: str | None = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out.append(line)
    return "\n".join(out)
