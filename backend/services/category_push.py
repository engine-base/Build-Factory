"""T-014-02: カテゴリ別 push (red_line/pr/progress/invite/system) + ダイジェスト.

5 カテゴリの通知を Slack (channel) + UI に流す.
ダイジェスト機能: 一定時間内の同カテゴリ通知をまとめて 1 件として送信.

カテゴリ:
  - red_line : 致命的違反 (本番事故・データ消失等)、 即時通知
  - pr       : Pull Request 関連
  - progress : タスク進捗・完了
  - invite   : ワークスペース招待
  - system   : システムアラート

公開 API:
  - push_message(category, message, *, channel, immediate, slack_send_fn)
  - get_digest(category) -> list[dict]
  - flush_digest(category, *, slack_send_fn) -> int
  - flush_all_digests(*, slack_send_fn) -> dict[category, count]
  - configure(category, *, channel, digest_window_seconds)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class CategoryPushError(RuntimeError):
    pass


# 5 カテゴリ
VALID_CATEGORIES = ("red_line", "pr", "progress", "invite", "system")
# red_line のみ default で即時送信 (digest 不可)
IMMEDIATE_ONLY = frozenset({"red_line"})

DEFAULT_DIGEST_WINDOW_SEC = 300  # 5 min
MAX_DIGEST_WINDOW_SEC = 24 * 3600
MAX_PENDING_PER_CATEGORY = 1000
MAX_MESSAGE_LEN = 4000
MAX_CHANNEL_LEN = 200


@dataclass
class PushMessage:
    id: int
    category: str
    message: str
    channel: Optional[str]
    created_at: float
    sent_at: Optional[float] = None
    delivered: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "message": self.message,
            "channel": self.channel,
            "created_at": self.created_at,
            "sent_at": self.sent_at,
            "delivered": self.delivered,
        }


@dataclass
class CategoryConfig:
    category: str
    channel: Optional[str] = None
    digest_window_seconds: float = DEFAULT_DIGEST_WINDOW_SEC
    last_flush_at: float = 0.0


# Slack 送信用 callable
SlackSendFn = Callable[[str, Optional[str]], Awaitable[bool]]


class CategoryPushStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._next_id = 1
        # category → list[PushMessage] (queued for digest)
        self._pending: dict[str, list[PushMessage]] = {c: [] for c in VALID_CATEGORIES}
        # category → list[PushMessage] (immediate / flushed)
        self._delivered: dict[str, list[PushMessage]] = {c: [] for c in VALID_CATEGORIES}
        self._configs: dict[str, CategoryConfig] = {
            c: CategoryConfig(category=c) for c in VALID_CATEGORIES
        }

    def _validate_category(self, category: str) -> str:
        if not isinstance(category, str) or category not in VALID_CATEGORIES:
            raise CategoryPushError(
                f"category must be one of {VALID_CATEGORIES}, got {category!r}"
            )
        return category

    def configure(
        self,
        category: str,
        *,
        channel: Optional[str] = None,
        digest_window_seconds: Optional[float] = None,
    ) -> CategoryConfig:
        c = self._validate_category(category)
        if channel is not None:
            if not isinstance(channel, str) or not channel.strip():
                raise CategoryPushError("channel must not be empty when provided")
            if len(channel) > MAX_CHANNEL_LEN:
                raise CategoryPushError(
                    f"channel must be <= {MAX_CHANNEL_LEN} chars"
                )
        if digest_window_seconds is not None:
            if not isinstance(digest_window_seconds, (int, float)) or digest_window_seconds < 0:
                raise CategoryPushError(
                    "digest_window_seconds must be >= 0"
                )
            if digest_window_seconds > MAX_DIGEST_WINDOW_SEC:
                raise CategoryPushError(
                    f"digest_window_seconds must be <= {MAX_DIGEST_WINDOW_SEC}"
                )
        with self._lock:
            cfg = self._configs[c]
            if channel is not None:
                cfg.channel = channel.strip()
            if digest_window_seconds is not None:
                cfg.digest_window_seconds = float(digest_window_seconds)
        return cfg

    def enqueue(
        self,
        category: str,
        message: str,
        *,
        channel: Optional[str] = None,
        immediate: bool = False,
    ) -> PushMessage:
        c = self._validate_category(category)
        if not isinstance(message, str) or not message.strip():
            raise CategoryPushError("message must not be empty")
        if len(message) > MAX_MESSAGE_LEN:
            raise CategoryPushError(f"message must be <= {MAX_MESSAGE_LEN} chars")
        if channel is not None:
            if not isinstance(channel, str) or not channel.strip():
                raise CategoryPushError(
                    "channel must not be empty when provided"
                )
            if len(channel) > MAX_CHANNEL_LEN:
                raise CategoryPushError(
                    f"channel must be <= {MAX_CHANNEL_LEN} chars"
                )

        with self._lock:
            cfg = self._configs[c]
            resolved_channel = (channel.strip() if channel else None) or cfg.channel
            pm = PushMessage(
                id=self._next_id,
                category=c,
                message=message.strip(),
                channel=resolved_channel,
                created_at=time.time(),
            )
            self._next_id += 1
            # red_line は強制 immediate
            if c in IMMEDIATE_ONLY or immediate or cfg.digest_window_seconds == 0:
                # 後で send_fn で送信されるため queue にも入れない
                return pm
            if len(self._pending[c]) >= MAX_PENDING_PER_CATEGORY:
                raise CategoryPushError(
                    f"pending queue full for {c} (max {MAX_PENDING_PER_CATEGORY})"
                )
            self._pending[c].append(pm)
            return pm

    def get_pending(self, category: str) -> list[PushMessage]:
        c = self._validate_category(category)
        with self._lock:
            return list(self._pending[c])

    def get_delivered(self, category: str) -> list[PushMessage]:
        c = self._validate_category(category)
        with self._lock:
            return list(self._delivered[c])

    def take_pending(self, category: str) -> list[PushMessage]:
        """pending を全て取り出す (テスト/flush 用; flush_digest で内部利用)."""
        c = self._validate_category(category)
        with self._lock:
            items = self._pending[c]
            self._pending[c] = []
            return items

    def record_delivered(self, category: str, msg: PushMessage) -> None:
        c = self._validate_category(category)
        msg.sent_at = time.time()
        msg.delivered = True
        with self._lock:
            self._delivered[c].append(msg)
            cfg = self._configs[c]
            cfg.last_flush_at = msg.sent_at

    def get_config(self, category: str) -> CategoryConfig:
        c = self._validate_category(category)
        with self._lock:
            return self._configs[c]


# Module-level singleton
_store: Optional[CategoryPushStore] = None


def get_store() -> CategoryPushStore:
    global _store
    if _store is None:
        _store = CategoryPushStore()
    return _store


def reset_store() -> None:
    global _store
    _store = CategoryPushStore()


# ──────────────────────────────────────────────────────────────────────────
# 高レベル API
# ──────────────────────────────────────────────────────────────────────────


async def _default_slack_send(message: str, channel: Optional[str]) -> bool:
    """T-014-01 slack_client を REUSE (未接続なら False)."""
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
        logger.warning("category-push default slack send failed: %s", e)
        return False


async def push_message(
    category: str,
    message: str,
    *,
    channel: Optional[str] = None,
    immediate: bool = False,
    slack_send_fn: Optional[SlackSendFn] = None,
) -> dict:
    """カテゴリ別 push. immediate / red_line は即時送信. それ以外は digest 待機."""
    store = get_store()
    msg = store.enqueue(category, message, channel=channel, immediate=immediate)

    # immediate 送信判定
    cfg = store.get_config(msg.category)
    is_immediate = (
        msg.category in IMMEDIATE_ONLY
        or immediate
        or cfg.digest_window_seconds == 0
    )

    delivered = False
    if is_immediate:
        send_fn = slack_send_fn or _default_slack_send
        delivered = await send_fn(
            f"[{msg.category.upper()}] {msg.message}",
            msg.channel,
        )
        if delivered:
            store.record_delivered(msg.category, msg)
    return {
        "id": msg.id,
        "category": msg.category,
        "immediate": is_immediate,
        "delivered": delivered,
        "channel": msg.channel,
    }


async def flush_digest(
    category: str,
    *,
    slack_send_fn: Optional[SlackSendFn] = None,
) -> dict:
    """指定カテゴリの pending をまとめて 1 送信に."""
    store = get_store()
    pending = store.take_pending(category)
    if not pending:
        return {"category": category, "flushed": 0, "delivered": False}
    cfg = store.get_config(category)
    # 1 通にまとめる
    header = f"[DIGEST {category.upper()}] ({len(pending)} items)"
    body_lines = [f"- {p.message[:200]}" for p in pending]
    combined = header + "\n" + "\n".join(body_lines)
    send_fn = slack_send_fn or _default_slack_send
    delivered = await send_fn(combined, cfg.channel)
    if delivered:
        for p in pending:
            store.record_delivered(category, p)
    return {
        "category": category,
        "flushed": len(pending),
        "delivered": delivered,
        "channel": cfg.channel,
    }


async def flush_all_digests(
    *,
    slack_send_fn: Optional[SlackSendFn] = None,
) -> dict:
    """全カテゴリの digest を flush."""
    out: dict[str, int] = {}
    delivered: dict[str, bool] = {}
    for c in VALID_CATEGORIES:
        r = await flush_digest(c, slack_send_fn=slack_send_fn)
        out[c] = r["flushed"]
        delivered[c] = r["delivered"]
    return {"flushed": out, "delivered": delivered}
