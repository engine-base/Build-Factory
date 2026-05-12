"""T-S0-08: claude-agent-sdk runner 基盤 — 7 AC 機械 invariant 検証.

PR #40 (T-S0-08 初版) で production 実装 + 23 件 behavior test が既に存在する.
本 module は **spec rigor** layer として、 7 AC が production code の
symbol / signature / constant / 不変条件と 1:1 整合していることを機械検証する.

既存 test_claude_agent_runner.py は behavior (run_task が回るか) を、
本 test は spec contract (公開 API + ADR-010 / migration 整合 / 4-choice
resume 不変) を担当する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : claude_agent_runner.py が claude_agent_sdk import +
                       SessionRecord / CostRecord / AuditEvent /
                       SessionStore (+ Db/InMemory) / CostHook (+ Db/Noop) /
                       SummaryHook (+ Db/Noop) / AuditHook (+ Db/Noop) /
                       VALID_RESUME_CHOICES を公開.
  AC-2 UBIQUITOUS    : ClaudeAgentRunner.run_task が sdk_session_id 引数受領 /
                       SDK の auto-compaction を再実装しない.
  AC-3 EVENT-DRIVEN  : run_task → SessionRecord(status='running') 作成 +
                       session_logs ストリーム + status enum 5 値 (migration
                       CHECK 一致).
  AC-4 STATE-DRIVEN  : cache_ttl_seconds default = 300 (5min) /
                       CostHook.record + DbCostHook が cache_read_tokens に
                       INSERT.
  AC-5 STATE-DRIVEN  : SummaryHook.persist + chat_messages.compressed_summary
                       JSONB persist / runner 側で summary 生成しない.
  AC-6 EVENT-DRIVEN  : crash で status='crashed' / VALID_RESUME_CHOICES =
                       ('from_checkpoint','rerun_full','manual_fix','cancel') /
                       handle_resume invalid input で ValueError / migration の
                       resume_choice CHECK 一致.
  AC-7 UNWANTED      : claude_agent_runner.py に langgraph/langchain import なし
                       + scripts/lint-mock.sh --no-langgraph PASS.
"""
from __future__ import annotations

import inspect
import json
import re
import subprocess
from pathlib import Path

import pytest

from integrations import claude_agent_runner as car


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "backend" / "integrations" / "claude_agent_runner.py"
MIGRATION_PATH = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260510000003_runner_session_tables.sql"
)
LINT_MOCK = REPO_ROOT / "scripts" / "lint-mock.sh"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public symbols / SDK import
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_imports_claude_agent_sdk():
    src = RUNNER_PATH.read_text(encoding="utf-8")
    assert "claude_agent_sdk" in src, (
        "runner must import claude_agent_sdk (ADR-010 Layer 3)"
    )


@pytest.mark.parametrize("sym", [
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
])
def test_ac1_public_symbol_exists(sym):
    assert hasattr(car, sym), f"missing public symbol: {sym}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 UBIQUITOUS — sdk_session_id parameter / SDK auto-compaction
# ══════════════════════════════════════════════════════════════════════


def test_ac2_run_task_accepts_sdk_session_id():
    sig = inspect.signature(car.ClaudeAgentRunner.run_task)
    assert "sdk_session_id" in sig.parameters, (
        "run_task() must accept sdk_session_id for SDK resume (AC-2)"
    )
    p = sig.parameters["sdk_session_id"]
    # Default = None (resume optional)
    assert p.default is None, "sdk_session_id default must be None"


def test_ac2_runner_does_not_reimplement_3_tier_compaction():
    """ADR-010 §自前実装禁止. SDK が auto-compaction を行うので、 runner で
    section_keys を再定義したり 9-section summary を組み立てたりしない."""
    src = _strip_strings_and_comments(RUNNER_PATH.read_text(encoding="utf-8"))
    # SDK が summary を生成し、 runner は persist するだけ.
    assert "SECTION_KEYS" not in src, (
        "runner re-implements SECTION_KEYS — ADR-010 violation"
    )
    # 9-section summary 自前生成パターン: dict comp on fixed keys.
    assert "def build_summary" not in src
    assert "def compress_context" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 EVENT-DRIVEN — SessionRecord status / session_logs / migration CHECK
