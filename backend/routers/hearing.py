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


@router.post("/{workspace_id}/hearing/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    res = await hs.start_step(workspace_id, body.step)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/{workspace_id}/hearing/reply")
async def reply(workspace_id: int, body: ReplyBody):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    return await hs.reply(workspace_id, body.step, body.message.strip())


@router.post("/{workspace_id}/hearing/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    return await hs.complete_step(workspace_id, body.step)


@router.get("/{workspace_id}/hearing/state")
async def get_state(workspace_id: int):
    return await hs.get_state(workspace_id)


@router.patch("/{workspace_id}/hearing/center")
async def update_center(workspace_id: int, body: CenterUpdateBody, step: int):
    """PM の直接編集 (BlockNote 経由) を反映。"""
    art = await hs.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = True
    updated = await hs.update_center_artifact(art["id"], center)
    return {"artifact": updated, "center": center}
