"""T-V3-B-20 / F-013: Client portal REST endpoints (public + 1 member).

Endpoints:
  GET  /api/client/workspaces/{token}                (public)
  GET  /api/client/workspaces/{token}/spec           (public)
  GET  /api/client/comments/{thread_id}              (public)
  POST /api/client/comments                          (public, rate-limited)
  POST /api/comments/{id}/resolve                    (member, F-013)

Auth model:
  The 4 public endpoints are token-gated (no Authorization header). The
  ``token`` is supplied via path (workspace/spec) or query string + body
  (comments). Lack of a valid token returns 401, matching features.json#F-013.

AC mapping (1:1 with audit MD docs/audit/2026-05-16_v3/T-V3-B-20.md):
  AC-F1  STATE-DRIVEN  : expired token -> 409 (GET workspace)
  AC-F2  UNWANTED      : POST comments rate-limited -> 429
  AC-F3  EVENT-DRIVEN  : GET workspace happy returns PublicWorkspaceView
  AC-F4  UNWANTED      : GET workspace without token -> 401
  AC-F5  EVENT-DRIVEN  : GET spec happy returns spec_html_url
  AC-F6  UNWANTED      : GET spec without token -> 401
  AC-F7  EVENT-DRIVEN  : GET comments happy returns PublicComment[]
  AC-F8  UNWANTED      : GET comments without token -> 401
  AC-F9  UNWANTED      : GET comments invalid thread_id -> 422
  AC-F10 EVENT-DRIVEN  : POST comments happy returns comment_id
  AC-F11 UNWANTED      : POST comments without token -> 401
  AC-F12 UNWANTED      : POST comments invalid body -> 422
  AC-F13 UNWANTED      : POST comments rate-limited -> 429
  AC-F14 EVENT-DRIVEN  : POST resolve happy returns resolved_at
  AC-F15 UNWANTED      : POST resolve without auth -> 401
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from services import client_portal_service as cps
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)


router = APIRouter(tags=["client-portal"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _service_error_to_http(e: cps.ClientPortalServiceError) -> HTTPException:
    """Map service errors to HTTP responses.

    AC-F4/F6/F8/F11: TokenInvalidError -> 401
    AC-F1         : TokenExpiredError -> 409
    AC-F9/F12     : CommentValidationError -> 422
    AC-F2/F13     : RateLimitedError -> 429
    """
    msg = str(e)
    if isinstance(e, cps.TokenInvalidError):
        return _error("client_portal.unauthorized", msg, status_code=401)
    if isinstance(e, cps.TokenExpiredError):
        return _error("client_portal.token_expired", msg, status_code=409)
    if isinstance(e, cps.CommentNotFoundError):
        return _error("client_portal.not_found", msg, status_code=404)
    if isinstance(e, cps.CommentForbiddenError):
        return _error("client_portal.forbidden", msg, status_code=403)
    if isinstance(e, cps.CommentConflictError):
        return _error("client_portal.conflict", msg, status_code=409)
    if isinstance(e, cps.RateLimitedError):
        return _error("client_portal.rate_limited", msg, status_code=429)
    if isinstance(e, cps.CommentValidationError):
        return _error("client_portal.validation_error", msg, status_code=422)
    return _error("client_portal.invalid", msg)


def _extract_user_id(user: dict) -> str:
    uid = user.get("sub") or user.get("user_id") or ""
    if not isinstance(uid, str) or not uid.strip():
        raise _error(
            "client_portal.unauthorized",
            "auth claims missing sub", status_code=401,
        )
    return uid.strip()


# ─────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────


class PostClientCommentRequest(BaseModel):
    token: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1, max_length=cps.MAX_COMMENT_BODY_LEN)
    anchor: Optional[str] = Field(default=None, max_length=cps.MAX_ANCHOR_LEN)
    thread_id: Optional[str] = Field(default=None)
    author_name: Optional[str] = Field(
        default=None, max_length=cps.MAX_AUTHOR_NAME_LEN,
    )


# ─────────────────────────────────────────────────────────────────────────
# Public endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/api/client/workspaces/{token}",
    operation_id="get_client_workspaces_by_token",
)
async def get_client_workspaces_by_token(
    token: str = Path(..., description="client review token"),
) -> dict[str, Any]:
    """AC-F3 happy / AC-F4 401 / AC-F1 409."""
    if not token or not token.strip():
        raise _error(
            "client_portal.unauthorized",
            "token must not be empty", status_code=401,
        )
    try:
        return await cps.get_workspace_by_token(token=token)
    except cps.ClientPortalServiceError as e:
        raise _service_error_to_http(e)


@router.get(
    "/api/client/workspaces/{token}/spec",
    operation_id="get_client_workspaces_by_token_spec",
)
async def get_client_workspaces_by_token_spec(
    token: str = Path(..., description="client review token"),
) -> dict[str, Any]:
    """AC-F5 happy / AC-F6 401 / AC-F1 409."""
    if not token or not token.strip():
        raise _error(
            "client_portal.unauthorized",
            "token must not be empty", status_code=401,
        )
    try:
        return await cps.get_spec_by_token(token=token)
    except cps.ClientPortalServiceError as e:
        raise _service_error_to_http(e)


@router.get(
    "/api/client/comments/{thread_id}",
    operation_id="get_client_comments_by_thread_id",
)
async def get_client_comments_by_thread_id(
    thread_id: str = Path(..., description="comment thread id (uuid)"),
    token: str = Query(..., description="client review token"),
) -> dict[str, Any]:
    """AC-F7 happy / AC-F8 401 / AC-F9 422."""
    if not token or not token.strip():
        raise _error(
            "client_portal.unauthorized",
            "token must not be empty", status_code=401,
        )
    try:
        return await cps.get_comments_by_thread(
            thread_id=thread_id, token=token,
        )
    except cps.ClientPortalServiceError as e:
        raise _service_error_to_http(e)


@router.post(
    "/api/client/comments",
    operation_id="post_client_comments",
    status_code=201,
)
async def post_client_comments(
    req: PostClientCommentRequest = ...,  # type: ignore[assignment]
) -> dict[str, Any]:
    """AC-F10 happy / AC-F11 401 / AC-F12 422 / AC-F13 (& AC-F2) 429."""
    if not req.token or not req.token.strip():
        raise _error(
            "client_portal.unauthorized",
            "token must not be empty", status_code=401,
        )
    try:
        return await cps.post_comment(
            token=req.token, body=req.body,
            anchor=req.anchor, thread_id=req.thread_id,
            author_name=req.author_name,
        )
    except cps.ClientPortalServiceError as e:
        raise _service_error_to_http(e)


# ─────────────────────────────────────────────────────────────────────────
# Member endpoint (resolve)
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/api/comments/{id}/resolve",
    operation_id="post_comments_by_id_resolve",
    status_code=201,
)
async def post_comments_by_id_resolve(
    id: str = Path(..., description="comment id (uuid)"),
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F14 happy / AC-F15 401 (require_user) / 403 non-member / 409 already."""
    actor = _extract_user_id(user)
    try:
        return await cps.resolve_comment(
            comment_id=id, actor_user_id=actor,
        )
    except cps.ClientPortalServiceError as e:
        raise _service_error_to_http(e)
