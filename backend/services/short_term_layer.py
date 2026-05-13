"""T-M30-02: 短期 layer (FIFO 直近 N=20 / existing chat_thread_store REUSE).

M-30 3 層 memory の Tier 1 (短期 = 生 message) を読み出すための **REUSE wrapper**.
chat_thread_store (T-M30-01) を base に、最近 N message を chronological (oldest-first)
で返す read-only view を提供する.

設計境界 (REUSE タスク, IMPLEMENTATION_PROTOCOL Step 4):
  既存 `backend/services/chat_thread_store.py` は **完全無改変** (REUSE).
  本 module は thin read-only wrapper. `add_message` / `delete_message` は呼ばない.

## 公開 API (read-only)

  - `recent_messages(thread_id, *, n=20, role_filter=None,
                     exclude_summaries=True, actor_user_id=None) -> dict`
      直近 N 件の生 message (chronological / oldest-first).
      exclude_summaries=True のとき role='system'+compressed_summary または
      role='system_summary' を除外 (Tier 2 mid_term_layer 重複防止).
  - `short_tier_stats(thread_id, *, actor_user_id=None) -> dict`
      thread の短期 layer 統計 (total / recent_count / by_role / summary_count).

## Mid-layer との分離 (cross-tier invariant)

  - 9-section structured summary は mid_term_layer の SECTION_KEYS を参照する
    ため、本 module では再定義しない (G15 cross-tier 一貫性).
  - mid_term_layer が summary を「掬う」対象を、短期 layer は default で「除外」する.
    これにより同一 message が 2 つの tier から重複 emit されない.

## ADR-010 整合性

  - main runner path で LangGraph / LangChain なし.
  - claude-agent-sdk auto 機能 (tool result trim / prompt cache) は再実装しない.
  - 本 module は in-memory chat_thread_store の薄い view であり,
    SDK auto-compaction 完了後も短期 = "raw window" の concept は変わらない.

## AC マッピング (T-M30-02 REUSE)

  AC-1 UBIQUITOUS    : recent_messages / short_tier_stats / 定数 + Error class
                       公開. 既存 chat_thread_store 無改変.
  AC-2 EVENT-DRIVEN  : 2 秒以内 / chronological oldest-first / mid_term summary
                       default exclude / 構造化 dict 返却.
  AC-3 STATE-DRIVEN  : read-only (add_message / delete_message 呼ばない).
                       chat_thread_store schema 不変. SECTION_KEYS 重定義禁止.
  AC-4 UNWANTED      : invalid input / unauthorized / not_found で 4xx.
                       ChatThreadError は ShortTermLayerError に変換 (内部例外を leak しない).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from services import chat_thread_store as cts

logger = logging.getLogger(__name__)


class ShortTermLayerError(RuntimeError):
    """短期 layer の入力 / 不変条件違反 (router 層で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

DEFAULT_FIFO_N = 20
MIN_FIFO_N = 1
MAX_FIFO_N = 200

MAX_ACTOR_USER_ID_LEN = 200
MAX_FETCH_MESSAGES = 10_000  # chat_thread_store list_messages 上限と一致

# mid_term_layer roles (重複排除のため参照).
# G15: SECTION_KEYS 再定義禁止 / mid_term_layer.SECTION_KEYS に委譲.
MID_TIER_ROLE_SYSTEM = "system"  # + compressed_summary
MID_TIER_ROLE_SYSTEM_SUMMARY = "system_summary"


# ──────────────────────────────────────────────────────────────────────
# Validation helpers (UNWANTED AC-4)
# ──────────────────────────────────────────────────────────────────────


def _validate_thread_id(thread_id: Any) -> int:
    if isinstance(thread_id, bool) or not isinstance(thread_id, int) or thread_id <= 0:
        raise ShortTermLayerError("thread_id must be int > 0")
    return thread_id


def _validate_n(n: Any) -> int:
    if isinstance(n, bool) or not isinstance(n, int):
        raise ShortTermLayerError(f"n must be int in {MIN_FIFO_N}..{MAX_FIFO_N}")
    if n < MIN_FIFO_N or n > MAX_FIFO_N:
        raise ShortTermLayerError(f"n must be in {MIN_FIFO_N}..{MAX_FIFO_N}")
    return n


def _validate_role_filter(role_filter: Any) -> Optional[frozenset[str]]:
    if role_filter is None:
        return None
    if isinstance(role_filter, str):
        if not role_filter.strip():
            raise ShortTermLayerError("role_filter entries must be non-empty strings")
        return frozenset({role_filter})
    if not isinstance(role_filter, (list, tuple, set, frozenset)):
        raise ShortTermLayerError(
            "role_filter must be None | str | list[str] | tuple[str] | set[str]"
        )
    cleaned: set[str] = set()
    for r in role_filter:
        if not isinstance(r, str) or not r.strip():
            raise ShortTermLayerError(
                "role_filter entries must be non-empty strings"
            )
        cleaned.add(r)
    if not cleaned:
        raise ShortTermLayerError("role_filter must not be empty when provided")
    return frozenset(cleaned)


def _validate_bool(value: Any, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise ShortTermLayerError(f"{name} must be bool")
    return value


def _validate_actor_user_id(actor_user_id: Optional[str]) -> Optional[str]:
    if actor_user_id is None:
        return None
    if not isinstance(actor_user_id, str):
        raise ShortTermLayerError("actor_user_id must be string or null")
    stripped = actor_user_id.strip()
    if not stripped:
        raise ShortTermLayerError("actor_user_id must not be empty when provided")
    if len(stripped) > MAX_ACTOR_USER_ID_LEN:
        raise ShortTermLayerError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return stripped


def _require_thread_exists(thread_id: int) -> None:
    store = cts.get_store()
    if store.get_thread(thread_id) is None:
        raise ShortTermLayerError(f"thread not found: {thread_id}")


# ──────────────────────────────────────────────────────────────────────
# Message classification (mid-tier summary 除外判定)
# ──────────────────────────────────────────────────────────────────────


def _is_mid_tier_summary(msg: cts.ChatMessage) -> bool:
    """mid_term_layer が掬う summary か判定.

    G15: mid_term_layer._classify_source と同じ semantics を維持 (cross-tier 整合).
    """
    # 経路 A: role='system' + compressed_summary フィールド
    if msg.role == MID_TIER_ROLE_SYSTEM and msg.compressed_summary:
        return True
    # 経路 B: role='system_summary'
    if msg.role == MID_TIER_ROLE_SYSTEM_SUMMARY:
        return True
    return False


def _to_dict(msg: cts.ChatMessage) -> dict[str, Any]:
    """ChatMessage → serializable dict (公開 view).

    `compressed_summary` の中身は短期 layer の責務ではないため、
    has_compressed_summary boolean だけを expose する (mid_term_layer の責務).
    """
    return {
        "id": msg.id,
        "thread_id": msg.thread_id,
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at,
        "has_compressed_summary": bool(msg.compressed_summary),
    }


def _fetch_messages_safely(thread_id: int) -> list[cts.ChatMessage]:
    """chat_thread_store から全 message を取得 (ChatThreadError → ShortTermLayerError)."""
    store = cts.get_store()
    try:
        total = store.count_messages(thread_id)
        if total == 0:
            return []
        fetch_limit = min(total, MAX_FETCH_MESSAGES)
        offset = max(0, total - fetch_limit)
        return store.list_messages(thread_id, limit=fetch_limit, offset=offset)
    except cts.ChatThreadError as e:
        # AC-4: 内部例外を leak しない
        raise ShortTermLayerError(f"chat_thread_store error: {e}") from e


# ──────────────────────────────────────────────────────────────────────
# Public API: recent_messages (read-only)
# ──────────────────────────────────────────────────────────────────────


def recent_messages(
    thread_id: int,
    *,
    n: int = DEFAULT_FIFO_N,
    role_filter: Optional[Iterable[str]] = None,
    exclude_summaries: bool = True,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """直近 N 件の生 message (chronological / oldest-first).

    Args:
      thread_id        : 対象 thread (must exist)
      n                : 直近 N 件 (1..200, default 20)
      role_filter      : 含めたい role の白リスト (None なら全 role)
      exclude_summaries: True (default) で role='system'+compressed_summary
                          または role='system_summary' を除外 (Tier 2 重複防止)
      actor_user_id    : UNAUTHORIZED 検知 (None なら skip)

    Returns:
      {
        "thread_id": int,
        "n": int,
        "count": int,                     # 返した message 数 (0..n)
        "exclude_summaries": bool,
        "role_filter": list[str] | None,
        "messages": [
          {id, thread_id, role, content, created_at, has_compressed_summary}, ...
        ],
      }
    """
    thread_id = _validate_thread_id(thread_id)
    n = _validate_n(n)
    role_set = _validate_role_filter(role_filter)
    exclude_summaries = _validate_bool(exclude_summaries, name="exclude_summaries")
    _validate_actor_user_id(actor_user_id)
    _require_thread_exists(thread_id)

    msgs = _fetch_messages_safely(thread_id)

    # filter: exclude_summaries + role_filter
    filtered: list[cts.ChatMessage] = []
    for m in msgs:
        if exclude_summaries and _is_mid_tier_summary(m):
            continue
        if role_set is not None and m.role not in role_set:
            continue
        filtered.append(m)

    # FIFO N: take last N, keep chronological order (oldest-first)
    recent = filtered[-n:] if len(filtered) > n else filtered

    return {
        "thread_id": thread_id,
        "n": n,
        "count": len(recent),
        "exclude_summaries": exclude_summaries,
        "role_filter": sorted(role_set) if role_set is not None else None,
        "messages": [_to_dict(m) for m in recent],
    }


# ──────────────────────────────────────────────────────────────────────
# Public API: short_tier_stats (read-only)
# ──────────────────────────────────────────────────────────────────────


def short_tier_stats(
    thread_id: int,
    *,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """thread の短期 layer 統計.

    Returns:
      {
        "thread_id": int,
        "total_messages": int,            # exclude_summaries=False 相当
        "recent_count": int,              # exclude_summaries=True で残る数
        "by_role": {role: int},           # 全 message を role でカウント
        "summary_count": int,             # mid-tier に該当する数 (exclude 対象)
        "oldest_at": float | None,
        "newest_at": float | None,
        "fifo_default_n": int,
      }
    """
    thread_id = _validate_thread_id(thread_id)
    _validate_actor_user_id(actor_user_id)
    _require_thread_exists(thread_id)

    msgs = _fetch_messages_safely(thread_id)
    total = len(msgs)
    by_role: dict[str, int] = {}
    summary_count = 0
    oldest_at: Optional[float] = None
    newest_at: Optional[float] = None

    for m in msgs:
        by_role[m.role] = by_role.get(m.role, 0) + 1
        if _is_mid_tier_summary(m):
            summary_count += 1
        if oldest_at is None or m.created_at < oldest_at:
            oldest_at = m.created_at
        if newest_at is None or m.created_at > newest_at:
            newest_at = m.created_at

    recent_count = total - summary_count
    return {
        "thread_id": thread_id,
        "total_messages": total,
        "recent_count": recent_count,
        "by_role": by_role,
        "summary_count": summary_count,
        "oldest_at": oldest_at,
        "newest_at": newest_at,
        "fifo_default_n": DEFAULT_FIFO_N,
    }
