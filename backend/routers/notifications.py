"""T-V3-B-25 / F-018: Notifications backend REST endpoints.

3 endpoints (features.json#F-018 + openapi.yaml):
  GET  /api/notifications              authenticated list (items + unread_count)
  POST /api/notifications/{id}/read    authenticated mark single as read
  POST /api/notifications/read-all     authenticated mark all unread as read

EARS AC マッピング (T-V3-B-25):
  AC-F1 STATE-DRIVEN  : While unread → included in unread_count
  AC-F2 EVENT-DRIVEN  : read-all (no category) → 全 unread を既読化
  AC-F3 EVENT-DRIVEN  : GET valid → 200 + items
  AC-F4 UNWANTED      : GET missing auth → 401
  AC-F5 UNWANTED      : GET invalid filter (bad type) → 422
  AC-F6 EVENT-DRIVEN  : POST /{id}/read valid → 200 + read_at
  AC-F7 UNWANTED      : POST /{id}/read missing auth → 401
  AC-F8 EVENT-DRIVEN  : POST /read-all valid → 200 + marked_count
  AC-F9 UNWANTED      : POST /read-all missing auth → 401

Access policies:
  - notifications:authenticated_select (E-038, recipient_user_id = auth.uid())

DB-level RLS: supabase/migrations/20260512000000_impl_integration_ops_tables.sql
  notifications_recipient policy で recipient_user_id = auth.uid()::text 強制.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request

from schemas.notifications import (
    Notification,
    NotificationListResponse,
    NotificationReadAllRequest,
    NotificationReadAllResponse,
    NotificationReadResponse,
)
from services import notifications as svc
from services.notifications import NotificationFilterError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ──────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _filter_error_to_http(err: NotificationFilterError) -> HTTPException:
    """NotificationFilterError → 422 HTTP. structured detail {code, message}."""
    detail: dict[str, Any] = {"code": err.code, "message": err.message}
    return HTTPException(status_code=422, detail=detail)


async def _require_user_dep(
    request: Request,
) -> dict:
    """Lazy auth dependency (audit_logs router と同じ pattern).

    `services.auth_middleware` を import 時ではなく call 時に読み込むことで、
    SUPABASE_* env vars が未設定でも router module 自身は import 可能.
    """
    from services.auth_middleware import get_current_user
    from fastapi.security import HTTPBearer
    bearer = HTTPBearer(auto_error=False)
    creds = await bearer(request)  # type: ignore[arg-type]
    user = await get_current_user(request, creds)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "notifications.unauthenticated",
                "message": "missing or invalid auth token",
            },
        )
    return user


def _user_id_from(user: dict) -> str:
    """user dict から recipient_user_id (DB の TEXT 列) を抽出. RLS と整合させる."""
    if not isinstance(user, dict):
        raise _error(
            "notifications.forbidden",
            "user payload invalid",
            status_code=403,
        )
    uid = user.get("sub") or user.get("id") or user.get("user_id")
    if not uid:
        raise _error(
            "notifications.forbidden",
            "user identifier missing",
            status_code=403,
        )
    return str(uid)


# ──────────────────────────────────────────────────────────────────────
# GET /api/notifications — list (AC-F1/F3/F4/F5)
# ──────────────────────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    unread_only: Optional[bool] = Query(None),
    category: Optional[str] = Query(None),
    user: dict = Depends(_require_user_dep),
) -> NotificationListResponse:
    """authenticated user の通知一覧 + unread_count.

    AC-F1: STATE-DRIVEN  — unread のものは unread_count に含まれる
    AC-F3: valid → 200 + items
    AC-F4: missing auth → 401 (_require_user_dep)
    AC-F5: invalid filter → 422 (NotificationFilterError → _filter_error_to_http)
    """
    recipient = _user_id_from(user)
    try:
        f = svc.normalize_filter(
            recipient_user_id=recipient,
            unread_only=unread_only,
            category=category,
        )
    except NotificationFilterError as e:
        raise _filter_error_to_http(e) from e
    rows = await svc.list_notifications(f)
    items = [Notification(**r) for r in rows]
    unread_count = await svc.count_unread(recipient)
    return NotificationListResponse(items=items, unread_count=unread_count)


# ──────────────────────────────────────────────────────────────────────
# POST /api/notifications/{id}/read — single (AC-F6/F7)
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/{id}/read",
    response_model=NotificationReadResponse,
    status_code=200,
)
async def post_notification_read(
    id: int = Path(..., gt=0),
    user: dict = Depends(_require_user_dep),
) -> NotificationReadResponse:
    """単一 notification を既読化.

    AC-F6: valid → 200 + read_at
    AC-F7: missing auth → 401
    404 if not found / not owned by caller (RLS 等価の row-level check).
    """
    recipient = _user_id_from(user)
    try:
        read_at = await svc.mark_as_read(id, recipient)
    except NotificationFilterError as e:
        raise _filter_error_to_http(e) from e
    if read_at is None:
        raise _error(
            "notifications.not_found",
            f"notification id={id} not found for current user",
            status_code=404,
        )
    return NotificationReadResponse(read_at=read_at)


# ──────────────────────────────────────────────────────────────────────
# POST /api/notifications/read-all — bulk (AC-F2/F8/F9)
# ──────────────────────────────────────────────────────────────────────


@router.post(
    "/read-all",
    response_model=NotificationReadAllResponse,
    status_code=200,
)
async def post_notifications_read_all(
    body: Optional[NotificationReadAllRequest] = Body(default=None),
    user: dict = Depends(_require_user_dep),
) -> NotificationReadAllResponse:
    """全 unread (or category filter) を既読化.

    AC-F2: read-all (no category) → 全 unread を既読化
    AC-F8: valid → 200 + marked_count
    AC-F9: missing auth → 401
    """
    recipient = _user_id_from(user)
    category = body.category if body is not None else None
    try:
        marked_count = await svc.mark_all_as_read(recipient, category=category)
    except NotificationFilterError as e:
        raise _filter_error_to_http(e) from e
    return NotificationReadAllResponse(marked_count=marked_count)
