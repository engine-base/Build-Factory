"""T-013-03 / F-013: PR 自動作成 + HTML diff 注釈レビュー資料添付 REST endpoint.

Endpoint:
  POST /api/pr-review/render-html       (T-013-03) diff + meta -> HTML レビュー資料
  POST /api/pr-review/parse-diff        (T-013-03) diff -> 構造化 JSON
  GET  /api/workspaces/{id}/prs/{pr_number}  (T-V3-B-19) PR 詳細
  POST /api/prs/{id}/approve            (T-V3-B-19) PR 承認 (workspace_admin)
  POST /api/prs/{id}/comments           (T-V3-B-19) PR コメント
  POST /api/prs/{id}/merge              (T-V3-B-19) PR マージ (workspace_admin)

AC マッピング (T-013-03):
  AC-1 UBIQUITOUS    : F-013 HTML レビュー資料生成 endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + service は read-only (input 非破壊)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない

AC マッピング (T-V3-B-19, audit MD docs/audit/2026-05-16_v3/T-V3-B-19.md):
  Tier 2 AC-F1..AC-F12 — 4 endpoint × {happy, 401, 409, 422} の派生 EARS。
  実装行は audit MD に逐語記録すること。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from pydantic import BaseModel, Field

from services import pr_review_annotator as pra
from services import pr_service
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pr-review", tags=["pr-review"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("pr-review audit emit failed: %s -- %s", event_type, e)


class RenderRequest(BaseModel):
    title: str
    body: str = ""
    branch: str = ""
    base_branch: str = "main"
    author: Optional[str] = None
    diff: str
    checklist: Optional[list[str]] = None
    actor_user_id: Optional[str] = None


class ParseDiffRequest(BaseModel):
    diff: str
    actor_user_id: Optional[str] = None


def _validate_meta_fields(
    title: str, body: str, branch: str, author: Optional[str],
) -> None:
    if not title or not title.strip():
        raise _error("pr_review.invalid_title", "title must not be empty")
    if len(title) > pra.MAX_TITLE_LEN:
        raise _error("pr_review.title_too_long",
                     f"title must be <= {pra.MAX_TITLE_LEN} chars")
    if len(body or "") > pra.MAX_BODY_LEN:
        raise _error("pr_review.body_too_long",
                     f"body must be <= {pra.MAX_BODY_LEN} chars")
    if branch and len(branch) > pra.MAX_BRANCH_LEN:
        raise _error("pr_review.invalid_branch",
                     f"branch must be <= {pra.MAX_BRANCH_LEN} chars")
    if author is not None and not author.strip():
        raise _error("pr_review.invalid_author",
                     "author must not be empty when provided")
    if author is not None and len(author) > 200:
        raise _error("pr_review.invalid_author",
                     "author must be <= 200 chars")


@router.post("/render-html")
async def render_html(req: RenderRequest) -> Response:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("pr_review.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    _validate_meta_fields(req.title, req.body, req.branch, req.author)
    if not req.diff or not req.diff.strip():
        raise _error("pr_review.invalid_diff", "diff must not be empty")
    if req.checklist is not None:
        if not isinstance(req.checklist, list):
            raise _error("pr_review.invalid_checklist",
                         "checklist must be a list")
        if len(req.checklist) > 50:
            raise _error("pr_review.invalid_checklist",
                         "checklist must be <= 50 items")
        for i, item in enumerate(req.checklist):
            if not isinstance(item, str) or not item.strip():
                raise _error("pr_review.invalid_checklist",
                             f"checklist[{i}] must be non-empty string")
            if len(item) > 500:
                raise _error("pr_review.invalid_checklist",
                             f"checklist[{i}] must be <= 500 chars")

    try:
        files, stats = pra.parse_unified_diff(req.diff)
        meta = pra.PRMeta(
            title=req.title.strip(),
            body=req.body or "",
            branch=req.branch or "",
            base_branch=req.base_branch or "main",
            author=req.author,
        )
        rendered = pra.render_review_html(
            meta, files, stats=stats, checklist=req.checklist,
        )
    except pra.PRAnnotatorError as e:
        raise _error("pr_review.invalid", str(e))

    await _audit(
        "pr_review.rendered",
        user_id=req.actor_user_id,
        detail={
            "title_len": len(req.title),
            "files": stats.files,
            "additions": stats.additions,
            "deletions": stats.deletions,
            "truncated": stats.truncated,
            "html_size": len(rendered),
        },
    )
    return Response(
        content=rendered,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="pr-review.html"',
        },
    )


@router.post("/parse-diff")
async def parse_diff(req: ParseDiffRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("pr_review.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not req.diff or not req.diff.strip():
        raise _error("pr_review.invalid_diff", "diff must not be empty")
    try:
        files, stats = pra.parse_unified_diff(req.diff)
    except pra.PRAnnotatorError as e:
        raise _error("pr_review.invalid", str(e))
    return {
        "stats": stats.to_dict(),
        "files": [f.to_dict() for f in files],
    }


# ─────────────────────────────────────────────────────────────────────────
# T-V3-B-19: PR review backend (get / approve / comments / merge) — F-013
# ─────────────────────────────────────────────────────────────────────────
#
# These endpoints live in a separate APIRouter (no prefix) because the
# OpenAPI spec defines them under /api/workspaces/{id}/prs/... and
# /api/prs/{id}/...; the pr-review-html router above uses prefix
# /api/pr-review and would otherwise force them under that path.

prs_router = APIRouter(tags=["prs"])


def _prs_error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _service_error_to_http(e: pr_service.PRServiceError) -> HTTPException:
    """Map service errors to HTTP responses (AC-F2..F4, F6, F8, F9, F11, F12)."""
    msg = str(e)
    if isinstance(e, pr_service.PRNotFoundError):
        return _prs_error("prs.not_found", msg, status_code=404)
    if isinstance(e, pr_service.PRForbiddenError):
        return _prs_error("prs.forbidden", msg, status_code=403)
    if isinstance(e, pr_service.PRConflictError):
        return _prs_error("prs.conflict", msg, status_code=409)
    if isinstance(e, pr_service.PRValidationError):
        return _prs_error("prs.validation_error", msg, status_code=422)
    return _prs_error("prs.invalid", msg)


def _extract_user_id(user: dict) -> str:
    """auth_middleware claims から user_id を取り出す (AC-F4/F6/F8/F11)."""
    uid = user.get("sub") or user.get("user_id") or ""
    if not isinstance(uid, str) or not uid.strip():
        raise _prs_error(
            "prs.unauthorized", "auth claims missing sub",
            status_code=401,
        )
    return uid.strip()


class ApprovePRRequest(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)


class CommentPRRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    anchor_file: Optional[str] = Field(default=None, max_length=500)
    anchor_line: Optional[int] = Field(default=None, ge=1)


class MergePRRequest(BaseModel):
    merge_method: str = Field(..., min_length=1)


@prs_router.get(
    "/api/workspaces/{id}/prs/{pr_number}",
    operation_id="get_workspaces_by_id_prs_by_pr_number",
)
async def get_workspace_pr(
    id: int = Path(..., description="workspace id", ge=1),
    pr_number: int = Path(..., description="PR number", ge=1),
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F3 happy / AC-F4 401 (handled by require_user)."""
    actor = _extract_user_id(user)
    try:
        result = await pr_service.get_pr_by_number(
            workspace_id=id, pr_number=pr_number, actor_user_id=actor,
        )
    except pr_service.PRServiceError as e:
        raise _service_error_to_http(e)
    await _audit(
        "pr_retrieved",
        user_id=actor,
        detail={"workspace_id": id, "pr_number": pr_number,
                "pr_id": result["pr"].get("id")},
    )
    return result


