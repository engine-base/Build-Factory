"""
design_pipeline.py — Phase A デザイン連鎖 API

GET  /api/design-pipeline/{workspace_id}             進捗取得
POST /api/design-pipeline/{workspace_id}/step/{n}    1 ステップ実行
POST /api/design-pipeline/{workspace_id}/run         全ステップ連続実行
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import design_pipeline as dp

router = APIRouter(prefix="/api/design-pipeline", tags=["design-pipeline"])


class StepRequest(BaseModel):
    user_input: Optional[str] = None
    helper_provider: str = "openai"
    helper_model: str = "gpt-4o-mini"


class RunRequest(BaseModel):
    user_input: str
    skip_optional: bool = True
    helper_provider: str = "openai"
    helper_model: str = "gpt-4o-mini"


@router.get("/{workspace_id}")
async def get_state(workspace_id: int):
    return await dp.get_pipeline_state(workspace_id)


@router.post("/{workspace_id}/step/{step_no}")
async def run_step(workspace_id: int, step_no: int, body: StepRequest):
    try:
        return await dp.kickoff_step(
            workspace_id, step_no,
            user_input=body.user_input,
            helper_provider=body.helper_provider,
            helper_model=body.helper_model,
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.post("/{workspace_id}/run")
async def run_full(workspace_id: int, body: RunRequest):
    return await dp.run_full_pipeline(
        workspace_id, body.user_input,
        skip_optional=body.skip_optional,
        helper_provider=body.helper_provider,
        helper_model=body.helper_model,
    )
