"""T-023-05: クローン opt-in + GDPR 削除権 REST API.

- POST   /api/user/clone-optin     { user_id, opted_in } → 切替
- GET    /api/user/clone-optin     ?user_id=...         → 現在状態
- POST   /api/user/deletion        { user_id, reason }  → 削除リクエスト
- DELETE /api/user/deletion/{id}                         → grace 期間内 cancel
- GET    /api/user/deletion/pending ?due_only=          → pending 一覧
- POST   /api/user/deletion/execute-due [dry_run=true]   → 確定実行
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.user_lifecycle import (
    set_clone_optin, get_clone_optin,
    request_deletion, cancel_deletion,
    list_pending_deletions, execute_due_deletions,
    GRACE_DAYS,
)


router = APIRouter(prefix="/api/user", tags=["user_lifecycle"])


# ── clone opt-in ───────────────────────────────────────

class CloneOptinRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    opted_in: bool


@router.post("/clone-optin")
async def clone_optin(body: CloneOptinRequest) -> dict:
    result = await set_clone_optin(body.user_id, body.opted_in)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown"))
    return result


@router.get("/clone-optin")
async def clone_optin_status(user_id: str) -> dict:
    return {"user_id": user_id, "opted_in": await get_clone_optin(user_id)}


# ── GDPR deletion ──────────────────────────────────────

class DeletionRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    reason: Optional[str] = None
    grace_days: int = Field(default=GRACE_DAYS, ge=0, le=365)


@router.post("/deletion")
async def request_user_deletion(body: DeletionRequest) -> dict:
    result = await request_deletion(
        body.user_id, reason=body.reason, grace_days=body.grace_days,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "unknown"))
    return result


@router.delete("/deletion/{request_id}")
async def cancel_user_deletion(request_id: int) -> dict:
    ok = await cancel_deletion(request_id)
    if not ok:
        raise HTTPException(status_code=404, detail="request not found or not cancellable")
    return {"ok": True, "request_id": request_id}


@router.get("/deletion/pending")
async def pending_deletions(due_only: bool = False) -> list[dict]:
    return await list_pending_deletions(due_only=due_only)


@router.post("/deletion/execute-due")
async def execute_due(dry_run: bool = False) -> dict:
    return await execute_due_deletions(dry_run=dry_run)
