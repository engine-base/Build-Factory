"""T-005b-04 / F-005b: 仕様 ↔ モック双方向リンク API.

Endpoint:
  POST   /api/spec-mock-links                       新規リンク作成
  GET    /api/spec-mock-links?spec_section_id=X     spec → mock list
  GET    /api/spec-mock-links?mock_id=N             mock → spec list
  GET    /api/spec-mock-links/{link_id}             get link
  DELETE /api/spec-mock-links/{link_id}             remove

AC マッピング:
  AC-1 UBIQUITOUS    : 双方向リンクの CRUD endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + 整合性 (重複 reject)
  AC-4 UNWANTED      : invalid input は 4xx + structured + persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import spec_mock_link as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/spec-mock-links", tags=["spec-mock-links"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("spec-mock-links audit emit failed: %s -- %s", event_type, e)


def _validate_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("spec_mock_links.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)


class CreateLinkRequest(BaseModel):
    workspace_id: int
    spec_section_id: str
    mock_id: int
    actor_user_id: Optional[str] = None


@router.post("")
async def create_link(body: CreateLinkRequest) -> dict[str, Any]:
    _validate_actor(body.actor_user_id)
    if body.workspace_id is None or body.workspace_id <= 0:
        raise _error("spec_mock_links.invalid_workspace_id",
                     "workspace_id must be > 0")
    if not body.spec_section_id or not body.spec_section_id.strip():
        raise _error("spec_mock_links.invalid_spec_section_id",
                     "spec_section_id must not be empty")
    if len(body.spec_section_id) > 200:
        raise _error("spec_mock_links.spec_section_id_too_long",
                     "spec_section_id must be <= 200 chars")
    if body.mock_id is None or body.mock_id <= 0:
        raise _error("spec_mock_links.invalid_mock_id", "mock_id must be > 0")

    try:
        result = svc.create_link(
            body.workspace_id, body.spec_section_id, body.mock_id,
            created_by=body.actor_user_id,
        )
    except svc.DuplicateLinkError as e:
        raise _error("spec_mock_links.duplicate", str(e), status_code=409)
    except svc.SpecMockLinkError as e:
        raise _error("spec_mock_links.invalid", str(e))

    await _audit(
        "spec_mock_links.created",
        user_id=body.actor_user_id,
        detail={
            "link_id": result["id"],
            "workspace_id": body.workspace_id,
            "spec_section_id": body.spec_section_id.strip(),
            "mock_id": body.mock_id,
        },
    )
    return result


@router.get("")
async def list_links(
    spec_section_id: Optional[str] = Query(None),
    mock_id: Optional[int] = Query(None),
    workspace_id: Optional[int] = Query(None),
) -> dict[str, Any]:
    """spec_section_id or mock_id どちらかが必要 (両方なしは 400)."""
    if not spec_section_id and not mock_id:
        raise _error(
            "spec_mock_links.missing_query",
            "either spec_section_id or mock_id is required",
        )
    if workspace_id is not None and workspace_id <= 0:
        raise _error("spec_mock_links.invalid_workspace_id",
                     "workspace_id must be > 0 when provided")
    if mock_id is not None and mock_id <= 0:
        raise _error("spec_mock_links.invalid_mock_id", "mock_id must be > 0")

    if spec_section_id:
        items = svc.list_links_for_spec(spec_section_id, workspace_id=workspace_id)
    else:
        items = svc.list_links_for_mock(mock_id, workspace_id=workspace_id)
    return {"links": items, "count": len(items)}


@router.get("/{link_id}")
async def get_link(link_id: int) -> dict[str, Any]:
    if link_id <= 0:
        raise _error("spec_mock_links.invalid_id", "link_id must be > 0")
    link = svc.get_link(link_id)
    if link is None:
        raise _error("spec_mock_links.not_found",
                     f"link not found: {link_id}", status_code=404)
    return link


@router.delete("/{link_id}")
async def delete_link(
    link_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    _validate_actor(actor_user_id)
    if link_id <= 0:
        raise _error("spec_mock_links.invalid_id", "link_id must be > 0")
    ok = svc.delete_link(link_id)
    if not ok:
        raise _error("spec_mock_links.not_found",
                     f"link not found: {link_id}", status_code=404)
    await _audit(
        "spec_mock_links.deleted",
        user_id=actor_user_id,
        detail={"link_id": link_id},
    )
    return {"deleted": True, "link_id": link_id}
