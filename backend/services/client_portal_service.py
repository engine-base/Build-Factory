"""T-V3-B-20 / F-013: Client portal backend service.

Implements the data-access + domain logic for the 4 public client-portal
endpoints + 1 member-scoped resolve endpoint:

    GET  /api/client/workspaces/{token}                 (public)
    GET  /api/client/workspaces/{token}/spec            (public)
    GET  /api/client/comments/{thread_id}               (public)
    POST /api/client/comments                           (public, rate-limited)
    POST /api/comments/{id}/resolve                     (member)

The service is hermetic: it reads/writes the local DB record via
``db.async_db.aiosqlite`` (the same adapter used by ``pr_service``). Tokens
are stored in ``client_review_tokens`` and comments in
``client_portal_comments`` — both seeded by
``supabase/migrations/20260517000000_client_portal_tokens_comments.sql`` and
mirrored idempotently here for the SQLite test path.

Entities:
    - E-033 PullRequest (workspace linkage)
    - E-034 Delivery   (token expiry / spec_html_url)
    - E-030 Comment    (client_portal_comments table)

AC mapping (1:1 with audit MD Tier 2):
    AC-F1  STATE-DRIVEN: expired token -> 409 (TokenExpiredError)
    AC-F2  UNWANTED   : POST comments > 20/h/token -> 429
    AC-F3  EVENT-DRIVEN: GET workspace happy returns PublicWorkspaceView
    AC-F4  UNWANTED   : GET workspace without token -> 401
    AC-F5  EVENT-DRIVEN: GET spec happy returns spec_html_url
    AC-F6  UNWANTED   : GET spec without token -> 401
    AC-F7  EVENT-DRIVEN: GET comments happy returns PublicComment[]
    AC-F8  UNWANTED   : GET comments without token -> 401
    AC-F9  UNWANTED   : GET comments invalid thread_id -> 422
    AC-F10 EVENT-DRIVEN: POST comments happy returns comment_id
    AC-F11 UNWANTED   : POST comments without token -> 401
    AC-F12 UNWANTED   : POST comments invalid body -> 422
    AC-F13 UNWANTED   : POST comments rate-limited -> 429
    AC-F14 EVENT-DRIVEN: POST resolve happy returns resolved_at
    AC-F15 UNWANTED   : POST resolve without auth -> 401 (router-level)
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Constants & errors
# ─────────────────────────────────────────────────────────────────────────

MAX_COMMENT_BODY_LEN = 8000
MAX_ANCHOR_LEN = 500
MAX_AUTHOR_NAME_LEN = 200
RATE_LIMIT_PER_HOUR = 20  # POST /api/client/comments, per token
DEFAULT_TOKEN_TTL_DAYS = 14


class ClientPortalServiceError(ValueError):
    """Base for client portal service errors mapped to 4xx by router layer."""


class TokenInvalidError(ClientPortalServiceError):
    """Token missing / unknown -> 401."""


class TokenExpiredError(ClientPortalServiceError):
    """Token expired or revoked -> 409."""


class CommentValidationError(ClientPortalServiceError):
    """Comment validation failure -> 422."""


class RateLimitedError(ClientPortalServiceError):
    """POST /api/client/comments rate limit exceeded -> 429."""


class CommentNotFoundError(ClientPortalServiceError):
    """Resolve target not found -> 404."""


class CommentConflictError(ClientPortalServiceError):
    """Resolve called on already-resolved comment -> 409."""


class CommentForbiddenError(ClientPortalServiceError):
    """Caller is not a workspace member -> 403."""


# ─────────────────────────────────────────────────────────────────────────
# Schema bootstrap (idempotent — for SQLite test path)
# ─────────────────────────────────────────────────────────────────────────


async def _ensure_tables(db) -> None:
    """SQLite-friendly schema bootstrap mirroring the migration."""
    await db.execute(
        """CREATE TABLE IF NOT EXISTS client_review_tokens (
            id TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            workspace_id INTEGER NOT NULL,
            issued_by TEXT,
            issued_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            client_email TEXT,
            spec_html_url TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    await db.execute(
        """CREATE TABLE IF NOT EXISTS client_portal_comments (
            id TEXT PRIMARY KEY,
            workspace_id INTEGER NOT NULL,
            thread_id TEXT NOT NULL,
            token_id TEXT,
            author_name TEXT NOT NULL DEFAULT 'client',
            body TEXT NOT NULL,
            anchor TEXT,
            resolved_at TEXT,
            resolved_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    # workspaces is referenced by FK in production. We only need a stand-in for
    # SQLite tests, so callers seed it before invoking these helpers.


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _set_row_factory(db) -> None:
    """Best-effort row factory hook (untyped to avoid pyright struct drift).

    The ``aiosqlite`` connection object exposes ``row_factory`` but the typed
    shim in ``db.async_db`` (``_ConnectionWrapper``) declares it as ``None``.
    We assign via an untyped helper so callers can keep clean signatures.
    """
    try:
        db.row_factory = aiosqlite.Row
    except Exception:  # pragma: no cover - defensive
        pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    # Accept "...+00:00" and "...Z" forms.
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


async def _emit_audit(action: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(action, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover - audit emission must never break flow
        logger.warning("client_portal audit emit failed: %s -- %s", action, e)


async def _load_token(db, *, token: str) -> dict:
    """Resolve a token string to its row, raising 401/409 as appropriate.

    AC-F4 / AC-F6 / AC-F8 / AC-F11: 401 when token unknown.
    AC-F1: 409 when token expired / revoked.
    """
    if not isinstance(token, str) or not token.strip():
        raise TokenInvalidError("token must be non-empty string")
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        "SELECT * FROM client_review_tokens WHERE token = ?", (token,),
    )
    row = await cur.fetchone()
    if row is None:
        raise TokenInvalidError("token not found")
    d = _row_to_dict(row)
    if d.get("revoked_at"):
        raise TokenExpiredError("token revoked")
    expires_at = _parse_iso(d.get("expires_at"))
    if expires_at is not None and expires_at < _now():
        raise TokenExpiredError("token expired")
    return d


async def _load_workspace(db, *, workspace_id: int) -> dict:
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        "SELECT id, name, status FROM workspaces WHERE id = ?",
        (workspace_id,),
    )
    row = await cur.fetchone()
    if row is None:
        # Token row exists but workspace is gone — treat as expired.
        raise TokenExpiredError("workspace no longer exists")
    return _row_to_dict(row)


async def _require_member(
    db, *, workspace_id: int, user_id: str,
) -> str:
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        "SELECT role FROM workspace_members "
        "WHERE workspace_id = ? AND user_id = ?",
        (workspace_id, user_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise CommentForbiddenError(
            f"user_id={user_id} is not a member of workspace_id={workspace_id}",
        )
    return row["role"]


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


async def issue_token(
    *, workspace_id: int, issued_by: Optional[str] = None,
    client_email: Optional[str] = None, spec_html_url: Optional[str] = None,
    ttl_days: int = DEFAULT_TOKEN_TTL_DAYS,
) -> dict:
    """Mint a client-portal token (used by T-V3-B-21 / send-client + tests).

    Returns ``{"token": str, "expires_at": iso, "id": uuid}``.
    """
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise CommentValidationError("workspace_id must be positive int")
    if not isinstance(ttl_days, int) or ttl_days <= 0:
        raise CommentValidationError("ttl_days must be positive int")
    token = secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    expires_at = (_now() + timedelta(days=ttl_days)).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00",
    )
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await db.execute(
            "INSERT INTO client_review_tokens "
            "(id, token, workspace_id, issued_by, expires_at, "
            "client_email, spec_html_url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token_id, token, workspace_id, issued_by, expires_at,
             client_email, spec_html_url),
        )
        await db.commit()
    return {"id": token_id, "token": token, "expires_at": expires_at}


async def get_workspace_by_token(*, token: str) -> dict:
    """GET /api/client/workspaces/{token} backend.

    AC-F3: happy returns ``{"workspace": PublicWorkspaceView}``.
    AC-F4: 401 propagated from _load_token.
    AC-F1: 409 propagated from _load_token (expired).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        tok = await _load_token(db, token=token)
        ws = await _load_workspace(db, workspace_id=int(tok["workspace_id"]))
    return {
        "workspace": {
            "workspace_id": str(ws["id"]),
            "name": ws.get("name"),
            "status": ws.get("status"),
            "spec_url": tok.get("spec_html_url") or "",
            # Delivery linkage is populated by T-V3-B-21 (delivery service);
            # we expose what we have so the contract is stable.
            "delivery": None,
        },
    }


async def get_spec_by_token(*, token: str) -> dict:
    """GET /api/client/workspaces/{token}/spec backend.

    AC-F5: happy returns ``{"spec_html_url": str}``.
    AC-F6: 401 propagated from _load_token.
    AC-F1: 409 propagated from _load_token (expired).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        tok = await _load_token(db, token=token)
    spec_html_url = tok.get("spec_html_url") or ""
    return {"spec_html_url": spec_html_url}


async def get_comments_by_thread(*, thread_id: str, token: str) -> dict:
    """GET /api/client/comments/{thread_id} backend.

    AC-F7: happy returns ``{"comments": PublicComment[]}``.
    AC-F8: 401 if no token.
    AC-F9: 422 if thread_id is not a valid UUID.
    """
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise CommentValidationError("thread_id must be non-empty string")
    try:
        uuid.UUID(thread_id)
    except (ValueError, AttributeError, TypeError):
        raise CommentValidationError("thread_id must be a valid uuid")
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        tok = await _load_token(db, token=token)
        _set_row_factory(db)
        cur = await db.execute(
            "SELECT id, author_name, body, created_at, resolved_at "
            "FROM client_portal_comments "
            "WHERE thread_id = ? AND workspace_id = ? "
            "ORDER BY created_at ASC",
            (thread_id, int(tok["workspace_id"])),
        )
        rows = await cur.fetchall()
    comments = [
        {
            "id": r["id"],
            "author_name": r["author_name"],
            "body": r["body"],
            "created_at": r["created_at"],
            "resolved": bool(r["resolved_at"]),
        }
        for r in rows
    ]
    return {"comments": comments}


async def _count_recent_comments(
    db, *, token_id: str, since: datetime,
) -> int:
    """Count comments under ``token_id`` created at or after ``since``.

    created_at is stored as ISO-8601 in production (Postgres TIMESTAMPTZ -> text)
    and as SQLite ``datetime('now')`` (``YYYY-MM-DD HH:MM:SS``) in tests, so we
    fetch rows and parse them in Python to avoid string-comparison drift.
    """
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        "SELECT created_at FROM client_portal_comments WHERE token_id = ?",
        (token_id,),
    )
    rows = await cur.fetchall()
    n = 0
    for r in rows:
        created_at_raw = r["created_at"] if hasattr(r, "keys") else r[0]
        dt = _parse_iso(created_at_raw)
        if dt is None and isinstance(created_at_raw, str):
            # SQLite datetime('now') -> "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(
                    created_at_raw, "%Y-%m-%d %H:%M:%S",
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                dt = None
        if dt is not None and dt >= since:
            n += 1
    return n


async def post_comment(
    *, token: str, body: str, anchor: Optional[str] = None,
    thread_id: Optional[str] = None, author_name: Optional[str] = None,
) -> dict:
    """POST /api/client/comments backend.

    AC-F10: happy returns ``{"comment_id": uuid}``.
    AC-F11: 401 if no token.
    AC-F12: 422 on invalid body/anchor.
    AC-F13 / AC-F2: 429 if rate limit (20/h/token) exceeded.
    """
    if body is None or not isinstance(body, str):
        raise CommentValidationError("body must be non-empty string")
    body_stripped = body.strip()
    if not body_stripped:
        raise CommentValidationError("body must not be empty")
    if len(body) > MAX_COMMENT_BODY_LEN:
        raise CommentValidationError(
            f"body must be <= {MAX_COMMENT_BODY_LEN} chars",
        )
    if anchor is not None:
        if not isinstance(anchor, str):
            raise CommentValidationError("anchor must be string or null")
        if len(anchor) > MAX_ANCHOR_LEN:
            raise CommentValidationError(
                f"anchor must be <= {MAX_ANCHOR_LEN} chars",
            )
    if thread_id is not None:
        if not isinstance(thread_id, str):
            raise CommentValidationError("thread_id must be string or null")
        try:
            uuid.UUID(thread_id)
        except (ValueError, AttributeError, TypeError):
            raise CommentValidationError("thread_id must be a valid uuid")
    if author_name is not None:
        if not isinstance(author_name, str):
            raise CommentValidationError("author_name must be string or null")
        if not author_name.strip():
            raise CommentValidationError(
                "author_name must not be empty when provided",
            )
        if len(author_name) > MAX_AUTHOR_NAME_LEN:
            raise CommentValidationError(
                f"author_name must be <= {MAX_AUTHOR_NAME_LEN} chars",
            )

    comment_id = str(uuid.uuid4())
    effective_thread_id = thread_id or str(uuid.uuid4())
    one_hour_ago = _now() - timedelta(hours=1)

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        tok = await _load_token(db, token=token)
        token_id = str(tok["id"])
        # AC-F13 / AC-F2: rate limit 20/hour/token.
        recent = await _count_recent_comments(
            db, token_id=token_id, since=one_hour_ago,
        )
        if recent >= RATE_LIMIT_PER_HOUR:
            raise RateLimitedError(
                f"rate limit exceeded: {recent}/{RATE_LIMIT_PER_HOUR} per hour",
            )
        await db.execute(
            "INSERT INTO client_portal_comments "
            "(id, workspace_id, thread_id, token_id, author_name, body, anchor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                comment_id, int(tok["workspace_id"]), effective_thread_id,
                token_id, (author_name or "client"),
                body_stripped, anchor,
            ),
        )
        await db.commit()
    await _emit_audit(
        "client_comment_posted",
        user_id=None,
        detail={
            "comment_id": comment_id,
            "thread_id": effective_thread_id,
            "workspace_id": int(tok["workspace_id"]),
            "token_id": token_id,
            "body_len": len(body_stripped),
        },
    )
    return {"comment_id": comment_id, "thread_id": effective_thread_id}


async def resolve_comment(
    *, comment_id: str, actor_user_id: str,
) -> dict:
    """POST /api/comments/{id}/resolve backend (member auth).

    AC-F14: happy returns ``{"resolved_at": iso}``.
    AC-F15: 401 in router via require_user.
    409 when already resolved. 403 when actor is not workspace member.
    """
    if not isinstance(comment_id, str) or not comment_id.strip():
        raise CommentValidationError("comment_id must be non-empty string")
    try:
        uuid.UUID(comment_id)
    except (ValueError, AttributeError, TypeError):
        raise CommentValidationError("comment_id must be a valid uuid")
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        _set_row_factory(db)
        cur = await db.execute(
            "SELECT * FROM client_portal_comments WHERE id = ?",
            (comment_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise CommentNotFoundError(
                f"comment not found: id={comment_id}",
            )
        d = _row_to_dict(row)
        if d.get("resolved_at"):
            raise CommentConflictError("comment already resolved")
        await _require_member(
            db, workspace_id=int(d["workspace_id"]),
            user_id=actor_user_id,
        )
        resolved_at = _now_iso()
        await db.execute(
            "UPDATE client_portal_comments "
            "SET resolved_at = ?, resolved_by = ? WHERE id = ?",
            (resolved_at, actor_user_id, comment_id),
        )
        await db.commit()
    await _emit_audit(
        "client_comment_resolved",
        user_id=actor_user_id,
        detail={"comment_id": comment_id, "resolved_at": resolved_at},
    )
    return {"resolved_at": resolved_at}
