"""T-V3-B-22 / F-016: Workspace-scoped knowledge base REST endpoints.

Endpoints:
  GET /api/workspaces/{id}/knowledge           list KnowledgeItem[]
  GET /api/workspaces/{id}/knowledge/search    hybrid search KnowledgeHit[]

仕様参照:
  - docs/api-design/2026-05-16_v3/openapi.yaml (/api/workspaces/{id}/knowledge[/search])
  - docs/functional-breakdown/2026-05-16_v3/features.json#F-016
  - docs/audit/2026-05-16_v3/T-V3-B-22.md

AC マッピング (T-V3-B-22 tickets-group-b-backend.json):
  AC-F1 EVENT-DRIVEN: search が pgvector + pg_trgm + FTS を合成し top 50 を返す
        → impl: backend/services/knowledge.py::hybrid_search (lines 175-275)
  AC-F2 EVENT-DRIVEN: GET /knowledge が 2xx + items (F-016 contract)
        → impl: backend/routers/knowledge.py::list_knowledge (lines 51-95)
  AC-F3 UNWANTED:     auth 不在 → 401
        → impl: backend/routers/knowledge.py::_require_actor (lines 38-49)
  AC-F4 UNWANTED:     invalid input → 422 field-level error map
        → impl: backend/routers/knowledge.py::list_knowledge (lines 51-95)
  AC-F5 EVENT-DRIVEN: GET /knowledge/search が 2xx + hits (F-016 contract)
        → impl: backend/routers/knowledge.py::search_knowledge (lines 98-140)
  AC-F6 UNWANTED:     auth 不在 → 401
        → impl: backend/routers/knowledge.py::_require_actor (lines 38-49)
  AC-F7 UNWANTED:     invalid input (q 空 / 500 字超 / limit<=0) → 422
        → impl: backend/routers/knowledge.py::search_knowledge (lines 98-140)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services import knowledge as svc

logger = logging.getLogger(__name__)

# /api/workspaces/{id}/knowledge[/search] を提供する.
router = APIRouter(prefix="/api/workspaces", tags=["knowledge"])


def _error(code: str, message: str, *, status_code: int = 400,
           field_errors: Optional[dict[str, str]] = None) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if field_errors is not None:
        detail["field_errors"] = field_errors
    return HTTPException(status_code=status_code, detail=detail)


def _require_actor(authorization: Optional[str], user_id: Optional[str]) -> str:
    """AC-F3 / AC-F6 UNWANTED:
    `Authorization: Bearer <token>` ヘッダ または `?user_id=` が必要.
    どちらも無ければ 401.

    Build-Factory 既存の routers/* と整合させるため、本実装は token 真偽値を
    検査するのみで、verify 自体は middleware / RLS で実施する想定.
    """
    # Bearer token (任意): 形式チェック
    if authorization:
        a = authorization.strip()
        if not a.lower().startswith("bearer "):
            raise _error("knowledge.unauthorized",
                         "Authorization header must be 'Bearer <token>'",
                         status_code=401)
        token = a[7:].strip()
        if not token:
            raise _error("knowledge.unauthorized",
                         "bearer token must not be empty",
                         status_code=401)
        return f"token:{token[:8]}..."  # masked actor id
    # 既存 backend の慣例: query で user_id を渡す
    if user_id is not None:
        u = user_id.strip()
        if not u:
            raise _error("knowledge.unauthorized",
                         "user_id must not be empty",
                         status_code=401)
        return u
    raise _error("knowledge.unauthorized",
                 "missing Authorization header or user_id query param",
                 status_code=401)


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("knowledge audit emit failed: %s -- %s", event_type, e)


class KnowledgeItemOut(BaseModel):
    id: str
    title: str
    path: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    updated_at: Optional[str] = None


class KnowledgeHitOut(BaseModel):
    id: str
    title: str
    snippet: str
    score: float
    source: str


class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeItemOut]


class KnowledgeSearchResponse(BaseModel):
    hits: list[KnowledgeHitOut]


@router.get("/{workspace_id}/knowledge", response_model=KnowledgeListResponse)
async def list_knowledge(
    workspace_id: int,
    category: Optional[str] = Query(default=None, max_length=200),
    user_id: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
) -> KnowledgeListResponse:
    """AC-F2 EVENT-DRIVEN / AC-F3 UNWANTED 401 / AC-F4 UNWANTED 422.

    F-016 contract: returns { items: KnowledgeItem[] }.
    """
    # AC-F3 401 (auth)
    actor = _require_actor(authorization, user_id)
    # AC-F4 422 (input validation) — workspace_id <= 0 / category type
    if workspace_id <= 0:
        raise _error(
            "knowledge.invalid_workspace_id",
            "workspace_id must be a positive integer",
            status_code=422,
            field_errors={"workspace_id": "must be > 0"},
        )
    try:
        items = await svc.list_knowledge(workspace_id, category=category)
    except svc.KnowledgeServiceError as e:
        raise _error("knowledge.invalid_input", str(e), status_code=422)

    await _audit(
        "knowledge.listed",
        user_id=actor,
        detail={"workspace_id": workspace_id, "category": category, "count": len(items)},
    )
    return KnowledgeListResponse(
        items=[KnowledgeItemOut(**i.to_dict()) for i in items]
    )


@router.get("/{workspace_id}/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    workspace_id: int,
    q: str = Query(..., min_length=1, max_length=10000),
    limit: Optional[int] = Query(default=None, ge=1, le=svc.MAX_SEARCH_LIMIT),
    user_id: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
) -> KnowledgeSearchResponse:
    """AC-F1 / AC-F5 / AC-F6 401 / AC-F7 422.

    F-016 contract: returns { hits: KnowledgeHit[] } (top <= 50).
    """
    actor = _require_actor(authorization, user_id)
    if workspace_id <= 0:
        raise _error(
            "knowledge.invalid_workspace_id",
            "workspace_id must be a positive integer",
            status_code=422,
            field_errors={"workspace_id": "must be > 0"},
        )
    try:
        hits = await svc.hybrid_search(workspace_id, q=q, limit=limit)
    except svc.KnowledgeServiceError as e:
        # AC-F7: q 空 / 500 字超 / limit<=0
        field = "q" if "q " in str(e) or "q must" in str(e) else "limit"
        raise _error(
            "knowledge.invalid_input",
            str(e),
            status_code=422,
            field_errors={field: str(e)},
        )

    await _audit(
        "knowledge.searched",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "q_len": len(q),
            "limit": limit,
            "hits": len(hits),
        },
    )
    return KnowledgeSearchResponse(
        hits=[KnowledgeHitOut(**h.to_dict()) for h in hits]
    )
