"""T-012-03: OS-level sandbox red-line policy (Linux Landlock + seccomp).

T-S0-09 (bwrap on Linux / sandbox-exec on macOS) を **policy layer** で補完する.
本 module は kernel-level Landlock LSM + seccomp BPF の **policy 宣言** と
**static 検査** を提供する (実 kernel binding は Phase 2). Codex CLI 参考.

責務:
  - LandlockPolicy: 読み / 書き / 実行許可パス + 拒否 syscall + network flag
  - DEFAULT_RED_LINE_POLICY: 即セッション kill 対象のデフォルト red-line
  - evaluate_command: cmd + policy + sandbox_cfg を static に check
  - audit_red_line: violations list を返す (audit log 用)
  - detect_landlock_availability: kernel 5.13+ で landlock LSM が
    enabled かどうか

設計境界:
  - T-S0-09 (backend/sandbox/{config,exec,__init__}.py) は完全無改変.
  - LandlockPolicy は SandboxConfig と相互参照しない (one-way: policy が
    SandboxConfig を読む).
  - ADR-010: LangGraph / LangChain / LiteLLM なし.

## 公開 API

  - LandlockPolicy (frozen dataclass)
  - DEFAULT_RED_LINE_POLICY: LandlockPolicy
  - DEFAULT_DENIED_SYSCALLS: tuple[str, ...]
  - detect_landlock_availability() -> dict[str, Any]
  - evaluate_command(cmd, policy, sandbox_cfg=None) -> dict
  - audit_red_line(cmd, policy, sandbox_cfg=None) -> list[dict]
  - LandlockPolicyError
"""
from __future__ import annotations

import os
import platform
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# T-S0-09 SandboxConfig は読み取りのみ (REUSE, 無改変).
from sandbox.config import SandboxConfig


