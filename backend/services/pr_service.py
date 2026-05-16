"""T-V3-B-19 / F-013: PR review backend service.

Implements the data-access + domain logic for the 4 new PR endpoints:

    GET  /api/workspaces/{id}/prs/{pr_number}   (member)
    POST /api/prs/{id}/approve                  (workspace_admin)
    POST /api/prs/{id}/comments                 (member)
    POST /api/prs/{id}/merge                    (workspace_admin)

The service is GitHub-API-stubbed: it owns the local DB record for the PR
(workspace-scoped via repos.workspace_id) and emits audit logs for each
mutation. A real GitHub merge integration is delegated to a pluggable
``github_merge_callable`` keyword (defaults to a no-op stub returning a
deterministic sha) so unit tests can run hermetically.

Entities (E-033 PullRequest / E-034 Delivery / E-030 Comment):
    - pull_requests (existing, supabase/migrations/20260501220000)
    - pr_comments   (new, supabase/migrations/20260516000000)

AC mapping (1:1 with audit MD Tier 2):
    AC-F1/F10 EVENT-DRIVEN: merge happy path emits pr_merged audit
    AC-F2     UNWANTED   : conflict / not-approved -> 409 (PRConflictError)
    AC-F3/F4  EVENT/UNWANTED: get_pr returns dict / PRNotFoundError -> 404
    AC-F5/F6  EVENT/UNWANTED: approve happy path / 401
    AC-F7-F9  EVENT/UNWANTED: comments happy / 401 / 422 validation
    AC-F11/12 UNWANTED   : merge 401 / 422 invalid merge_method
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Constants & errors
# ─────────────────────────────────────────────────────────────────────────

VALID_MERGE_METHODS: tuple[str, ...] = ("squash", "merge", "rebase")
MAX_COMMENT_BODY_LEN = 8000
MAX_ANCHOR_FILE_LEN = 500
MAX_APPROVE_COMMENT_LEN = 2000

# PR statuses we recognise. "open" / "approved" / "merged" / "closed".
STATUS_OPEN = "open"
STATUS_APPROVED = "approved"
STATUS_MERGED = "merged"


class PRServiceError(ValueError):
    """Base for PR service errors mapped to 4xx in router layer."""


class PRNotFoundError(PRServiceError):
    """PR not found (router -> 404)."""


class PRConflictError(PRServiceError):
    """PR state conflict: already approved / merged / unresolved conflicts.

    Router -> 409.
    """


class PRValidationError(PRServiceError):
    """PR input validation failure (router -> 422)."""


class PRForbiddenError(PRServiceError):
    """PR access forbidden (caller is not workspace member / admin).

    Router -> 403.
    """


# ─────────────────────────────────────────────────────────────────────────
# Schema bootstrap (idempotent — for SQLite test path)
# ─────────────────────────────────────────────────────────────────────────


async def _ensure_pr_tables(db) -> None:
    """SQLite-friendly schema bootstrap.

    Supabase Postgres production schema lives in
    ``supabase/migrations/20260501220000_initial_schema.sql`` (pull_requests +
    repos) and ``supabase/migrations/20260516000000_pr_comments.sql``
    (pr_comments). This helper mirrors them for the embedded SQLite path
    used by FastAPI tests so the service can run without a separate
    migration step.
    """
    await db.execute(
        """CREATE TABLE IF NOT EXISTS repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            default_branch TEXT DEFAULT 'main',
            created_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    await db.execute(
        """CREATE TABLE IF NOT EXISTS pull_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo_id INTEGER NOT NULL,
            number INTEGER NOT NULL,
            title TEXT NOT NULL,
            author TEXT,
            status TEXT DEFAULT 'open',
            head_branch TEXT,
            base_branch TEXT DEFAULT 'main',
            url TEXT,
            has_conflicts INTEGER DEFAULT 0,
            approved_at TEXT,
            approved_by TEXT,
            merged_at TEXT,
            merged_sha TEXT,
            merge_method TEXT,
            html_review_url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )"""
    )
    await db.execute(
        """CREATE TABLE IF NOT EXISTS pr_comments (
            id TEXT PRIMARY KEY,
            pr_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            author_user_id TEXT NOT NULL,
            body TEXT NOT NULL,
            anchor_file TEXT,
            anchor_line INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        )"""
    )


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _row_to_pr(row) -> dict:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        d = {k: row[k] for k in row.keys()}
    else:
        d = dict(row)
    d["has_conflicts"] = bool(d.get("has_conflicts") or 0)
    return d


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