# ══════════════════════════════════════════════════════════════════════


def test_ac3_session_record_status_default_running():
    rec = car.SessionRecord(workspace_id=1, bf_task_id=1)
    assert rec.status == "running"


def test_ac3_session_store_create_and_append_log_methods():
    """SessionStore abstract に create_session / append_log が定義されている."""
    for name in ("create_session", "append_log",
                 "update_sdk_session_id", "finalize_session", "get_session"):
        assert hasattr(car.SessionStore, name), (
            f"SessionStore missing method: {name}"
        )


def test_ac3_migration_status_check_5_values():
    """migration の CHECK 制約が 5 値 (running/done/crashed/cancelled/paused)."""
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    # Look for the status CHECK
    m = re.search(
        r"status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'running'\s*\n?\s*CHECK\s*"
        r"\(\s*status\s+IN\s*\(([^)]+)\)\s*\)",
        sql,
    )
    assert m, "migration must declare status CHECK constraint"
    values = re.findall(r"'([^']+)'", m.group(1))
    assert set(values) == {
        "running", "done", "crashed", "cancelled", "paused",
    }, f"unexpected status enum: {values}"


def test_ac3_session_logs_table_exists():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+session_logs",
        sql,
    ), "session_logs table missing from migration"


# ══════════════════════════════════════════════════════════════════════
# AC-4 STATE-DRIVEN — cache_ttl_seconds default 300 / cost_logs columns
# ══════════════════════════════════════════════════════════════════════


def test_ac4_cache_ttl_default_is_300_seconds():
    sig = inspect.signature(car.ClaudeAgentRunner.__init__)
    p = sig.parameters.get("cache_ttl_seconds")
    assert p is not None, "ClaudeAgentRunner must have cache_ttl_seconds param"
    assert p.default == 300, (
        f"cache_ttl_seconds default must be 300 (5min ephemeral), got {p.default}"
    )


def test_ac4_cost_hook_has_record_method():
    assert hasattr(car.CostHook, "record")
    assert hasattr(car.DbCostHook, "record")
    assert hasattr(car.NoopCostHook, "record")


def test_ac4_cost_record_has_cache_token_fields():
    """CostRecord が cache_read_tokens / cache_write_tokens を持つ."""
    fields = {f for f in dir(car.CostRecord) if not f.startswith("_")}
    # dataclass attrs are class-level. inspect via signature
    sig = inspect.signature(car.CostRecord)
    params = set(sig.parameters.keys())
    assert "cache_read_tokens" in params or "cache_read_tokens" in fields, (
        f"CostRecord must have cache_read_tokens, got: {params}"
    )
    assert "cache_write_tokens" in params or "cache_write_tokens" in fields, (
        f"CostRecord must have cache_write_tokens, got: {params}"
    )


def test_ac4_migration_cost_logs_has_cache_columns():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "cache_read_tokens" in sql
    assert "cache_write_tokens" in sql


# ══════════════════════════════════════════════════════════════════════
# AC-5 STATE-DRIVEN — SummaryHook + chat_messages.compressed_summary
# ══════════════════════════════════════════════════════════════════════


def test_ac5_summary_hook_has_persist_method():
    assert hasattr(car.SummaryHook, "persist")
    assert hasattr(car.DbSummaryHook, "persist")
    assert hasattr(car.NoopSummaryHook, "persist")


def test_ac5_migration_chat_messages_compressed_summary_is_jsonb():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    # compressed_summary JSONB column on chat_messages
    assert re.search(
        r"compressed_summary\s+JSONB",
        sql,
    ), "chat_messages.compressed_summary must be JSONB"


def test_ac5_db_summary_hook_inserts_into_chat_messages():
    """DbSummaryHook.persist が chat_messages テーブルへの INSERT を含む."""
    src = inspect.getsource(car.DbSummaryHook)
    assert "chat_messages" in src
    assert "compressed_summary" in src


# ══════════════════════════════════════════════════════════════════════
# AC-6 EVENT-DRIVEN — crash / VALID_RESUME_CHOICES / handle_resume / migration
# ══════════════════════════════════════════════════════════════════════


