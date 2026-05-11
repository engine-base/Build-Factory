"""T-M30-02: 短期 layer (FIFO 直近 N=20).

M-30 3 層 memory の Tier 1 (短期記憶) を統一インターフェースで提供する.
既存 `chat_thread_store.list_messages` を REUSE し, FIFO の最新 N 件を返す
recent-window + LLM 向け context 組立 (role/content の list) を提供する.

公開 API:
  - recent_window(thread_id, *, limit=20, role_filter=None) -> list[ChatMessage]
      thread に紐づく直近 N 件のメッセージ (FIFO 順: 古い -> 新しい)
  - assemble_context(thread_id, *, limit=20, role_filter=None) -> list[dict]
      LLM ready の {role, content} list (system は含む)

設計:
  - REUSE: `chat_thread_store.get_store().list_messages` を活用
  - FIFO: 既存 store は insertion order (古い -> 新しい) を保持
    末尾 N 件を返す = recent window
  - 既存 store / API は無改変 (Tier 1 layer は store 上の view のみ)
  - persistent state mutation 無し (read-only)
"""
from __future__ import annotations

import logging
from typing import Optional

from services import chat_thread_store as cts

logger = logging.getLogger(__name__)


class ShortTermLayerError(RuntimeError):
    pass


DEFAULT_WINDOW = 20
MAX_WINDOW = 200
MIN_WINDOW = 1
VALID_ROLES = cts.VALID_ROLES


def _validate_thread_id(thread_id: int) -> int:
    if not isinstance(thread_id, int) or isinstance(thread_id, bool) or thread_id <= 0:
        raise ShortTermLayerError("thread_id must be > 0")
    return thread_id


def _validate_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ShortTermLayerError(f"limit must be int in {MIN_WINDOW}..{MAX_WINDOW}")
    if limit < MIN_WINDOW or limit > MAX_WINDOW:
        raise ShortTermLayerError(f"limit must be in {MIN_WINDOW}..{MAX_WINDOW}")
    return limit


def _validate_role_filter(role_filter: Optional[list[str]]) -> Optional[list[str]]:
    if role_filter is None:
        return None
    if not isinstance(role_filter, (list, tuple)):
        raise ShortTermLayerError("role_filter must be a list of role strings")
    out: list[str] = []
    for r in role_filter:
        if r not in VALID_ROLES:
            raise ShortTermLayerError(
                f"role_filter contains invalid role {r!r}; "
                f"must be one of {VALID_ROLES}"
            )
        if r in out:
            raise ShortTermLayerError("role_filter must be unique")
        out.append(r)
    if not out:
        raise ShortTermLayerError("role_filter must not be empty when provided")
    return out


def recent_window(
    thread_id: int,
    *,
    limit: int = DEFAULT_WINDOW,
    role_filter: Optional[list[str]] = None,
) -> list[cts.ChatMessage]:
    """直近 N 件の ChatMessage を FIFO 順 (古い -> 新しい) で返す."""
    thread_id = _validate_thread_id(thread_id)
    limit = _validate_limit(limit)
    role_filter = _validate_role_filter(role_filter)

    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise ShortTermLayerError(f"thread not found: {thread_id}")

    total = store.count_messages(thread_id)
    if total == 0:
        return []
    # store.list_messages の cap (10_000) に揃える. MAX_WINDOW=200 << 10_000 なので
    # role_filter で削れた後の最新 N=window もこの範囲で必ず取れる.
    fetch_limit = min(total, 10_000)
    offset = max(0, total - fetch_limit)
    items = store.list_messages(thread_id, limit=fetch_limit, offset=offset)
    if role_filter is not None:
        items = [m for m in items if m.role in role_filter]
    if len(items) > limit:
        items = items[-limit:]
    return items


def assemble_context(
    thread_id: int,
    *,
    limit: int = DEFAULT_WINDOW,
    role_filter: Optional[list[str]] = None,
) -> list[dict]:
    """LLM ready な {role, content} list を生成する.

    role_filter が None の場合は user/assistant/system/tool 全て含む.
    """
    msgs = recent_window(thread_id, limit=limit, role_filter=role_filter)
    return [{"role": m.role, "content": m.content} for m in msgs]


def window_stats(thread_id: int) -> dict:
    """thread の short-term window 容量状況を返す (audit/可視化用).

    Returns:
      {thread_id, total, default_window, max_window, fits_in_default}
    """
    thread_id = _validate_thread_id(thread_id)
    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise ShortTermLayerError(f"thread not found: {thread_id}")
    total = store.count_messages(thread_id)
    return {
        "thread_id": thread_id,
        "total": total,
        "default_window": DEFAULT_WINDOW,
        "max_window": MAX_WINDOW,
        "fits_in_default": total <= DEFAULT_WINDOW,
    }
