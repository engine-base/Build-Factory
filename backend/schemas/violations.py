"""T-V3-B-18 / F-012: Violations backend Pydantic schemas.

OpenAPI 仕様: docs/api-design/2026-05-16_v3/openapi.yaml#RedLineViolation
Entity: E-031 RedLine, E-032 RedLineViolation

このモジュールは violations backend の list / approve / reject endpoint の
request / response shape を定義する. router 層はここで定義する型のみを
レスポンスとして返却し、サービス層との contract を一箇所に集約する.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

ViolationStatus = Literal["pending", "approved", "rejected"]
ViolationActionTaken = Literal["blocked", "warned", "logged"]


# ─────────────────────────────────────────────────────────────────────────────
# Response DTOs (OpenAPI #RedLineViolation に対応)
# ─────────────────────────────────────────────────────────────────────────────


class ViolationOut(BaseModel):
    """E-032 RedLineViolation の serialize 形.

    F-012 contract: list / approve / reject endpoint の各レスポンスで
    返却される共通レコード型.
    """

    violation_id: str = Field(..., description="RedLineViolation primary key (uuid)")
    workspace_id: str = Field(..., description="所属 workspace の uuid")
    red_line_id: str = Field(..., description="紐付く red_line の uuid (default:: prefix も可)")
    session_id: Optional[str] = Field(
        None, description="originating AI session id (None なら session 紐付け無し)"
    )
    matched_text: str = Field(..., description="block 一致したテキスト (先頭 1000 chars)")
    action_taken: ViolationActionTaken = Field(..., description="blocked | warned | logged")
    status: ViolationStatus = Field(..., description="pending | approved | rejected")
    resolution_reason: Optional[str] = Field(None, description="approve/reject 時の理由")
    resolved_by: Optional[str] = Field(None, description="approve/reject を実行した user id")
    resolved_at: Optional[str] = Field(None, description="解決時刻 (ISO8601, UTC)")
    created_at: str = Field(..., description="作成時刻 (ISO8601, UTC)")


class ViolationListResponse(BaseModel):
    """GET /api/workspaces/{id}/violations — list response.

    AC-F3 EVENT-DRIVEN: 2xx + ``violations`` 配列を返す contract.
    """

    violations: list[ViolationOut] = Field(
        default_factory=list,
        description="workspace に属する violation 一覧 (created_at desc 順)",
    )
    count: int = Field(..., ge=0, description="violations array の長さと一致")


class ViolationApproveResponse(BaseModel):
    """POST /api/violations/{id}/approve — approve response.

    AC-F6 EVENT-DRIVEN: 2xx + ``approved_at`` を必ず含む.
    """

    violation_id: str
    workspace_id: str
    red_line_id: str
    session_id: Optional[str] = None
    matched_text: str
    action_taken: ViolationActionTaken
    status: ViolationStatus
    resolution_reason: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str
    approved_at: str = Field(
        ...,
        description="approve 確定時刻 (AC-F6 必須フィールド, resolved_at と同値)",
    )
    resumed_session_id: Optional[str] = Field(
        None,
        description="approve により resume された session id (AC-F1 mapping)",
    )


class ViolationRejectResponse(BaseModel):
    """POST /api/violations/{id}/reject — reject response.

    AC-F8 EVENT-DRIVEN: 2xx + ``rejected_at`` を必ず含む.
    """

    violation_id: str
    workspace_id: str
    red_line_id: str
    session_id: Optional[str] = None
    matched_text: str
    action_taken: ViolationActionTaken
    status: ViolationStatus
    resolution_reason: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str
    rejected_at: str = Field(
        ...,
        description="reject 確定時刻 (AC-F8 必須フィールド, resolved_at と同値)",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Request DTOs
# ─────────────────────────────────────────────────────────────────────────────


class ViolationResolveRequest(BaseModel):
    """POST /api/violations/{id}/{approve|reject} の共通 request body.

    AC-F2 / AC-F5 / AC-F9: reason は 1..4096 chars の非空文字列.
    422 は field-level error map で返却する (router 層責務).
    """

    reason: str = Field(..., min_length=1, max_length=4096)


# ─────────────────────────────────────────────────────────────────────────────
# Error envelope (router 層が HTTPException.detail に流し込む)
# ─────────────────────────────────────────────────────────────────────────────


class ViolationErrorEnvelope(BaseModel):
    """422 / 401 / 403 / 404 / 409 の HTTPException.detail 構造.

    OpenAPI #ErrorResponse と互換: `{code, message, errors?: [{loc,msg,type}]}`.
    """

    code: str
    message: str
    errors: Optional[list[dict[str, Any]]] = None


__all__ = [
    "ViolationStatus",
    "ViolationActionTaken",
    "ViolationOut",
    "ViolationListResponse",
    "ViolationApproveResponse",
    "ViolationRejectResponse",
    "ViolationResolveRequest",
    "ViolationErrorEnvelope",
]
