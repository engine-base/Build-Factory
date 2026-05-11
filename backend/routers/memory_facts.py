"""T-AI-01: Memory Facts REST API.

- POST   /api/memory/facts              fact 1 件追加
- POST   /api/memory/facts/extract      session_id を渡して D-XXX を抽出
- GET    /api/memory/facts/recall       user_id + query で top_k recall (<200ms)
- DELETE /api/memory/facts/{fact_id}    soft-delete + 24h 後 physical delete
- POST   /api/memory/facts/process-retry-queue   失敗 fact の再送
- POST   /api/memory/facts/process-deletions     soft-delete を実削除
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.memory_facts import (
    extract_facts_from_session, process_pending_deletions,
    process_retry_queue, recall_facts, request_deletion, write_fact,
)


router = APIRouter(prefix="/api/memory/facts", tags=["memory_facts"])


class WriteFactRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    fact_text: str = Field(..., min_length=1)
    source_session_id: Optional[int] = None
    workspace_id: Optional[str] = None
    confidence_score: float = Field(default=0.7, ge=0.0, le=1.0)
    kind: str = "durable"


@router.post("")
async def create_fact(body: WriteFactRequest) -> dict:
    rec = await write_fact(
        user_id=body.user_id, fact_text=body.fact_text,
        source_session_id=body.source_session_id,
        workspace_id=body.workspace_id,
        confidence_score=body.confidence_score, kind=body.kind,
    )
    if rec is None:
        raise HTTPException(status_code=500, detail="failed to persist fact")
    return rec.to_dict()


class ExtractRequest(BaseModel):
    session_id: int
    user_id: str
    workspace_id: Optional[str] = None
    confidence_score: float = Field(default=0.7, ge=0.0, le=1.0)


@router.post("/extract")
async def extract(body: ExtractRequest) -> dict:
    facts = await extract_facts_from_session(
        session_id=body.session_id, user_id=body.user_id,
        workspace_id=body.workspace_id,
        confidence_score=body.confidence_score,
    )
    return {"extracted": len(facts), "facts": [f.to_dict() for f in facts]}


@router.get("/recall")
async def recall(user_id: str, query: str, top_k: int = 5) -> dict:
    facts = await recall_facts(user_id=user_id, query=query, top_k=top_k)
    return {"count": len(facts), "facts": [f.to_dict() for f in facts]}


@router.delete("/{fact_id}")
async def delete(fact_id: int, user_id: str) -> dict:
    ok = await request_deletion(fact_id=fact_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="fact not found or already deleted")
    return {"ok": True, "fact_id": fact_id, "scheduled_physical_delete_within": "24h"}


@router.post("/process-retry-queue")
async def process_retry(max_items: int = 50) -> dict:
    return await process_retry_queue(max_items=max_items)


@router.post("/process-deletions")
async def process_deletions(dry_run: bool = False) -> dict:
    return await process_pending_deletions(dry_run=dry_run)
