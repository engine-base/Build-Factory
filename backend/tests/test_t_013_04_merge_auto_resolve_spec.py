"""T-013-04: merge conflict 自動解決試行 — 1:1 spec test (4 AC).

NEW BE task. F-013 error_path "merge conflict → AI 自動解決試行 → 失敗で
人間エスカ" の 3 段を T-M29-03 ``sequential_merge`` REUSE で実装した
``services/merge_auto_resolve.py`` を検査する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 4 public symbols + T-M29-03 REUSE 無改変 + 3 段 flow
                        + force-push 文字列なし.
  AC-2 EVENT-DRIVEN  : dict 返却 / 必須 keys / AutoResolveError raise /
                        per-attempt timeout ≤ 2 秒.
  AC-3 STATE-DRIVEN  : no shell=True / no os.system / no langgraph /
                        langchain / litellm / no mutating git / no
                        REPO_ROOT redefinition.
  AC-4 UNWANTED      : invalid base / shell metachar / over-length /
                        invalid strategy / no secret / no DB mutation /
                        no fs write.
"""
from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path

import pytest

from services import merge_auto_resolve as mar
from services.swarm import sequential_merge as sm


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "backend" / "services" / "merge_auto_resolve.py"
T_M29_03_PATH = REPO_ROOT / "backend" / "services" / "swarm" / "sequential_merge.py"


def _source() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


def _source_code_only() -> str:
    """Source with docstrings + comments stripped (for forbidden-string
    checks that should not collide with AC labels mentioned in docs)."""
    raw = MODULE_PATH.read_text(encoding="utf-8")
    # Strip triple-quoted docstrings (greedy across lines).
    no_docstrings = re.sub(r'"""[\s\S]*?"""', "", raw)
    # Strip line comments.
    lines = []
    for line in no_docstrings.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — module + 4 public symbols + T-M29-03 REUSE + 3-phase
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_file_exists():
    assert MODULE_PATH.exists(), f"missing module: {MODULE_PATH}"


@pytest.mark.parametrize("sym", [
    "AutoResolveError",
    "try_auto_resolve",
    "STRATEGIES",
    "DEFAULT_TIMEOUT_SEC",
])
def test_ac1_public_symbols_exposed(sym):
    assert hasattr(mar, sym), f"missing public symbol: {sym}"


def test_ac1_public_symbols_kinds():
    assert isinstance(mar.AutoResolveError, type)
    assert issubclass(mar.AutoResolveError, Exception)
    assert inspect.iscoroutinefunction(mar.try_auto_resolve)
    assert isinstance(mar.STRATEGIES, tuple)
    assert len(mar.STRATEGIES) >= 3
    assert "default" in mar.STRATEGIES
    assert isinstance(mar.DEFAULT_TIMEOUT_SEC, int)


def test_ac1_t_m29_03_module_intact():
    # T-M29-03 sequential_merge.py is the dep — verify 5 public symbols
    # remain (REUSE invariant; nothing in this PR should mutate it).
    for sym in (
        "MergeConflictError",
        "SequentialMergeError",
        "detect_conflict_dry_run",
        "plan_sequential_merge",
        "MAX_CELLS_PER_PLAN",
    ):
        assert hasattr(sm, sym), f"T-M29-03 invariant broken: missing {sym}"


def test_ac1_t_m29_03_file_not_modified_in_this_pr():
    # No identifier rename / signature change should appear in
    # sequential_merge.py — we only IMPORT from it.
    src = T_M29_03_PATH.read_text(encoding="utf-8")
    # core helper signature
    assert "async def detect_conflict_dry_run(" in src
    assert "async def plan_sequential_merge(" in src
    assert "MAX_CELLS_PER_PLAN = 64" in src


def test_ac1_three_phase_flow_present():
    """detect / try / escalate の 3 段が return path として現れる."""
    src = _source_code_only()
    # 3 status literal strings present in code (not just docs).
    for status in ("no_conflict", "resolved", "escalate"):
        assert f'"{status}"' in src, (
            f"3-phase flow incomplete: missing status literal {status!r}"
        )


