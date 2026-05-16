"""T-V3-B-09 / F-005b: Screen-flow backend service (graph nodes + edges).

F-005b 画面モック自動生成パイプライン (M-5b) — screen-flow map graph.

公開 API:
  - get_screen_flow(workspace_id) -> dict {nodes: [...], edges: [...]}
  - register_node(workspace_id, *, screen_id, name, kind) -> dict (test 用)
  - register_edge(workspace_id, *, from_screen_id, to_screen_id, trigger)
  - reset_store()  (test 用)

スコープ entities: E-011 Screen (workspace_scoped).

AC マッピング (T-V3-B-09):
  AC-F12 EVENT-DRIVEN  : GET /screen-flow → 2xx {nodes, edges}
  AC-F13 UNWANTED      : GET /screen-flow w/o token → 401 (router)
  AC-F14 UNWANTED      : GET /screen-flow bad input → 422
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


SCREEN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-:.]{1,64}$")


# ──────────────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────────────


class ScreenFlowError(RuntimeError):
    """generic screen-flow service error (mapped to 400)."""


class ScreenFlowValidationError(ScreenFlowError):
    """invalid input (mapped to 422)."""


# ──────────────────────────────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _NodeRecord:
    workspace_id: int
    screen_id: str
    name: str = ""
    kind: str = ""


@dataclass
class _EdgeRecord:
    workspace_id: int
    from_screen_id: str
    to_screen_id: str
    trigger: str = ""


@dataclass
class _Store:
    nodes: dict[tuple[int, str], _NodeRecord] = field(default_factory=dict)
    edges: list[_EdgeRecord] = field(default_factory=list)


_lock = threading.Lock()
_store = _Store()


def reset_store() -> None:
    """test 用 reset."""
    with _lock:
        _store.nodes.clear()
        _store.edges.clear()


# ──────────────────────────────────────────────────────────────────────
# Validators
# ──────────────────────────────────────────────────────────────────────


def _validate_workspace_id(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ScreenFlowValidationError("workspace_id must be int")
    if value <= 0:
        raise ScreenFlowValidationError("workspace_id must be > 0")
    return value


def _validate_screen_id(value: object) -> str:
    if not isinstance(value, str):
        raise ScreenFlowValidationError("screen_id must be string")
    s = value.strip()
    if not s:
        raise ScreenFlowValidationError("screen_id must not be empty")
    if not SCREEN_ID_PATTERN.match(s):
        raise ScreenFlowValidationError(
            "screen_id contains invalid chars "
            "(allowed: [A-Za-z0-9_-:.] up to 64)",
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Test fixtures / registration API
# ──────────────────────────────────────────────────────────────────────


def register_node(
    workspace_id: int,
    *,
    screen_id: str,
    name: str = "",
    kind: str = "screen",
) -> dict:
    """test 用 node 登録."""
    ws = _validate_workspace_id(workspace_id)
    sid = _validate_screen_id(screen_id)
    with _lock:
        rec = _NodeRecord(
            workspace_id=ws,
            screen_id=sid,
            name=name or sid,
            kind=kind or "screen",
        )
        _store.nodes[(ws, sid)] = rec
    return {"screen_id": rec.screen_id, "name": rec.name, "kind": rec.kind}


def register_edge(
    workspace_id: int,
    *,
    from_screen_id: str,
    to_screen_id: str,
    trigger: str = "",
) -> dict:
    """test 用 edge 登録."""
    ws = _validate_workspace_id(workspace_id)
    fr = _validate_screen_id(from_screen_id)
    to = _validate_screen_id(to_screen_id)
    if not isinstance(trigger, str):
        raise ScreenFlowValidationError("trigger must be string")
    with _lock:
        rec = _EdgeRecord(
            workspace_id=ws,
            from_screen_id=fr,
            to_screen_id=to,
            trigger=trigger,
        )
        _store.edges.append(rec)
    return {
        "from_screen_id": rec.from_screen_id,
        "to_screen_id": rec.to_screen_id,
        "trigger": rec.trigger,
    }


# ──────────────────────────────────────────────────────────────────────
# Public read API
# ──────────────────────────────────────────────────────────────────────


def get_screen_flow(workspace_id: int) -> dict:
    """画面遷移グラフを返す (AC-F12)."""
    ws = _validate_workspace_id(workspace_id)
    with _lock:
        nodes = [
            {
                "screen_id": rec.screen_id,
                "name": rec.name,
                "kind": rec.kind,
            }
            for (rec_ws, _sid), rec in _store.nodes.items()
            if rec_ws == ws
        ]
        nodes.sort(key=lambda n: n["screen_id"])
        edges = [
            {
                "from_screen_id": e.from_screen_id,
                "to_screen_id": e.to_screen_id,
                "trigger": e.trigger,
            }
            for e in _store.edges
            if e.workspace_id == ws
        ]
        edges.sort(key=lambda e: (e["from_screen_id"], e["to_screen_id"]))
    return {"nodes": nodes, "edges": edges}
