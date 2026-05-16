"""skill_test_rate_limiter.py — POST /api/skills/{id}/test の per-user rate limiter (T-V3-B-03).

F-002 / Feature spec: `rate_limit: 10/min/user`.
AC マッピング:
  AC-F1 UNWANTED: If POST /api/skills/{id}/test is invoked more than 10 times per
                  minute per user, the system shall return 429.

実装方針:
  - In-process sliding window (deque[timestamp]) を user_id 単位で保持
  - 同期/非同期どちらからも安全に呼べる asyncio.Lock 保護
  - test 時に DI / monkeypatch で時刻を差し替えられるよう `_now()` を分離
  - 完全 in-memory: 再起動でリセット (single-instance backend 前提)
    多 instance 環境 (Phase 2 以降) で Redis ベースへ差し替える前提

外部 API:
  await check_and_consume(user_id, *, limit=10, window_sec=60) -> tuple[bool, int]
      Returns (allowed, remaining). allowed=False のとき remaining=0.
  reset_all() -> None
      テスト用: 全 user の window をクリア.
  set_clock(callable) -> None
      テスト用: 時刻 source を差し替え (e.g. fake clock).
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Callable

# Defaults (F-002 / openapi: "10/min/user")
DEFAULT_LIMIT = 10
DEFAULT_WINDOW_SEC = 60

# user_id -> deque[timestamp_seconds]
_buckets: dict[str, deque[float]] = defaultdict(deque)
_lock = asyncio.Lock()

# 時刻 source (test で差し替え可能)
_clock: Callable[[], float] = time.monotonic


def set_clock(fn: Callable[[], float]) -> None:
    """テスト用: 時刻 source を差し替える."""
    global _clock
    _clock = fn


def reset_all() -> None:
    """テスト用: bucket を全クリア."""
    _buckets.clear()


def _now() -> float:
    return _clock()


async def check_and_consume(
    user_id: str,
    *,
    limit: int = DEFAULT_LIMIT,
    window_sec: int = DEFAULT_WINDOW_SEC,
) -> tuple[bool, int]:
    """Sliding window で 1 件分 consume を試みる.

    Args:
        user_id: rate limit key. empty / None は呼び出し側で reject 推奨.
        limit: 許可される最大件数 / window.
        window_sec: window 幅 (秒).

    Returns:
        (allowed, remaining):
            allowed=True なら consume 成功, remaining は残量 (>=0).
            allowed=False なら window 上限に達した状態, remaining=0.
    """
    if not user_id:
        # 空 user は consume せず即拒否 (呼び出し側で 401 にする想定)
        return False, 0

    async with _lock:
        bucket = _buckets[user_id]
        now = _now()
        # window 外を破棄
        cutoff = now - window_sec
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            return False, 0

        bucket.append(now)
        remaining = limit - len(bucket)
        return True, remaining
