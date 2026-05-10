"""T-S0-09: OS-level sandbox 基盤。

ClaudeAgentRunner が起動する subprocess (Claude Code, bash 命令, Python プロセス) を
Linux では bwrap (bubblewrap)、macOS では sandbox-exec で隔離実行する。

公開 API:
    SandboxConfig    — allow_paths / allow_hosts / read_only_paths を保持
    SandboxResult    — exit code / stdout / stderr / violation flag
    SandboxViolation — sandbox からの脱出 / 違反検知時に raise (AC-5)
    SandboxUnavailable — bwrap / sandbox-exec が PATH に無い環境
    run_sandboxed()  — 同期実行 (内部で subprocess を spawn)
"""
from __future__ import annotations

from .config import SandboxConfig
from .exec import (
    SandboxResult,
    SandboxUnavailable,
    SandboxViolation,
    run_sandboxed,
)

__all__ = [
    "SandboxConfig",
    "SandboxResult",
    "SandboxUnavailable",
    "SandboxViolation",
    "run_sandboxed",
]
