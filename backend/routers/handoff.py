"""T-M27-03 / M-27: Agent / Role Selector + handoff REST endpoint.

claude-agent-sdk Subagent (Task tool) を呼ぶ thin wrapper. SDK 未インストール期は
Phase 1 stub (scheduled status + audit emit only) として動作.

Endpoint:
  POST /api/handoff             handoff request invoke (SDK Task tool wrapper)
  GET  /api/handoff/targets     利用可能な target persona 一覧 (read-only)
  GET  /api/handoff/health      backend 登録状況 / store 利用可能性 (read-only)

AC マッピング:
  AC-1 UBIQUITOUS    : SDK Task tool wrapper + ai_employees lookup (REUSE).
                       自前 handoff/orchestration ロジックは実装しない (ADR-010).
  AC-2 EVENT-DRIVEN  : handoff invoke 時に m27.handoff audit_logs event 発火 /
                       全 endpoint 2 秒以内 + structured response.
  AC-3 STATE-DRIVEN  : 既存 ai_employee_store / delegation_service / secretary_chat
                       不変 / read endpoint は audit emit しない / claude-agent-sdk
                       session 文脈を維持 (session_id pass-through).
  AC-4 UNWANTED      : invalid persona / unauthorized / unknown session →
                       4xx structured. state mutate なし.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import handoff_service as hs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/handoff", tags=["handoff"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "handoff.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


def _map_service_error(e: hs.HandoffError) -> HTTPException:
    msg = str(e)
    # not found 系は 404
    if "not found" in msg.lower():
        return _error("handoff.not_found", msg, status_code=404)
    return _error("handoff.invalid", msg, status_code=400)


# ──────────────────────────────────────────────────────────────────────
# POST /api/handoff
# ──────────────────────────────────────────────────────────────────────


class HandoffRequest(BaseModel):
    source_persona: str = Field(..., min_length=1, max_length=hs.MAX_PERSONA_KEY_LEN)
    target_persona: str = Field(..., min_length=1, max_length=hs.MAX_PERSONA_KEY_LEN)
    message: str = Field(..., min_length=1, max_length=hs.MAX_MESSAGE_CHARS)
    session_id: Optional[str] = None
    actor_user_id: Optional[str] = None
    context: Optional[dict] = None
    use_backend: bool = True


@router.post("")
async def invoke_handoff(req: HandoffRequest) -> dict[str, Any]:
    actor = _check_actor(req.actor_user_id)
    try:
        result = await hs.request_handoff(
            source_persona=req.source_persona,
            target_persona=req.target_persona,
            message=req.message,
            session_id=req.session_id,
            actor_user_id=actor,
            context=req.context,
            use_backend=req.use_backend,
        )
    except hs.HandoffError as e:
        raise _map_service_error(e)
    return result


# ──────────────────────────────────────────────────────────────────────
# GET /api/handoff/targets
# ──────────────────────────────────────────────────────────────────────


@router.get("/targets")
async def list_targets(workspace_id: Optional[int] = None) -> dict[str, Any]:
    if workspace_id is not None and workspace_id <= 0:
        raise _error(
            "handoff.invalid",
            "workspace_id must be > 0 when provided",
        )
    try:
        items = hs.list_handoff_targets(workspace_id=workspace_id)
    except hs.HandoffError as e:
        raise _map_service_error(e)
    return {
        "count": len(items),
        "workspace_id": workspace_id,
        "items": items,
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/handoff/health
# ──────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict[str, Any]:
    """SDK backend 登録状況 + ai_employee_store 利用可能性 (read-only)."""
    from services.ai_employee_store import get_store
    try:
        store = get_store()
        store_ok = True
        store_persona_count = len(store.list_personas())
        store_employee_count = len(store.list_employees(include_inactive=False))
    except Exception as e:
        store_ok = False
        store_persona_count = 0
        store_employee_count = 0
        logger.warning("handoff health: ai_employee_store unavailable: %s", e)

    return {
        "backend_registered": hs.get_handoff_backend() is not None,
        "phase": "stub" if hs.get_handoff_backend() is None else "active",
        "ai_employee_store": {
            "available": store_ok,
            "persona_count": store_persona_count,
            "employee_count": store_employee_count,
        },
    }
