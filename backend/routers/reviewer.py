"""
reviewer.py — レビュアー AI 壁打ちループ API

POST /api/reviewer/request                レビュー依頼作成（pending）
POST /api/reviewer/{id}/execute           レビュー実行（壁打ち）
GET  /api/reviewer/{id}                   詳細取得
GET  /api/reviewer?workspace_id=N         一覧
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import reviewer_loop as rl

router = APIRouter(prefix="/api/reviewer", tags=["reviewer"])


class ReviewRequest(BaseModel):
    task_id: Optional[int] = None
    workspace_id: Optional[int] = None
    review_kind: str = "task_review"  # task_review / integration
    target_artifact_ids: Optional[list[str]] = None
    summary: str = ""


class ExecuteRequest(BaseModel):
    helper_provider: str = "openai"
    helper_model: str = "gpt-4o-mini"


@router.post("/request")
async def request_review(body: ReviewRequest):
    try:
        return await rl.request_review(
            task_id=body.task_id,
            workspace_id=body.workspace_id,
            review_kind=body.review_kind,
            target_artifact_ids=body.target_artifact_ids,
            summary=body.summary,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{review_id}/execute")
async def execute_review(review_id: int, body: ExecuteRequest):
    try:
        return await rl.execute_review(
            review_id,
            helper_provider=body.helper_provider,
            helper_model=body.helper_model,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.get("/{review_id}")
async def get_review(review_id: int):
    r = await rl.get_review(review_id)
    if not r:
        raise HTTPException(404, "review not found")
    return r


@router.get("")
async def list_reviews(workspace_id: Optional[int] = None, limit: int = 30):
    return {"reviews": await rl.list_reviews(workspace_id=workspace_id, limit=limit)}