def test_ac6_valid_resume_choices_exact_4():
    assert car.VALID_RESUME_CHOICES == (
        "from_checkpoint", "rerun_full", "manual_fix", "cancel",
    ), f"VALID_RESUME_CHOICES drift: {car.VALID_RESUME_CHOICES}"


def test_ac6_handle_resume_exists_and_is_async():
    assert hasattr(car.ClaudeAgentRunner, "handle_resume")
    assert inspect.iscoroutinefunction(car.ClaudeAgentRunner.handle_resume)


def test_ac6_handle_resume_rejects_invalid_choice_at_source():
    """ソースコード上で handle_resume が VALID_RESUME_CHOICES 検証 +
    ValueError raise を実装していることを確認 (async test runner 非依存)."""
    src = inspect.getsource(car.ClaudeAgentRunner.handle_resume)
    assert "VALID_RESUME_CHOICES" in src
    assert "raise ValueError" in src


def test_ac6_handle_resume_signature():
    """handle_resume(self, session_id: int, choice: str) -> SessionRecord."""
    sig = inspect.signature(car.ClaudeAgentRunner.handle_resume)
    params = list(sig.parameters.keys())
    assert "session_id" in params
    assert "choice" in params


def test_ac6_migration_resume_choice_check_matches_4():
    """migration の resume_choice CHECK が 4 値 (from_checkpoint / rerun_full /
    manual_fix / cancel) と一致."""
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    # CHECK 制約の中身を抽出 (multiline 対応)
    m = re.search(
        r"CHECK\s*\(\s*resume_choice\s+IN\s*\(([^)]+)\)",
        sql,
        re.DOTALL,
    )
    assert m, "resume_choice CHECK constraint missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {
        "from_checkpoint", "rerun_full", "manual_fix", "cancel",
    }, f"resume_choice enum drift: {values}"


def test_ac6_crashed_status_path_present():
    """run_task の例外パスで status='crashed' / crash_reason が設定される."""
    src = inspect.getsource(car.ClaudeAgentRunner.run_task)
    assert 'status = "crashed"' in src or "status='crashed'" in src
    assert "crash_reason" in src


# ══════════════════════════════════════════════════════════════════════
# AC-7 UNWANTED — no langgraph / no langchain
# ══════════════════════════════════════════════════════════════════════


def test_ac7_no_langgraph_import_in_runner():
    src = RUNNER_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    # importable lines only
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "langgraph" not in stripped, (
                f"forbidden langgraph import: {stripped}"
            )
            assert "langchain" not in stripped, (
                f"forbidden langchain import: {stripped}"
            )


def test_ac7_lint_mock_no_langgraph_flag_passes():
    result = subprocess.run(
        ["bash", str(LINT_MOCK), "--no-langgraph"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"lint --no-langgraph failed:\n{result.stdout}\n{result.stderr}"
    )


def test_ac7_no_hardcoded_anthropic_secret_in_runner():
    src = RUNNER_PATH.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_08_ac_normalized_to_canonical_ears():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-08"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    # legacy "EVENT" / "STATE" は廃止. canonical form のみ使う.
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-S0-08 still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "UBIQUITOUS" in types
    assert "UNWANTED" in types


def test_tickets_t_s0_08_has_adr_link_and_7_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-08"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert len(files) >= 7, f"expected >= 7 existing_files, got {len(files)}"
    assert "backend/integrations/claude_agent_runner.py" in files
    assert any("20260510000003_runner_session_tables.sql" in f for f in files)


def test_tickets_t_s0_08_ac_mentions_method_names():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-08"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    # Concretized AC should reference actual method names
    assert "run_task" in full
    assert "create_session" in full
    assert "append_log" in full
    assert "VALID_RESUME_CHOICES" in full
    assert "compressed_summary" in full
    assert "cache_ttl_seconds" in full


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_strings_and_comments(src: str) -> str:
    """簡易的に triple-quoted docstring + # comment を除外."""
    out: list[str] = []
    in_triple = False
    triple_char = None
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
