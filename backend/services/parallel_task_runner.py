"""T-010c-01: asyncio.Semaphore + Queue による並列タスク実行制御.

task_executor / skill_runner と組み合わせて使う、汎用的な並列実行サービス.
固定 concurrency でタスクを並列実行し、queue 経由で進捗を観測可能.

公開 API:
  - ParallelRunner(max_concurrency)
  - submit(task_id, coro_fn) -> Awaitable[TaskOutcome]
  - stats() -> dict
  - close()
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class ParallelRunnerError(RuntimeError):
    pass


class RunnerClosedError(ParallelRunnerError):
    pass


@dataclass
class TaskOutcome:
    task_id: int
    status: str  # "queued" / "running" / "done" / "failed" / "cancelled"
    result: Any = None
    error: Optional[str] = None
    queued_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def duration_sec(self) -> Optional[float]:
        if self.started_at is None or self.completed_at is None:
            return None
        return self.completed_at - self.started_at

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "error": self.error,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_sec": self.duration_sec,
        }


@dataclass
class _Stats:
    queued: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0
    cancelled: int = 0
    total_submitted: int = 0


CoroFn = Callable[[], Awaitable[Any]]


class ParallelRunner:
    """asyncio.Semaphore で max_concurrency を制限する並列実行マネージャ.

    submit(task_id, coro_fn) で coroutine を queue 投入し、
    背景で max_concurrency 件まで並列に実行する.
    """

    def __init__(self, *, max_concurrency: int = 4):
        if not isinstance(max_concurrency, int) or max_concurrency <= 0:
            raise ParallelRunnerError(
                f"max_concurrency must be > 0, got {max_concurrency}"
            )
        if max_concurrency > 100:
            raise ParallelRunnerError("max_concurrency must be <= 100")
        self._sem = asyncio.Semaphore(max_concurrency)
        self._max_concurrency = max_concurrency
        self._stats = _Stats()
        self._outcomes: dict[int, TaskOutcome] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    @property
    def closed(self) -> bool:
        return self._closed

    async def submit(self, task_id: int, coro_fn: CoroFn) -> TaskOutcome:
        """task_id 付きで coroutine を投入. await すると完了 outcome を返す."""
        if self._closed:
            raise RunnerClosedError("runner is closed")
        if not isinstance(task_id, int) or task_id <= 0:
            raise ParallelRunnerError(
                f"task_id must be > 0, got {task_id}"
            )
        if not callable(coro_fn):
            raise ParallelRunnerError("coro_fn must be callable")

        async with self._lock:
            if task_id in self._outcomes:
                raise ParallelRunnerError(
                    f"task_id {task_id} already submitted"
                )
            outcome = TaskOutcome(
                task_id=task_id,
                status="queued",
                queued_at=time.time(),
            )
            self._outcomes[task_id] = outcome
            self._stats.queued += 1
            self._stats.total_submitted += 1

        await self._sem.acquire()
        async with self._lock:
            self._stats.queued -= 1
            self._stats.running += 1
            outcome.status = "running"
            outcome.started_at = time.time()
        try:
            result = await coro_fn()
            async with self._lock:
                self._stats.running -= 1
                self._stats.done += 1
                outcome.status = "done"
                outcome.result = result
                outcome.completed_at = time.time()
            return outcome
        except asyncio.CancelledError:
            async with self._lock:
                self._stats.running -= 1
                self._stats.cancelled += 1
                outcome.status = "cancelled"
                outcome.completed_at = time.time()
            raise
        except Exception as e:
            async with self._lock:
                self._stats.running -= 1
                self._stats.failed += 1
                outcome.status = "failed"
                outcome.error = str(e)
                outcome.completed_at = time.time()
            logger.warning("parallel task %s failed: %s", task_id, e)
            return outcome
        finally:
            self._sem.release()

    def stats(self) -> dict:
        return {
            "max_concurrency": self._max_concurrency,
            "queued": self._stats.queued,
            "running": self._stats.running,
            "done": self._stats.done,
            "failed": self._stats.failed,
            "cancelled": self._stats.cancelled,
            "total_submitted": self._stats.total_submitted,
            "closed": self._closed,
        }

    def get_outcome(self, task_id: int) -> Optional[TaskOutcome]:
        return self._outcomes.get(task_id)

    def list_outcomes(self) -> list[TaskOutcome]:
        return list(self._outcomes.values())

    async def close(self) -> None:
        """新規 submit を拒否する (既に走っている task は完了まで継続)."""
        self._closed = True


# ──────────────────────────────────────────────────────────────────────────
# Module-level singleton (test では reset)
# ──────────────────────────────────────────────────────────────────────────


_runner: Optional[ParallelRunner] = None
_DEFAULT_MAX = 4


def get_runner() -> ParallelRunner:
    global _runner
    if _runner is None or _runner.closed:
        _runner = ParallelRunner(max_concurrency=_DEFAULT_MAX)
    return _runner


def reset_runner(*, max_concurrency: int = _DEFAULT_MAX) -> None:
    global _runner
    _runner = ParallelRunner(max_concurrency=max_concurrency)
