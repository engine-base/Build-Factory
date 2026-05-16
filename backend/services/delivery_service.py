"""T-V3-B-21 / F-013: Delivery backend service (delivery pack / approve / send-client).

Implements the data-access + domain logic for the 3 workspace-scoped delivery
endpoints:

    GET  /api/workspaces/{id}/delivery               (member)
    POST /api/workspaces/{id}/delivery/approve       (workspace_admin)
    POST /api/workspaces/{id}/delivery/send-client   (workspace_admin)

Entities:
    - E-034 Delivery       (workspace_deliveries table, this service)
    - E-033 PullRequest    (workspace linkage; PR review feeds delivery)
    - E-030 Comment        (handled by client_portal_service; tokens linkage)

State machine:
    draft  ── approve ──>  approved  ── send-client ──> sent  ── (client review) ──> accepted

The service is hermetic: it reads/writes the local DB via ``db.async_db.aiosqlite``
(same adapter as ``pr_service`` and ``client_portal_service``). Production lives
on ``supabase/migrations/20260518000000_workspace_deliveries.sql`` and is
mirrored idempotently here for the SQLite test path.

send-client delegates to ``client_portal_service.issue_token`` (T-V3-B-20)
which mints a public review token + persists into ``client_review_tokens``.
The actual email send is delegated to a pluggable
``email_send_callable`` keyword (defaults to a no-op stub recording the
intent in audit logs) so unit tests can run hermetically.

AC mapping (1:1 with audit MD docs/audit/2026-05-16_v3/T-V3-B-21.md Tier 2):
    AC-F1 EVENT-DRIVEN : send-client mints public token + emails client
    AC-F2 EVENT-DRIVEN : GET delivery happy returns {delivery: Delivery}
    AC-F3 UNWANTED     : GET delivery without auth -> 401 (router-level via require_user)
    AC-F4 UNWANTED     : GET delivery invalid id -> 422 (Pydantic + service validation)
    AC-F5 EVENT-DRIVEN : approve happy returns {approved_at}
    AC-F6 UNWANTED     : approve without auth -> 401 (router-level)
    AC-F7 EVENT-DRIVEN : send-client happy returns {sent_at, delivery_token}
    AC-F8 UNWANTED     : send-client without auth -> 401 (router-level)
    AC-F9 UNWANTED     : send-client invalid body (email / ttl) -> 422 (Pydantic)
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

VALID_STATUSES: tuple[str, ...] = ("draft", "approved", "sent", "accepted")
STATUS_DRAFT = "draft"
STATUS_APPROVED = "approved"
STATUS_SENT = "sent"
STATUS_ACCEPTED = "accepted"


class DeliveryServiceError(ValueError):
    """Base for delivery service errors mapped to 4xx by router layer."""


class DeliveryNotFoundError(DeliveryServiceError):
    """Delivery row not found for workspace -> 404."""


class DeliveryForbiddenError(DeliveryServiceError):
    """Caller is not a workspace member / admin -> 403."""


class DeliveryConflictError(DeliveryServiceError):
    """Delivery in wrong state for this action (e.g. approve already approved,
    send-client before approve) -> 409.
    """


class DeliveryValidationError(DeliveryServiceError):
    """Invalid input -> 422."""


# Type alias for the (pluggable) email send callable. Returns nothing on
# success; raises any Exception on failure (router maps to 500).
EmailSendCallable = Callable[..., Awaitable[None]]


# ─────────────────────────────────────────────────────────────────────────
# Schema bootstrap (idempotent — for SQLite test path)
# ─────────────────────────────────────────────────────────────────────────


async def _ensure_tables(db) -> None:
    """SQLite-friendly schema bootstrap mirroring the production migration."""
    await db.execute(
        """CREATE TABLE IF NOT EXISTS workspace_deliveries (
            id TEXT PRIMARY KEY,
            workspace_id INTEGER NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            approved_at TEXT,
            approved_by TEXT,
            sent_at TEXT,
            sent_by TEXT,
            accepted_at TEXT,
            client_email TEXT,
            artifact_urls TEXT NOT NULL DEFAULT '[]',
            delivery_token_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _set_row_factory(db) -> None:
    try:
        db.row_factory = aiosqlite.Row
    except Exception:  # pragma: no cover - defensive
        pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _row_to_dict(row: Any) -> dict:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return dict(row)


async def _emit_audit(action: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(action, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover - audit must never break flow
        logger.warning("delivery audit emit failed: %s -- %s", action, e)


def _parse_workspace_id(workspace_id: Any) -> int:
    """Coerce path id (int or uuid-style) to the workspace_id integer.

    The OpenAPI spec models id as uuid, but the local SQLite test schema (and
    the existing workspaces table) is keyed on INTEGER. Accept both forms.
    """
    if isinstance(workspace_id, int):
        if workspace_id <= 0:
            raise DeliveryValidationError("workspace_id must be positive int")
        return workspace_id
    if isinstance(workspace_id, str):
        s = workspace_id.strip()
        if not s:
            raise DeliveryValidationError("workspace_id must not be empty")
        # Allow plain int strings ("1") or uuid (we map uuid via int fallback).
        try:
            n = int(s)
            if n <= 0:
                raise DeliveryValidationError("workspace_id must be positive")
            return n
        except ValueError:
            # uuid form: not supported by SQLite test schema. The Pydantic
            # path-parameter validator will normally enforce; we surface 422.
            raise DeliveryValidationError(
                "workspace_id must be a positive integer in this schema",
            )
    raise DeliveryValidationError("workspace_id must be int or str")


async def _require_member(
    db, *, workspace_id: int, user_id: str,
    require_admin: bool = False,
) -> str:
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        "SELECT role FROM workspace_members "
        "WHERE workspace_id = ? AND user_id = ?",
        (workspace_id, user_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise DeliveryForbiddenError(
            f"user_id={user_id} is not a member of workspace_id={workspace_id}",
        )
    role = row["role"]
    if require_admin and role not in ("admin", "owner"):
        raise DeliveryForbiddenError(
            f"workspace_admin required (got role={role})",
        )
    return role


async def _load_delivery(db, *, workspace_id: int) -> dict:
    """Read the (singleton) delivery row for workspace_id. 404 if missing."""
    db.row_factory = aiosqlite.Row
    cur = await db.execute(
        "SELECT * FROM workspace_deliveries WHERE workspace_id = ?",
        (workspace_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise DeliveryNotFoundError(
            f"delivery not found for workspace_id={workspace_id}",
        )
    return _row_to_dict(row)


def _serialise_delivery(row: dict) -> dict:
    """Map a DB row to the Delivery wire shape (openapi#components.Delivery)."""
    import json as _json
    artifact_urls_raw = row.get("artifact_urls") or "[]"
    try:
        artifact_urls = _json.loads(artifact_urls_raw)
        if not isinstance(artifact_urls, list):
            artifact_urls = []
    except (TypeError, ValueError):
        artifact_urls = []
    return {
        "id": row["id"],
        "workspace_id": str(row["workspace_id"]),
        "status": row.get("status") or STATUS_DRAFT,
        "approved_at": row.get("approved_at"),
        "sent_at": row.get("sent_at"),
        "artifact_urls": artifact_urls,
    }


async def _ensure_delivery_exists(
    db, *, workspace_id: int,
) -> dict:
    """Get-or-create the delivery row for ``workspace_id`` (idempotent).

    Used by approve / send-client to lazily materialise the pack on first
    write, and by GET when the workspace has been bootstrapped but no
    explicit "create delivery" call has been made.
    """
    try:
        return await _load_delivery(db, workspace_id=workspace_id)
    except DeliveryNotFoundError:
        new_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO workspace_deliveries "
            "(id, workspace_id, status, artifact_urls) "
            "VALUES (?, ?, 'draft', '[]')",
            (new_id, workspace_id),
        )
        await db.commit()
        return await _load_delivery(db, workspace_id=workspace_id)


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


async def get_delivery(
    *, workspace_id: Any, actor_user_id: str,
) -> dict:
    """GET /api/workspaces/{id}/delivery backend.

    AC-F2 happy returns ``{"delivery": Delivery}``. AC-F3 401 is enforced by
    the router via ``require_user``. AC-F4 422 surfaces on
    DeliveryValidationError (path normalisation). 403 if caller is not a
    workspace member. 404 if workspace exists but delivery row never created
    (and auto-bootstrap is disabled — here we auto-bootstrap on first read).
    """
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise DeliveryValidationError("actor_user_id must be non-empty string")
    ws_id = _parse_workspace_id(workspace_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await _require_member(db, workspace_id=ws_id, user_id=actor_user_id)
        row = await _ensure_delivery_exists(db, workspace_id=ws_id)
    await _emit_audit(
        "delivery_read",
        user_id=actor_user_id,
        detail={"workspace_id": ws_id, "delivery_id": row["id"]},
    )
    return {"delivery": _serialise_delivery(row)}


async def approve_delivery(
    *, workspace_id: Any, actor_user_id: str,
) -> dict:
    """POST /api/workspaces/{id}/delivery/approve backend (workspace_admin).

    AC-F5 happy returns ``{"approved_at": iso}``. AC-F6 401 is enforced by
    the router via ``require_user``. 403 if caller is not a workspace
    admin (workspace_admin_rw policy). 409 if delivery already approved /
    sent / accepted (state machine).
    """
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise DeliveryValidationError("actor_user_id must be non-empty string")
    ws_id = _parse_workspace_id(workspace_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await _require_member(
            db, workspace_id=ws_id, user_id=actor_user_id,
            require_admin=True,
        )
        row = await _ensure_delivery_exists(db, workspace_id=ws_id)
        if row["status"] != STATUS_DRAFT:
            raise DeliveryConflictError(
                f"delivery status={row['status']} is not draft "
                f"(cannot approve)",
            )
        approved_at = _now_iso()
        await db.execute(
            "UPDATE workspace_deliveries "
            "SET status = ?, approved_at = ?, approved_by = ?, "
            "    updated_at = ? "
            "WHERE workspace_id = ?",
            (STATUS_APPROVED, approved_at, actor_user_id, approved_at, ws_id),
        )
        await db.commit()
    await _emit_audit(
        "delivery_approved",
        user_id=actor_user_id,
        detail={
            "workspace_id": ws_id, "delivery_id": row["id"],
            "approved_at": approved_at,
        },
    )
    return {"approved_at": approved_at}


async def _default_email_send(
    *, client_email: str, token: str, workspace_id: int,
) -> None:
    """No-op stub used in dev / tests.

    A real implementation would integrate with
    ``services.email_delivery_service`` (T-V3-B-?? email_templates_deliveries).
    """
    logger.info(
        "delivery.email.stub: would email %s with token=%s (workspace_id=%s)",
        client_email, token[:8] + "...", workspace_id,
    )


async def send_client(
    *, workspace_id: Any, actor_user_id: str,
    client_email: str,
    ttl_days: Optional[int] = None,
    email_send_callable: Optional[EmailSendCallable] = None,
    issue_token_callable: Optional[Callable[..., Awaitable[dict]]] = None,
) -> dict:
    """POST /api/workspaces/{id}/delivery/send-client backend (workspace_admin).

    AC-F1 / AC-F7: happy mints a public token via
    ``client_portal_service.issue_token`` + emails the client + returns
    ``{"sent_at": iso, "delivery_token": str}``.
    AC-F8 401 enforced by router. AC-F9 422 enforced by Pydantic +
    DeliveryValidationError below. 403 non-admin. 409 if not approved yet.
    """
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise DeliveryValidationError("actor_user_id must be non-empty string")
    if not isinstance(client_email, str) or "@" not in client_email:
        raise DeliveryValidationError("client_email must contain @")
    if ttl_days is not None:
        if not isinstance(ttl_days, int) or ttl_days <= 0:
            raise DeliveryValidationError("ttl_days must be positive int")
        if ttl_days > 365:
            raise DeliveryValidationError("ttl_days must be <= 365")
    ws_id = _parse_workspace_id(workspace_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await _require_member(
            db, workspace_id=ws_id, user_id=actor_user_id,
            require_admin=True,
        )
        row = await _ensure_delivery_exists(db, workspace_id=ws_id)
        if row["status"] not in (STATUS_APPROVED, STATUS_SENT):
            raise DeliveryConflictError(
                f"delivery status={row['status']} is not approved "
                f"(cannot send-client)",
            )

    # Mint the public token (uses client_portal_service from T-V3-B-20).
    if issue_token_callable is None:
        from services import client_portal_service as cps
        issue_token_callable = cps.issue_token  # type: ignore[assignment]

    token_kwargs: dict[str, Any] = {
        "workspace_id": ws_id,
        "issued_by": actor_user_id,
        "client_email": client_email,
    }
    if ttl_days is not None:
        token_kwargs["ttl_days"] = ttl_days
    assert issue_token_callable is not None  # for type checker
    token_row = await issue_token_callable(**token_kwargs)
    if not isinstance(token_row, dict) or "token" not in token_row:
        raise DeliveryServiceError(
            "issue_token returned malformed response",
        )
    token_value = str(token_row["token"])
    token_id = str(token_row.get("id") or "")

    # Email the client (delegated; default is a no-op stub).
    send = email_send_callable or _default_email_send
    try:
        await send(
            client_email=client_email,
            token=token_value,
            workspace_id=ws_id,
        )
    except Exception as e:
        # Audit the failure but bubble up so the router can map to 500.
        await _emit_audit(
            "delivery_send_failed",
            user_id=actor_user_id,
            detail={
                "workspace_id": ws_id,
                "delivery_id": row["id"],
                "error": str(e),
            },
        )
        raise

    sent_at = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_tables(db)
        await db.execute(
            "UPDATE workspace_deliveries "
            "SET status = ?, sent_at = ?, sent_by = ?, "
            "    client_email = ?, delivery_token_id = ?, updated_at = ? "
            "WHERE workspace_id = ?",
            (STATUS_SENT, sent_at, actor_user_id, client_email,
             token_id or None, sent_at, ws_id),
        )
        await db.commit()

    await _emit_audit(
        "delivery_sent_client",
        user_id=actor_user_id,
        detail={
            "workspace_id": ws_id,
            "delivery_id": row["id"],
            "client_email": client_email,
            "token_id": token_id,
            "sent_at": sent_at,
        },
    )
    return {"sent_at": sent_at, "delivery_token": token_value}
