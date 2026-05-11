"""T-AI-03: chat_messages hybrid search REST API.

S-011 Global Search の backend。

- GET /api/search/chat?q=... &top_k=20 &user_id=... &workspace_id=...
- query に `date:2026-04` を含めると月単位フィルタ
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from services.chat_search import hybrid_search


router = APIRouter(prefix="/api/search", tags=["chat_search"])


@router.get("/chat")
async def search_chat(
    q: str,
    top_k: int = 20,
    user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    use_vector: bool = True,
) -> dict:
    """hybrid score で chat_messages を検索する。"""
    hits = await hybrid_search(
        q,
        user_id=user_id,
        workspace_id=workspace_id,
        top_k=top_k,
        use_vector=use_vector,
    )
    return {"count": len(hits), "results": [h.to_dict() for h in hits]}
