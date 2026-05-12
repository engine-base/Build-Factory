"""T-M28-02: Tier 1 tool result trimming REST endpoint (audit wrapper only).

ADR-010: trim 本体は claude-agent-sdk の内蔵機能.
application code は trimming logic を再実装しない (AC-4 UNWANTED).

Endpoint:
  POST /api/tier1/tool-result-trim   SDK の trim 完了 event を audit に記録.

AC マッピング:
  AC-1 UBIQUITOUS    : SDK 内蔵 trim 結果の audit 受信のみ.
  AC-2 EVENT-DRIVEN  : 2 秒以内に応答 + tier1.tool_result_trimmed audit emit.
  AC-3 STATE-DRIVEN  : chat_messages 不変 (SDK 側が保持) /
                       audit_logs RLS は memory_service 経由.
  AC-4 UNWANTED      : invalid input / unauthorized → 4xx {detail:{code,message}}.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import tier1_tool_trim as t1

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tier1", tags=["tier1-tool-trim"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_service_error(e: t1.Tier1ToolTrimError) -> HTTPException:
    msg = str(e)
    if "actor_user_id must not be empty" in msg:
        return _error("tier1.unauthorized", msg, status_code=401)
    return _error("tier1.invalid", msg, status_code=400)


class TrimEventRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=t1.MAX_SESSION_ID_LEN)
    original_size: int = Field(..., ge=0, le=t1.MAX_ORIGINAL_SIZE)
    trimmed_size: int = Field(..., ge=0, le=t1.MAX_ORIGINAL_SIZE)
    actor_user_id: Optional[str] = None
    tool_name: Optional[str] = None
    reason: Optional[str] = None


@router.post("/tool-result-trim")
async def tool_result_trim(req: TrimEventRequest) -> dict[str, Any]:
    """SDK が tool result trim を実行した時に呼ぶ audit endpoint."""
    try:
        return await t1.record_trim_event(
            req.session_id,
            req.original_size,
            req.trimmed_size,
            actor_user_id=req.actor_user_id,
            tool_name=req.tool_name,
            reason=req.reason,
        )
    except t1.Tier1ToolTrimError as e:
        raise _map_service_error(e)


@router.get("/trim/reasons")
async def trim_reasons() -> dict[str, Any]:
    """SDK trim の有効な reason 一覧 (read-only)."""
    return {"valid_reasons": list(t1.VALID_TRIM_REASONS)}
