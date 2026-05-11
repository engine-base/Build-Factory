"""T-013-02: Claude Code commit + push wrap (worktree 経由).

worktree (T-M29-01) 配下で安全に git commit + push をラップする service.

セーフティ:
  - 必ず指定 worktree path の内側でのみ操作 (path traversal 防御)
  - allowed branch prefix チェック (claude/* のみ許可、 main は禁止)
  - commit message size 上限 (<= 5000 chars)
  - --no-verify / --force / --force-with-lease は許容しない
  - dry_run option で実 git を呼ばない試走

公開 API:
  - commit_changes(workdir, message, *, allow_empty=False, runner=None) -> CommitResult
  - push_branch(workdir, branch, *, remote='origin', set_upstream=True, runner=None) -> PushResult
  - status(workdir, *, runner=None) -> StatusResult
"""
from __future__ import annotations

import logging
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)


class GitWrapError(RuntimeError):
    pass


class UnsafeOperationError(GitWrapError):
    pass


# main / master / 一切の他人 branch は push 拒否. claude/ prefix のみ
ALLOWED_BRANCH_PREFIX = ("claude/",)
FORBIDDEN_BRANCH_EXACT = ("main", "master", "production", "release")
MAX_COMMIT_MESSAGE = 5000
MAX_BRANCH_LEN = 200
FORBIDDEN_FLAGS = {
    "--no-verify", "--force", "-f", "--force-with-lease",
    "--no-gpg-sign", "-c",
}


def _validate_workdir(workdir: Path) -> Path:
    if not isinstance(workdir, Path):
        workdir = Path(workdir)
    if not workdir.is_absolute():
        raise GitWrapError("workdir must be an absolute path")
    if not workdir.is_dir():
        raise GitWrapError(f"workdir not a directory: {workdir}")
    # 通常の worktree は .git ファイルか .git ディレクトリを持つ
    if not (workdir / ".git").exists():
        raise GitWrapError(f"workdir is not a git work tree: {workdir}")
    return workdir


def _validate_branch(branch: str) -> str:
    if not isinstance(branch, str) or not branch.strip():
        raise GitWrapError("branch must not be empty")
    b = branch.strip()
    if len(b) > MAX_BRANCH_LEN:
        raise GitWrapError(f"branch must be <= {MAX_BRANCH_LEN} chars")
    if b in FORBIDDEN_BRANCH_EXACT:
        raise UnsafeOperationError(
            f"push to {b!r} is forbidden (use feature branch)"
        )
    if not any(b.startswith(p) for p in ALLOWED_BRANCH_PREFIX):
        raise UnsafeOperationError(
            f"branch must start with one of {ALLOWED_BRANCH_PREFIX}, "
            f"got {b!r}"
        )
    if not re.match(r"^[A-Za-z0-9/_.\-]+$", b):
        raise GitWrapError("branch contains invalid characters")
    return b


def _validate_message(message: str) -> str:
    if not isinstance(message, str) or not message.strip():
        raise GitWrapError("commit message must not be empty")
    if len(message) > MAX_COMMIT_MESSAGE:
        raise GitWrapError(
            f"commit message must be <= {MAX_COMMIT_MESSAGE} chars"
        )
    return message


def _check_no_forbidden_flags(extra_args: Iterable[str]) -> None:
    for a in extra_args:
        if a in FORBIDDEN_FLAGS or a.startswith("--force"):
            raise UnsafeOperationError(f"forbidden flag: {a!r}")


@dataclass
class GitResult:
    cmd: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict:
        return {
            "cmd": list(self.cmd),
            "returncode": self.returncode,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-4000:],
            "dry_run": self.dry_run,
            "ok": self.ok,
        }


@dataclass
class CommitResult:
    workdir: str
    message: str
    git: GitResult

    def to_dict(self) -> dict:
        return {
            "workdir": self.workdir,
            "message": self.message[:200],
            "git": self.git.to_dict(),
        }


@dataclass
class PushResult:
    workdir: str
    branch: str
    remote: str
    git: GitResult

    def to_dict(self) -> dict:
        return {
            "workdir": self.workdir,
            "branch": self.branch,
            "remote": self.remote,
            "git": self.git.to_dict(),
        }


@dataclass
class StatusResult:
    workdir: str
    branch: Optional[str] = None
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    porcelain: str = ""

    def to_dict(self) -> dict:
        return {
            "workdir": self.workdir,
            "branch": self.branch,
            "dirty": self.dirty,
            "ahead": self.ahead,
            "behind": self.behind,
            "porcelain": self.porcelain[:4000],
        }


