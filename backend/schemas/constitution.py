"""T-V3-B-28 / F-026: Constitution backend Pydantic schemas.

依存:
  - features.json#F-026 api_endpoints
  - docs/api-design/2026-05-16_v3/openapi.yaml /api/workspaces/{id}/constitution*
  - entities.json#E-017 Constitution (table bf_constitutions)

API:
  - GET    /api/workspaces/{id}/constitution
  - POST   /api/workspaces/{id}/constitution/versions
  - POST   /api/workspaces/{id}/constitution/versions/{v}/approve

contract:
  - GET    response: { content_md: str, version: int, is_active: bool }
  - POST   versions request: { content_md: str, message: str }
  - POST   versions response: { version_id: uuid, version_number: int }
  - POST   approve response: { approved_at: iso datetime, active_version: int }

constraint:
  - features.json#F-026 policies "max_size_kb 10" → content_md <= 10240 bytes
  - 超過時 422 (AC-F3)
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# 10 KB 上限 (features.json#F-026 policies: max_size_kb 10).
# bytes 単位 (UTF-8 encoded length) で判定する.
CONTENT_MD_MAX_BYTES = 10 * 1024


class ConstitutionResponse(BaseModel):
    """GET /api/workspaces/{id}/constitution 2xx 応答 (features.json#F-026)."""

    content_md: str
    version: int
    is_active: bool


class ConstitutionVersionCreateRequest(BaseModel):
    """POST /api/workspaces/{id}/constitution/versions リクエスト本文."""

    content_md: str = Field(
        ..., description="Constitution Markdown 本文 (max 10 KB)",
    )
    message: str = Field(
        ..., description="改訂 message (rationale / changelog)",
    )

    @field_validator("content_md")
    @classmethod
    def _validate_content_md_size(cls, v: str) -> str:
        # 422: content_md too large (>10KB) (AC-F3 / features.json error 422).
        # bytes 単位 (UTF-8 encoded) で判定する.
        if v is None:
            raise ValueError("content_md must not be null")
        if not isinstance(v, str):
            raise ValueError("content_md must be a string")
        if not v.strip():
            raise ValueError("content_md must not be empty")
        if len(v.encode("utf-8")) > CONTENT_MD_MAX_BYTES:
            raise ValueError(
                f"content_md exceeds {CONTENT_MD_MAX_BYTES} bytes (>10KB)"
            )
        return v

    @field_validator("message")
    @classmethod
    def _validate_message(cls, v: str) -> str:
        if v is None or not isinstance(v, str):
            raise ValueError("message must be a string")
        if not v.strip():
            raise ValueError("message must not be empty")
        if len(v) > 2000:
            raise ValueError("message must be <= 2000 chars")
        return v


class ConstitutionVersionCreateResponse(BaseModel):
    """POST /api/workspaces/{id}/constitution/versions 2xx 応答."""

    version_id: str  # uuid 風文字列 (sqlite 環境では bigserial.id を str(uuid4) 化)
    version_number: int


class ConstitutionVersionApproveResponse(BaseModel):
    """POST /api/workspaces/{id}/constitution/versions/{v}/approve 2xx 応答."""

    approved_at: str  # ISO 8601 timestamptz
    active_version: int


class ConstitutionErrorDetail(BaseModel):
    """4xx error 共通 envelope (workspaces.py の _error helper と互換)."""

    code: str
    message: str
    field: Optional[str] = None


__all__ = [
    "CONTENT_MD_MAX_BYTES",
    "ConstitutionResponse",
    "ConstitutionVersionCreateRequest",
    "ConstitutionVersionCreateResponse",
    "ConstitutionVersionApproveResponse",
    "ConstitutionErrorDetail",
]