def test_ac1_no_force_push_in_module():
    """F-013 policy red-line: force_push 自動停止 — module 実コード行に
    force / push 文字列 (実マージ呼び出し) を持たない.

    AC labels が docstring に書かれる分は許容. 検査対象は code-only.
    """
    src = _source_code_only().lower()
    forbidden_substrings = [
        "git push",
        "--force",
        "subprocess.run(",          # 直接 subprocess (shell 含む可能性)
        "os.system",
        "shell=true",
    ]
    for s in forbidden_substrings:
        assert s not in src, f"forbidden substring (code) found: {s!r}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — structured dict + required keys + 2-sec timeout
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def patch_detect_no_conflict(monkeypatch):
    async def fake(base, target, *, timeout_sec=2):
        return {
            "has_conflict": False,
            "conflicts": [],
            "stdout_sample": "",
            "returncode": 0,
            "base": base,
            "target": target,
        }
    monkeypatch.setattr(mar, "detect_conflict_dry_run", fake)
    return fake


@pytest.fixture
def patch_detect_always_conflict(monkeypatch):
    async def fake(base, target, *, timeout_sec=2):
        return {
            "has_conflict": True,
            "conflicts": ["file_a.py", "file_b.py"],
            "stdout_sample": "",
            "returncode": 1,
            "base": base,
            "target": target,
        }
    monkeypatch.setattr(mar, "detect_conflict_dry_run", fake)
    return fake


def test_ac2_returns_structured_dict(patch_detect_no_conflict):
    out = asyncio.run(mar.try_auto_resolve("main", "feature-x"))
    assert isinstance(out, dict)


REQUIRED_KEYS = ("status", "strategy_used", "base", "target",
                 "conflicts", "attempts")


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_ac2_required_keys_present_no_conflict(key, patch_detect_no_conflict):
    out = asyncio.run(mar.try_auto_resolve("main", "feature-x"))
    assert key in out


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_ac2_required_keys_present_escalate(key, patch_detect_always_conflict):
    out = asyncio.run(mar.try_auto_resolve("main", "feature-x"))
    assert key in out


def test_ac2_no_conflict_status(patch_detect_no_conflict):
    out = asyncio.run(mar.try_auto_resolve("main", "feature-x"))
    assert out["status"] == "no_conflict"
    assert out["conflicts"] == []
    assert out["strategy_used"] is None
    assert len(out["attempts"]) >= 1


def test_ac2_escalate_when_all_strategies_conflict(patch_detect_always_conflict):
    out = asyncio.run(mar.try_auto_resolve("main", "feature-x"))
    assert out["status"] == "escalate"
    assert out["strategy_used"] is None
    assert len(out["conflicts"]) >= 1
    assert len(out["attempts"]) == len(mar.STRATEGIES)


def test_ac2_invalid_input_raises_auto_resolve_error():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve("", "feature-x"))


def test_ac2_per_attempt_timeout_bound():
    """DEFAULT_TIMEOUT_SEC ≤ 2 (AC-2 'within 2 seconds')."""
    assert mar.DEFAULT_TIMEOUT_SEC <= 2


def test_ac2_strategies_parameter_validated():
    # Empty list
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve("main", "x", strategies=[]))
    # Non-list
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve("main", "x", strategies="ours"))  # type: ignore[arg-type]


def test_ac2_attempt_records_strategy_and_has_conflict(patch_detect_always_conflict):
    out = asyncio.run(mar.try_auto_resolve("main", "feature-x"))
    for att in out["attempts"]:
        assert "strategy" in att
        assert "has_conflict" in att
        assert "conflicts" in att
        assert att["strategy"] in mar.STRATEGIES


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — no shell=True / no forbidden AI stack / no mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_shell_true_no_os_system():
    src = _source_code_only()
    assert "shell=True" not in src
    assert "os.system" not in src


def test_ac3_no_forbidden_ai_stack_import():
    src = _source_code_only()
    forbidden = ("import langgraph", "from langgraph",
                 "import langchain", "from langchain",
                 "import litellm", "from litellm")
    for f in forbidden:
        assert f not in src, f"forbidden AI-stack import: {f}"


def test_ac3_no_mutating_git_subcommands():
    """Module はあくまで read-only dry-run の薄いラッパー.
    実 merge / push / commit 系 subcommand を直接 spawn しない."""
    src = _source_code_only()
    # T-M29-03 helper を経由するので merge-tree literal は本 module 内には
    # 出現しない (検出は impl の責務). 直接 spawn する場合に出る git command
    # 名のリストで grep する.
    mutating_cmds = (
        '"merge"', "'merge'",
        '"commit"', "'commit'",
        '"push"', "'push'",
        '"reset"', "'reset'",
        '"checkout"', "'checkout'",
        '"branch"', "'branch'",
    )
    for c in mutating_cmds:
        assert c not in src, f"mutating git command literal present: {c}"


