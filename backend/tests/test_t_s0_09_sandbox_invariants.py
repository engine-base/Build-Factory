"""T-S0-09: OS-level sandbox 基盤 — 5 AC 機械 invariant 検証.

PR #12 / #41 (T-S0-09 初版) で production 実装 + 22 件 behavior test
(test_sandbox.py) が存在する. 本 module は **spec contract layer** として
5 AC が production code の symbol / argv 構築 / runner 統合と 1:1 整合
していることを機械検証する.

既存 test_sandbox.py は behavior (subprocess actually denied) を、
本 test は spec contract (公開 API + argv invariant + runner 統合 +
zero-trust default + violation → audit) を担当する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : SandboxConfig + SandboxResult + SandboxError +
                       SandboxUnavailable + SandboxViolation + run_sandboxed +
                       _build_bwrap_argv + _build_sandbox_exec_argv 公開 /
                       runner が subprocess.Popen / subprocess.run を直接
                       呼ばない (sandbox bypass 禁止).
  AC-2 EVENT-DRIVEN  : bwrap argv が --ro-bind / --bind / --unshare-pid /
                       --unshare-ipc / --unshare-uts / sandbox-exec が
                       (version 1) (deny default) (allow process-fork) 始まり.
  AC-3 STATE-DRIVEN  : allow_hosts 空で --unshare-net (Linux) +
                       (deny network*) (macOS) / network_enabled() = False.
  AC-4 OPTIONAL      : allow_hosts 空 default で --unshare-net 含まれる /
                       allow_hosts 非空でのみ network namespace 保持.
  AC-5 UNWANTED      : _detect_violation が rc=159 (SIGSYS) / 137 (SIGKILL) /
                       "permission denied in bwrap" を検出 + SandboxViolation
                       raise / runner で crash_reason='sandbox_violation' +
                       action='sandbox.violation' audit emit.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from sandbox import (
    SandboxConfig,
    SandboxError,
    SandboxResult,
    SandboxUnavailable,
    SandboxViolation,
    run_sandboxed,
)
from sandbox import exec as sandbox_exec


REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_DIR = REPO_ROOT / "backend" / "sandbox"
CONFIG_PATH = SANDBOX_DIR / "config.py"
EXEC_PATH = SANDBOX_DIR / "exec.py"
RUNNER_PATH = REPO_ROOT / "backend" / "integrations" / "claude_agent_runner.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public API + runner integration (no bypass)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sym", [
    "SandboxConfig",
    "SandboxResult",
    "SandboxError",
    "SandboxUnavailable",
    "SandboxViolation",
    "run_sandboxed",
])
def test_ac1_public_symbols_exported(sym):
    import sandbox
    assert hasattr(sandbox, sym), f"sandbox package missing public symbol: {sym}"


def test_ac1_internal_argv_builders_exist():
    assert hasattr(sandbox_exec, "_build_bwrap_argv")
    assert hasattr(sandbox_exec, "_build_sandbox_exec_argv")
    assert hasattr(sandbox_exec, "_detect_violation")


def test_ac1_sandbox_config_is_frozen_dataclass():
    """SandboxConfig は immutable (frozen) であること."""
    cfg = SandboxConfig()
    with pytest.raises(Exception):
        cfg.timeout_sec = 999  # type: ignore[misc]


@pytest.mark.parametrize("field_name", [
    "allow_paths",
    "read_only_paths",
    "allow_hosts",
    "timeout_sec",
    "cwd",
    "extra_env",
])
def test_ac1_sandbox_config_fields(field_name):
    cfg = SandboxConfig()
    assert hasattr(cfg, field_name)


def test_ac1_sandbox_violation_is_sandbox_error():
    assert issubclass(SandboxViolation, SandboxError)
    assert issubclass(SandboxUnavailable, SandboxError)


def test_ac1_runner_does_not_call_subprocess_directly_on_user_cmd():
    """claude_agent_runner.py がユーザ供給 cmd に対して subprocess.Popen /
    subprocess.run を直接呼ばない. sandbox 経由必須 (bypass 禁止)."""
    src = _strip_strings_and_comments(RUNNER_PATH.read_text(encoding="utf-8"))
    # subprocess module を import すること自体は OK だが、直接 cmd を渡して
    # Popen / run することは禁止 (run_sandboxed 経由のみ).
    for line in src.splitlines():
        stripped = line.strip()
        # subprocess.Popen( / subprocess.run( のような直接呼びがないこと
        assert not re.search(r"subprocess\.Popen\s*\(", stripped), (
            f"forbidden direct subprocess.Popen: {stripped}"
        )
        assert not re.search(r"subprocess\.run\s*\(", stripped), (
            f"forbidden direct subprocess.run: {stripped}"
        )


def test_ac1_run_sandboxed_signature():
    sig = inspect.signature(run_sandboxed)
    params = list(sig.parameters.keys())
    assert "cmd" in params
    assert "cfg" in params


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — argv builder invariants (bwrap + sandbox-exec)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_bwrap_argv_starts_with_bwrap():
    argv = sandbox_exec._build_bwrap_argv(
        ["echo", "hi"], SandboxConfig(),
    )
    assert argv[0] == "bwrap"


def test_ac2_bwrap_argv_contains_namespace_isolation():
    argv = sandbox_exec._build_bwrap_argv(
        ["echo", "hi"], SandboxConfig(),
    )
    joined = " ".join(argv)
    assert "--unshare-pid" in joined
    assert "--unshare-ipc" in joined
    assert "--unshare-uts" in joined


def test_ac2_bwrap_argv_ro_bind_for_read_only_paths():
    cfg = SandboxConfig(
        read_only_paths=(Path("/usr"),),
        allow_paths=(),
    )
    argv = sandbox_exec._build_bwrap_argv(["echo", "hi"], cfg)
    # /usr は存在する read-only root だから --ro-bind が出る
    assert "--ro-bind" in argv


def test_ac2_bwrap_argv_bind_for_allow_paths(tmp_path):
    cfg = SandboxConfig(
        read_only_paths=(),
        allow_paths=(tmp_path,),
    )
    argv = sandbox_exec._build_bwrap_argv(["echo", "hi"], cfg)
    # writable bind 出る
    assert "--bind" in argv
    assert str(tmp_path) in argv


def test_ac2_bwrap_argv_separator_before_cmd():
    """`--` separator が cmd の前にあること (bwrap 標準)."""
    argv = sandbox_exec._build_bwrap_argv(["echo", "hi"], SandboxConfig())
    assert "--" in argv
    sep_idx = argv.index("--")
    assert argv[sep_idx + 1:] == ["echo", "hi"]


def test_ac2_sandbox_exec_argv_starts_with_deny_default():
    """macOS sandbox-exec profile は (version 1) (deny default) で始まる."""
    cfg = SandboxConfig(allow_paths=(Path("/tmp/ws"),))
    argv = sandbox_exec._build_sandbox_exec_argv(["echo", "hi"], cfg)
    # argv の中に profile inline 文字列が含まれる
    profile = " ".join(arg for arg in argv if "version" in arg or "deny" in arg or "allow" in arg)
    assert "(version 1)" in profile
    assert "(deny default)" in profile
    assert "(allow process-fork)" in profile


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — zero-trust network: --unshare-net / (deny network*)
# ══════════════════════════════════════════════════════════════════════


def test_ac3_network_enabled_is_false_when_allow_hosts_empty():
    cfg = SandboxConfig(allow_hosts=())
    assert cfg.network_enabled() is False


def test_ac3_network_enabled_is_true_when_allow_hosts_non_empty():
    cfg = SandboxConfig(allow_hosts=("example.com",))
    assert cfg.network_enabled() is True


def test_ac3_bwrap_argv_unshare_net_when_allow_hosts_empty():
    cfg = SandboxConfig(allow_hosts=())
    argv = sandbox_exec._build_bwrap_argv(["echo", "hi"], cfg)
    assert "--unshare-net" in argv


def test_ac3_bwrap_argv_omits_unshare_net_when_allow_hosts_set():
    cfg = SandboxConfig(allow_hosts=("example.com",))
    argv = sandbox_exec._build_bwrap_argv(["echo", "hi"], cfg)
    # network 残す → --unshare-net 入れない
    assert "--unshare-net" not in argv


def test_ac3_sandbox_exec_denies_network_when_allow_hosts_empty():
    cfg = SandboxConfig(allow_hosts=())
    argv = sandbox_exec._build_sandbox_exec_argv(["echo", "hi"], cfg)
    profile = " ".join(argv)
    assert "(deny network*)" in profile


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — zero-trust default
# ══════════════════════════════════════════════════════════════════════


def test_ac4_default_config_has_empty_allow_hosts():
    """デフォルトの SandboxConfig() は zero-trust (allow_hosts 空)."""
    cfg = SandboxConfig()
    assert cfg.allow_hosts == ()


def test_ac4_default_config_disables_network():
    cfg = SandboxConfig()
    assert cfg.network_enabled() is False


def test_ac4_default_argv_includes_unshare_net():
    """default SandboxConfig() を渡すと bwrap argv に --unshare-net が入る."""
    argv = sandbox_exec._build_bwrap_argv(["true"], SandboxConfig())
    assert "--unshare-net" in argv


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — violation detection + runner integration
# ══════════════════════════════════════════════════════════════════════


def test_ac5_detect_violation_recognizes_sigsys_rc_159():
    """128 + SIGSYS (31) = 159: seccomp による violation 検出."""
    assert sandbox_exec._detect_violation(159, "") is not None


def test_ac5_detect_violation_recognizes_sigkill_rc_137():
    """128 + SIGKILL (9) = 137: namespace escape detected."""
    assert sandbox_exec._detect_violation(137, "") is not None


def test_ac5_detect_violation_recognizes_bwrap_permission_denied():
    reason = sandbox_exec._detect_violation(
        1, "bwrap: Operation not permitted",
    )
    assert reason is not None


def test_ac5_detect_violation_returns_none_for_normal_exit():
    """rc=0 / 通常エラーで violation 検出されない."""
    assert sandbox_exec._detect_violation(0, "") is None
    assert sandbox_exec._detect_violation(1, "syntax error") is None


def test_ac5_sandbox_violation_carries_reason():
    """SandboxViolation は reason を保持する."""
    result = SandboxResult(
        returncode=159,
        stdout="",
        stderr="seccomp",
        duration_sec=0.0,
        backend="bwrap",
    )
    err = SandboxViolation(result, reason="sigsys")
    assert err.reason == "sigsys"
    assert err.result is result


def test_ac5_runner_handles_sandbox_violation():
    """claude_agent_runner.run_task の except 節に SandboxViolation 専用処理
    (crash_reason='sandbox_violation' + action='sandbox.violation') がある."""
    src = RUNNER_PATH.read_text(encoding="utf-8")
    assert "SandboxViolation" in src
    assert "sandbox_violation" in src
    assert "sandbox.violation" in src


# ══════════════════════════════════════════════════════════════════════
# ADR-010 / security hygiene
# ══════════════════════════════════════════════════════════════════════


def test_adr_010_no_langgraph_in_sandbox():
    for path in (CONFIG_PATH, EXEC_PATH):
        src = path.read_text(encoding="utf-8")
        code = _strip_strings_and_comments(src)
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "langgraph" not in stripped, (
                    f"forbidden langgraph in {path.name}: {stripped}"
                )
                assert "langchain" not in stripped


def test_security_no_hardcoded_anthropic_key():
    for path in (CONFIG_PATH, EXEC_PATH):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


def test_security_clearenv_in_bwrap():
    """bwrap argv に --clearenv が含まれる (host env 漏洩防止)."""
    argv = sandbox_exec._build_bwrap_argv(["true"], SandboxConfig())
    assert "--clearenv" in argv


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_09_ac_normalized_to_canonical_ears():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-09"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-S0-09 still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "OPTIONAL" in types
    assert "UNWANTED" in types


def test_tickets_t_s0_09_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-09"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert len(files) >= 5, f"expected >= 5 existing_files, got {len(files)}"
    assert "backend/sandbox/exec.py" in files
    assert "backend/sandbox/config.py" in files
    assert "backend/integrations/claude_agent_runner.py" in files


def test_tickets_t_s0_09_ac_mentions_concrete_symbols():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-09"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "SandboxConfig", "SandboxViolation", "run_sandboxed",
        "_build_bwrap_argv", "_build_sandbox_exec_argv",
        "--unshare-net", "sandbox.violation", "sandbox_violation",
        "network_enabled",
    ):
        assert sym in full, f"T-S0-09 AC missing concrete symbol: {sym}"


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_strings_and_comments(src: str) -> str:
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
