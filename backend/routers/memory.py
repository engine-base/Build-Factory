"""T-020-02: Memory 3 tier REST API.

- POST /api/memory/recall          merge_for_session の結果を取得
- POST /api/memory/compaction      9-section summary を chat_messages に保存
- POST /api/memory/fact            durable fact (Memory API + Mem0)
- GET  /api/memory/events          audit_logs (event_type フィルタ可)
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.memory_service import (
    merge_for_session, persist_compaction, write_fact, emit_event,
    mirror_to_obsidian,
)


router = APIRouter(prefix="/api/memory", tags=["memory"])


class RecallRequest(BaseModel):
    session_id: int
    prior_session_id: Optional[int] = None
    user_message: str = Field(..., min_length=1)
    user_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class RecallResponse(BaseModel):
    memory_block: str


@router.post("/recall", response_model=RecallResponse)
async def recall(req: RecallRequest) -> RecallResponse:
    block = await merge_for_session(
        session_id=req.session_id,
        prior_session_id=req.prior_session_id,
        user_message=req.user_message,
        user_id=req.user_id,
        top_k=req.top_k,
    )
    return RecallResponse(memory_block=block)


class CompactionRequest(BaseModel):
    session_id: int
    summary: dict


@router.post("/compaction")
async def compaction(req: CompactionRequest) -> dict:
    if not req.summary:
        raise HTTPException(status_code=400, detail="summary is empty")
    msg_id = await persist_compaction(req.session_id, req.summary)
    return {"ok": True, "summary_message_id": msg_id}


class FactRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    fact_text: str = Field(..., min_length=1)
    kind: str = Field(default="durable")
    obsidian_title: Optional[str] = None


@router.post("/fact")
async def fact(req: FactRequest) -> dict:
    result = await write_fact(req.user_id, req.fact_text, kind=req.kind)
    obsidian_path = None
    if req.obsidian_title:
        p = mirror_to_obsidian(req.user_id, req.fact_text, req.obsidian_title)
        obsidian_path = str(p) if p else None
    return {**result, "obsidian_path": obsidian_path}


@router.get("/events")
async def events(
    event_type: Optional[str] = None,
    session_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict]:
    from services.memory_service import _db, _db_path
    sql = "SELECT * FROM audit_logs WHERE 1=1"
    args: list = []
    if event_type:
        sql += " AND event_type = ?"
        args.append(event_type)
    if session_id is not None:
        sql += " AND session_id = ?"
        args.append(session_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(min(max(limit, 1), 500))
    async with _db().connect(_db_path()) as db:
        db.row_factory = _db().Row
        cur = await db.execute(sql, tuple(args))
        rows = await cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("detail_json"):
            try:
                d["detail"] = json.loads(d["detail_json"])
            except json.JSONDecodeError:
                d["detail"] = None
        out.append(d)
    return out
