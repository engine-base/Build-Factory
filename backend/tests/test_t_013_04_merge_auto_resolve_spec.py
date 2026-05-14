"""T-013-04 (Phase 1): merge conflict detection + human escalation — 1:1 spec test.

Spot-check で発覚した spec drift (strategy 名が意味を持たない偽装) を Option B で
是正した後の 1:1 spec test. Phase 1 は detect + escalate の 2 段のみ.
Phase 1.5 (T-013-04b) の strategy 試行 / resolved status は本 PR scope 外.

AC マッピング (Phase 1 honest version):
  AC-1 UBIQUITOUS    : 4 public symbols (detect_and_escalate / AutoResolveError /
                        DEFAULT_TIMEOUT_SEC / PHASE) + T-M29-03 REUSE 無改変 +
                        2 段 flow + force-push 文字列なし + Phase 識別子明示.
  AC-2 EVENT-DRIVEN  : dict 返却 / 必須 keys / AutoResolveError raise /
                        per-call timeout ≤ 2 秒.
  AC-3 STATE-DRIVEN  : no shell=True / no os.system / no langgraph / langchain /
                        litellm / no mutating git / no REPO_ROOT redefinition /
                        no direct subprocess.
  AC-4 UNWANTED      : invalid input rejection (empty / non-str / shell metachar
                        / over-length / git error / fatal) / no secret / no fs /
                        no DB mutation.
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


def _source_code_only() -> str:
    """Source with docstrings + comments stripped (forbidden-string checks)."""
    raw = MODULE_PATH.read_text(encoding="utf-8")
    no_docstrings = re.sub(r'"""[\s\S]*?"""', "", raw)
    lines = []
    for line in no_docstrings.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — module + 4 public symbols + T-M29-03 REUSE + 2-phase
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_file_exists():
    assert MODULE_PATH.exists(), f"missing module: {MODULE_PATH}"


@pytest.mark.parametrize("sym", [
    "AutoResolveError",
    "detect_and_escalate",
    "DEFAULT_TIMEOUT_SEC",
    "PHASE",
])
def test_ac1_public_symbols_exposed(sym):
    assert hasattr(mar, sym), f"missing public symbol: {sym}"


def test_ac1_public_symbols_kinds():
    assert isinstance(mar.AutoResolveError, type)
    assert issubclass(mar.AutoResolveError, Exception)
    assert inspect.iscoroutinefunction(mar.detect_and_escalate)
    assert isinstance(mar.DEFAULT_TIMEOUT_SEC, int)
    assert mar.DEFAULT_TIMEOUT_SEC <= 2
    assert mar.PHASE == "1"


def test_ac1_t_m29_03_module_intact():
    """REUSE invariant — T-M29-03 sequential_merge.py の 5 public symbols が残る."""
    for sym in (
        "MergeConflictError",
        "SequentialMergeError",
        "detect_conflict_dry_run",
        "plan_sequential_merge",
        "MAX_CELLS_PER_PLAN",
    ):
        assert hasattr(sm, sym), f"T-M29-03 invariant broken: missing {sym}"


def test_ac1_t_m29_03_file_not_modified_in_this_pr():
    src = T_M29_03_PATH.read_text(encoding="utf-8")
    assert "async def detect_conflict_dry_run(" in src
    assert "async def plan_sequential_merge(" in src
    assert "MAX_CELLS_PER_PLAN = 64" in src


def test_ac1_two_phase_flow_present():
    """Phase 1: status ∈ {no_conflict, escalate} のみ."""
    src = _source_code_only()
    for status in ("no_conflict", "escalate"):
        assert f'"{status}"' in src, f"missing status literal {status!r}"
    # Phase 1 では "resolved" は実装されない (Phase 1.5 へ deferral)
    assert '"resolved"' not in src, (
        "Phase 1 must NOT emit 'resolved' status — that requires Phase 1.5 "
        "strategy implementation. Spot-check で発覚した spec drift を防止."
    )


def test_ac1_phase_identifier_explicit():
    """Phase 識別子が response にもコード定数にも明示されている."""
    src = _source_code_only()
    assert "PHASE" in src
    assert '"phase": PHASE' in src or '"phase":PHASE' in src


def test_ac1_no_force_push_in_module():
    """F-013 policy red-line: force_push 自動停止."""
    src = _source_code_only().lower()
    forbidden = ["git push", "--force", "subprocess.run(", "os.system", "shell=true"]
    for s in forbidden:
        assert s not in src, f"forbidden substring (code) found: {s!r}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — structured dict + required keys + 2s timeout
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
def patch_detect_with_conflict(monkeypatch):
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


REQUIRED_KEYS = ("status", "phase", "base", "target", "conflicts", "next_step")


def test_ac2_returns_structured_dict(patch_detect_no_conflict):
    out = asyncio.run(mar.detect_and_escalate("main", "feature-x"))
    assert isinstance(out, dict)


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_ac2_required_keys_no_conflict(key, patch_detect_no_conflict):
    out = asyncio.run(mar.detect_and_escalate("main", "feature-x"))
    assert key in out


@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_ac2_required_keys_escalate(key, patch_detect_with_conflict):
    out = asyncio.run(mar.detect_and_escalate("main", "feature-x"))
    assert key in out


def test_ac2_no_conflict_status_shape(patch_detect_no_conflict):
    out = asyncio.run(mar.detect_and_escalate("main", "feature-x"))
    assert out["status"] == "no_conflict"
    assert out["phase"] == "1"
    assert out["conflicts"] == []
    assert out["next_step"] == "none"


def test_ac2_escalate_status_shape(patch_detect_with_conflict):
    out = asyncio.run(mar.detect_and_escalate("main", "feature-x"))
    assert out["status"] == "escalate"
    assert out["phase"] == "1"
    assert len(out["conflicts"]) >= 1
    assert out["next_step"] == "human_review"


def test_ac2_invalid_input_raises_auto_resolve_error():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate("", "feature-x"))


def test_ac2_per_call_timeout_bound():
    assert mar.DEFAULT_TIMEOUT_SEC <= 2


def test_ac2_phase_1_does_not_return_resolved_status(patch_detect_with_conflict):
    """Phase 1 は conflict があれば必ず escalate. "resolved" は Phase 1.5 まで返らない."""
    out = asyncio.run(mar.detect_and_escalate("main", "feature-x"))
    assert out["status"] != "resolved", (
        "Phase 1 must NOT return 'resolved' — that's Phase 1.5 (T-013-04b) territory"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — no shell / no forbidden AI stack / no mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_shell_true_no_os_system():
    src = _source_code_only()
    assert "shell=True" not in src
    assert "os.system" not in src


def test_ac3_no_forbidden_ai_stack_import():
    src = _source_code_only()
    forbidden = (
        "import langgraph", "from langgraph",
        "import langchain", "from langchain",
        "import litellm", "from litellm",
    )
    for f in forbidden:
        assert f not in src, f"forbidden AI-stack import: {f}"


def test_ac3_no_mutating_git_subcommands():
    """Module は read-only dry-run の薄いラッパー."""
    src = _source_code_only()
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
    src = _source_code_only()
    assert "REPO_ROOT =" not in src
    assert "REPO_ROOT:" not in src


def test_ac3_no_direct_subprocess_call():
    src = _source_code_only()
    assert "create_subprocess_exec" not in src
    assert "create_subprocess_shell" not in src
    assert "subprocess.Popen" not in src


def test_ac3_delegates_to_sequential_merge_only():
    src = _source_code_only()
    assert "from services.swarm.sequential_merge import" in src
    assert "detect_conflict_dry_run" in src


def test_ac3_no_db_write_path():
    src = _source_code_only().lower()
    for sql in ("insert into", "update ", "delete from", "truncate"):
        assert sql not in src, f"DB mutation SQL fragment present: {sql!r}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input rejection + no mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_base_branch_rejected():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate("", "feature-x"))


def test_ac4_empty_target_branch_rejected():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate("main", ""))


@pytest.mark.parametrize("bad", [None, 0, 3.14, [], {}, b"main"])
def test_ac4_non_string_base_rejected(bad):
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate(bad, "feature-x"))  # type: ignore[arg-type]


@pytest.mark.parametrize("metachar", [
    "main; rm -rf /", "main|cat", "main`whoami`", "main$(id)",
    "main\nfoo", "main\\bar",
])
def test_ac4_shell_metachars_rejected(metachar):
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate(metachar, "feature-x"))


def test_ac4_overlength_branch_rejected():
    too_long = "a" * 300
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate(too_long, "feature-x"))


def test_ac4_no_hardcoded_secret():
    src = _source_code_only()
    forbidden = [
        re.compile(r"sk-ant-[A-Za-z0-9]"),
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
        re.compile(r"eyJhbGciOiJIUzI1NiIs"),
    ]
    for pat in forbidden:
        assert not pat.search(src), f"hardcoded secret matching: {pat.pattern}"


def test_ac4_no_filesystem_write_outside_tmp():
    src = _source_code_only()
    forbidden = ("open(", ".write(", ".write_text(", "Path(", "shutil.")
    for f in forbidden:
        assert f not in src, f"filesystem write API present: {f}"


def test_ac4_propagates_helper_validation_error():
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate("main", "x;bad"))


def test_ac4_propagates_helper_git_error(monkeypatch):
    async def fake_raises(base, target, *, timeout_sec=2):
        raise sm.MergeConflictError("unknown ref")
    monkeypatch.setattr(mar, "detect_conflict_dry_run", fake_raises)
    with pytest.raises(mar.AutoResolveError):
        asyncio.run(mar.detect_and_escalate("main", "feature-x"))


# ══════════════════════════════════════════════════════════════════════
# Sanity + spec-drift防止 guard
# ══════════════════════════════════════════════════════════════════════


def test_module_importable_from_services_namespace():
    import services.merge_auto_resolve as m  # noqa: F401
    assert m is mar


def test_drift_guard_phase_1_5_api_not_yet_exposed():
    """Phase 1.5 で導入予定の API が誤って Phase 1 に出ていないか守る."""
    # try_auto_resolve / strategies / resolved 系は Phase 1.5 (T-013-04b) territory.
    # Phase 1 PR では絶対に exposed されてはならない (spot-check で発覚した偽装の再発防止).
    assert not hasattr(mar, "try_auto_resolve"), (
        "try_auto_resolve is Phase 1.5 (T-013-04b) — must not be in Phase 1"
    )
    assert not hasattr(mar, "STRATEGIES"), (
        "STRATEGIES is Phase 1.5 (T-013-04b) — must not be in Phase 1"
    )
    # Source code level: no resolved emission path.
    src = _source_code_only()
    assert '"resolved"' not in src
    assert "'resolved'" not in src
