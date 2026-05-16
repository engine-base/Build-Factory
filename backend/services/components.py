"""T-V3-B-09 / F-005b: Components backend service (catalog + usage).

F-005b 画面モック自動生成パイプライン (M-5b) — component catalog + usage.

公開 API:
  - list_components(workspace_id) -> dict {components: [...]}
  - get_component_usage(workspace_id, component_id) -> dict {usages: [...]}
  - register_component(workspace_id, *, id, name, type, ...) -> dict (test 用)
  - register_usage(workspace_id, component_id, screen_id, *, instance_count=1)
  - reset_store()  (test 用)

スコープ entities: E-012 Component / E-013 ScreenComponent (workspace_scoped).

ストレージ: in-memory store (mocks service と同様 pure-function 化).
将来 DB バックエンドへ差し替え可能.

AC マッピング (T-V3-B-09):
  AC-F6  EVENT-DRIVEN  : GET /components → {components: [...]}
  AC-F7  UNWANTED      : GET /components w/o token → 401 (handled at router)
  AC-F8  UNWANTED      : GET /components bad input → 422
  AC-F9  EVENT-DRIVEN  : GET /components/{id}/usage → {usages: [...]}
  AC-F10 UNWANTED      : GET /components/{id}/usage w/o token → 401 (router)
  AC-F11 UNWANTED      : GET /components/{id}/usage bad input → 422
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

COMPONENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-:.]{1,64}$")
SCREEN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-:.]{1,64}$")


# ──────────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────────


class ComponentError(RuntimeError):
    """generic component service error (mapped to 400)."""


class ComponentValidationError(ComponentError):
    """invalid input (mapped to 422)."""


class ComponentNotFoundError(ComponentError):
    """component not found (mapped to 404)."""


# ──────────────────────────────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _ComponentRecord:
    workspace_id: int
    component_id: str
    name: str = ""
    type: str = ""
    description: str = ""


@dataclass
class _UsageRecord:
    workspace_id: int
    component_id: str
    screen_id: str
    screen_name: str = ""
    instance_count: int = 1


@dataclass
class _Store:
    # key = (workspace_id, component_id)
    components: dict[tuple[int, str], _ComponentRecord] = field(default_factory=dict)
    # list of usage rows
    usages: list[_UsageRecord] = field(default_factory=list)


_lock = threading.Lock()
_store = _Store()


def reset_store() -> None:
    """test 用 reset."""
    with _lock:
        _store.components.clear()
        _store.usages.clear()


# ──────────────────────────────────────────────────────────────────────
# Validators
# ──────────────────────────────────────────────────────────────────────


def _validate_workspace_id(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ComponentValidationError("workspace_id must be int")
    if value <= 0:
        raise ComponentValidationError("workspace_id must be > 0")
    return value


def _validate_component_id(value: object) -> str:
    if not isinstance(value, str):
        raise ComponentValidationError("component_id must be string")
    s = value.strip()
    if not s:
        raise ComponentValidationError("component_id must not be empty")
    if not COMPONENT_ID_PATTERN.match(s):
        raise ComponentValidationError(
            "component_id contains invalid chars "
            "(allowed: [A-Za-z0-9_-:.] up to 64)",
        )
    return s


def _validate_screen_id(value: object) -> str:
    if not isinstance(value, str):
        raise ComponentValidationError("screen_id must be string")
    s = value.strip()
    if not s:
        raise ComponentValidationError("screen_id must not be empty")
    if not SCREEN_ID_PATTERN.match(s):
        raise ComponentValidationError(
            "screen_id contains invalid chars "
            "(allowed: [A-Za-z0-9_-:.] up to 64)",
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Test fixtures / registration API
# ──────────────────────────────────────────────────────────────────────


def register_component(
    workspace_id: int,
    *,
    id: str,
    name: str = "",
    type: str = "",
    description: str = "",
) -> dict:
    """test 用 component 登録. (production では DB seed)."""
    ws = _validate_workspace_id(workspace_id)
    cid = _validate_component_id(id)
    with _lock:
        rec = _ComponentRecord(
            workspace_id=ws,
            component_id=cid,
            name=name or cid,
            type=type,
            description=description,
        )
        _store.components[(ws, cid)] = rec
    return _serialize_component(rec)


def register_usage(
    workspace_id: int,
    component_id: str,
    screen_id: str,
    *,
    screen_name: str = "",
    instance_count: int = 1,
) -> dict:
    """test 用 usage 登録."""
    ws = _validate_workspace_id(workspace_id)
    cid = _validate_component_id(component_id)
    sid = _validate_screen_id(screen_id)
    if not isinstance(instance_count, int) or instance_count <= 0:
        raise ComponentValidationError("instance_count must be int > 0")
    with _lock:
        rec = _UsageRecord(
            workspace_id=ws,
            component_id=cid,
            screen_id=sid,
            screen_name=screen_name or sid,
            instance_count=instance_count,
        )
        _store.usages.append(rec)
    return {
        "screen_id": rec.screen_id,
        "screen_name": rec.screen_name,
        "instance_count": rec.instance_count,
    }


# ──────────────────────────────────────────────────────────────────────
# Public read API
# ──────────────────────────────────────────────────────────────────────


def list_components(workspace_id: int) -> dict:
    """workspace 内の全 component を返す (AC-F6)."""
    ws = _validate_workspace_id(workspace_id)
    with _lock:
        items = [
            _serialize_component(rec)
            for (rec_ws, _cid), rec in _store.components.items()
            if rec_ws == ws
        ]
        items.sort(key=lambda c: c["id"])
    return {"components": items}


def get_component_usage(workspace_id: int, component_id: str) -> dict:
    """component の screen 横断 usage を返す (AC-F9).

    component が存在しない場合は 404. usage が無い場合は {usages: []}.
    """
    ws = _validate_workspace_id(workspace_id)
    cid = _validate_component_id(component_id)
    with _lock:
        rec = _store.components.get((ws, cid))
        if rec is None:
            raise ComponentNotFoundError(
                f"component not found: workspace={ws} component={cid}",
            )
        usages = [
            {
                "screen_id": u.screen_id,
                "screen_name": u.screen_name,
                "instance_count": u.instance_count,
            }
            for u in _store.usages
            if u.workspace_id == ws and u.component_id == cid
        ]
        usages.sort(key=lambda u: u["screen_id"])
    return {"usages": usages}


# ──────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────


def _serialize_component(rec: _ComponentRecord) -> dict:
    return {
        "id": rec.component_id,
        "workspace_id": rec.workspace_id,
        "name": rec.name,
        "type": rec.type,
        "description": rec.description,
    }
