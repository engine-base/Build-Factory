"""T-AI-02: Mem0 bridge REST API.

- GET  /api/memory/mem0/search        user_id + query で top-K re-rank
- GET  /api/memory/mem0/preload       secretary preload (top-50)
- POST /api/memory/mem0/divergence    Mem0 未同期 fact の検出 + audit
- POST /api/memory/mem0/mirror/{id}   1 件強制ミラー (失敗 fact の再同期用)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services.mem0_bridge import (
    detect_divergence, mirror_fact_to_mem0, preload_secretary_facts,
    search_with_rerank,
)


router = APIRouter(prefix="/api/memory/mem0", tags=["mem0_bridge"])


@router.get("/search")
async def search(user_id: str, query: str, top_k: int = 5) -> dict:
    scored = await search_with_rerank(user_id=user_id, query=query, top_k=top_k)
    return {
        "count": len(scored),
        "results": [
            {
                "fact": s.fact.to_dict(),
                "vector_score": s.vector_score,
                "confidence": s.confidence,
                "final_score": s.final_score,
            }
            for s in scored
        ],
    }


@router.get("/preload")
async def preload(user_id: str, top_n: int = 50) -> dict:
    facts = await preload_secretary_facts(user_id=user_id, top_n=top_n)
    return {"count": len(facts), "facts": [f.to_dict() for f in facts]}


@router.post("/divergence")
async def divergence(user_id: str, sample: int = 100) -> dict:
    return await detect_divergence(user_id=user_id, sample=sample)


@router.post("/mirror/{fact_id}")
async def mirror(fact_id: int) -> dict:
    """1 件の fact を Mem0 にミラーする (失敗 fact の再同期用)。"""
    # DB から FactRecord を取得
    try:
        from db import async_db as aiosqlite
        from db.queries import DB_PATH
        from services.memory_facts import _row_to_fact
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM memory_facts WHERE id = ?", (fact_id,)
            )
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="fact not found")
        fact = _row_to_fact(dict(row))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"db read failed: {e}")

    mem0_id = await mirror_fact_to_mem0(fact)
    return {"ok": mem0_id is not None, "mem0_id": mem0_id}
