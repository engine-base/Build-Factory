"""
template_builder.py — テンプレビルダー対話駆動 API

Account 単位 (workspace 単位ではない) で動作。
6 STEP で User Base Template (account_settings.template_config) を組み立てる。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import template_builder_service as svc

router = APIRouter(prefix="/api/accounts", tags=["template-builder"])


class StartStepBody(BaseModel):
    step: int


class ReplyBody(BaseModel):
    step: int
    message: str


class CompleteStepBody(BaseModel):
    step: int


@router.post("/{account_id}/template-builder/start-step")
async def start_step(account_id: int, body: StartStepBody):
    res = await svc.start_step(account_id, body.step)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/{account_id}/template-builder/reply")
async def reply(account_id: int, body: ReplyBody):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    return await svc.reply(account_id, body.step, body.message.strip())


@router.post("/{account_id}/template-builder/complete-step")
async def complete_step(account_id: int, body: CompleteStepBody):
    return await svc.complete_step(account_id, body.step)


@router.get("/{account_id}/template-builder/state")
async def get_state(account_id: int):
    return await svc.get_state(account_id)