class LandlockPolicyError(RuntimeError):
    """policy 入力 / 不変条件違反 (router で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

MAX_CMD_LEN = 200
MAX_PATH_COUNT = 100
MAX_SYSCALL_COUNT = 200
MAX_CMD_ARG_LEN = 4096

# kernel-level Landlock LSM 利用可能になるバージョン (5.13+).
# seccomp BPF は 3.5+ で広く使えるので availability check は landlock のみ.
LANDLOCK_MIN_KERNEL = (5, 13)

# CLAUDE.md §5.4 レッドライン syscall (即セッション kill).
# Codex CLI の seccomp BPF filter を参考に Phase 1 default を組む.
DEFAULT_DENIED_SYSCALLS: tuple[str, ...] = (
    # network
    "socket",
    "connect",
    "accept",
    "bind",
    "listen",
    # process control
    "ptrace",
    "reboot",
    "init_module",
    "delete_module",
    "kexec_load",
    # fs escape
    "mount",
    "umount",
    "umount2",
    "chroot",
    "pivot_root",
)


# ──────────────────────────────────────────────────────────────────────
# Policy dataclass (frozen / immutable / Landlock semantics)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LandlockPolicy:
    """Landlock LSM + seccomp 統合 policy.

    Landlock は file system access mode を path 単位で許可リスト方式に
    制限する LSM. seccomp BPF は syscall 単位の deny list.

    Attributes:
      read_paths   : 読み取り許可パス (絶対パス必須)
      write_paths  : 書き込み許可パス (絶対パス必須)
      exec_paths   : 実行許可パス (絶対パス必須)
      denied_syscalls : seccomp BPF で deny する syscall 名
      network_allowed : True なら network namespace 保持 (T-S0-09 と整合)
    """

    read_paths: tuple[Path, ...] = ()
    write_paths: tuple[Path, ...] = ()
    exec_paths: tuple[Path, ...] = ()
    denied_syscalls: tuple[str, ...] = DEFAULT_DENIED_SYSCALLS
    network_allowed: bool = False
    description: str = ""


# Phase 1 デフォルト: 一般的な開発作業を許可しつつ network / mount は完全 deny.
DEFAULT_RED_LINE_POLICY: LandlockPolicy = LandlockPolicy(
    read_paths=(
        Path("/usr"),
        Path("/lib"),
        Path("/lib64"),
        Path("/bin"),
        Path("/etc/ssl"),
        Path("/etc/ca-certificates"),
    ),
    write_paths=(
        Path("/tmp"),
    ),
    exec_paths=(
        Path("/usr/bin"),
        Path("/usr/local/bin"),
        Path("/bin"),
    ),
    denied_syscalls=DEFAULT_DENIED_SYSCALLS,
    network_allowed=False,
    description="Build-Factory Phase 1 red-line: no network / no mount / "
                "no ptrace / no kernel module / write only under /tmp",
)


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_cmd(cmd: Any) -> tuple[str, ...]:
    if not isinstance(cmd, (list, tuple)):
        raise LandlockPolicyError("cmd must be list or tuple of strings")
    if not cmd:
        raise LandlockPolicyError("cmd must not be empty")
    if len(cmd) > MAX_CMD_LEN:
        raise LandlockPolicyError(
            f"cmd length must be <= {MAX_CMD_LEN}, got {len(cmd)}"
        )
    out: list[str] = []
    for i, c in enumerate(cmd):
        if not isinstance(c, str):
            raise LandlockPolicyError(
                f"cmd[{i}] must be string, got {type(c).__name__}"
            )
        if len(c) > MAX_CMD_ARG_LEN:
            raise LandlockPolicyError(
                f"cmd[{i}] exceeds {MAX_CMD_ARG_LEN} chars"
            )
        out.append(c)
    return tuple(out)


def _validate_policy(policy: Any) -> LandlockPolicy:
    if not isinstance(policy, LandlockPolicy):
        raise LandlockPolicyError(
            f"policy must be LandlockPolicy, got {type(policy).__name__}"
        )
    for field_name in ("read_paths", "write_paths", "exec_paths"):
        for p in getattr(policy, field_name):
            if not isinstance(p, Path):
                raise LandlockPolicyError(
                    f"{field_name} entries must be Path"
                )
            if not p.is_absolute():
                raise LandlockPolicyError(
                    f"{field_name} entries must be absolute path "
                    f"(relative path breaks Landlock): {p}"
                )
    if len(policy.denied_syscalls) > MAX_SYSCALL_COUNT:
        raise LandlockPolicyError(
            f"denied_syscalls too long: {len(policy.denied_syscalls)}"
        )
    if (
        len(policy.read_paths)
        + len(policy.write_paths)
        + len(policy.exec_paths)
        > MAX_PATH_COUNT * 3
    ):
        raise LandlockPolicyError("policy paths exceed budget")
    return policy


def _validate_sandbox_cfg(cfg: Any) -> Optional[SandboxConfig]:
    if cfg is None:
        return None
    if not isinstance(cfg, SandboxConfig):
        raise LandlockPolicyError(
            f"sandbox_cfg must be SandboxConfig, got {type(cfg).__name__}"
        )
    return cfg


# ──────────────────────────────────────────────────────────────────────
# Landlock availability (cached per process)
# ──────────────────────────────────────────────────────────────────────

_AVAILABILITY_LOCK = threading.RLock()
_AVAILABILITY_CACHE: Optional[dict[str, Any]] = None


def _parse_kernel_version(release: str) -> tuple[int, int]:
    """e.g. '6.18.5' / '5.13.0-generic' から (major, minor) を抽出."""
    parts = release.split(".")
    try:
        return (int(parts[0]), int(parts[1]))
    except (IndexError, ValueError):
        return (0, 0)


def detect_landlock_availability() -> dict[str, Any]:
    """Linux kernel 5.13+ + Landlock LSM enabled なら available=True.

    Process-local cache (deterministic per process / AC-3).
    """
    global _AVAILABILITY_CACHE
    with _AVAILABILITY_LOCK:
        if _AVAILABILITY_CACHE is not None:
            return dict(_AVAILABILITY_CACHE)  # defensive copy
        system = platform.system()
        if system != "Linux":
            result = {
                "available": False,
                "reason": f"non-linux platform: {system}",
                "kernel_version": platform.release(),
                "min_kernel": ".".join(str(x) for x in LANDLOCK_MIN_KERNEL),
            }
        else:
            release = platform.release()
            major_minor = _parse_kernel_version(release)
            kernel_ok = major_minor >= LANDLOCK_MIN_KERNEL
            lsm_ok = _landlock_lsm_enabled()
            result = {
                "available": kernel_ok and lsm_ok,
                "reason": (
                    "ok" if (kernel_ok and lsm_ok)
                    else f"kernel_ok={kernel_ok} lsm_ok={lsm_ok}"
                ),
                "kernel_version": release,
                "min_kernel": ".".join(str(x) for x in LANDLOCK_MIN_KERNEL),
                "lsm_enabled": lsm_ok,
            }
        _AVAILABILITY_CACHE = result
        return dict(result)


def _landlock_lsm_enabled() -> bool:
    """/sys/kernel/security/lsm が landlock を含むか確認."""
    try:
        lsm_path = Path("/sys/kernel/security/lsm")
        if not lsm_path.exists():
            return False
        content = lsm_path.read_text(encoding="utf-8")
        return "landlock" in content.lower()
    except (OSError, PermissionError):
        return False


def _reset_availability_cache_for_test() -> None:
    """test cleanup 用 (production code では呼ばない)."""
    global _AVAILABILITY_CACHE
    with _AVAILABILITY_LOCK:
        _AVAILABILITY_CACHE = None


# ──────────────────────────────────────────────────────────────────────
# Evaluation (red-line static check)
# ──────────────────────────────────────────────────────────────────────


def evaluate_command(
    cmd: Iterable[str],
    policy: LandlockPolicy,
    sandbox_cfg: Optional[SandboxConfig] = None,
) -> dict[str, Any]:
    """cmd + policy + sandbox_cfg を static に red-line check する.

    Returns:
      {
        "allowed": bool,
        "violations": list[dict{kind, detail}],
        "landlock_available": bool,
        "kernel_version": str,
      }
    """
    cmd_tuple = _validate_cmd(cmd)
    pol = _validate_policy(policy)
    cfg = _validate_sandbox_cfg(sandbox_cfg)

    violations = audit_red_line(cmd_tuple, pol, cfg)
    avail = detect_landlock_availability()
    return {
        "allowed": len(violations) == 0,
        "violations": violations,
        "landlock_available": avail["available"],
        "kernel_version": avail["kernel_version"],
    }


def audit_red_line(
    cmd: Iterable[str],
    policy: LandlockPolicy,
    sandbox_cfg: Optional[SandboxConfig] = None,
) -> list[dict[str, str]]:
    """red-line 違反を deterministic list で返す (kind asc sorted)."""
    cmd_tuple = _validate_cmd(cmd)
    pol = _validate_policy(policy)
    cfg = _validate_sandbox_cfg(sandbox_cfg)

    violations: list[dict[str, str]] = []

    # 1. denied syscall: cmd 引数文字列に直接含まれるパターン (ptrace / strace 等)
    cmd_joined = " ".join(cmd_tuple)
    for sc in pol.denied_syscalls:
        if _command_uses_syscall(cmd_tuple, cmd_joined, sc):
            violations.append({
                "kind": "denied_syscall",
                "detail": f"command appears to invoke denied syscall: {sc}",
            })

    # 2. write outside policy.write_paths: 'rm -rf /' 'cp ... /usr/' 等のパターン
    for arg in cmd_tuple[1:]:  # cmd[0] = executable name は exec 判定で扱う
        if arg.startswith("/") and _looks_like_write_target(cmd_tuple, arg):
            if not _path_under_any(arg, pol.write_paths):
                violations.append({
                    "kind": "write_outside_policy",
                    "detail": f"argument '{arg}' may write outside "
                              f"policy.write_paths",
                })

    # 3. network 違反: policy.network_allowed=False + sandbox_cfg.allow_hosts 非空
    if not pol.network_allowed and cfg is not None and cfg.allow_hosts:
        violations.append({
            "kind": "network_not_allowed",
            "detail": (
                f"policy disallows network but sandbox_cfg.allow_hosts="
                f"{cfg.allow_hosts}"
            ),
        })

    # 4. exec path 違反: cmd[0] が exec_paths 配下でない (absolute path 指定時のみ)
    if cmd_tuple[0].startswith("/"):
        if not _path_under_any(cmd_tuple[0], pol.exec_paths):
            violations.append({
                "kind": "exec_outside_policy",
                "detail": f"executable '{cmd_tuple[0]}' not under "
                          f"policy.exec_paths",
            })

    # deterministic order: kind asc, detail asc
    violations.sort(key=lambda v: (v["kind"], v["detail"]))
    return violations


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


_WRITE_LIKE_FLAGS = frozenset((
    "-w", "--write", "-o", "--output", ">", ">>", "--out",
))

_WRITE_LIKE_COMMANDS = frozenset((
    "rm", "mv", "cp", "dd", "tee", "touch", "mkdir", "rmdir",
    "truncate", "chmod", "chown", "ln",
))


def _looks_like_write_target(cmd_tuple: tuple[str, ...], arg: str) -> bool:
    """cmd の文脈で arg が書き込み先っぽいかを heuristic で判定."""
    exe = os.path.basename(cmd_tuple[0])
    if exe in _WRITE_LIKE_COMMANDS:
        return True
    for tok in cmd_tuple:
        if tok in _WRITE_LIKE_FLAGS:
            return True
    return False


def _command_uses_syscall(
    cmd_tuple: tuple[str, ...],
    cmd_joined: str,
    syscall: str,
) -> bool:
    """cmd が指定 syscall を呼ぶ binary を起動しているか heuristic 判定.

    厳密には kernel ftrace が必要だが Phase 1 は string 一致.
    """
    exe = os.path.basename(cmd_tuple[0])
    # well-known mapping: ptrace → strace/gdb/ltrace, mount → mount/umount 等
    SYSCALL_TO_EXE = {
        "ptrace": {"strace", "ltrace", "gdb"},
        "mount": {"mount"},
        "umount": {"umount"},
        "umount2": {"umount", "umount2"},
        "chroot": {"chroot"},
        "pivot_root": {"pivot_root"},
        "init_module": {"insmod", "modprobe"},
        "delete_module": {"rmmod"},
        "reboot": {"reboot", "shutdown", "halt"},
    }
    if syscall in SYSCALL_TO_EXE:
        if exe in SYSCALL_TO_EXE[syscall]:
            return True
    return False


def _path_under_any(target: str, allowed: tuple[Path, ...]) -> bool:
    """target が allowed のいずれかの prefix 配下か."""
    try:
        target_path = Path(target).resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    for a in allowed:
        try:
            target_path.relative_to(a.resolve(strict=False))
            return True
        except ValueError:
            continue
    return False
