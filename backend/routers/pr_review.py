"""T-013-03 / F-013: PR 自動作成 + HTML diff 注釈レビュー資料添付 REST endpoint.

Endpoint:
  POST /api/pr-review/render-html   diff + meta から HTML レビュー資料を生成
  POST /api/pr-review/parse-diff    diff を構造化 JSON に解析

AC マッピング:
  AC-1 UBIQUITOUS    : F-013 HTML レビュー資料生成 endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + service は read-only (input 非破壊)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from services import pr_review_annotator as pra

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
