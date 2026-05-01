"""
workflows.py — マルチエージェント・ワークフロー API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.workflow_service import (
    run_workflow,
    list_workflows,
    get_workflow_detail,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowRunRequest(BaseModel):
    request: str


@router.get("")
async def api_list_workflows(limit: int = 30):
    """ワークフロー実行履歴の一覧。"""
    return await list_workflows(limit=limit)


@router.get("/{workflow_id}")
async def api_get_workflow(workflow_id: int):
    """ワークフロー詳細（ステップ別の入出力含む）。"""
    detail = await get_workflow_detail(workflow_id)
    if not detail:
        raise HTTPException(404, "workflow not found")
    return detail


@router.post("/run")
async def api_run_workflow(body: WorkflowRunRequest):
    """マルチエージェント・ワークフローを即時実行する。"""
    result = await run_workflow(body.request)
    return result
