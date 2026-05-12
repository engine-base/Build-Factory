"""T-M28-04: Tier 3 9-section structured summary persistence REST endpoint.

ADR-010 / requirements §11.6 EVENT:
  SDK が claude-agent-sdk 95% context 閾値で生成した 9-section structured
  summary を受け取り chat_messages.compressed_summary へ persist する.

Endpoint:
  POST /api/tier3/persist   SDK auto-compaction の persist wrapper.

AC マッピング:
  AC-1 UBIQUITOUS    : application code は summary 自前生成しない;
                       本 router は受信 + validation + persist のみ.
  AC-2 EVENT-DRIVEN  : 2 秒以内に応答 + memory_compacted audit emit
                       (summary_message_id + section_keys 付き).
  AC-3 STATE-DRIVEN  : original messages 不変 (chat_thread_store append-only).
  AC-4 UNWANTED      : invalid schema → 4xx {detail:{code,message}}; persist
                       されない (state mutate 無し).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import tier3_structured_summary as t3

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tier3", tags=["tier3"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _map_service_error(e: t3.Tier3PersistError) -> HTTPException:
    """Tier3PersistError を 400 / 401 / 404 に振り分ける."""
    msg = str(e)
    if "not found" in msg:
        return _error("tier3.not_found", msg, status_code=404)
    if "actor_user_id must not be empty" in msg:
        return _error("tier3.unauthorized", msg, status_code=401)
    return _error("tier3.invalid", msg, status_code=400)


class PersistRequest(BaseModel):
    thread_id: int = Field(..., gt=0)
    summary: dict
    persist_legacy: bool = True
    actor_user_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
# POST /api/tier3/persist
# ──────────────────────────────────────────────────────────────────────


@router.post("/persist")
async def persist(req: PersistRequest) -> dict[str, Any]:
    """SDK memory_compacted event を受けて 9-section を persist する.

    呼出元は claude-agent-sdk runner のみが想定される (application code は
    自前で summary を生成しない — AC-1 UBIQUITOUS / AC-4 UNWANTED).
    """
    try:
        return await t3.run_compaction(
            req.thread_id,
            req.summary,
            persist_legacy=req.persist_legacy,
            actor_user_id=req.actor_user_id,
        )
    except t3.Tier3PersistError as e:
        raise _map_service_error(e)
