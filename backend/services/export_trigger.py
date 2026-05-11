"""T-016-03: artifact export trigger 管理.

4 種類の trigger:
  - manual         手動実行
  - realtime       artifact 更新時に即座 (event-driven)
  - hourly         1 時間ごと (scheduler)
  - on_completion  task 完了時 (event-driven)

公開 API:
  - register_trigger(artifact_id, trigger_type, *, scheduled_at)
  - list_triggers(*, artifact_id, trigger_type)
  - fire_trigger(trigger_id) -> dict
  - delete_trigger(trigger_id) -> bool
  - due_triggers(now=None) -> list[Trigger]
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class ExportTriggerError(RuntimeError):
    pass


VALID_TRIGGER_TYPES = ("manual", "realtime", "hourly", "on_completion")
SCHEDULED_TYPES = frozenset({"hourly"})       # 時間ベース
EVENT_TYPES = frozenset({"realtime", "on_completion"})  # event-driven
MANUAL_TYPES = frozenset({"manual"})

MAX_TRIGGERS = 5000
HOURLY_INTERVAL_SEC = 3600
MAX_ARTIFACT_ID_LEN = 200


@dataclass
class Trigger:
    id: int
    artifact_id: str
    trigger_type: str
    enabled: bool = True
    last_fired_at: Optional[float] = None
    fire_count: int = 0
    scheduled_at: Optional[float] = None
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "artifact_id": self.artifact_id,
            "trigger_type": self.trigger_type,
            "enabled": self.enabled,
            "last_fired_at": self.last_fired_at,
            "fire_count": self.fire_count,
            "scheduled_at": self.scheduled_at,
            "created_at": self.created_at,
        }


@dataclass
class FireResult:
    trigger_id: int
    artifact_id: str
    trigger_type: str
    fired_at: float
    success: bool
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trigger_id": self.trigger_id,
            "artifact_id": self.artifact_id,
            "trigger_type": self.trigger_type,
            "fired_at": self.fired_at,
            "success": self.success,
            "detail": dict(self.detail),
        }


# Export 実行用 callable (注入可能)
ExportFn = Callable[[str], Awaitable[dict]]


class ExportTriggerStore:
    def __init__(self, *, max_triggers: int = MAX_TRIGGERS):
        if not isinstance(max_triggers, int) or max_triggers <= 0:
            raise ExportTriggerError("max_triggers must be > 0")
        self._lock = threading.Lock()
        self._triggers: dict[int, Trigger] = {}
        self._next_id = 1
        self._max = max_triggers

    def _validate_artifact_id(self, aid: str) -> str:
        if not isinstance(aid, str) or not aid.strip():
            raise ExportTriggerError("artifact_id must not be empty")
        if len(aid) > MAX_ARTIFACT_ID_LEN:
            raise ExportTriggerError(
                f"artifact_id must be <= {MAX_ARTIFACT_ID_LEN} chars"
            )
        return aid.strip()

    def _validate_trigger_type(self, t: str) -> str:
        if not isinstance(t, str) or t not in VALID_TRIGGER_TYPES:
            raise ExportTriggerError(
                f"trigger_type must be one of {VALID_TRIGGER_TYPES}, got {t!r}"
            )
        return t

    def register(
        self,
        artifact_id: str,
        trigger_type: str,
        *,
        scheduled_at: Optional[float] = None,
        enabled: bool = True,
    ) -> Trigger:
        aid = self._validate_artifact_id(artifact_id)
        tt = self._validate_trigger_type(trigger_type)
        if scheduled_at is not None:
            if not isinstance(scheduled_at, (int, float)) or scheduled_at < 0:
                raise ExportTriggerError(
                    "scheduled_at must be a non-negative number"
                )
            if tt not in SCHEDULED_TYPES:
                raise ExportTriggerError(
                    f"scheduled_at only allowed for {SCHEDULED_TYPES}"
                )

        with self._lock:
            # 重複検出: 同 artifact_id + 同 trigger_type は 1 個まで
            for t in self._triggers.values():
                if t.artifact_id == aid and t.trigger_type == tt:
                    raise ExportTriggerError(
                        f"trigger already exists "
                        f"(artifact_id={aid}, type={tt})"
                    )
            if len(self._triggers) >= self._max:
                raise ExportTriggerError(
                    f"triggers full (max={self._max})"
                )
            trig = Trigger(
                id=self._next_id,
                artifact_id=aid,
                trigger_type=tt,
                enabled=enabled,
                scheduled_at=scheduled_at,
                created_at=time.time(),
            )
            self._triggers[self._next_id] = trig
            self._next_id += 1
            return trig

    def list(
        self,
        *,
        artifact_id: Optional[str] = None,
        trigger_type: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> list[Trigger]:
        result: list[Trigger] = []
        with self._lock:
            for t in self._triggers.values():
                if artifact_id is not None and t.artifact_id != artifact_id:
                    continue
                if trigger_type is not None and t.trigger_type != trigger_type:
                    continue
                if enabled is not None and t.enabled != enabled:
                    continue
                result.append(t)
        return result

    def get(self, trigger_id: int) -> Optional[Trigger]:
        if not isinstance(trigger_id, int) or trigger_id <= 0:
            return None
        with self._lock:
            return self._triggers.get(trigger_id)

    def delete(self, trigger_id: int) -> bool:
        if not isinstance(trigger_id, int) or trigger_id <= 0:
            raise ExportTriggerError("trigger_id must be > 0")
        with self._lock:
            return self._triggers.pop(trigger_id, None) is not None

    def disable(self, trigger_id: int) -> bool:
        if not isinstance(trigger_id, int) or trigger_id <= 0:
            raise ExportTriggerError("trigger_id must be > 0")
        with self._lock:
            t = self._triggers.get(trigger_id)
            if t is None:
                return False
            t.enabled = False
            return True

    def due_triggers(self, *, now: Optional[float] = None) -> list[Trigger]:
        """hourly trigger で last_fired_at から HOURLY_INTERVAL_SEC 経過した
        ものを return (enabled のみ)."""
        ts = now if now is not None else time.time()
        due: list[Trigger] = []
        with self._lock:
            for t in self._triggers.values():
                if not t.enabled:
                    continue
                if t.trigger_type != "hourly":
                    continue
                if t.last_fired_at is None:
                    due.append(t)
                    continue
                if ts - t.last_fired_at >= HOURLY_INTERVAL_SEC:
                    due.append(t)
        return due

    def mark_fired(self, trigger_id: int) -> None:
        with self._lock:
            t = self._triggers.get(trigger_id)
            if t is None:
                return
            t.last_fired_at = time.time()
            t.fire_count += 1


# Module-level singleton
_store: Optional[ExportTriggerStore] = None


def get_store() -> ExportTriggerStore:
    global _store
    if _store is None:
        _store = ExportTriggerStore()
    return _store


def reset_store() -> None:
    global _store
    _store = ExportTriggerStore()


async def fire_trigger(
    trigger_id: int,
    *,
    export_fn: Optional[ExportFn] = None,
) -> FireResult:
    """trigger を 1 回 fire. export_fn(artifact_id) を呼んで結果を記録."""
    if not isinstance(trigger_id, int) or trigger_id <= 0:
        raise ExportTriggerError("trigger_id must be > 0")
    store = get_store()
    trig = store.get(trigger_id)
    if trig is None:
        raise ExportTriggerError(f"trigger not found: {trigger_id}")
    if not trig.enabled:
        raise ExportTriggerError(
            f"trigger {trigger_id} is disabled"
        )
    success = True
    detail: dict = {"artifact_id": trig.artifact_id}
    if export_fn is not None:
        try:
            export_result = await export_fn(trig.artifact_id)
            if isinstance(export_result, dict):
                detail.update({"export": export_result})
        except Exception as e:
            success = False
            detail.update({"error": str(e)})
    store.mark_fired(trigger_id)
    return FireResult(
        trigger_id=trigger_id,
        artifact_id=trig.artifact_id,
        trigger_type=trig.trigger_type,
        fired_at=time.time(),
        success=success,
        detail=detail,
    )
