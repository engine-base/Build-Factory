"""T-010c-03: 完了次第キュー補充 (FIFO + priority) サービス.

並列実行 worker のための queue 実装:
  - priority 4 段階 (urgent / high / medium / low)
  - 同 priority 内は FIFO
  - dequeue でアイテムを 1 件取り出し
  - 完了通知 (mark_done / mark_failed) で metrics 更新
  - 自動 refill: queue が空になったら refill_fn を呼んで補充

公開 API:
  - PriorityQueue(refill_fn=None)
  - enqueue(item) -> int (位置)
  - dequeue() -> Optional[QueueItem]
  - mark_done(item_id) -> bool
  - mark_failed(item_id, error) -> bool
  - stats() -> dict
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class PriorityQueueError(RuntimeError):
    pass


PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
VALID_PRIORITIES = tuple(PRIORITY_ORDER.keys())
MAX_QUEUE_SIZE = 10000


@dataclass
class QueueItem:
    id: int
    task_id: int
    priority: str
    payload: dict = field(default_factory=dict)
    enqueued_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: str = "queued"  # queued / processing / done / failed
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "priority": self.priority,
            "payload": dict(self.payload),
            "enqueued_at": self.enqueued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "error": self.error,
        }


RefillFn = Callable[[], Awaitable[list[dict]]]


class PriorityQueue:
    """FIFO + priority queue. 同 priority 内は FIFO."""

    def __init__(self, *, max_size: int = MAX_QUEUE_SIZE):
        if not isinstance(max_size, int) or max_size <= 0 or max_size > MAX_QUEUE_SIZE:
            raise PriorityQueueError(
                f"max_size must be 1..{MAX_QUEUE_SIZE}, got {max_size}"
            )
        self._lock = threading.Lock()
        self._max_size = max_size
        self._next_id = 1
        # priority → FIFO deque
        self._bands: dict[str, deque[QueueItem]] = {p: deque() for p in VALID_PRIORITIES}
        self._all: dict[int, QueueItem] = {}
        self._enqueued = 0
        self._dequeued = 0
        self._done = 0
        self._failed = 0

    def __len__(self) -> int:
        with self._lock:
            return sum(len(b) for b in self._bands.values())

    @property
    def max_size(self) -> int:
        return self._max_size

    def enqueue(
        self, *,
        task_id: int,
        priority: str = "medium",
        payload: Optional[dict] = None,
    ) -> QueueItem:
        if not isinstance(task_id, int) or task_id <= 0:
            raise PriorityQueueError(f"task_id must be > 0, got {task_id}")
        p = (priority or "medium").lower()
        if p not in VALID_PRIORITIES:
            raise PriorityQueueError(
                f"priority must be one of {VALID_PRIORITIES}, got {priority!r}"
            )
        if payload is not None and not isinstance(payload, dict):
            raise PriorityQueueError("payload must be a dict")
        with self._lock:
            cur_size = sum(len(b) for b in self._bands.values())
            if cur_size >= self._max_size:
                raise PriorityQueueError(
                    f"queue full (size={cur_size}, max={self._max_size})"
                )
            item = QueueItem(
                id=self._next_id,
                task_id=task_id,
                priority=p,
                payload=dict(payload or {}),
                enqueued_at=time.time(),
            )
            self._next_id += 1
            self._bands[p].append(item)
            self._all[item.id] = item
            self._enqueued += 1
        return item

    def dequeue(self) -> Optional[QueueItem]:
        """priority 順 → FIFO で 1 件 dequeue."""
        with self._lock:
            for p in VALID_PRIORITIES:
                if self._bands[p]:
                    item = self._bands[p].popleft()
                    item.status = "processing"
                    item.started_at = time.time()
                    self._dequeued += 1
                    return item
        return None

    def mark_done(self, item_id: int) -> bool:
        with self._lock:
            item = self._all.get(item_id)
            if item is None or item.status != "processing":
                return False
            item.status = "done"
            item.completed_at = time.time()
            self._done += 1
        return True

    def mark_failed(self, item_id: int, error: str) -> bool:
        with self._lock:
            item = self._all.get(item_id)
            if item is None or item.status != "processing":
                return False
            item.status = "failed"
            item.completed_at = time.time()
            item.error = str(error)[:1000] if error else None
            self._failed += 1
        return True

    def peek_next(self) -> Optional[QueueItem]:
        with self._lock:
            for p in VALID_PRIORITIES:
                if self._bands[p]:
                    return self._bands[p][0]
        return None

    def get_item(self, item_id: int) -> Optional[QueueItem]:
        with self._lock:
            return self._all.get(item_id)

    def stats(self) -> dict:
        with self._lock:
            by_band = {p: len(self._bands[p]) for p in VALID_PRIORITIES}
            cur_size = sum(by_band.values())
            return {
                "size": cur_size,
                "max_size": self._max_size,
                "by_priority": by_band,
                "enqueued_total": self._enqueued,
                "dequeued_total": self._dequeued,
                "done_total": self._done,
                "failed_total": self._failed,
                "in_flight": self._dequeued - self._done - self._failed,
            }

    async def refill(self, refill_fn: RefillFn) -> int:
        """queue が空 (or 半分以下) になったら refill_fn を呼んで補充する.

        refill_fn は dict list を返す必要がある: [{"task_id":..., "priority":..., "payload":...}, ...]
        戻り値: 補充した件数.
        """
        cur_size = len(self)
        if cur_size > self._max_size // 2:
            return 0
        try:
            items = await refill_fn()
        except Exception as e:
            logger.warning("queue refill_fn failed: %s", e)
            return 0
        if not isinstance(items, list):
            return 0
        added = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            tid = it.get("task_id")
            if not isinstance(tid, int) or tid <= 0:
                continue
            try:
                self.enqueue(
                    task_id=tid,
                    priority=it.get("priority") or "medium",
                    payload=it.get("payload") or {},
                )
                added += 1
            except PriorityQueueError:
                break  # full
        return added


# ──────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────


_queue: Optional[PriorityQueue] = None


def get_queue() -> PriorityQueue:
    global _queue
    if _queue is None:
        _queue = PriorityQueue()
    return _queue


def reset_queue(*, max_size: int = MAX_QUEUE_SIZE) -> None:
    global _queue
    _queue = PriorityQueue(max_size=max_size)
