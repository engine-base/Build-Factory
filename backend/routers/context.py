"""T-M28-01: Context Builder REST API (gap closure G1-G4).

- POST /api/context/build              build_context (Mem0 + Obsidian + Constitution + D-XXX)
- GET  /api/context/decisions/{id}     D-XXX で Constitution を引く
- GET  /api/context/constitution       preload_constitution の結果を返す
- GET  /api/context/obsidian/{slug}    G1: Obsidian markdown read
- POST /api/context/obsidian/{slug}    G1: Obsidian markdown write

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : Mem0 + Obsidian read/write + Constitution unified API
                       (G1: write endpoint 追加).
  AC-2 EVENT-DRIVEN  : D-XXX lookup 200ms 以内.
  AC-3 STATE-DRIVEN  : secretary_active 状態を build_context で明示判定 (G2).
  AC-4 UNWANTED      : conflicts surface + has_conflicts フラグ (G3) /
                       全 4xx を {detail:{code,message}} 統一 (G4) /
                       state mutate なし.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from services.context_builder import (
    build_context,
    lookup_decision,
    preload_constitution,
    read_obsidian_note,
    write_obsidian_note,
    DECISION_REF_RE,
    ContextBuilderError,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/context", tags=["context"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_builder_error(e: ContextBuilderError) -> HTTPException:
    return _error("context.invalid", str(e), status_code=400)


@router.post("/build")
async def build(request: Request) -> dict[str, Any]:
    """AC-4: 全 4xx を {detail:{code,message}} に統一."""
    try:
        body = await request.json()
    except Exception:
        raise _error("context.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("context.invalid", "request body must be a JSON object")
    user_message = body.get("user_message")
    if not isinstance(user_message, str) or not user_message.strip():
        raise _error("context.invalid", "user_message must be a non-empty string")
    session_id = body.get("session_id")
    if isinstance(session_id, bool) or not isinstance(session_id, int) or session_id <= 0:
        raise _error("context.invalid", "session_id must be int > 0")
    prior_session_id = body.get("prior_session_id")
    if prior_session_id is not None:
        if isinstance(prior_session_id, bool) or not isinstance(prior_session_id, int):
            raise _error("context.invalid", "prior_session_id must be int or null")
    user_id = body.get("user_id")
    if user_id is not None and not isinstance(user_id, str):
        raise _error("context.invalid", "user_id must be string or null")
    top_k = body.get("top_k", 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not (1 <= top_k <= 20):
        raise _error("context.invalid", "top_k must be int in 1..20")
    include_constitution = body.get("include_constitution", True)
    if not isinstance(include_constitution, bool):
        raise _error("context.invalid", "include_constitution must be bool")
    secretary_active = body.get("secretary_active")
    if secretary_active is not None and not isinstance(secretary_active, bool):
        raise _error("context.invalid", "secretary_active must be bool or null")
    try:
        return await build_context(
            user_message=user_message,
            session_id=session_id,
            prior_session_id=prior_session_id,
            user_id=user_id,
            top_k=top_k,
            include_constitution=include_constitution,
            secretary_active=secretary_active,
        )
    except ContextBuilderError as e:
        raise _map_builder_error(e)


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str) -> dict[str, Any]:
    if not DECISION_REF_RE.fullmatch(decision_id):
        raise _error(
            "context.invalid",
            f"invalid decision_id format (expect D-XXX): {decision_id}",
        )
    d = lookup_decision(decision_id)
    if not d:
        raise _error(
            "context.not_found", f"decision not found: {decision_id}",
            status_code=404,
        )
    return d


@router.get("/constitution")
async def get_constitution(user_id: str = "masato") -> dict[str, Any]:
    if not isinstance(user_id, str) or not user_id.strip():
        raise _error("context.invalid", "user_id must not be empty")
    return {"constitution": await preload_constitution(user_id)}


# ──────────────────────────────────────────────────────────────────────
# G1 (AC-1): Obsidian markdown read/write unified endpoints
# ──────────────────────────────────────────────────────────────────────


@router.get("/obsidian/{slug:path}")
async def obsidian_read(slug: str) -> dict[str, Any]:
    try:
        content = read_obsidian_note(slug)
    except ContextBuilderError as e:
        raise _map_builder_error(e)
    if content is None:
        raise _error(
            "context.not_found",
            f"obsidian note not found: {slug}",
            status_code=404,
        )
    return {"slug": slug, "content": content}


@router.post("/obsidian/{slug:path}")
async def obsidian_write(slug: str, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise _error("context.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("context.invalid", "request body must be a JSON object")
    content = body.get("content")
    if not isinstance(content, str):
        raise _error("context.invalid", "content must be string")
    try:
        path = write_obsidian_note(slug, content)
    except ContextBuilderError as e:
        raise _map_builder_error(e)
    return {
        "slug": slug,
        "path": str(path),
        "bytes_written": len(content.encode("utf-8")),
    }
