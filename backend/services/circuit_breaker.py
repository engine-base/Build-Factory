"""T-010c-04: circuit breaker (連続失敗 N で auto-block).

target ごとに失敗カウンタを保持し、threshold を超えたら open (block) する.
open 状態で recover_seconds 経過後 half_open に遷移し、次の試行成功で closed に戻る.
失敗すれば再度 open.

状態:
  closed     → 通常運転 (call 可)
  open       → block 中 (call 拒否)
  half_open  → 試験運転 (call 可、失敗で open に戻る)

公開 API:
  - CircuitBreakerRegistry(failure_threshold, recover_seconds)
  - record_success(target_key) -> BreakerState
  - record_failure(target_key) -> BreakerState
  - allow(target_key) -> bool
  - reset(target_key) -> bool
  - status(target_key) -> dict
  - list_breakers() -> list[dict]
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitBreakerError(RuntimeError):
    pass


VALID_STATES = ("closed", "open", "half_open")
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RECOVER_SECONDS = 60.0
MAX_RECOVER_SECONDS = 24 * 3600  # 24h
MAX_TARGETS = 5000


@dataclass
class BreakerState:
    target_key: str
    state: str = "closed"  # closed / open / half_open
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    opened_at: Optional[float] = None
    last_event_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "target_key": self.target_key,
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "opened_at": self.opened_at,
            "last_event_at": self.last_event_at,
        }


class CircuitBreakerRegistry:
    """複数 target の breaker 状態を一元管理."""

    def __init__(
        self,
        *,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recover_seconds: float = DEFAULT_RECOVER_SECONDS,
        max_targets: int = MAX_TARGETS,
    ):
        if not isinstance(failure_threshold, int) or failure_threshold <= 0:
            raise CircuitBreakerError(
                f"failure_threshold must be > 0, got {failure_threshold}"
            )
        if failure_threshold > 1000:
            raise CircuitBreakerError("failure_threshold must be <= 1000")
        if not isinstance(recover_seconds, (int, float)) or recover_seconds <= 0:
            raise CircuitBreakerError(
                f"recover_seconds must be > 0, got {recover_seconds}"
            )
        if recover_seconds > MAX_RECOVER_SECONDS:
            raise CircuitBreakerError(
                f"recover_seconds must be <= {MAX_RECOVER_SECONDS}"
            )
        if not isinstance(max_targets, int) or max_targets <= 0:
            raise CircuitBreakerError(
                f"max_targets must be > 0, got {max_targets}"
            )
        self._failure_threshold = failure_threshold
        self._recover_seconds = float(recover_seconds)
        self._max_targets = max_targets
        self._lock = threading.Lock()
        self._breakers: dict[str, BreakerState] = {}

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @property
    def recover_seconds(self) -> float:
        return self._recover_seconds

    def _validate_key(self, target_key: str) -> str:
        if not isinstance(target_key, str) or not target_key.strip():
            raise CircuitBreakerError("target_key must not be empty")
        k = target_key.strip()
        if len(k) > 200:
            raise CircuitBreakerError("target_key must be <= 200 chars")
        return k

    def _get_or_create(self, target_key: str) -> BreakerState:
        if target_key not in self._breakers:
            if len(self._breakers) >= self._max_targets:
                raise CircuitBreakerError(
                    f"breakers full (max={self._max_targets})"
                )
            self._breakers[target_key] = BreakerState(target_key=target_key)
        return self._breakers[target_key]

    def _maybe_half_open(self, state: BreakerState) -> None:
        """open 状態で recover_seconds 経過していたら half_open に遷移."""
        if state.state != "open" or state.opened_at is None:
            return
        if time.time() - state.opened_at >= self._recover_seconds:
            state.state = "half_open"
            state.last_event_at = time.time()

    def allow(self, target_key: str) -> bool:
        """call を許可するか判定 (state 自動遷移込み)."""
        k = self._validate_key(target_key)
        with self._lock:
            if k not in self._breakers:
                return True  # 未登録 = closed 扱い
            state = self._breakers[k]
            self._maybe_half_open(state)
            return state.state in ("closed", "half_open")

    def record_success(self, target_key: str) -> BreakerState:
        k = self._validate_key(target_key)
        with self._lock:
            state = self._get_or_create(k)
            self._maybe_half_open(state)
            state.consecutive_failures = 0
            state.total_successes += 1
            state.last_event_at = time.time()
            # half_open or open → closed (open でも success が来ること自体は許容)
            state.state = "closed"
            state.opened_at = None
            return state

    def record_failure(self, target_key: str) -> BreakerState:
        k = self._validate_key(target_key)
        with self._lock:
            state = self._get_or_create(k)
            self._maybe_half_open(state)
            state.consecutive_failures += 1
            state.total_failures += 1
            state.last_event_at = time.time()
            # half_open で失敗 → open
            if state.state == "half_open":
                state.state = "open"
                state.opened_at = time.time()
            # closed で threshold 超え → open
            elif state.consecutive_failures >= self._failure_threshold:
                state.state = "open"
                state.opened_at = time.time()
            return state

    def status(self, target_key: str) -> dict:
        k = self._validate_key(target_key)
        with self._lock:
            if k not in self._breakers:
                # 未登録 = closed の default
                return BreakerState(target_key=k).to_dict()
            self._maybe_half_open(self._breakers[k])
            return self._breakers[k].to_dict()

    def reset(self, target_key: str) -> bool:
        k = self._validate_key(target_key)
        with self._lock:
            if k not in self._breakers:
                return False
            del self._breakers[k]
            return True

    def list_breakers(self) -> list[dict]:
        with self._lock:
            return [s.to_dict() for s in self._breakers.values()]


# ──────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────


_registry: Optional[CircuitBreakerRegistry] = None
_DEFAULT_THRESHOLD = DEFAULT_FAILURE_THRESHOLD
_DEFAULT_RECOVER = DEFAULT_RECOVER_SECONDS


def get_registry() -> CircuitBreakerRegistry:
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry(
            failure_threshold=_DEFAULT_THRESHOLD,
            recover_seconds=_DEFAULT_RECOVER,
        )
    return _registry


def reset_registry(
    *,
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
    recover_seconds: float = DEFAULT_RECOVER_SECONDS,
) -> None:
    global _registry
    _registry = CircuitBreakerRegistry(
        failure_threshold=failure_threshold,
        recover_seconds=recover_seconds,
    )
