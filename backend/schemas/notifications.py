"""T-V3-B-25 / F-018: Notifications API Pydantic schemas.

3 endpoints (features.json#F-018 + openapi.yaml):
  GET  /api/notifications                — list + unread_count
  POST /api/notifications/{id}/read      — mark single as read (read_at)
  POST /api/notifications/read-all       — mark all (optionally by category) as read (marked_count)

EARS AC マッピング (T-V3-B-25 / functional 9):
  AC-F1 STATE-DRIVEN  : unread のものは unread_count に含まれる
  AC-F2 EVENT-DRIVEN  : read-all (no category filter) → 全 unread を既読化
  AC-F3 EVENT-DRIVEN  : GET valid → 200 + items
  AC-F4 UNWANTED      : GET missing/invalid auth → 401
  AC-F5 UNWANTED      : GET invalid filter → 422 (field-level error map)
  AC-F6 EVENT-DRIVEN  : POST /{id}/read valid → 2xx + read_at
  AC-F7 UNWANTED      : POST /{id}/read missing/invalid auth → 401
  AC-F8 EVENT-DRIVEN  : POST /read-all valid → 2xx + marked_count
  AC-F9 UNWANTED      : POST /read-all missing/invalid auth → 401

DB columns (supabase/migrations/20260512000000_impl_integration_ops_tables.sql L244):
  id BIGSERIAL, workspace_id BIGINT, recipient_user_id TEXT, event_type TEXT,
  title TEXT, body TEXT, link_url TEXT, is_read BOOLEAN, priority TEXT,
  detail JSONB, created_at TIMESTAMPTZ, read_at TIMESTAMPTZ
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Entity (E-038 Notification) — DB row representation
# ──────────────────────────────────────────────────────────────────────


class Notification(BaseModel):
    """notifications テーブル 1 行の API 表現.

    openapi.yaml#Notification の contract に追従しつつ、
    DB 実カラム (recipient_user_id / event_type / title / body / link_url /
    is_read / priority / detail / created_at / read_at) を含む.
    """
    id: int
    workspace_id: Optional[int] = None
    recipient_user_id: str
    event_type: str
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    is_read: bool = False
    priority: str = "normal"
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None  # ISO-8601
    read_at: Optional[str] = None  # ISO-8601


# ──────────────────────────────────────────────────────────────────────
# GET /api/notifications — list response (items + unread_count)
# ──────────────────────────────────────────────────────────────────────


class NotificationListResponse(BaseModel):
    """GET /api/notifications response contract (features.json#F-018 / AC-F1, AC-F3)."""
    items: list[Notification] = Field(default_factory=list)
    unread_count: int = 0


# ──────────────────────────────────────────────────────────────────────
# POST /api/notifications/{id}/read — single read response
# ──────────────────────────────────────────────────────────────────────


class NotificationReadResponse(BaseModel):
    """POST /api/notifications/{id}/read response contract (AC-F6)."""
    read_at: str  # ISO-8601


# ──────────────────────────────────────────────────────────────────────
# POST /api/notifications/read-all — bulk read response + request
# ──────────────────────────────────────────────────────────────────────


class NotificationReadAllRequest(BaseModel):
    """POST /api/notifications/read-all request contract.

    `category` (event_type prefix) で対象を絞る. None or "" の場合は全 unread.
    """
    category: Optional[str] = None


class NotificationReadAllResponse(BaseModel):
    """POST /api/notifications/read-all response contract (AC-F2, AC-F8)."""
    marked_count: int = 0


# ──────────────────────────────────────────────────────────────────────
# Filter input — GET /api/notifications query
# ──────────────────────────────────────────────────────────────────────


class NotificationFilter(BaseModel):
    """GET /api/notifications query filter.

    全フィールド optional.
    - unread_only: True → is_read = false のみ
    - category   : event_type prefix で絞る
    """
    unread_only: Optional[bool] = None
    category: Optional[str] = None
