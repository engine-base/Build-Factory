"""T-M28-01: Context Builder REST API.

- POST /api/context/build              build_context (Mem0 + Obsidian + Constitution + D-XXX)
- GET  /api/context/decisions/{id}     D-XXX で Constitution を引く
- GET  /api/context/constitution       preload_constitution の結果を返す
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.context_builder import (
    build_context, lookup_decision, preload_constitution, DECISION_REF_RE,
)


router = APIRouter(prefix="/api/context", tags=["context"])


class BuildRequest(BaseModel):
    user_message: str = Field(..., min_length=1)
    session_id: int
    prior_session_id: Optional[int] = None
    user_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_constitution: bool = True


@router.post("/build")
async def build(req: BuildRequest) -> dict:
    return await build_context(
        user_message=req.user_message,
        session_id=req.session_id,
        prior_session_id=req.prior_session_id,
        user_id=req.user_id,
        top_k=req.top_k,
        include_constitution=req.include_constitution,
    )


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str) -> dict:
    if not DECISION_REF_RE.fullmatch(decision_id):
        raise HTTPException(status_code=400, detail="invalid decision_id format (expect D-XXX)")
    d = lookup_decision(decision_id)
    if not d:
        raise HTTPException(status_code=404, detail=f"decision not found: {decision_id}")
    return d


@router.get("/constitution")
async def get_constitution(user_id: str = "masato") -> dict:
    return {"constitution": await preload_constitution(user_id)}