@prs_router.post(
    "/api/prs/{id}/approve",
    operation_id="post_prs_by_id_approve",
    status_code=201,
)
async def approve_pr_endpoint(
    id: int = Path(..., description="PR id", ge=1),
    body: ApprovePRRequest = ApprovePRRequest(),
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F5 happy / AC-F6 401 (require_user) / 409 already approved."""
    actor = _extract_user_id(user)
    try:
        return await pr_service.approve_pr(
            pr_id=id, actor_user_id=actor, comment=body.comment,
        )
    except pr_service.PRServiceError as e:
        raise _service_error_to_http(e)


@prs_router.post(
    "/api/prs/{id}/comments",
    operation_id="post_prs_by_id_comments",
    status_code=201,
)
async def add_pr_comment_endpoint(
    id: int = Path(..., description="PR id", ge=1),
    body: CommentPRRequest = ...,  # type: ignore[assignment]
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F7 happy / AC-F8 401 / AC-F9 422 (Pydantic + service validation)."""
    actor = _extract_user_id(user)
    try:
        return await pr_service.add_pr_comment(
            pr_id=id, actor_user_id=actor,
            body=body.body, anchor_file=body.anchor_file,
            anchor_line=body.anchor_line,
        )
    except pr_service.PRServiceError as e:
        raise _service_error_to_http(e)


@prs_router.post(
    "/api/prs/{id}/merge",
    operation_id="post_prs_by_id_merge",
    status_code=201,
)
async def merge_pr_endpoint(
    id: int = Path(..., description="PR id", ge=1),
    body: MergePRRequest = ...,  # type: ignore[assignment]
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """AC-F1/F10 happy + pr_merged audit / AC-F11 401 / AC-F2 + AC-F12 4xx."""
    actor = _extract_user_id(user)
    if body.merge_method not in pr_service.VALID_MERGE_METHODS:
        raise _prs_error(
            "prs.validation_error",
            f"merge_method must be one of {pr_service.VALID_MERGE_METHODS}",
            status_code=422,
        )
    try:
        return await pr_service.merge_pr(
            pr_id=id, actor_user_id=actor, merge_method=body.merge_method,
        )
    except pr_service.PRServiceError as e:
        raise _service_error_to_http(e)
