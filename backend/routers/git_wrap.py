"""T-013-02 / F-013: Claude Code commit + push wrap REST endpoint (worktree 経由).

Endpoint:
  POST /api/git/worktree/{pool_id}/{cell_index}/commit   commit_changes
  POST /api/git/worktree/{pool_id}/{cell_index}/push     push_branch
  GET  /api/git/worktree/{pool_id}/{cell_index}/status   status

AC マッピング:
  AC-1 UBIQUITOUS    : F-013 commit + push wrap endpoint (worktree path resolved)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 swarm.worktree service REUSE (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid branch / 禁止 flag / path traversal は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import git_wrap as gw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/git/worktree", tags=["git-wrap"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("git-wrap audit emit failed: %s -- %s", event_type, e)


def _resolve_worktree(pool_id: int, cell_index: int) -> Path:
    if pool_id <= 0:
        raise _error("git.invalid_pool_id", "pool_id must be > 0")
    if cell_index < 0:
        raise _error("git.invalid_cell_index", "cell_index must be >= 0")
    try:
        from services.swarm.worktree import worktree_path
        return worktree_path(pool_id, cell_index)
    except Exception as e:
        raise _error("git.invalid_worktree",
                     f"failed to resolve worktree: {e}")


class CommitRequest(BaseModel):
    message: str
    allow_empty: bool = False
    add_all: bool = True
    dry_run: bool = False
    actor_user_id: Optional[str] = None


class PushRequest(BaseModel):
    branch: str
    remote: str = Field("origin", max_length=100)
    set_upstream: bool = True
    dry_run: bool = False
    actor_user_id: Optional[str] = None


@router.post("/{pool_id}/{cell_index}/commit")
async def commit(pool_id: int, cell_index: int, body: CommitRequest) -> dict[str, Any]:
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("git.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not body.message or not body.message.strip():
        raise _error("git.invalid_message", "message must not be empty")
    if len(body.message) > gw.MAX_COMMIT_MESSAGE:
        raise _error("git.message_too_long",
                     f"message must be <= {gw.MAX_COMMIT_MESSAGE} chars")
    wd = _resolve_worktree(pool_id, cell_index)
    try:
        result = await gw.commit_changes(
            wd, body.message,
            allow_empty=body.allow_empty,
            add_all=body.add_all,
            dry_run=body.dry_run,
        )
    except gw.UnsafeOperationError as e:
        raise _error("git.unsafe_operation", str(e), status_code=403)
    except gw.GitWrapError as e:
        msg = str(e)
        if "not a git work tree" in msg or "not a directory" in msg:
            raise _error("git.worktree_not_found", msg, status_code=404)
        raise _error("git.commit_failed", msg, status_code=500)

    await _audit(
        "git.commit",
        user_id=body.actor_user_id,
        detail={
            "pool_id": pool_id,
            "cell_index": cell_index,
            "dry_run": body.dry_run,
            "returncode": result.git.returncode,
        },
    )
    return result.to_dict()


@router.post("/{pool_id}/{cell_index}/push")
async def push(pool_id: int, cell_index: int, body: PushRequest) -> dict[str, Any]:
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("git.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not body.branch or not body.branch.strip():
        raise _error("git.invalid_branch", "branch must not be empty")
    wd = _resolve_worktree(pool_id, cell_index)
    try:
        result = await gw.push_branch(
            wd, body.branch,
            remote=body.remote,
            set_upstream=body.set_upstream,
            dry_run=body.dry_run,
        )
    except gw.UnsafeOperationError as e:
        raise _error("git.unsafe_operation", str(e), status_code=403)
    except gw.GitWrapError as e:
        msg = str(e)
        if "not a git work tree" in msg or "not a directory" in msg:
            raise _error("git.worktree_not_found", msg, status_code=404)
        if "invalid characters" in msg or "must be <=" in msg \
                or "must not be empty" in msg:
            raise _error("git.invalid_branch", msg)
        raise _error("git.push_failed", msg, status_code=502)

    await _audit(
        "git.push",
        user_id=body.actor_user_id,
        detail={
            "pool_id": pool_id,
            "cell_index": cell_index,
            "branch": body.branch,
            "remote": body.remote,
            "dry_run": body.dry_run,
        },
    )
    return result.to_dict()


@router.get("/{pool_id}/{cell_index}/status")
async def status(pool_id: int, cell_index: int) -> dict[str, Any]:
    wd = _resolve_worktree(pool_id, cell_index)
    try:
        result = await gw.status(wd)
    except gw.GitWrapError as e:
        msg = str(e)
        if "not a git work tree" in msg or "not a directory" in msg:
            raise _error("git.worktree_not_found", msg, status_code=404)
        raise _error("git.status_failed", msg, status_code=500)
    return result.to_dict()
