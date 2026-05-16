"""T-V3-B-30 / F-028: Email delivery service.

Two responsibilities:
  1. `list_templates(workspace_id)` — return active EmailTemplate rows scoped to
     workspace (workspace_id IS NULL = global templates always included).
  2. `enqueue_test_send(workspace_id, template_id, recipient, ...)` —
     enqueue an email_deliveries row with status='queued' and a rate-limit guard
     (10/hour/workspace, in-memory token-bucket — replaced by Redis in Phase 1.5).

Provider abstraction (Resend / SES / SMTP) is a stub here; this PR implements
the *queueing* layer only (per the ticket scope). The actual provider call is
performed by a downstream worker (out of scope for T-V3-B-30).

AC mapping (features.json#F-028 ears_ac_seed + ticket functional AC):
  AC-F1 / AC-F8 UNWANTED  : 10/hour/workspace 超過 → RateLimitedError (HTTP 429)
  AC-F2          EVENT    : list_templates() → list[EmailTemplate]
  AC-F5          EVENT    : enqueue_test_send() → EmailDelivery with delivery_id
                           (queued_at = now)
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# Recipient validation — must catch "obviously invalid" inputs but not the
# RFC 5321 long-tail (production uses provider-side validation).
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class EmailServiceError(Exception):
    """Base class for email service errors."""


class TemplateNotFoundError(EmailServiceError):
    """Requested template_id does not exist."""


class InvalidRecipientError(EmailServiceError):
    """Recipient address failed format validation."""


class RateLimitedError(EmailServiceError):
    """Workspace has exceeded the 10/hour test-send rate limit."""

    def __init__(self, limit: int, window_seconds: int, retry_after: int) -> None:
        super().__init__(
            f"rate limit exceeded ({limit}/{window_seconds}s); retry after {retry_after}s"
        )
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after = retry_after


@dataclass(frozen=True)
class EmailTemplate:
    id: str
    workspace_id: Optional[int]
    name: str
    locale: str
    subject: str
    body_html: Optional[str]
    body_text: Optional[str]
    variables: list[str]
    version: int
    is_active: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "locale": self.locale,
            "subject": self.subject,
            "body_html": self.body_html,
            "body_text": self.body_text,
            "variables": list(self.variables),
            "version": self.version,
            "is_active": self.is_active,
        }


@dataclass
class EmailDelivery:
    id: str
    workspace_id: Optional[int]
    template_id: str
    recipient: str
    status: str
    queued_at: float  # unix epoch seconds
    provider: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from datetime import datetime, timezone
        return {
            "delivery_id": self.id,
            "workspace_id": self.workspace_id,
            "template_id": self.template_id,
            "recipient": self.recipient,
            "status": self.status,
            "queued_at": datetime.fromtimestamp(self.queued_at, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            "provider": self.provider,
            "detail": dict(self.detail),
        }


# ──────────────────────────────────────────────────────────────────
# In-memory store (Phase 1A — replaced by Supabase persistence later)
# ──────────────────────────────────────────────────────────────────
_LOCK = threading.RLock()
_TEMPLATES: dict[str, EmailTemplate] = {}
_DELIVERIES: dict[str, EmailDelivery] = {}
# rate-limit bucket: workspace_id (or "global") → list of unix-epoch send times
_RATE_BUCKETS: dict[str, list[float]] = {}


def _seed_default_templates() -> None:
    """Idempotent seed of the 5 standard templates (mirrors migration seed)."""
    defaults = [
        ("signup_verify", "ja",
         "Build-Factory にようこそ — メール認証",
         "認証リンク: {{verify_url}}",
         ["name", "verify_url"]),
        ("password_reset", "ja",
         "Build-Factory パスワード再設定",
         "再設定リンク: {{reset_url}}",
         ["name", "reset_url"]),
        ("invitation", "ja",
         "{{inviter_name}} さんから Build-Factory ワークスペース招待",
         "招待リンク: {{accept_url}}",
         ["inviter_name", "workspace_name", "accept_url"]),
        ("task_notification", "ja",
         "[Build-Factory] {{task_title}} に動きがあります",
         "状態: {{status}} — {{task_url}}",
         ["task_title", "status", "task_url"]),
        ("weekly_summary", "ja",
         "[Build-Factory] 今週のサマリー ({{week_range}})",
         "完了 {{done_count}} / 進行中 {{wip_count}} / ブロック {{blocked_count}}",
         ["week_range", "done_count", "wip_count", "blocked_count", "dashboard_url"]),
    ]
    for name, locale, subject, body_text, variables in defaults:
        # deterministic uuid5 keyed on (name, locale) so re-seed yields same id
        tid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"email-template:{name}:{locale}"))
        if tid in _TEMPLATES:
            continue
        _TEMPLATES[tid] = EmailTemplate(
            id=tid,
            workspace_id=None,
            name=name,
            locale=locale,
            subject=subject,
            body_html=None,
            body_text=body_text,
            variables=variables,
            version=1,
            is_active=True,
        )


def reset_store() -> None:
    """Clear in-memory store. Test-only helper."""
    with _LOCK:
        _TEMPLATES.clear()
        _DELIVERIES.clear()
        _RATE_BUCKETS.clear()
        _seed_default_templates()


# bootstrap on import
_seed_default_templates()


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────
def list_templates(workspace_id: Optional[int]) -> list[dict[str, Any]]:
    """Return active templates accessible to the workspace.

    Global templates (workspace_id IS NULL) are always returned; workspace
    overrides (workspace_id == given) are appended on top.
    AC-F2: EVENT-DRIVEN → 2xx with `templates` array.
    """
    with _LOCK:
        rows = [
            t.to_dict()
            for t in _TEMPLATES.values()
            if t.is_active and (t.workspace_id is None or t.workspace_id == workspace_id)
        ]
    rows.sort(key=lambda r: (r["workspace_id"] is not None, r["name"], r["locale"]))
    return rows


RATE_LIMIT_COUNT = 10
RATE_LIMIT_WINDOW_SECONDS = 60 * 60  # 1 hour


def _check_and_record_rate_limit(workspace_id: Optional[int]) -> None:
    """Token-bucket style rate limit. Raises RateLimitedError on overflow.

    AC-F1 / AC-F8 UNWANTED: >10/hour/workspace → 429.
    """
    # Allow tests / dev to override via env (e.g. faster test runs).
    limit = int(os.environ.get("EMAIL_TEST_SEND_RATE_LIMIT", str(RATE_LIMIT_COUNT)))
    window = int(
        os.environ.get("EMAIL_TEST_SEND_RATE_WINDOW", str(RATE_LIMIT_WINDOW_SECONDS))
    )
    if limit <= 0:
        return  # disabled
    key = str(workspace_id) if workspace_id is not None else "global"
    now = time.time()
    cutoff = now - window
    with _LOCK:
        bucket = _RATE_BUCKETS.setdefault(key, [])
        # purge expired entries
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= limit:
            oldest = min(bucket)
            retry_after = max(1, int(oldest + window - now))
            raise RateLimitedError(
                limit=limit, window_seconds=window, retry_after=retry_after
            )
        bucket.append(now)


def enqueue_test_send(
    workspace_id: Optional[int],
    template_id: str,
    recipient: str,
    *,
    provider: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Enqueue an email send request for delivery.

    AC-F5 EVENT-DRIVEN: returns `{delivery_id, queued_at}` (mapped to 201).
    Raises:
      - InvalidRecipientError (→ 422)
      - TemplateNotFoundError (→ 404)
      - RateLimitedError (→ 429)
    """
    if not recipient or not _EMAIL_RE.match(recipient):
        raise InvalidRecipientError(f"invalid recipient address: {recipient!r}")
    if not template_id:
        raise InvalidRecipientError("template_id must not be empty")
    with _LOCK:
        tpl = _TEMPLATES.get(template_id)
    if tpl is None or not tpl.is_active:
        raise TemplateNotFoundError(f"template_id {template_id!r} not found")

    # Rate limit check happens AFTER input validation so 422 wins on bad input.
    _check_and_record_rate_limit(workspace_id)

    delivery = EmailDelivery(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        template_id=template_id,
        recipient=recipient,
        status="queued",
        queued_at=time.time(),
        provider=provider,
        detail=dict(detail or {}),
    )
    with _LOCK:
        _DELIVERIES[delivery.id] = delivery
    return delivery.to_dict()


def get_delivery(delivery_id: str) -> Optional[dict[str, Any]]:
    """Test / introspection helper (not exposed by router in this task)."""
    with _LOCK:
        d = _DELIVERIES.get(delivery_id)
    return d.to_dict() if d else None