async def _emit_audit(action: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(action, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover - audit emission must never break flow
        logger.warning("pr_service audit emit failed: %s -- %s", action, e)


async def _require_member(
    db, *, workspace_id: int, user_id: str, admin_only: bool = False,
) -> str:
    """Return the member role for (workspace_id, user_id) or raise.

    Mirrors workspace_service.get_member but is inlined here so that the
    same DB transaction can be re-used.
    """
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        "SELECT role FROM workspace_members "
        "WHERE workspace_id = ? AND user_id = ?",
        (workspace_id, user_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise PRForbiddenError(
            f"user_id={user_id} is not a member of workspace_id={workspace_id}"
        )
    role = row["role"]
    if admin_only and role not in ("admin", "ws_admin", "owner"):
        raise PRForbiddenError(
            f"user_id={user_id} role={role} is not workspace_admin"
        )
    return role


async def _load_pr(db, *, pr_id: Optional[int] = None,
                    workspace_id: Optional[int] = None,
                    pr_number: Optional[int] = None) -> dict:
    db.row_factory = aiosqlite.Row
    if pr_id is not None:
        cur = await db.execute(
            "SELECT pr.*, r.workspace_id AS workspace_id "
            "FROM pull_requests pr JOIN repos r ON pr.repo_id = r.id "
            "WHERE pr.id = ?",
            (pr_id,),
        )
    else:
        cur = await db.execute(
            "SELECT pr.*, r.workspace_id AS workspace_id "
            "FROM pull_requests pr JOIN repos r ON pr.repo_id = r.id "
            "WHERE r.workspace_id = ? AND pr.number = ?",
            (workspace_id, pr_number),
        )
    row = await cur.fetchone()
    if row is None:
        raise PRNotFoundError(
            f"PR not found: pr_id={pr_id} workspace={workspace_id} number={pr_number}"
        )
    return _row_to_pr(row)


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


async def get_pr_by_number(
    *, workspace_id: int, pr_number: int, actor_user_id: str,
) -> dict:
    """GET /api/workspaces/{id}/prs/{pr_number} backend.

    Returns ``{"pr": {...}, "html_review_url": "..."}`` shape matching
    features.json#F-013 outputs_2xx.

    AC-F3: happy path.
    AC-F4: 401 handled in router (no actor_user_id).
    """
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise PRValidationError("workspace_id must be positive int")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise PRValidationError("pr_number must be positive int")
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_pr_tables(db)
        await _require_member(
            db, workspace_id=workspace_id, user_id=actor_user_id,
        )
        pr = await _load_pr(
            db, workspace_id=workspace_id, pr_number=pr_number,
        )
    return {
        "pr": pr,
        "html_review_url": pr.get("html_review_url")
        or f"/api/pr-review/render-html?pr_id={pr['id']}",
    }


async def approve_pr(
    *, pr_id: int, actor_user_id: str, comment: Optional[str] = None,
) -> dict:
    """POST /api/prs/{id}/approve backend.

    AC-F1 / AC-F5: happy path.
    AC-F2 / AC-F11: 409 when already approved or merged.
    AC-F6: 401 in router.
    """
    if not isinstance(pr_id, int) or pr_id <= 0:
        raise PRValidationError("pr_id must be positive int")
    if comment is not None:
        if not isinstance(comment, str):
            raise PRValidationError("comment must be string or null")
        if len(comment) > MAX_APPROVE_COMMENT_LEN:
            raise PRValidationError(
                f"comment must be <= {MAX_APPROVE_COMMENT_LEN} chars"
            )
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_pr_tables(db)
        pr = await _load_pr(db, pr_id=pr_id)
        await _require_member(
            db, workspace_id=int(pr["workspace_id"]),
            user_id=actor_user_id, admin_only=True,
        )
        if pr["status"] == STATUS_MERGED:
            raise PRConflictError(f"PR {pr_id} is already merged")
        if pr["status"] == STATUS_APPROVED or pr.get("approved_at"):
            raise PRConflictError(f"PR {pr_id} is already approved")
        approved_at = _now_iso()
        await db.execute(
            "UPDATE pull_requests SET status = ?, approved_at = ?, "
            "approved_by = ?, updated_at = datetime('now') WHERE id = ?",
            (STATUS_APPROVED, approved_at, actor_user_id, pr_id),
        )
        await db.commit()
    await _emit_audit(
        "pr_approved",
        user_id=actor_user_id,
        detail={"pr_id": pr_id, "approved_at": approved_at,
                "comment_len": len(comment or "")},
    )
    return {"approved_at": approved_at}


async def add_pr_comment(
    *, pr_id: int, actor_user_id: str, body: str,
    anchor_file: Optional[str] = None, anchor_line: Optional[int] = None,
) -> dict:
    """POST /api/prs/{id}/comments backend.

    AC-F7: happy path returns ``{"comment_id": uuid}``.
    AC-F8: 401 in router.
    AC-F9: validation -> PRValidationError -> router 422.
    """
    if not isinstance(pr_id, int) or pr_id <= 0:
        raise PRValidationError("pr_id must be positive int")
    if body is None or not isinstance(body, str):
        raise PRValidationError("body must be non-empty string")
    body_stripped = body.strip()
    if not body_stripped:
        raise PRValidationError("body must not be empty")
    if len(body) > MAX_COMMENT_BODY_LEN:
        raise PRValidationError(
            f"body must be <= {MAX_COMMENT_BODY_LEN} chars"
        )
    if anchor_file is not None:
        if not isinstance(anchor_file, str):
            raise PRValidationError("anchor_file must be string or null")
        if not anchor_file.strip():
            raise PRValidationError(
                "anchor_file must not be empty string when provided"
            )
        if len(anchor_file) > MAX_ANCHOR_FILE_LEN:
            raise PRValidationError(
                f"anchor_file must be <= {MAX_ANCHOR_FILE_LEN} chars"
            )
    if anchor_line is not None:
        if not isinstance(anchor_line, int) or isinstance(anchor_line, bool):
            raise PRValidationError("anchor_line must be int or null")
        if anchor_line < 1:
            raise PRValidationError("anchor_line must be >= 1")
    comment_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_pr_tables(db)
        pr = await _load_pr(db, pr_id=pr_id)
        await _require_member(
            db, workspace_id=int(pr["workspace_id"]),
            user_id=actor_user_id,
        )
        await db.execute(
            "INSERT INTO pr_comments "
            "(id, pr_id, workspace_id, author_user_id, body, anchor_file, anchor_line) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (comment_id, pr_id, int(pr["workspace_id"]), actor_user_id,
             body_stripped, anchor_file, anchor_line),
        )
        await db.commit()
    await _emit_audit(
        "pr_comment_added",
        user_id=actor_user_id,
        detail={
            "pr_id": pr_id, "comment_id": comment_id,
            "body_len": len(body_stripped), "has_anchor": anchor_file is not None,
        },
    )
    return {"comment_id": comment_id}


async def merge_pr(
    *, pr_id: int, actor_user_id: str, merge_method: str,
    github_merge_callable: Optional[
        Callable[[int, str], Awaitable[dict[str, Any]]]
    ] = None,
) -> dict:
    """POST /api/prs/{id}/merge backend.

    AC-F1 / AC-F10: happy path emits ``pr_merged`` audit.
    AC-F2: PR with unresolved conflicts -> 409.
    AC-F11: 401 in router.
    AC-F12: invalid merge_method -> 422.

    ``github_merge_callable`` is an injectable async ``(pr_id, merge_method)
    -> {"sha": "..."}`` adapter so tests don't hit GitHub.
    """
    if not isinstance(pr_id, int) or pr_id <= 0:
        raise PRValidationError("pr_id must be positive int")
    if not isinstance(merge_method, str) or merge_method not in VALID_MERGE_METHODS:
        raise PRValidationError(
            f"merge_method must be one of {VALID_MERGE_METHODS}"
        )
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_pr_tables(db)
        pr = await _load_pr(db, pr_id=pr_id)
        await _require_member(
            db, workspace_id=int(pr["workspace_id"]),
            user_id=actor_user_id, admin_only=True,
        )
        if pr["status"] == STATUS_MERGED:
            raise PRConflictError(f"PR {pr_id} is already merged")
        if pr.get("has_conflicts"):
            raise PRConflictError(
                f"PR {pr_id} has unresolved conflicts"
            )
        if pr["status"] != STATUS_APPROVED:
            raise PRConflictError(
                f"PR {pr_id} is not approved (status={pr['status']})"
            )
        # GitHub adapter
        if github_merge_callable is None:
            gh_result = {"sha": f"stub-{pr_id}-{merge_method}"}
        else:
            gh_result = await github_merge_callable(pr_id, merge_method)
        sha = str(gh_result.get("sha") or "")
        merged_at = _now_iso()
        await db.execute(
            "UPDATE pull_requests SET status = ?, merged_at = ?, "
            "merged_sha = ?, merge_method = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (STATUS_MERGED, merged_at, sha, merge_method, pr_id),
        )
        await db.commit()
    await _emit_audit(
        "pr_merged",
        user_id=actor_user_id,
        detail={"pr_id": pr_id, "merged_at": merged_at,
                "sha": sha, "merge_method": merge_method},
    )
    return {"merged_at": merged_at, "sha": sha}
