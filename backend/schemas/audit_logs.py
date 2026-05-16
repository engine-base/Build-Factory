"""T-V3-B-24 / F-018: Audit logs API Pydantic schemas.

GET /api/audit-logs           — workspace_admin list audit_logs with filters
GET /api/audit-logs/export.csv — workspace_admin CSV export
GET /api/audit-logs/export.json — workspace_admin JSON export

EARS AC マッピング (T-V3-B-24):
  AC-F1 EVENT-DRIVEN  : >90 days range → 422 filter_too_broad
  AC-F2 EVENT-DRIVEN  : valid auth → 2xx with items + total
  AC-F3 UNWANTED      : missing/invalid auth → 401
  AC-F4 UNWANTED      : invalid filter (bad date / unknown field) → 422
  AC-F5 EVENT-DRIVEN  : valid auth → csv_body
  AC-F6 UNWANTED      : missing/invalid auth → 401 (csv)
  AC-F7 UNWANTED      : invalid filter → 422 (csv)
  AC-F8 EVENT-DRIVEN  : valid auth → json_body
  AC-F9 UNWANTED      : missing/invalid auth → 401 (json)
  AC-F10 UNWANTED     : invalid filter → 422 (json)
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Entity (E-037 AuditLog) — DB row representation
# ──────────────────────────────────────────────────────────────────────


class AuditLog(BaseModel):
    """audit_logs テーブル 1 行の API 表現.

    DB columns (supabase/migrations/20260510000001_bf_project_tables.sql L227):
      id BIGSERIAL, workspace_id BIGINT, actor_user_id TEXT, actor_persona TEXT,
      action TEXT, resource_type TEXT, resource_id BIGINT,
      payload JSONB, success BOOLEAN, created_at TIMESTAMPTZ
    """
    id: int
    workspace_id: Optional[int] = None
    actor_user_id: Optional[str] = None
    actor_persona: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    created_at: Optional[str] = None  # ISO-8601


# ──────────────────────────────────────────────────────────────────────
# GET /api/audit-logs — list response
# ──────────────────────────────────────────────────────────────────────


class AuditLogListResponse(BaseModel):
    """GET /api/audit-logs response contract (features.json#F-018)."""
    items: list[AuditLog] = Field(default_factory=list)
    total: int = 0


# ──────────────────────────────────────────────────────────────────────
# GET /api/audit-logs/export.csv — csv response
# ──────────────────────────────────────────────────────────────────────


class AuditLogCsvExportResponse(BaseModel):
    """GET /api/audit-logs/export.csv response contract.

    NOTE: 実際の content-type は text/csv だが、 features.json は
    response object に csv_body キーを持つことを要求しているため
    JSON wrapper response も提供する.
    """
    csv_body: str = ""


# ──────────────────────────────────────────────────────────────────────
# GET /api/audit-logs/export.json — json response
# ──────────────────────────────────────────────────────────────────────


class AuditLogJsonExportResponse(BaseModel):
    """GET /api/audit-logs/export.json response contract."""
    json_body: list[AuditLog] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Filter input — 共通 (3 endpoint で共有)
# ──────────────────────────────────────────────────────────────────────


class AuditLogFilter(BaseModel):
    """3 endpoint 共通 input filter.

    全フィールド optional. date format = ISO-8601 (YYYY-MM-DD or full ISO).
    """
    workspace_id: Optional[int] = None
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[str] = None

    model_config = {"populate_by_name": True}
