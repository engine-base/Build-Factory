"""
hearing.py — Phase 1 ヒアリング 対話駆動 API

POST /api/workspaces/{id}/hearing/start-step    body: { step: int }
POST /api/workspaces/{id}/hearing/reply          body: { step: int, message: str }
POST /api/workspaces/{id}/hearing/complete-step  body: { step: int }
GET  /api/workspaces/{id}/hearing/state          全 STEP の状態取得
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import hearing_service as hs

router = APIRouter(prefix="/api/workspaces", tags=["hearing"])


class StartStepBody(BaseModel):
    step: int


class ReplyBody(BaseModel):
    step: int
    message: str


class CompleteStepBody(BaseModel):
    step: int


class CenterUpdateBody(BaseModel):
    center: dict
    edited_by_pm: bool = True


VALID_STEPS = (1, 2, 3, 4)  # T-005-01 / F-005: hearing AI Mary 4STEP


def _ensure_valid_step(step: int) -> None:
    """T-005-01 AC-4: step は 4STEP のいずれか."""
    if step not in VALID_STEPS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_step",
                "message": f"step must be one of {list(VALID_STEPS)}, got {step}",
            },
        )


@router.post("/{workspace_id}/hearing/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    _ensure_valid_step(body.step)
    res = await hs.start_step(workspace_id, body.step)
    if "error" in res:
        raise HTTPException(
            status_code=400,
            detail={"code": "hearing_start_failed", "message": str(res["error"])},
        )
    return res


@router.post("/{workspace_id}/hearing/reply")
async def reply(workspace_id: int, body: ReplyBody):
    _ensure_valid_step(body.step)
    if not body.message.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_message", "message": "message must not be empty"},
        )
    return await hs.reply(workspace_id, body.step, body.message.strip())


@router.post("/{workspace_id}/hearing/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    _ensure_valid_step(body.step)
    return await hs.complete_step(workspace_id, body.step)


@router.get("/{workspace_id}/hearing/state")
async def get_state(workspace_id: int):
    return await hs.get_state(workspace_id)


@router.patch("/{workspace_id}/hearing/center")
async def update_center(workspace_id: int, body: CenterUpdateBody, step: int):
    """PM の直接編集 (BlockNote 経由) を反映."""
    _ensure_valid_step(step)
    art = await hs.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = True
    updated = await hs.update_center_artifact(art["id"], center)
    return {"artifact": updated, "center": center}
