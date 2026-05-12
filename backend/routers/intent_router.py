"""T-M27-01b: Intent Router entry node REST endpoint.

ADR-010 (T-M27-01 supersede): LangGraph 不使用 / claude-agent-sdk runtime.

Endpoint:
  POST /api/intent-router/dispatch   user_message + session_id → chosen_persona

AC マッピング:
  AC-1 UBIQUITOUS    : LangGraph 不使用; 入出力は user_message + session_id
                       → chosen_persona (persona key string).
  AC-2 EVENT-DRIVEN  : 2 秒以内に応答 + m27.entry_node.dispatched audit emit.
  AC-3 STATE-DRIVEN  : audit_logs RLS は memory_service 側 / session 記録は
                       best-effort (本 endpoint は read-only routing decision).
  AC-4 UNWANTED      : invalid input / unauthorized → 4xx {detail:{code,message}}
                       / LangGraph import は lint で fail.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import intent_router_entry as ire

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intent-router", tags=["intent-router"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_service_error(e: ire.IntentRouterEntryError) -> HTTPException:
    msg = str(e)
    if "actor_user_id must not be empty" in msg:
        return _error("intent_router.unauthorized", msg, status_code=401)
    return _error("intent_router.invalid", msg, status_code=400)


class DispatchRequest(BaseModel):
    user_message: str = Field(..., min_length=1, max_length=ire.MAX_MESSAGE_CHARS)
    session_id: str = Field(..., min_length=1, max_length=ire.MAX_SESSION_ID_LEN)
    actor_user_id: Optional[str] = None
    history: Optional[list[dict]] = None
    rules_only: bool = False


@router.post("/dispatch")
async def dispatch(req: DispatchRequest) -> dict[str, Any]:
    try:
        return await ire.dispatch(
            req.user_message,
            req.session_id,
            actor_user_id=req.actor_user_id,
            history=req.history,
            rules_only=req.rules_only,
        )
    except ire.IntentRouterEntryError as e:
        raise _map_service_error(e)


@router.get("/personas")
async def list_personas() -> dict[str, Any]:
    """既知 persona 一覧 + skill -> persona マッピング (read-only)."""
    return {
        "default_persona": ire.DEFAULT_PERSONA,
        "valid_personas": list(ire.VALID_PERSONA_KEYS),
        "persona_by_skill": dict(ire.PERSONA_BY_SKILL),
    }
