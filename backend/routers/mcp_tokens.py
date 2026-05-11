"""T-010a-04 / F-010a: MCP token scope (workspace 単位) REST endpoint.

Endpoint:
  POST   /api/mcp/tokens              issue
  GET    /api/mcp/tokens?workspace_id=N  list (token は masked)
  POST   /api/mcp/tokens/verify       verify (scope + workspace)
  DELETE /api/mcp/tokens/{token_id}   revoke

AC マッピング:
  AC-1 UBIQUITOUS    : F-010a で MCP token CRUD + verify endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit / token 平文 list で返さない (mask)
  AC-4 UNWANTED      : invalid input は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import mcp_token as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp/tokens", tags=["mcp-tokens"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("mcp-tokens audit emit failed: %s -- %s", event_type, e)


class IssueRequest(BaseModel):
    workspace_id: int
    scopes: list[str]
    expires_in_days: int = Field(30, ge=1, le=365)
    issued_by: Optional[str] = None


class VerifyRequest(BaseModel):
    token: str
    required_scope: Optional[str] = None
    workspace_id: Optional[int] = None


@router.post("")
async def issue_token(body: IssueRequest) -> dict[str, Any]:
    if body.workspace_id is None or body.workspace_id <= 0:
        raise _error("mcp_tokens.invalid_workspace_id", "workspace_id must be > 0")
    if not body.scopes:
        raise _error("mcp_tokens.invalid_scopes", "scopes must not be empty")
    if body.issued_by is not None and not body.issued_by.strip():
        raise _error("mcp_tokens.unauthorized",
                     "issued_by must not be empty when provided",
                     status_code=401)

    try:
        result = svc.issue_token(
            body.workspace_id,
            body.scopes,
            expires_in_days=body.expires_in_days,
            issued_by=body.issued_by,
        )
    except svc.MCPTokenError as e:
        raise _error("mcp_tokens.invalid", str(e))

    await _audit(
        "mcp_tokens.issued",
        user_id=body.issued_by,
        detail={
            "token_id": result["id"],
            "workspace_id": body.workspace_id,
            "scopes": list(body.scopes),
            "expires_in_days": body.expires_in_days,
        },
    )
    return result


@router.get("")
async def list_tokens(
    workspace_id: int = Query(..., gt=0),
    include_revoked: bool = Query(False),
) -> dict[str, Any]:
    items = svc.list_tokens(workspace_id, include_revoked=include_revoked)
    return {"workspace_id": workspace_id, "count": len(items), "tokens": items}


@router.post("/verify")
async def verify_token(body: VerifyRequest) -> dict[str, Any]:
    if not body.token or not body.token.strip():
        raise _error("mcp_tokens.invalid_token", "token must not be empty")
    if body.workspace_id is not None and body.workspace_id <= 0:
        raise _error("mcp_tokens.invalid_workspace_id",
                     "workspace_id must be > 0 when provided")
    if body.required_scope is not None:
        if body.required_scope not in svc.VALID_SCOPES:
            raise _error(
                "mcp_tokens.invalid_scope",
                f"required_scope must be one of {svc.VALID_SCOPES}",
            )
    result = svc.verify_token(
        body.token,
        required_scope=body.required_scope,
        workspace_id=body.workspace_id,
    )
    # verify は audit emit しない (read-only). 失敗時のみ debug log
    if not result.get("valid"):
        logger.debug("mcp_token verify denied: reason=%s", result.get("reason"))
    return result


@router.delete("/{token_id}")
async def revoke_token(
    token_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    if token_id <= 0:
        raise _error("mcp_tokens.invalid_id", "token_id must be > 0")
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error("mcp_tokens.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    ok = svc.revoke_token(token_id)
    if not ok:
        raise _error("mcp_tokens.not_found",
                     f"token not found or already revoked: {token_id}",
                     status_code=404)
    await _audit(
        "mcp_tokens.revoked",
        user_id=actor_user_id,
        detail={"token_id": token_id},
    )
    return {"revoked": True, "token_id": token_id}
