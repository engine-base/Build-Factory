"""T-S0-09: OS-level sandbox 実行レイヤー。

Linux  : bwrap (bubblewrap) で chroot + namespace + 一部 syscall フィルタ。
macOS  : sandbox-exec (Apple Seatbelt) で SBPL profile を適用。
他 OS  : SandboxUnavailable を raise。

実装方針:
- bwrap が存在しない場合は run_sandboxed() が SandboxUnavailable を raise する
  (silently 素の subprocess を呼ばない / AC-1 UBIQUITOUS の "shall" を厳守)。
- 違反検知 (sandbox-violation) は subprocess の終了コード解析で行う:
    bwrap     : 違反で kill された場合 returncode が 159 (128+31=SIGSYS) など。
                bwrap が EACCES を出した場合は stderr 文言で判定。
    sandbox-exec: stderr に "Sandbox violation" / "Operation not permitted"。
- SandboxViolation 例外を呼び出し側 (ClaudeAgentRunner) が catch し、
  session.status='crashed' / crash_reason='sandbox_violation' を設定する
  (AC-5 UNWANTED)。
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import SandboxConfig


@dataclass
class SandboxResult:
    """run_sandboxed() の戻り値。"""

    returncode: int
    stdout: str
    stderr: str
    duration_sec: float
    backend: str  # "bwrap" / "sandbox-exec"


class SandboxError(Exception):
    """sandbox 実行関連の基底例外。"""


class SandboxUnavailable(SandboxError):
    """bwrap / sandbox-exec が PATH に無い環境。"""


class SandboxViolation(SandboxError):
    """sandbox 内 process が許可されていない操作を試みた (AC-5)。

    Attributes:
        result: SandboxResult — exit code / stderr を保持。
        reason: 違反の種類 (例: "write_outside_allow_paths" / "network_disabled" /
                "sigsys" / "unknown")。
    """

    def __init__(self, result: SandboxResult, reason: str) -> None:
        super().__init__(f"sandbox violation ({reason}): rc={result.returncode}")
        self.result = result
        self.reason = reason


def _detect_violation(rc: int, stderr: str) -> Optional[str]:
    """違反パターンを stderr / returncode から抽出。検出できなければ None。"""
    if rc == 159:  # 128 + SIGSYS (seccomp)
        return "sigsys"
    if rc == 137:  # 128 + SIGKILL — namespace escape detected by kernel
        return "sigkill_during_sandbox"
    lower = (stderr or "").lower()
    if "operation not permitted" in lower and "bwrap" in lower:
        return "permission_denied_in_bwrap"
    if "sandbox violation" in lower:
        return "sandbox_exec_violation"
    if "permission denied" in lower and "/bin" in lower:
        return "write_outside_allow_paths"
    return None


def _build_bwrap_argv(cmd: list[str], cfg: SandboxConfig) -> list[str]:
    """bwrap 引数を組み立てる (Linux only)。"""
    argv: list[str] = ["bwrap"]
    # read-only system roots
    for p in cfg.read_only_paths:
        if p.exists():
            argv += ["--ro-bind", str(p), str(p)]
    # writable workspace paths
    for p in cfg.allow_paths:
        argv += ["--bind", str(p), str(p)]
    # tmpfs for /tmp inside sandbox (workspace 外への書き込みを吸収する)
    argv += ["--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev"]
    # network: allow_hosts が空なら network namespace を切る (AC-3 / AC-4)
    if not cfg.network_enabled():
        argv += ["--unshare-net"]
    # PID / IPC / UTS namespace 隔離
    argv += ["--unshare-pid", "--unshare-ipc", "--unshare-uts"]
    # cwd
    if cfg.cwd is not None:
        argv += ["--chdir", str(cfg.cwd)]
    # env clearing → 必要なものだけ通す
    argv += ["--clearenv"]
    for k, v in {"PATH": "/usr/local/bin:/usr/bin:/bin", **cfg.extra_env}.items():
        argv += ["--setenv", k, v]
    argv += ["--"]
    argv += cmd
    return argv


def _build_sandbox_exec_argv(cmd: list[str], cfg: SandboxConfig) -> list[str]:
    """sandbox-exec 引数を組み立てる (macOS only)。

    SBPL (Sandbox Profile Language) を inline で渡す。
    """
    parts: list[str] = ["(version 1)", "(deny default)", "(allow process-fork)"]
    parts.append("(allow process-exec)")
    # read 全許可 + 書き込みは allow_paths 配下のみ
    parts.append("(allow file-read*)")
    if cfg.allow_paths:
        regex_writes = "|".join(str(p).replace("/", "\\/") for p in cfg.allow_paths)
        parts.append(f'(allow file-write* (regex #"^({regex_writes})"))')
    if not cfg.network_enabled():
        parts.append("(deny network*)")
    else:
        parts.append("(allow network*)")
    profile = "\n".join(parts)
    return ["sandbox-exec", "-p", profile] + cmd


def run_sandboxed(cmd: list[str], cfg: SandboxConfig) -> SandboxResult:
    """サンドボックス内で cmd を実行し SandboxResult を返す。

    違反検知時は SandboxViolation を raise (AC-5 UNWANTED の "shall" を機械的に強制)。

    Args:
        cmd: 実行するコマンドと引数。argv リスト形式。
        cfg: SandboxConfig。allow_paths / allow_hosts / timeout_sec を保持。

    Raises:
        SandboxUnavailable: bwrap (Linux) / sandbox-exec (macOS) が PATH に無い。
        SandboxViolation:   sandbox 内 process が違反操作を試みた。
        TimeoutError:       cfg.timeout_sec を超過。
    """
    system = platform.system()
    if system == "Linux":
        if shutil.which("bwrap") is None:
            raise SandboxUnavailable(
                "bwrap (bubblewrap) が PATH に無い。`apt install bubblewrap` で導入してください"
            )
        argv = _build_bwrap_argv(cmd, cfg)
        backend = "bwrap"
    elif system == "Darwin":
        if shutil.which("sandbox-exec") is None:
            raise SandboxUnavailable(
                "sandbox-exec が PATH に無い (通常は macOS に同梱)"
            )
        argv = _build_sandbox_exec_argv(cmd, cfg)
        backend = "sandbox-exec"
    else:
        raise SandboxUnavailable(f"unsupported platform: {system}")

    start = time.monotonic()
    try:
        cp = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=cfg.timeout_sec,
        )
    except subprocess.TimeoutExpired as e:
        duration = time.monotonic() - start
        raise TimeoutError(
            f"sandboxed cmd timed out after {duration:.1f}s (limit={cfg.timeout_sec}s)"
        ) from e
    duration = time.monotonic() - start
    result = SandboxResult(
        returncode=cp.returncode,
        stdout=cp.stdout or "",
        stderr=cp.stderr or "",
        duration_sec=duration,
        backend=backend,
    )

    # AC-2 EVENT / AC-5 UNWANTED: 違反検知
    violation = _detect_violation(cp.returncode, cp.stderr or "")
    if violation is not None:
        raise SandboxViolation(result, reason=violation)
    return result
