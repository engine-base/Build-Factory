"""T-S0-09: OS-level sandbox pytest (5 AC 全網羅).

実 bwrap / sandbox-exec を呼ばずに subprocess.run を mock することで
プラットフォーム非依存の検証を行う。 argv 組み立てロジックを確認するための
内部 _build_bwrap_argv / _build_sandbox_exec_argv も間接検証する。

AC マッピング:
  AC-1 UBIQUITOUS: bwrap (Linux) / sandbox-exec (macOS) で実行 + SandboxConfig
  AC-2 EVENT:      write outside allow_paths を block (引数組み立てで検証)
  AC-3 STATE:      outbound network deny by default (--unshare-net)
  AC-4 OPTIONAL:   allow_hosts 空 → network 完全無効 (zero-trust)
  AC-5 UNWANTED:   sandbox 違反検知 → SandboxViolation raise + reason 識別
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxViolation,
    SandboxUnavailable,
    run_sandboxed,
)
from sandbox.exec import (
    _build_bwrap_argv,
    _build_sandbox_exec_argv,
    _detect_violation,
)


# ---------------------------------------------------------------------------
# AC-1 / AC-3 / AC-4: SandboxConfig + bwrap argv
# ---------------------------------------------------------------------------


def test_sandbox_config_default_network_disabled() -> None:
    """AC-4: allow_hosts 未指定 → network_enabled() == False (zero-trust)."""
    cfg = SandboxConfig()
    assert cfg.network_enabled() is False
    assert cfg.allow_hosts == ()


def test_sandbox_config_with_allow_hosts_enables_network() -> None:
    """AC-3 inverse: allow_hosts が指定されると network_enabled() == True."""
    cfg = SandboxConfig(allow_hosts=("api.anthropic.com",))
    assert cfg.network_enabled() is True


def test_bwrap_argv_includes_unshare_net_when_no_hosts() -> None:
    """AC-3 STATE: allow_hosts 空 → bwrap argv に --unshare-net が含まれる."""
    cfg = SandboxConfig(allow_paths=(Path("/tmp/ws"),))
    argv = _build_bwrap_argv(["echo", "hi"], cfg)
    assert "--unshare-net" in argv


def test_bwrap_argv_omits_unshare_net_when_hosts_allowed() -> None:
    """allow_hosts が空でなければ --unshare-net しない (relay 経由を想定)."""
    cfg = SandboxConfig(
        allow_paths=(Path("/tmp/ws"),),
        allow_hosts=("api.anthropic.com",),
    )
    argv = _build_bwrap_argv(["echo", "hi"], cfg)
    assert "--unshare-net" not in argv


def test_bwrap_argv_binds_allow_paths_writable_and_read_only_paths_ro() -> None:
    """AC-1 / AC-2: --bind allow_paths (書込可) / --ro-bind read_only_paths (読込のみ)."""
    cfg = SandboxConfig(
        allow_paths=(Path("/tmp/ws"),),
        read_only_paths=(Path("/usr"),),
    )
    argv = _build_bwrap_argv(["echo"], cfg)
    assert "--bind" in argv and "/tmp/ws" in argv
    # /usr が存在する環境前提 (CI Linux で ok)
    if Path("/usr").exists():
        # --ro-bind のすぐ後に /usr が来る
        idx = argv.index("--ro-bind")
        assert argv[idx + 1] == "/usr"


def test_bwrap_argv_isolates_pid_ipc_uts_namespaces() -> None:
    """AC-1: PID/IPC/UTS 名前空間を切り離す."""
    cfg = SandboxConfig()
    argv = _build_bwrap_argv(["true"], cfg)
    for flag in ("--unshare-pid", "--unshare-ipc", "--unshare-uts"):
        assert flag in argv


def test_bwrap_argv_clearenv_and_sets_path() -> None:
    """env clearing + PATH のみ通す (情報漏洩防止)."""
    cfg = SandboxConfig(extra_env={"FOO": "bar"})
    argv = _build_bwrap_argv(["true"], cfg)
    assert "--clearenv" in argv
    # --setenv FOO bar が含まれる
    assert "FOO" in argv and "bar" in argv


def test_bwrap_argv_chdir_when_cwd_set() -> None:
    """cwd 指定時は --chdir で sandbox 内 cwd を切替."""
    cfg = SandboxConfig(cwd=Path("/tmp/ws"))
    argv = _build_bwrap_argv(["pwd"], cfg)
    idx = argv.index("--chdir")
    assert argv[idx + 1] == "/tmp/ws"


# ---------------------------------------------------------------------------
# AC-1 (macOS): sandbox-exec profile 構築
# ---------------------------------------------------------------------------


def test_sandbox_exec_argv_denies_default_and_network_when_no_hosts() -> None:
    """AC-1 (macOS) + AC-4: deny default + deny network*."""
    cfg = SandboxConfig(allow_paths=(Path("/tmp/ws"),))
    argv = _build_sandbox_exec_argv(["echo", "hi"], cfg)
    assert argv[0] == "sandbox-exec"
    assert "-p" in argv
    profile = argv[argv.index("-p") + 1]
    assert "(deny default)" in profile
    assert "(deny network*)" in profile


def test_sandbox_exec_argv_allows_writes_only_under_allow_paths() -> None:
    """AC-2: file-write* は allow_paths regex 配下のみ許可."""
    cfg = SandboxConfig(allow_paths=(Path("/tmp/ws"),))
    argv = _build_sandbox_exec_argv(["touch", "/tmp/ws/x"], cfg)
    profile = argv[argv.index("-p") + 1]
    assert "(allow file-write*" in profile
    assert "/tmp\\/ws" in profile


# ---------------------------------------------------------------------------
# AC-5: 違反検知
# ---------------------------------------------------------------------------


def test_detect_violation_sigsys_rc_159() -> None:
    """seccomp が syscall を block して SIGSYS で kill → rc 159."""
    assert _detect_violation(159, "") == "sigsys"


def test_detect_violation_sigkill_rc_137() -> None:
    """namespace escape を kernel が SIGKILL → rc 137."""
    assert _detect_violation(137, "") == "sigkill_during_sandbox"


def test_detect_violation_sandbox_exec_violation_in_stderr() -> None:
    assert _detect_violation(1, "Sandbox violation: open(/etc/passwd)") == "sandbox_exec_violation"


def test_detect_violation_bwrap_permission_denied() -> None:
    assert (
        _detect_violation(1, "bwrap: Operation not permitted")
        == "permission_denied_in_bwrap"
    )


def test_detect_violation_returns_none_for_normal_failure() -> None:
    """rc != sandbox 系 + stderr に sandbox 痕跡なし → None (普通の失敗)."""
    assert _detect_violation(1, "ImportError: no module") is None
    assert _detect_violation(0, "") is None


# ---------------------------------------------------------------------------
# AC-1: run_sandboxed の dispatch (subprocess を mock)
# ---------------------------------------------------------------------------


def test_run_sandboxed_unsupported_platform_raises() -> None:
    with patch("sandbox.exec.platform.system", return_value="Windows"):
        with pytest.raises(SandboxUnavailable, match="unsupported platform"):
            run_sandboxed(["echo"], SandboxConfig())


def test_run_sandboxed_linux_without_bwrap_raises() -> None:
    with patch("sandbox.exec.platform.system", return_value="Linux"), \
         patch("sandbox.exec.shutil.which", return_value=None):
        with pytest.raises(SandboxUnavailable, match="bwrap"):
            run_sandboxed(["echo"], SandboxConfig())


def test_run_sandboxed_macos_without_sandbox_exec_raises() -> None:
    with patch("sandbox.exec.platform.system", return_value="Darwin"), \
         patch("sandbox.exec.shutil.which", return_value=None):
        with pytest.raises(SandboxUnavailable, match="sandbox-exec"):
            run_sandboxed(["echo"], SandboxConfig())


def test_run_sandboxed_linux_happy_path_returns_result() -> None:
    """AC-1 happy path: bwrap が存在 → SandboxResult(backend='bwrap')."""
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "ok"
    completed.stderr = ""
    with patch("sandbox.exec.platform.system", return_value="Linux"), \
         patch("sandbox.exec.shutil.which", return_value="/usr/bin/bwrap"), \
         patch("sandbox.exec.subprocess.run", return_value=completed):
        res = run_sandboxed(["echo", "hi"], SandboxConfig())
    assert res.returncode == 0
    assert res.backend == "bwrap"
    assert res.stdout == "ok"


def test_run_sandboxed_violation_raises_sandbox_violation() -> None:
    """AC-5 UNWANTED: rc=159 (sigsys) → SandboxViolation(reason='sigsys')."""
    completed = MagicMock()
    completed.returncode = 159
    completed.stdout = ""
    completed.stderr = ""
    with patch("sandbox.exec.platform.system", return_value="Linux"), \
         patch("sandbox.exec.shutil.which", return_value="/usr/bin/bwrap"), \
         patch("sandbox.exec.subprocess.run", return_value=completed):
        with pytest.raises(SandboxViolation) as ei:
            run_sandboxed(["bad"], SandboxConfig())
    assert ei.value.reason == "sigsys"
    assert ei.value.result.returncode == 159


def test_run_sandboxed_timeout_raises() -> None:
    """timeout_sec 超過 → TimeoutError."""
    import subprocess as _sp
    with patch("sandbox.exec.platform.system", return_value="Linux"), \
         patch("sandbox.exec.shutil.which", return_value="/usr/bin/bwrap"), \
         patch(
             "sandbox.exec.subprocess.run",
             side_effect=_sp.TimeoutExpired(cmd="bwrap", timeout=1),
         ):
        with pytest.raises(TimeoutError, match="timed out"):
            run_sandboxed(["sleep", "10"], SandboxConfig(timeout_sec=1))


def test_run_sandboxed_macos_happy_path_returns_result() -> None:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "mac"
    completed.stderr = ""
    with patch("sandbox.exec.platform.system", return_value="Darwin"), \
         patch("sandbox.exec.shutil.which", return_value="/usr/bin/sandbox-exec"), \
         patch("sandbox.exec.subprocess.run", return_value=completed):
        res = run_sandboxed(["echo"], SandboxConfig(allow_paths=(Path("/tmp/ws"),)))
    assert res.backend == "sandbox-exec"
    assert res.stdout == "mac"
