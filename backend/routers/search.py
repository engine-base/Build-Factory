"""T-V3-B-27 / F-024: GET /api/search router.

Endpoint::
  GET /api/search?q=...&category=tasks|artifacts|knowledge|audit&limit=...

Auth: ``authenticated`` (Depends(require_user)). The user's resolved id drives
the per-user rate limiter and the workspace allow-list for RLS-equivalent
filtering at the service layer.

EARS AC mapping (T-V3-B-27 functional Tier):

  AC-F1 : EVENT-DRIVEN — non-empty q returns hits ranked by combined FTS +
          vector score (delegated to services.search.global_search).
  AC-F2 : UNWANTED — q > 500 chars or empty -> 422 with field-level error map.
  AC-F3 : UNWANTED — > 60 req/min/user -> 429 (RateLimitExceeded).
  AC-F5 : EVENT-DRIVEN — 2xx response uses the openapi.yaml#/api/search shape.
  AC-F6 : UNWANTED — missing/invalid auth -> 401 (require_user).
  AC-F7 : UNWANTED — query schema validation failure -> 422 with field map.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services import search as search_svc
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["global-search"])


def _field_error(field: str, message: str) -> HTTPException:
    """422 with a {detail: {code, message, errors: {field: msg}}} shape."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "validation_error",
            "message": message,
            "errors": {field: message},
        },
    )


def _resolve_user_key(user: dict) -> str:
    """Stable per-user key for rate-limiter bucket."""
    return (
        user.get("sub")
        or (user.get("user_metadata") or {}).get("slug")
        or user.get("email")
        or "anonymous"
    )


async def _emit_audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("audit emit failed %s: %s", event_type, e)


@router.get("")
async def search(
    q: str = Query(..., description="search query (1..500 chars)"),
    category: Optional[str] = Query(None, description="tasks|artifacts|knowledge|audit"),
    limit: Optional[int] = Query(None, ge=1, le=search_svc.MAX_LIMIT),
    user: dict = Depends(require_user),
) -> dict[str, Any]:
    """``GET /api/search`` — global search with FTS + vector ranking.

    Status codes:
      200 — hits/total/categories per openapi.yaml#/api/search.
      401 — handled by require_user.
      422 — invalid q / category / limit (field-level error map).
      429 — caller exceeded 60 req/min (Retry-After header set).
    """
    # AC-F3 rate limit per user
    user_key = _resolve_user_key(user)
    try:
        remaining = search_svc.get_rate_limiter().check(user_key)
    except search_svc.RateLimitExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limit_exceeded",
                "message": str(e),
                "retry_after_sec": e.retry_after_sec,
            },
            headers={"Retry-After": str(int(e.retry_after_sec) + 1)},
        )

    # AC-F2 / AC-F7 validation (service-level invariants)
    try:
        result = await search_svc.global_search(
            q,
            category=category,
            limit=limit,
            user_id=user_key,
        )
    except search_svc.InvalidSearchQuery as e:
        raise _field_error(e.field, str(e))
    except Exception as e:  # pragma: no cover
        logger.exception("global_search failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "internal_server_error", "message": "search failed"},
        )

    await _emit_audit(
        "search_invoked",
        user_id=user_key,
        detail={
            "query_chars": len(result.get("query") or ""),
            "category": category,
            "total": result.get("total"),
        },
    )

    # Response matches schemas.search.SearchResponse and openapi 2xx shape.
    return {
        "hits": result["hits"],
        "total": result["total"],
        "categories": result["categories"],
        "query": result["query"],
        "rate_limit_remaining": remaining,
    }
