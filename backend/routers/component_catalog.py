"""T-005b-03: component-catalog REST endpoint.

Endpoint:
  GET /api/component-catalog/screens            全 screen catalog
  GET /api/component-catalog/screens/{screen_id} 1 screen
  GET /api/component-catalog/transitions        遷移 DAG

AC マッピング:
  AC-1 UBIQUITOUS    : 3 endpoint mount.
  AC-2 EVENT-DRIVEN  : 2 秒以内 / structured response.
  AC-3 STATE-DRIVEN  : read-only / audit_logs emit per request.
  AC-4 UNWANTED      : invalid screen_id / 404 / path traversal → 4xx structured.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from services import component_catalog as cc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/component-catalog", tags=["component-catalog"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning(
            "component-catalog audit emit failed: %s -- %s", event_type, e,
        )


def _map_service_error(e: cc.ComponentCatalogError) -> HTTPException:
    msg = str(e)
    if "not found" in msg or "no S-" in msg or "does not exist" in msg:
        return _error("component_catalog.not_found", msg, status_code=404)
    return _error("component_catalog.invalid_input", msg, status_code=400)


@router.get("/screens")
async def list_screens_endpoint(
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error(
            "component_catalog.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    try:
        return cc.build_catalog()
    except cc.ComponentCatalogError as e:
        raise _map_service_error(e)


@router.get("/screens/{screen_id}")
async def get_screen_endpoint(
    screen_id: str,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error(
            "component_catalog.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    try:
        return cc.get_screen(None, screen_id)
    except cc.ComponentCatalogError as e:
        raise _map_service_error(e)


@router.get("/transitions")
async def transitions_endpoint(
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error(
            "component_catalog.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    try:
        return cc.build_transition_map()
    except cc.ComponentCatalogError as e:
        raise _map_service_error(e)
