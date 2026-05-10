"""T-S0-09: SandboxConfig.

サンドボックス内のファイルシステム / ネットワーク許可リストを表現する。
zero-trust デフォルト: allow_hosts が空なら network 完全無効。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SandboxConfig:
    """サンドボックス実行時の許可セット。

    Attributes:
        allow_paths: 書き込み許可するパス (workspace ディレクトリなど)。
        read_only_paths: 読み込みのみ許可するパス (システムライブラリ / SDK)。
        allow_hosts: ネットワーク許可ホスト名 (空なら network 完全無効 / AC-4)。
        timeout_sec: subprocess の最大実行時間。
        cwd: subprocess の working directory (allow_paths のいずれかに含まれる必要)。
    """

    allow_paths: tuple[Path, ...] = ()
    read_only_paths: tuple[Path, ...] = (
        Path("/usr"),
        Path("/lib"),
        Path("/lib64"),
        Path("/bin"),
        Path("/sbin"),
        Path("/etc/ssl"),
        Path("/etc/ca-certificates"),
        Path("/etc/resolv.conf"),
    )
    allow_hosts: tuple[str, ...] = ()
    timeout_sec: int = 300
    cwd: Path | None = None
    extra_env: dict[str, str] = field(default_factory=dict)

    def network_enabled(self) -> bool:
        """AC-4 OPTIONAL: allow_hosts が空 → network なし (zero-trust)。"""
        return bool(self.allow_hosts)
