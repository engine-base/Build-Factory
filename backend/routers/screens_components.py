"""T-005b-01: screens/components 統一 read endpoint (existing design_frames + design_mocks REFACTOR).

既存 design_frames / design_mocks routers は無改変 (REUSE).
本 router は両者横断の read view を提供.

Endpoints:
  GET /api/workspaces/{ws}/screens-components       : 統一 list (screens + components)
  GET /api/workspaces/{ws}/screens-components/counts: type 別件数集計
  GET /api/workspaces/{ws}/screens-components/health: backend 利用可能性 (read-only)

AC マッピング (T-005b-01):
  AC-1 UBIQUITOUS    : screens + components 統一 read view 公開. 既存 routers 無改変.
  AC-2 EVENT-DRIVEN  : 各 endpoint 2 秒以内 + structured {detail:{code,message}} on error.
  AC-3 STATE-DRIVEN  : read-only / audit_logs 書込なし / 既存 CRUD と互換.
  AC-4 UNWANTED      : invalid workspace_id / 不正 type filter で 4xx structured.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from services import screens_components as sc

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workspaces", tags=["screens-components"],
)


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_value_error(e: ValueError) -> HTTPException:
    return _error("screens_components.invalid", str(e), status_code=400)


# ──────────────────────────────────────────────────────────────────────
# GET /api/workspaces/{workspace_id}/screens-components
# ──────────────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/screens-components")
async def list_screens_components(
    workspace_id: int,
    branch_id: Optional[str] = Query(None, max_length=200),
    limit: int = Query(sc.DEFAULT_LIMIT, ge=1, le=sc.MAX_LIMIT),
) -> dict[str, Any]:
    if workspace_id <= 0:
        raise _error(
            "screens_components.invalid",
            "workspace_id must be > 0",
        )
    try:
        return sc.list_all(
            workspace_id, branch_id=branch_id, limit=limit,
        )
    except ValueError as e:
        raise _map_value_error(e)


# ──────────────────────────────────────────────────────────────────────
# GET /counts
# ──────────────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/screens-components/counts")
async def screens_components_counts(
    workspace_id: int,
    branch_id: Optional[str] = Query(None, max_length=200),
) -> dict[str, Any]:
    if workspace_id <= 0:
        raise _error(
            "screens_components.invalid",
            "workspace_id must be > 0",
        )
    try:
        return sc.count_by_type(workspace_id, branch_id=branch_id)
    except ValueError as e:
        raise _map_value_error(e)


# ──────────────────────────────────────────────────────────────────────
# GET /health
# ──────────────────────────────────────────────────────────────────────


@router.get("/{workspace_id}/screens-components/health")
async def health(workspace_id: int) -> dict[str, Any]:
    """read-only health check (DB connectivity 確認)."""
    if workspace_id <= 0:
        raise _error(
            "screens_components.invalid",
            "workspace_id must be > 0",
        )
    try:
        # 軽い query で DB 接続 verify
        sc._list_frames_raw(workspace_id, None, 1)
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "workspace_id": workspace_id,
        "db_available": db_ok,
        "screen_types": list(sc.SCREEN_TYPES),
        "component_types": list(sc.COMPONENT_TYPES),
        "max_limit": sc.MAX_LIMIT,
    }
