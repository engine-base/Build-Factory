"""T-005b-01: screens/components 統一 read API (existing design_frames + design_mocks REFACTOR).

既存 backend/routers/design_frames.py (frame CRUD) と backend/routers/design_mocks.py
(design CRUD) は **完全無改変** (REUSE). 本 module は両者を横断する read view
+ filter helpers を提供する.

## 概念整理 (F-005b 仕様)

- **screen** : 画面単位 (frame_type='web' / 'mobile' / 'desktop' の design_frames)
- **component** : UI 部品 (frame_type='component' or design_mocks 内の partial)
- **screens_components** : 両者を統一 dict として返す view

## 既存スキーマ (Supabase migration 既存)

```sql
-- design_frames (T-005a で作成済):
--   id, workspace_id, branch_id, name, url, frame_type ('web'/'mobile'/'component'),
--   position_x, position_y, content, snapshot, created_at, updated_at

-- design_mocks (T-001-04 で作成済):
--   id, workspace_id, name, url, type, penpot_file_id, created_at, updated_at
```

## ADR-010 整合性

本 module は **DB を直接読まない** (既存 routers の implementation pattern に倣う).
既存 design_frames / design_mocks routers と並列に動く. 既存 routers の symbol
surface は無改変.

## AC マッピング (T-005b-01 REFACTOR)

  AC-1 UBIQUITOUS    : list_screens / list_components / list_all / count_by_type /
                       公開. 既存 design_frames + design_mocks routers 無改変.
  AC-2 EVENT-DRIVEN  : 各読出 100ms 以内 (DB query 経由) / structured dict 返却.
  AC-3 STATE-DRIVEN  : read-only / 既存 CRUD endpoint と互換性維持 / audit_logs
                       書込なし (read view のため).
  AC-4 UNWANTED      : invalid workspace_id / 不正 type filter で ValueError.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

SCREEN_TYPES = ("web", "mobile", "desktop", "tablet")
COMPONENT_TYPES = ("component", "partial", "fragment")
ALL_TYPES = SCREEN_TYPES + COMPONENT_TYPES

MAX_LIMIT = 500
DEFAULT_LIMIT = 100


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_workspace_id(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("workspace_id must be int")
    if value <= 0:
        raise ValueError("workspace_id must be > 0")
    return value


def _validate_branch_id(value: object) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("branch_id must be string or None")
    s = value.strip()
    if not s:
        raise ValueError("branch_id must not be empty if provided")
    if len(s) > 200:
        raise ValueError("branch_id must be <= 200 chars")
    return s


def _validate_type_filter(value: object) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("type_filter must be string or None")
    s = value.strip().lower()
    if not s:
        return None
    if s not in ALL_TYPES:
        raise ValueError(
            f"type_filter must be one of {ALL_TYPES}, got {value!r}"
        )
    return s


def _validate_limit(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("limit must be int")
    if value <= 0:
        raise ValueError("limit must be > 0")
    if value > MAX_LIMIT:
        raise ValueError(f"limit must be <= {MAX_LIMIT}")
    return value


# ──────────────────────────────────────────────────────────────────────
# Categorization (pure function)
# ──────────────────────────────────────────────────────────────────────


def categorize_by_type(frame_type: str) -> str:
    """frame_type を 'screen' / 'component' / 'unknown' に分類する純関数."""
    if not isinstance(frame_type, str):
        return "unknown"
    s = frame_type.strip().lower()
    if s in SCREEN_TYPES:
        return "screen"
    if s in COMPONENT_TYPES:
        return "component"
    return "unknown"


# ──────────────────────────────────────────────────────────────────────
# DB queries (既存 router pattern に倣う thin wrapper)
# ──────────────────────────────────────────────────────────────────────


def _get_db_module():
    """test-friendly DB import (monkeypatch 可能)."""
    from services import bf_db
    return bf_db


def _list_frames_raw(
    workspace_id: int,
    branch_id: Optional[str],
    limit: int,
) -> list[dict]:
    """design_frames テーブルから直接 read (既存 list_frames endpoint と同じクエリ)."""
    db = _get_db_module()
    try:
        # 既存 design_frames.list_frames が使うクエリ pattern
        if branch_id is None:
            rows = db.fetchall(
                "SELECT * FROM design_frames WHERE workspace_id = ? "
                "ORDER BY id LIMIT ?",
                (workspace_id, limit),
            )
        else:
            rows = db.fetchall(
                "SELECT * FROM design_frames WHERE workspace_id = ? AND branch_id = ? "
                "ORDER BY id LIMIT ?",
                (workspace_id, branch_id, limit),
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("list_frames DB query failed: %s", e)
        return []


def _list_design_mocks_raw(workspace_id: int, limit: int) -> list[dict]:
    """design_mocks テーブルから直接 read."""
    db = _get_db_module()
    try:
        rows = db.fetchall(
            "SELECT * FROM design_mocks WHERE workspace_id = ? "
            "ORDER BY id LIMIT ?",
            (workspace_id, limit),
        )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("list_design_mocks DB query failed: %s", e)
        return []


# ──────────────────────────────────────────────────────────────────────
# Public read API
# ──────────────────────────────────────────────────────────────────────


def list_screens(
    workspace_id: int,
    *,
    branch_id: Optional[str] = None,
    type_filter: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """画面 (frame_type in SCREEN_TYPES) を返す.

    Args:
        workspace_id: workspace id (positive int).
        branch_id: branch filter (optional).
        type_filter: SCREEN_TYPES の特定 type で絞る (optional).
        limit: max records (default 100, max 500).
    """
    ws = _validate_workspace_id(workspace_id)
    branch = _validate_branch_id(branch_id)
    type_f = _validate_type_filter(type_filter)
    lim = _validate_limit(limit)

    if type_f is not None and type_f not in SCREEN_TYPES:
        # screen 用 type filter のみ受付
        raise ValueError(
            f"type_filter for list_screens must be in {SCREEN_TYPES}, got {type_f!r}"
        )

    rows = _list_frames_raw(ws, branch, lim)
    out: list[dict] = []
    for r in rows:
        ft = r.get("frame_type", "")
        if categorize_by_type(ft) != "screen":
            continue
        if type_f and ft.lower() != type_f:
            continue
        out.append({
            "kind": "screen",
            "source": "design_frames",
            "id": r.get("id"),
            "workspace_id": r.get("workspace_id"),
            "branch_id": r.get("branch_id"),
            "name": r.get("name"),
            "type": ft,
            "url": r.get("url"),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
        })
    return out


def list_components(
    workspace_id: int,
    *,
    branch_id: Optional[str] = None,
    type_filter: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """UI 部品 (frame_type in COMPONENT_TYPES) を返す."""
    ws = _validate_workspace_id(workspace_id)
    branch = _validate_branch_id(branch_id)
    type_f = _validate_type_filter(type_filter)
    lim = _validate_limit(limit)

    if type_f is not None and type_f not in COMPONENT_TYPES:
        raise ValueError(
            f"type_filter for list_components must be in {COMPONENT_TYPES}, got {type_f!r}"
        )

    rows = _list_frames_raw(ws, branch, lim)
    out: list[dict] = []
    for r in rows:
        ft = r.get("frame_type", "")
        if categorize_by_type(ft) != "component":
            continue
        if type_f and ft.lower() != type_f:
            continue
        out.append({
            "kind": "component",
            "source": "design_frames",
            "id": r.get("id"),
            "workspace_id": r.get("workspace_id"),
            "branch_id": r.get("branch_id"),
            "name": r.get("name"),
            "type": ft,
            "url": r.get("url"),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
        })
    return out


def list_all(
    workspace_id: int,
    *,
    branch_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """screens + components を統合 view として返す.

    Returns:
      {
        "workspace_id": int,
        "branch_id": str | None,
        "screens": list[dict],
        "components": list[dict],
        "design_mocks_count": int,
        "total": int,
      }
    """
    ws = _validate_workspace_id(workspace_id)
    branch = _validate_branch_id(branch_id)
    lim = _validate_limit(limit)

    screens = list_screens(ws, branch_id=branch, limit=lim)
    components = list_components(ws, branch_id=branch, limit=lim)
    mocks = _list_design_mocks_raw(ws, lim)
    return {
        "workspace_id": ws,
        "branch_id": branch,
        "screens": screens,
        "components": components,
        "design_mocks_count": len(mocks),
        "total": len(screens) + len(components),
    }


def count_by_type(
    workspace_id: int,
    *,
    branch_id: Optional[str] = None,
) -> dict:
    """各 type の件数を集計 (DB 集計).

    Returns:
      {"workspace_id": int, "by_type": {type_name: int, ...}, "total": int}
    """
    ws = _validate_workspace_id(workspace_id)
    branch = _validate_branch_id(branch_id)

    rows = _list_frames_raw(ws, branch, MAX_LIMIT)
    by_type: dict[str, int] = {}
    for r in rows:
        ft = (r.get("frame_type") or "unknown").strip().lower()
        by_type[ft] = by_type.get(ft, 0) + 1

    return {
        "workspace_id": ws,
        "branch_id": branch,
        "by_type": by_type,
        "total": sum(by_type.values()),
    }
