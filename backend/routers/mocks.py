"""T-V3-B-08 / T-V3-B-09 / F-005b: Mocks backend router.

F-005b 画面モック自動生成パイプライン (M-5b) — backend endpoint surface.

Endpoints:
  T-V3-B-08:
    GET    /api/workspaces/{workspace_id}/mocks
    GET    /api/workspaces/{workspace_id}/mocks/{screen_id}
    GET    /api/workspaces/{workspace_id}/mocks/{screen_id}/html
    PUT    /api/workspaces/{workspace_id}/mocks/{screen_id}/html
  T-V3-B-09 (this PR):
    POST   /api/workspaces/{workspace_id}/mocks/{screen_id}/ai-edit
           (rate-limited to 30/min/workspace per F-005b policy)

Auth role: member (GET) / workspace_admin (PUT) — access enforced via
Supabase RLS + workspace_member_select / workspace_admin_rw policies
(access_policies_required: screens|components|screen_components|artifacts
:workspace_member_select).

EARS AC mapping (verbatim from features.json#F-005b.ears_ac_seed +
派生 AC for the 4 endpoints):
  AC-F1  EVENT-DRIVEN  GET html → latest version
  AC-F2  EVENT-DRIVEN  PUT html → version increment + snapshot
  AC-F3  UNWANTED      PUT html > 1MB → 422
  AC-F5  STATE-DRIVEN  mock locked → PUT → 409
  AC-F6  EVENT-DRIVEN  GET list → 2xx {mocks, total}
  AC-F7  UNWANTED      GET list w/o token → 401
  AC-F8  UNWANTED      GET list bad input → 422
  AC-F9  EVENT-DRIVEN  GET detail → 2xx {screen, html_url, version}
  AC-F10 UNWANTED      GET detail w/o token → 401
  AC-F11 UNWANTED      GET detail bad input → 422
  AC-F12 EVENT-DRIVEN  GET html → 2xx {html}
  AC-F13 UNWANTED      GET html w/o token → 401
  AC-F14 EVENT-DRIVEN  PUT html → 2xx {new_version, updated_at}
  AC-F15 UNWANTED      PUT html w/o token → 401
  AC-F16 UNWANTED      PUT html bad input → 422
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from schemas.mocks import (
    MockAiEditRequest,
    MockAiEditResponse,
    MockDetailResponse,
    MockHtmlPutRequest,
    MockHtmlPutResponse,
    MockHtmlResponse,
    MockListResponse,
)
from services import mocks as svc
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["mocks"])


# ──────────────────────────────────────────────────────────────────────
# Error helpers
# ──────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _map_service_error(e: Exception) -> HTTPException:
    """Map service-level exception to FastAPI HTTPException with structured detail."""
    if isinstance(e, svc.MockNotFoundError):
        return _error("mocks.not_found", str(e), status_code=404)
    if isinstance(e, svc.MockLockedError):
        return _error("mocks.locked", str(e), status_code=409)
    if isinstance(e, svc.MockRateLimitedError):
        # T-V3-B-09 AC-F1 / AC-F5: ai-edit > 30/min/workspace → 429
        return _error("mocks.rate_limited", str(e), status_code=429)
    if isinstance(e, svc.MockHtmlTooLargeError):
        return _error("mocks.html_too_large", str(e), status_code=422)
    if isinstance(e, svc.MockValidationError):
        return _error("mocks.invalid_input", str(e), status_code=422)
    if isinstance(e, svc.MockError):
        return _error("mocks.invalid", str(e), status_code=400)
    logger.exception("mocks.internal_error: %s", e)
    return _error("mocks.internal", "internal server error", status_code=500)


def _validate_workspace_id(workspace_id: int) -> int:
    if workspace_id is None or workspace_id <= 0:
        raise _error(
            "mocks.invalid_workspace_id",
            "workspace_id must be > 0",
            status_code=422,
        )
    return workspace_id


def _actor_id_from_user(user: dict) -> Optional[str]:
    """JWT claims から actor user_id を抽出."""
    if not isinstance(user, dict):
        return None
    return user.get("sub") or user.get("user_id") or user.get("email")


# ──────────────────────────────────────────────────────────────────────
# GET /api/workspaces/{workspace_id}/mocks
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/mocks",
    response_model=MockListResponse,
    status_code=status.HTTP_200_OK,
    summary="画面モック一覧 (F-005b)",
)
async def list_mocks(
    workspace_id: int,
    user: dict = Depends(require_user),
) -> MockListResponse:
    """AC-F6 EVENT-DRIVEN / AC-F7 UNWANTED 401 / AC-F8 UNWANTED 422."""
    _validate_workspace_id(workspace_id)
    try:
        result = svc.list_mocks(workspace_id)
    except Exception as e:
        raise _map_service_error(e) from e
    return MockListResponse(**result)


# ──────────────────────────────────────────────────────────────────────
# GET /api/workspaces/{workspace_id}/mocks/{screen_id}
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/mocks/{screen_id}",
    response_model=MockDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="画面モック詳細 (F-005b)",
)
async def get_mock_detail(
    workspace_id: int,
    screen_id: str,
    user: dict = Depends(require_user),
) -> MockDetailResponse:
    """AC-F9 EVENT-DRIVEN / AC-F10 UNWANTED 401 / AC-F11 UNWANTED 422."""
    _validate_workspace_id(workspace_id)
    try:
        result = svc.get_mock(workspace_id, screen_id)
    except Exception as e:
        raise _map_service_error(e) from e
    return MockDetailResponse(**result)


# ──────────────────────────────────────────────────────────────────────
# GET /api/workspaces/{workspace_id}/mocks/{screen_id}/html
# ──────────────────────────────────────────────────────────────────────


@router.get(
    "/{workspace_id}/mocks/{screen_id}/html",
    response_model=MockHtmlResponse,
    status_code=status.HTTP_200_OK,
    summary="画面モック HTML 取得 (F-005b)",
)
async def get_mock_html(
    workspace_id: int,
    screen_id: str,
    user: dict = Depends(require_user),
) -> MockHtmlResponse:
    """AC-F1 / AC-F12 EVENT-DRIVEN / AC-F13 UNWANTED 401."""
    _validate_workspace_id(workspace_id)
    try:
        result = svc.get_mock_html(workspace_id, screen_id)
    except Exception as e:
        raise _map_service_error(e) from e
    return MockHtmlResponse(**result)


# ──────────────────────────────────────────────────────────────────────
# PUT /api/workspaces/{workspace_id}/mocks/{screen_id}/html
# ──────────────────────────────────────────────────────────────────────


@router.put(
    "/{workspace_id}/mocks/{screen_id}/html",
    response_model=MockHtmlPutResponse,
    status_code=status.HTTP_200_OK,
    summary="画面モック HTML 更新 (F-005b)",
)
async def put_mock_html(
    workspace_id: int,
    screen_id: str,
    body: MockHtmlPutRequest,
    user: dict = Depends(require_user),
) -> MockHtmlPutResponse:
    """AC-F2 EVENT-DRIVEN / AC-F3 UNWANTED 422 (>1MB) / AC-F5 STATE-DRIVEN 409 /
    AC-F14 EVENT-DRIVEN / AC-F15 UNWANTED 401 / AC-F16 UNWANTED 422.
    """
    _validate_workspace_id(workspace_id)
    actor = _actor_id_from_user(user)
    try:
        result = svc.put_mock_html(
            workspace_id,
            screen_id,
            body.html,
            actor_user_id=actor,
            name=body.name,
        )
    except Exception as e:
        raise _map_service_error(e) from e

    # audit_logs: mock_edited (best-effort, non-blocking)
    await _emit_audit(
        "mock_edited",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "screen_id": screen_id,
            "new_version": result["new_version"],
        },
    )
    return MockHtmlPutResponse(**result)


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-09: POST /api/workspaces/{workspace_id}/mocks/{screen_id}/ai-edit
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/{workspace_id}/mocks/{screen_id}/ai-edit",
    response_model=MockAiEditResponse,
    status_code=status.HTTP_201_CREATED,
    summary="画面モック AI 編集 (F-005b / 30/min/workspace)",
)
async def post_mock_ai_edit(
    workspace_id: int,
    screen_id: str,
    body: MockAiEditRequest,
    user: dict = Depends(require_user),
) -> MockAiEditResponse:
    """T-V3-B-09 — F-005b POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit.

    AC マッピング:
      AC-F1  UNWANTED   : > 30/min/workspace → 429
      AC-F2  EVENT      : valid input → 201 {diff, new_html, tokens_used}
      AC-F3  UNWANTED   : without auth → 401 (require_user)
      AC-F4  UNWANTED   : invalid body → 422
      AC-F5  UNWANTED   : same as AC-F1 (rate limit alias)
    """
    _validate_workspace_id(workspace_id)
    actor = _actor_id_from_user(user)
    try:
        result = svc.ai_edit_mock(
            workspace_id,
            screen_id,
            body.prompt,
            actor_user_id=actor,
        )
    except Exception as e:
        raise _map_service_error(e) from e

    # audit_logs: mock_ai_edited (best-effort, non-blocking)
    await _emit_audit(
        "mock_ai_edited",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "screen_id": screen_id,
            "tokens_used": result["tokens_used"],
        },
    )
    return MockAiEditResponse(**result)


# ──────────────────────────────────────────────────────────────────────
# audit helper (best-effort)
# ──────────────────────────────────────────────────────────────────────


async def _emit_audit(
    event_type: str, *, user_id: Optional[str], detail: dict[str, Any],
) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("mocks audit emit failed: %s -- %s", event_type, e)
