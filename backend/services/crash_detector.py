"""T-010c-05: crash detection (worker 監視).

worker session の crash を 3 つの観点で検出する:
  1. heartbeat: 最終 heartbeat から timeout_seconds (default 30 min) 経過
  2. memory: memory_mb が threshold (default 4096) 超え
  3. unexpected_exit: status=exited で exit_code != 0

公開 API:
  - register_session(session_id, *, started_at, heartbeat_timeout, memory_limit_mb)
  - record_heartbeat(session_id, *, memory_mb=None)
  - record_exit(session_id, exit_code)
  - detect_crashes(now=None) -> list[CrashReport]
  - get_session(session_id) -> Optional[dict]
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class CrashDetectorError(RuntimeError):
    pass


DEFAULT_HEARTBEAT_TIMEOUT_SEC = 30 * 60  # 30 min
DEFAULT_MEMORY_LIMIT_MB = 4096
MAX_HEARTBEAT_TIMEOUT_SEC = 24 * 3600
MAX_MEMORY_LIMIT_MB = 1_000_000
MAX_SESSIONS = 10000


# crash reasons
REASON_HEARTBEAT = "heartbeat_timeout"
REASON_MEMORY = "memory_threshold_exceeded"
REASON_UNEXPECTED_EXIT = "unexpected_exit"


@dataclass
class SessionWatch:
    session_id: int
    started_at: float
    heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT_SEC
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB
    last_heartbeat_at: float = 0.0
    last_memory_mb: float = 0.0
    status: str = "running"  # running / crashed / exited
    crash_reason: Optional[str] = None
    exit_code: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "heartbeat_timeout": self.heartbeat_timeout,
            "memory_limit_mb": self.memory_limit_mb,
            "last_heartbeat_at": self.last_heartbeat_at,
            "last_memory_mb": self.last_memory_mb,
            "status": self.status,
            "crash_reason": self.crash_reason,
            "exit_code": self.exit_code,
        }


@dataclass
class CrashReport:
    session_id: int
    reason: str
    detected_at: float
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "reason": self.reason,
            "detected_at": self.detected_at,
            "detail": dict(self.detail),
        }


class CrashDetector:
    def __init__(self, *, max_sessions: int = MAX_SESSIONS):
        if not isinstance(max_sessions, int) or max_sessions <= 0:
            raise CrashDetectorError("max_sessions must be > 0")
        self._max_sessions = max_sessions
        self._lock = threading.Lock()
        self._sessions: dict[int, SessionWatch] = {}

    def _validate_session_id(self, sid: int) -> None:
        if not isinstance(sid, int) or sid <= 0:
            raise CrashDetectorError("session_id must be > 0")

    def register_session(
        self,
        session_id: int,
        *,
        started_at: Optional[float] = None,
        heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT_SEC,
        memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
    ) -> SessionWatch:
        self._validate_session_id(session_id)
        if not isinstance(heartbeat_timeout, (int, float)) or heartbeat_timeout <= 0:
            raise CrashDetectorError("heartbeat_timeout must be > 0")
        if heartbeat_timeout > MAX_HEARTBEAT_TIMEOUT_SEC:
            raise CrashDetectorError(
                f"heartbeat_timeout must be <= {MAX_HEARTBEAT_TIMEOUT_SEC}"
            )
        if not isinstance(memory_limit_mb, int) or memory_limit_mb <= 0:
            raise CrashDetectorError("memory_limit_mb must be > 0")
        if memory_limit_mb > MAX_MEMORY_LIMIT_MB:
            raise CrashDetectorError(
                f"memory_limit_mb must be <= {MAX_MEMORY_LIMIT_MB}"
            )

        now = time.time()
        with self._lock:
            if session_id in self._sessions:
                raise CrashDetectorError(
                    f"session_id {session_id} already registered"
                )
            if len(self._sessions) >= self._max_sessions:
                raise CrashDetectorError(
                    f"max_sessions reached ({self._max_sessions})"
                )
            watch = SessionWatch(
                session_id=session_id,
                started_at=started_at if started_at is not None else now,
                heartbeat_timeout=float(heartbeat_timeout),
                memory_limit_mb=memory_limit_mb,
                last_heartbeat_at=now,
            )
            self._sessions[session_id] = watch
            return watch

    def record_heartbeat(
        self,
        session_id: int,
        *,
        memory_mb: Optional[float] = None,
    ) -> SessionWatch:
        self._validate_session_id(session_id)
        if memory_mb is not None and (
            not isinstance(memory_mb, (int, float)) or memory_mb < 0
        ):
            raise CrashDetectorError("memory_mb must be >= 0 when provided")
        with self._lock:
            watch = self._sessions.get(session_id)
            if watch is None:
                raise CrashDetectorError(
                    f"session_id {session_id} not registered"
                )
            if watch.status != "running":
                # 既に crashed / exited 状態のセッションは update しない
                raise CrashDetectorError(
                    f"session {session_id} not in 'running' state "
                    f"(got {watch.status})"
                )
            watch.last_heartbeat_at = time.time()
            if memory_mb is not None:
                watch.last_memory_mb = float(memory_mb)
            return watch

    def record_exit(self, session_id: int, exit_code: int) -> SessionWatch:
        self._validate_session_id(session_id)
        if not isinstance(exit_code, int):
            raise CrashDetectorError("exit_code must be int")
        with self._lock:
            watch = self._sessions.get(session_id)
            if watch is None:
                raise CrashDetectorError(
                    f"session_id {session_id} not registered"
                )
            watch.status = "exited"
            watch.exit_code = exit_code
            if exit_code != 0 and watch.crash_reason is None:
                watch.crash_reason = REASON_UNEXPECTED_EXIT
            return watch

    def get_session(self, session_id: int) -> Optional[dict]:
        with self._lock:
            w = self._sessions.get(session_id)
            return w.to_dict() if w else None

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return [w.to_dict() for w in self._sessions.values()]

    def detect_crashes(self, *, now: Optional[float] = None) -> list[CrashReport]:
        """全 running session を走査して crash 条件を判定."""
        ts = now if now is not None else time.time()
        reports: list[CrashReport] = []
        with self._lock:
            for sid, watch in self._sessions.items():
                if watch.status != "running":
                    # exited で unexpected_exit を 1 度だけ報告
                    if (
                        watch.status == "exited"
                        and watch.crash_reason == REASON_UNEXPECTED_EXIT
                    ):
                        # 既に detected されたかどうかは呼び出し側責任
                        reports.append(CrashReport(
                            session_id=sid,
                            reason=REASON_UNEXPECTED_EXIT,
                            detected_at=ts,
                            detail={"exit_code": watch.exit_code},
                        ))
                    continue
                # 1. heartbeat timeout
                if ts - watch.last_heartbeat_at > watch.heartbeat_timeout:
                    watch.status = "crashed"
                    watch.crash_reason = REASON_HEARTBEAT
                    reports.append(CrashReport(
                        session_id=sid,
                        reason=REASON_HEARTBEAT,
                        detected_at=ts,
                        detail={
                            "last_heartbeat_at": watch.last_heartbeat_at,
                            "timeout_seconds": watch.heartbeat_timeout,
                            "elapsed": ts - watch.last_heartbeat_at,
                        },
                    ))
                    continue
                # 2. memory threshold
                if watch.last_memory_mb > watch.memory_limit_mb:
                    watch.status = "crashed"
                    watch.crash_reason = REASON_MEMORY
                    reports.append(CrashReport(
                        session_id=sid,
                        reason=REASON_MEMORY,
                        detected_at=ts,
                        detail={
                            "memory_mb": watch.last_memory_mb,
                            "limit_mb": watch.memory_limit_mb,
                        },
                    ))
        return reports

    def reset(self, session_id: int) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None


# ──────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────


_detector: Optional[CrashDetector] = None


def get_detector() -> CrashDetector:
    global _detector
    if _detector is None:
        _detector = CrashDetector()
    return _detector


def reset_detector() -> None:
    global _detector
    _detector = CrashDetector()