def test_ac3_no_repo_root_redefinition():
    """T-M29-01 REPO_ROOT は T-M29-03 経由でのみ参照. 再定義禁止."""
    src = _source_code_only()
    assert "REPO_ROOT =" not in src
    assert "REPO_ROOT:" not in src


def test_ac3_no_direct_subprocess_call():
    """T-M29-03 helper 経由 (detect_conflict_dry_run) のみで subprocess を
    起動する. 本 module 内では asyncio.create_subprocess_exec を直接
    呼び出さない (delegate purity)."""
    src = _source_code_only()
    assert "create_subprocess_exec" not in src
    assert "create_subprocess_shell" not in src
    assert "subprocess.Popen" not in src


def test_ac3_delegates_to_sequential_merge_only():
    """本 module 唯一の git 経路は ``detect_conflict_dry_run`` import."""
    src = _source_code_only()
    # import line 検証
    assert "from services.swarm.sequential_merge import" in src
    assert "detect_conflict_dry_run" in src


def test_ac3_no_db_write_path():
    """audit_logs / chat_messages / cost_logs / sessions 等への INSERT/UPDATE
    SQL を一切持たない (read-only service)."""
    src = _source_code_only().lower()
    for sql in ("insert into", "update ", "delete from", "truncate"):
        assert sql not in src, f"DB mutation SQL fragment present: {sql!r}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input rejection + no mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_base_branch_rejected():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve("", "feature-x"))


def test_ac4_empty_target_branch_rejected():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve("main", ""))


@pytest.mark.parametrize("bad", [None, 0, 3.14, [], {}, b"main"])
def test_ac4_non_string_base_rejected(bad):
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve(bad, "feature-x"))  # type: ignore[arg-type]


@pytest.mark.parametrize("metachar", [
    "main; rm -rf /",
    "main|cat",
    "main`whoami`",
    "main$(id)",
    "main\nfoo",
    "main\\bar",
])
def test_ac4_shell_metachars_rejected(metachar):
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve(metachar, "feature-x"))


def test_ac4_overlength_branch_rejected():
    too_long = "a" * 300
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve(too_long, "feature-x"))


@pytest.mark.parametrize("bad_strategy", [
    "rebase", "force", "drop_theirs", "", "FORCE", "ours ", " ours",
])
def test_ac4_invalid_strategy_rejected(bad_strategy):
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve(
            "main", "feature-x", strategies=[bad_strategy],
        ))


def test_ac4_non_string_strategy_rejected():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve(
            "main", "feature-x", strategies=[1, 2],  # type: ignore[list-item]
        ))


def test_ac4_no_hardcoded_secret():
    src = _source_code_only()
    # Anthropic / Supabase / OpenAI / GitHub PAT prefix
    forbidden = [
        re.compile(r"sk-ant-[A-Za-z0-9]"),
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
        re.compile(r"eyJhbGciOiJIUzI1NiIs"),  # supabase JWT typical prefix
    ]
    for pat in forbidden:
        assert not pat.search(src), f"hardcoded secret matching: {pat.pattern}"


def test_ac4_no_filesystem_write_outside_tmp():
    src = _source_code_only()
    forbidden = ("open(", ".write(", ".write_text(", "Path(", "shutil.")
    for f in forbidden:
        assert f not in src, f"filesystem write API present: {f}"


def test_ac4_propagates_helper_validation_error():
    """T-M29-03 helper 経由の SequentialMergeError は AutoResolveError として
    surface される (caller が 4xx envelope に統一できる)."""
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve("main", "x;bad"))


def test_ac4_propagates_helper_git_error(monkeypatch):
    """T-M29-03 helper の MergeConflictError (ref-not-found 等) も
    AutoResolveError として surface."""
    async def fake_raises(base, target, *, timeout_sec=2):
        raise sm.MergeConflictError("unknown ref")
    monkeypatch.setattr(mar, "detect_conflict_dry_run", fake_raises)
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.try_auto_resolve("main", "feature-x"))


# ══════════════════════════════════════════════════════════════════════
# Sanity: module is importable from the package path the codebase uses
# ══════════════════════════════════════════════════════════════════════


def test_module_importable_from_services_namespace():
    import services.merge_auto_resolve as m  # noqa: F401
    assert m is mar
