"""ADR-012: Memory Tool / Context Editing / Subagent Memory REST endpoints.

- POST /api/anthropic-memory/{command}          Memory Tool 6 commands (view/create/...)
- GET  /api/anthropic-memory/context-editing    既定 context_management config を返す
- POST /api/anthropic-memory/subagent/handoff   Subagent Memory handoff 記録
- GET  /api/anthropic-memory/subagent/{persona} Subagent Memory pre-load

AC マッピング (ADR-012):
  AC-1 UBIQUITOUS  : Memory Tool / Context Editing / Subagent Memory unified.
  AC-2 EVENT       : 各 endpoint 2 秒以内.
  AC-3 STATE       : `/memories` 外への path traversal blocked.
  AC-4 UNWANTED    : 全 4xx は {detail:{code,message}} 統一. state mutate なし.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from services import anthropic_context_editing as ce
from services.anthropic_memory_tool import (
    VALID_COMMANDS,
    MemoryToolError,
    MemoryToolHandler,
    memory_tool_spec,
)
from services.subagent_memory import (
    SubagentMemoryError,
    SubagentMemoryStore,
    get_default_store,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/anthropic-memory", tags=["anthropic-memory"])

# 注: prefix を /api/memory にすると既存 memory_pipeline_router の
# /api/memory/context と衝突するため /api/anthropic-memory を採用 (ADR-012).


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_memory_error(e: MemoryToolError) -> HTTPException:
    msg = str(e)
    if "does not exist" in msg or "not exist" in msg:
        return _error("memory.not_found", msg, status_code=404)
    if "already exists" in msg:
        return _error("memory.conflict", msg, status_code=409)
    return _error("memory.invalid", msg, status_code=400)


def _map_subagent_error(e: SubagentMemoryError) -> HTTPException:
    return _error("memory.subagent.invalid", str(e), status_code=400)


# ──────────────────────────────────────────────────────────────────────
# Tool spec (claude-agent-sdk tools list helper)
# ──────────────────────────────────────────────────────────────────────


@router.get("/tool-spec")
async def get_tool_spec() -> dict[str, Any]:
    """claude-agent-sdk / anthropic-python の tools list に追加する dict を返す."""
    return memory_tool_spec()


@router.get("/context-editing")
async def get_context_editing_config() -> dict[str, Any]:
    """既定 context_management config + beta headers."""
    return {
        "context_management": ce.default_context_management_config(),
        "betas": ce.recommended_beta_headers(),
    }


# ──────────────────────────────────────────────────────────────────────
# Memory Tool 6 commands (passthrough)
# ──────────────────────────────────────────────────────────────────────


@router.post("/{command}")
async def memory_command(command: str, request: Request) -> dict[str, Any]:
    if command not in VALID_COMMANDS:
        raise _error(
            "memory.invalid",
            f"unknown command {command!r}, expected one of {VALID_COMMANDS}",
        )
    try:
        body = await request.json()
    except Exception:
        raise _error("memory.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("memory.invalid", "request body must be a JSON object")

    handler = MemoryToolHandler()
    try:
        result_text = handler.dispatch(command, **body)
    except MemoryToolError as e:
        raise _map_memory_error(e)
    except TypeError as e:
        raise _error("memory.invalid", f"bad arguments: {e}")
    return {"command": command, "result": result_text}


# ──────────────────────────────────────────────────────────────────────
# Subagent Memory
# ──────────────────────────────────────────────────────────────────────


@router.post("/subagent/handoff")
async def subagent_handoff(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise _error("memory.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("memory.invalid", "request body must be a JSON object")
    source = body.get("source")
    target = body.get("target")
    message = body.get("message")
    context = body.get("context")
    workspace_id = body.get("workspace_id")
    session_id = body.get("session_id")
    store = get_default_store()
    try:
        return store.record_handoff(
            source=source,
            target=target,
            message=message,
            context=context,
            workspace_id=workspace_id,
            session_id=session_id,
        )
    except SubagentMemoryError as e:
        raise _map_subagent_error(e)


@router.get("/subagent/{persona}")
async def subagent_preload(
    persona: str,
    request: Request,
) -> dict[str, Any]:
    q = request.query_params
    workspace_id_raw = q.get("workspace_id")
    workspace_id: Optional[int] = None
    if workspace_id_raw is not None:
        try:
            workspace_id = int(workspace_id_raw)
        except ValueError:
            raise _error("memory.invalid", "workspace_id must be int")
    limit_raw = q.get("limit")
    limit = 5
    if limit_raw is not None:
        try:
            limit = int(limit_raw)
        except ValueError:
            raise _error("memory.invalid", "limit must be int")
    store = get_default_store()
    try:
        snippets = store.preload_for(
            persona, workspace_id=workspace_id, limit=limit,
        )
    except SubagentMemoryError as e:
        raise _map_subagent_error(e)
    return {
        "persona": persona,
        "workspace_id": workspace_id,
        "limit": limit,
        "count": len(snippets),
        "snippets": snippets,
    }
