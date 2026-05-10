"""T-021-03: Swarm 並列実行 REST API.

- POST   /api/swarm/start                 Swarm を起動
- GET    /api/swarm/{pool_id}             Pool + stats
- GET    /api/swarm/{pool_id}/cells       Cell 一覧 (per-cell log path 含む)
- POST   /api/swarm/{pool_id}/cancel      Pool 全 cell を cancel
- GET    /api/swarm/{pool_id}/redlines    Redline event 履歴
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.swarm import (
    ALLOWED_SIZES, start_swarm, get_pool, get_cells, cancel_pool, get_stats,
)
from services.swarm.models import fetch_redlines


router = APIRouter(prefix="/api/swarm", tags=["swarm"])


class StartRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    size: int = Field(..., description="4, 9, 16, or 64")
    task_prompt: str = Field(..., min_length=1)
    base_branch: str = Field(default="main")
    created_by: Optional[str] = None


class StartResponse(BaseModel):
    pool_id: int
    size: int
    status: str


@router.post("/start", response_model=StartResponse)
async def start(req: StartRequest) -> StartResponse:
    if req.size not in ALLOWED_SIZES:
        raise HTTPException(
            status_code=400,
            detail=f"size must be one of {ALLOWED_SIZES}, got {req.size}",
        )
    pool_id = await start_swarm(
        name=req.name, size=req.size, task_prompt=req.task_prompt,
        base_branch=req.base_branch, created_by=req.created_by,
    )
    return StartResponse(pool_id=pool_id, size=req.size, status="running")


@router.get("/{pool_id}")
async def read_pool(pool_id: int) -> dict:
    pool = await get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="pool not found")
    stats = await get_stats(pool_id)
    return {
        "id": pool.id,
        "name": pool.name,
        "size": pool.size,
        "status": pool.status,
        "base_branch": pool.base_branch,
        "created_at": pool.created_at,
        "started_at": pool.started_at,
        "completed_at": pool.completed_at,
        "stats": stats,
    }


@router.get("/{pool_id}/cells")
async def read_cells(pool_id: int) -> list[dict]:
    cells = await get_cells(pool_id)
    if not cells:
        raise HTTPException(status_code=404, detail="no cells for pool")
    return [
        {
            "id": c.id, "cell_index": c.cell_index,
            "worktree_path": c.worktree_path, "branch_name": c.branch_name,
            "status": c.status, "session_id": c.session_id,
            "exit_code": c.exit_code, "error_msg": c.error_msg,
            "log_path": c.log_path,
            "started_at": c.started_at, "completed_at": c.completed_at,
        }
        for c in cells
    ]


@router.post("/{pool_id}/cancel")
async def cancel(pool_id: int) -> dict:
    pool = await get_pool(pool_id)
    if not pool:
        raise HTTPException(status_code=404, detail="pool not found")
    await cancel_pool(pool_id)
    return {"ok": True, "pool_id": pool_id}


@router.get("/{pool_id}/redlines")
async def read_redlines(pool_id: int) -> list[dict]:
    events = await fetch_redlines(pool_id)
    return [
        {
            "id": e.id, "cell_id": e.cell_id, "event_type": e.event_type,
            "detail": e.detail, "detected_at": e.detected_at,
        }
        for e in events
    ]
