"""T-V3-B-07 / F-005: Spec CRUD + Comment endpoint.

v3 phase 1 で追加する 3 endpoint:
  - GET  /api/workspaces/{id}/specs                       # spec 一覧
  - GET  /api/workspaces/{id}/specs/{spec_id}/comments    # comment 一覧
  - POST /api/workspaces/{id}/specs/{spec_id}/comments    # comment 追加

合わせて F-005 contract に従い、内部利用の helper として spec 作成 endpoint
(POST /api/workspaces/{id}/specs) も提供する (test fixture / hearing → spec
pipeline 用. F-005 では spec 自動生成は別 service が担うが、本タスクの内部 API
として最低限のフックを置く).

auth: F-005 では `member` ロール. require_user で 401 / 403 を返す.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from services import specs_store as ss
from services.auth_middleware import require_user
from services.specs_store import (
    MAX_COMMENT_ANCHOR_CHARS,
    MAX_COMMENT_BODY_CHARS,
    SpecsStoreError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["specs"])


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    """best-effort audit emit; 失敗しても endpoint は成功する."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("specs audit emit failed: %s -- %s", event_type, e)


def _user_id(user: dict) -> Optional[str]:
    sub = user.get("sub") if isinstance(user, dict) else None
    if isinstance(sub, str) and sub.strip():
        return sub
    return None


# ----------------------------------------------------------------
# Pydantic schemas
# ----------------------------------------------------------------


class SpecCreateBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    hearing_id: Optional[str] = Field(None, min_length=1, max_length=200)
    html_url: Optional[str] = Field(None, max_length=2048)
    body_md: Optional[str] = Field(None, max_length=1_000_000)
    status: str = Field(
        "draft", pattern=r"^(draft|review|published|archived)$",
    )


class CommentCreateBody(BaseModel):
    # NOTE: max_length は MAX_COMMENT_BODY_CHARS (10000) ちょうど.
    # 10001 chars 以上は pydantic で 422 を返す (AC-F3 UNWANTED).
    body: str = Field(
        ...,
        min_length=1,
        max_length=MAX_COMMENT_BODY_CHARS,
    )
    anchor: Optional[str] = Field(
        None, max_length=MAX_COMMENT_ANCHOR_CHARS,
    )


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------


@router.get("/{workspace_id}/specs")
async def list_specs(
    workspace_id: str = Path(..., min_length=1, max_length=200),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_user),
) -> dict:
    """F-005 GET /api/workspaces/{id}/specs.

    AC-F7 (EVENT-DRIVEN): 200 with {specs: Spec[]}.
    AC-F8 (UNWANTED): 401 if no valid token (handled by require_user).
    AC-F9 (UNWANTED): 422 if validation fails (handled by Path/Query).
    """
    store = ss.get_store()
    try:
        specs = store.list_specs(workspace_id, limit=limit, offset=offset)
    except SpecsStoreError as e:
        raise _error("spec.invalid", str(e), status_code=400) from e
    items = [s.to_dict() for s in specs]
    return {"specs": items, "count": len(items)}


@router.post("/{workspace_id}/specs", status_code=status.HTTP_201_CREATED)
async def create_spec(
    body: SpecCreateBody,
    workspace_id: str = Path(..., min_length=1, max_length=200),
    user: dict = Depends(require_user),
) -> dict:
    """Internal helper (F-005 spec 自動生成 service と並列に test fixture 用)."""
    store = ss.get_store()
    try:
        spec = store.create_spec(
            workspace_id,
            title=body.title,
            hearing_id=body.hearing_id,
            html_url=body.html_url,
            body_md=body.body_md,
            status=body.status,
        )
    except SpecsStoreError as e:
        msg = str(e)
        if "not found" in msg:
            raise _error("spec.hearing_not_found", msg, status_code=404) from e
        raise _error("spec.invalid", msg, status_code=400) from e
    await _audit(
        "spec.created",
        user_id=_user_id(user),
        detail={"workspace_id": workspace_id, "spec_id": spec.id},
    )
    return spec.to_dict()


@router.get("/{workspace_id}/specs/{spec_id}/comments")
async def list_spec_comments(
    workspace_id: str = Path(..., min_length=1, max_length=200),
    spec_id: str = Path(..., min_length=1, max_length=200),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_user),
) -> dict:
    """F-005 GET /api/workspaces/{id}/specs/{spec_id}/comments.

    AC-F10 (EVENT-DRIVEN): 200 with {comments: Comment[]}.
    AC-F11 (UNWANTED): 401 if no valid token.
    AC-F12 (UNWANTED): 422 if validation fails.
    """
    store = ss.get_store()
    try:
        comments = store.list_comments(
            workspace_id, spec_id, limit=limit, offset=offset,
        )
    except SpecsStoreError as e:
        msg = str(e)
        if "not found" in msg:
            raise _error("spec.not_found", msg, status_code=404) from e
        if "does not belong" in msg:
            raise _error("spec.forbidden", msg, status_code=403) from e
        raise _error("spec.invalid", msg, status_code=400) from e
    items = [c.to_dict() for c in comments]
    return {"comments": items, "count": len(items)}


@router.post(
    "/{workspace_id}/specs/{spec_id}/comments",
    status_code=status.HTTP_201_CREATED,
)
async def add_spec_comment(
    body: CommentCreateBody,
    workspace_id: str = Path(..., min_length=1, max_length=200),
    spec_id: str = Path(..., min_length=1, max_length=200),
    user: dict = Depends(require_user),
) -> dict:
    """F-005 POST /api/workspaces/{id}/specs/{spec_id}/comments.

    AC-F3  (UNWANTED): body > 10000 chars → 422 (pydantic max_length).
    AC-F13 (EVENT-DRIVEN): 201 with {comment_id, created_at}.
    AC-F14 (UNWANTED): 401 if no valid token.
    AC-F15 (UNWANTED): 422 if validation fails.
    """
    store = ss.get_store()
    try:
        comment = store.add_comment(
            workspace_id,
            spec_id,
            body=body.body,
            anchor=body.anchor,
            author_user_id=_user_id(user),
        )
    except SpecsStoreError as e:
        msg = str(e)
        if "not found" in msg:
            raise _error("spec.not_found", msg, status_code=404) from e
        if "does not belong" in msg:
            raise _error("spec.forbidden", msg, status_code=403) from e
        if "<= 10000" in msg or "must be a string" in msg or "must not be empty" in msg:
            raise _error("comment.invalid", msg, status_code=422) from e
        raise _error("comment.invalid", msg, status_code=400) from e
    await _audit(
        "spec_comment_added",
        user_id=_user_id(user),
        detail={
            "workspace_id": workspace_id,
            "spec_id": spec_id,
            "comment_id": comment.id,
        },
    )
    return {
        "comment_id": comment.id,
        "created_at": comment.created_at,
        "comment": comment.to_dict(),
    }
