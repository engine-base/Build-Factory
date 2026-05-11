"""T-011-03: エスカレ通知 (Slack DM + UI バッジ).

通知経路:
  1. Slack DM (slack_client.send_rich_message を REUSE; 未接続なら skip)
  2. in-memory UI バッジ queue (user 別) — 未読のみ list_badges で取得

公開 API:
  - escalate(target_user_id, message, *, severity, badge_label, slack_dm, slack_channel)
  - list_badges(user_id, *, include_read=False) -> list[dict]
  - mark_badge_read(badge_id, *, user_id) -> bool
  - clear_badges_for_user(user_id) -> int
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class EscalationError(RuntimeError):
    pass


VALID_SEVERITIES = ("info", "warning", "critical", "redline")
MAX_BADGES_PER_USER = 100
MAX_BADGES_TOTAL = 50000


@dataclass
class Badge:
    id: int
    user_id: str
    severity: str
    label: str
    message: str
    slack_delivered: bool = False
    read_at: Optional[float] = None
    created_at: float = 0.0
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "severity": self.severity,
            "label": self.label,
            "message": self.message,
            "slack_delivered": self.slack_delivered,
            "read_at": self.read_at,
            "created_at": self.created_at,
            "detail": dict(self.detail),
            "is_read": self.read_at is not None,
        }


# Slack 送信用 callable (test で差し替え可能)
SlackSendFn = Callable[[str, Optional[str]], Awaitable[bool]]


class EscalationStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._badges: dict[int, Badge] = {}
        self._by_user: dict[str, list[int]] = {}
        self._next_id = 1
        self._total = 0

    def _validate_user(self, user_id: str) -> str:
        if not isinstance(user_id, str) or not user_id.strip():
            raise EscalationError("user_id must not be empty")
        if len(user_id) > 200:
            raise EscalationError("user_id must be <= 200 chars")
        return user_id.strip()

    def add_badge(
        self,
        *,
        user_id: str,
        severity: str,
        label: str,
        message: str,
        slack_delivered: bool,
        detail: Optional[dict] = None,
    ) -> Badge:
        u = self._validate_user(user_id)
        if severity not in VALID_SEVERITIES:
            raise EscalationError(
                f"severity must be one of {VALID_SEVERITIES}, got {severity!r}"
            )
        if not isinstance(label, str) or not label.strip():
            raise EscalationError("label must not be empty")
        if len(label) > 200:
            raise EscalationError("label must be <= 200 chars")
        if not isinstance(message, str) or not message.strip():
            raise EscalationError("message must not be empty")
        if len(message) > 4000:
            raise EscalationError("message must be <= 4000 chars")
        with self._lock:
            user_list = self._by_user.setdefault(u, [])
            if len(user_list) >= MAX_BADGES_PER_USER:
                raise EscalationError(
                    f"too many badges for user (max {MAX_BADGES_PER_USER})"
                )
            if self._total >= MAX_BADGES_TOTAL:
                raise EscalationError(
                    f"badges store full (max {MAX_BADGES_TOTAL})"
                )
            badge = Badge(
                id=self._next_id,
                user_id=u,
                severity=severity,
                label=label.strip(),
                message=message.strip(),
                slack_delivered=slack_delivered,
                created_at=time.time(),
                detail=dict(detail or {}),
            )
            self._badges[self._next_id] = badge
            user_list.append(self._next_id)
            self._next_id += 1
            self._total += 1
            return badge

    def list_for_user(
        self, user_id: str, *, include_read: bool = False,
    ) -> list[Badge]:
        u = self._validate_user(user_id)
        with self._lock:
            ids = list(self._by_user.get(u, []))
        result: list[Badge] = []
        for bid in ids:
            b = self._badges.get(bid)
            if b is None:
                continue
            if not include_read and b.read_at is not None:
                continue
            result.append(b)
        # severity の高い順 → 新しい順
        sev_rank = {s: i for i, s in enumerate(VALID_SEVERITIES)}
        result.sort(key=lambda b: (-sev_rank[b.severity], -b.created_at))
        return result

    def mark_read(self, badge_id: int, *, user_id: str) -> bool:
        u = self._validate_user(user_id)
        if not isinstance(badge_id, int) or badge_id <= 0:
            raise EscalationError("badge_id must be > 0")
        with self._lock:
            b = self._badges.get(badge_id)
            if b is None:
                return False
            if b.user_id != u:
                # 他人の badge を勝手に既読化できない (AC-4 UNWANTED)
                raise EscalationError("badge does not belong to this user")
            if b.read_at is not None:
                return False  # already read
            b.read_at = time.time()
            return True

    def clear_user(self, user_id: str) -> int:
        u = self._validate_user(user_id)
        with self._lock:
            ids = self._by_user.pop(u, [])
            n = 0
            for bid in ids:
                if self._badges.pop(bid, None) is not None:
                    n += 1
                    self._total -= 1
            return n

    def get_badge(self, badge_id: int) -> Optional[Badge]:
        with self._lock:
            return self._badges.get(badge_id)


# Module-level singleton
_store: Optional[EscalationStore] = None


def get_store() -> EscalationStore:
    global _store
    if _store is None:
        _store = EscalationStore()
    return _store


def reset_store() -> None:
    global _store
    _store = EscalationStore()


# ──────────────────────────────────────────────────────────────────────────
# 高レベル API
# ──────────────────────────────────────────────────────────────────────────


async def _default_slack_send(message: str, channel: Optional[str]) -> bool:
    """default Slack 送信 (T-014-01 slack_client REUSE; 未接続なら False)."""
    try:
        from integrations import slack_client as sc
        if not sc._slack_enabled or sc._app is None:
            return False
        if channel:
            await sc._app.client.chat_postMessage(channel=channel, text=message[:2900])
        else:
            await sc.send_rich_message(message)
        return True
    except Exception as e:
        logger.warning("default slack send failed: %s", e)
        return False


async def escalate(
    target_user_id: str,
    message: str,
    *,
    severity: str = "warning",
    badge_label: str = "Escalation",
    slack_dm: bool = True,
    slack_channel: Optional[str] = None,
    detail: Optional[dict] = None,
    slack_send_fn: Optional[SlackSendFn] = None,
) -> dict:
    """Slack DM + UI バッジに通知を流す."""
    if not isinstance(target_user_id, str) or not target_user_id.strip():
        raise EscalationError("target_user_id must not be empty")
    if severity not in VALID_SEVERITIES:
        raise EscalationError(
            f"severity must be one of {VALID_SEVERITIES}, got {severity!r}"
        )

    delivered = False
    if slack_dm:
        send_fn = slack_send_fn or _default_slack_send
        # severity が critical/redline なら強い prefix
        prefix = {
            "redline": "[REDLINE] ",
            "critical": "[CRITICAL] ",
            "warning": "[WARN] ",
            "info": "[INFO] ",
        }.get(severity, "")
        delivered = await send_fn(f"{prefix}{badge_label}\n{message}", slack_channel)

    badge = get_store().add_badge(
        user_id=target_user_id,
        severity=severity,
        label=badge_label,
        message=message,
        slack_delivered=delivered,
        detail=detail,
    )
    return {
        "badge_id": badge.id,
        "user_id": badge.user_id,
        "severity": badge.severity,
        "label": badge.label,
        "slack_delivered": delivered,
    }
