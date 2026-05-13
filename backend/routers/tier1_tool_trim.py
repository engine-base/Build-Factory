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

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
    """型検査のみ. range/長さ validation は service 層へ委譲 (AC-4 4xx 形式統一)."""
    session_id: Optional[str] = None
    original_size: Optional[int] = None
    trimmed_size: Optional[int] = None
    actor_user_id: Optional[str] = None
    tool_name: Optional[str] = None
    reason: Optional[str] = None


@router.post("/tool-result-trim")
async def tool_result_trim(request: Request) -> dict[str, Any]:
    """SDK が tool result trim を実行した時に呼ぶ audit endpoint.

    AC-4: 全 4xx は {detail:{code,message}} 形式で統一.
    pydantic 標準 422 ({detail:[...]}) は本 endpoint では返さず, 全 validation
    を service 層 (Tier1ToolTrimError) に委譲して 400/401 + structured error
    に正規化する.
    """
    try:
        body = await request.json()
    except Exception:
        raise _error("tier1.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("tier1.invalid", "request body must be a JSON object")

    # 型 / 必須 check (range は service 層)
    for required in ("session_id", "original_size", "trimmed_size"):
        if required not in body:
            raise _error("tier1.invalid", f"{required} is required")

    try:
        return await t1.record_trim_event(
            body.get("session_id"),
            body.get("original_size"),
            body.get("trimmed_size"),
            actor_user_id=body.get("actor_user_id"),
            tool_name=body.get("tool_name"),
            reason=body.get("reason"),
        )
    except t1.Tier1ToolTrimError as e:
        raise _map_service_error(e)


@router.get("/trim/reasons")
async def trim_reasons() -> dict[str, Any]:
    """SDK trim の有効な reason 一覧 (read-only)."""
    return {"valid_reasons": list(t1.VALID_TRIM_REASONS)}