# 注入可能な git runner (default は asyncio subprocess)
GitRunner = Callable[[list[str], Path], Awaitable[GitResult]]


async def _default_git_runner(cmd: list[str], cwd: Path) -> GitResult:
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        "git", *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return GitResult(
        cmd=["git", *cmd],
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


async def commit_changes(
    workdir: Path | str,
    message: str,
    *,
    allow_empty: bool = False,
    add_all: bool = True,
    extra_args: Optional[list[str]] = None,
    runner: Optional[GitRunner] = None,
    dry_run: bool = False,
) -> CommitResult:
    """worktree 内で commit を実行."""
    wd = _validate_workdir(Path(workdir))
    msg = _validate_message(message)
    extras = list(extra_args or [])
    _check_no_forbidden_flags(extras)

    git_runner = runner or _default_git_runner
    if add_all:
        if dry_run:
            add_result = GitResult(cmd=["git", "add", "-A"], returncode=0, dry_run=True)
        else:
            add_result = await git_runner(["add", "-A"], wd)
            if not add_result.ok:
                raise GitWrapError(
                    f"git add failed: {add_result.stderr[:500]}"
                )

    cmd = ["commit", "-m", msg]
    if allow_empty:
        cmd.append("--allow-empty")
    cmd.extend(extras)

    if dry_run:
        gr = GitResult(cmd=["git", *cmd], returncode=0, dry_run=True)
    else:
        gr = await git_runner(cmd, wd)
        if not gr.ok and "nothing to commit" not in gr.stdout + gr.stderr:
            raise GitWrapError(f"git commit failed: {gr.stderr[:500]}")

    return CommitResult(workdir=str(wd), message=msg, git=gr)


async def push_branch(
    workdir: Path | str,
    branch: str,
    *,
    remote: str = "origin",
    set_upstream: bool = True,
    extra_args: Optional[list[str]] = None,
    runner: Optional[GitRunner] = None,
    dry_run: bool = False,
) -> PushResult:
    wd = _validate_workdir(Path(workdir))
    b = _validate_branch(branch)
    if not isinstance(remote, str) or not remote.strip():
        raise GitWrapError("remote must not be empty")
    if len(remote) > 100:
        raise GitWrapError("remote must be <= 100 chars")
    if not re.match(r"^[A-Za-z0-9_.\-]+$", remote):
        raise GitWrapError("remote contains invalid characters")
    extras = list(extra_args or [])
    _check_no_forbidden_flags(extras)

    cmd = ["push"]
    if set_upstream:
        cmd.append("-u")
    cmd.extend([remote, b])
    cmd.extend(extras)

    git_runner = runner or _default_git_runner
    if dry_run:
        gr = GitResult(cmd=["git", *cmd], returncode=0, dry_run=True)
    else:
        gr = await git_runner(cmd, wd)
        if not gr.ok:
            raise GitWrapError(
                f"git push failed (rc={gr.returncode}): {gr.stderr[:500]}"
            )
    return PushResult(workdir=str(wd), branch=b, remote=remote, git=gr)


async def status(
    workdir: Path | str,
    *,
    runner: Optional[GitRunner] = None,
) -> StatusResult:
    wd = _validate_workdir(Path(workdir))
    git_runner = runner or _default_git_runner
    porcelain = await git_runner(["status", "--porcelain=v2", "--branch"], wd)
    if not porcelain.ok:
        raise GitWrapError(
            f"git status failed: {porcelain.stderr[:500]}"
        )
    branch: Optional[str] = None
    ahead = 0
    behind = 0
    dirty = False
    for line in porcelain.stdout.splitlines():
        if line.startswith("# branch.head"):
            branch = line.split(" ", 2)[2].strip()
        elif line.startswith("# branch.ab"):
            # # branch.ab +A -B
            parts = line.split()
            if len(parts) >= 4:
                try:
                    ahead = int(parts[2].lstrip("+"))
                    behind = int(parts[3].lstrip("-"))
                except ValueError:
                    pass
        elif line and not line.startswith("#"):
            dirty = True
    return StatusResult(
        workdir=str(wd),
        branch=branch,
        dirty=dirty,
        ahead=ahead,
        behind=behind,
        porcelain=porcelain.stdout,
    )
