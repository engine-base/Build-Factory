"""T-V3-B-08 / F-005b: Pydantic schemas for Mocks backend (list / detail / html GET/PUT).

OpenAPI 仕様 (docs/api-design/2026-05-16_v3/openapi.yaml) との contract に
1:1 対応する request / response model 群.

スコープ entities: E-011 Screen / E-012 Component / E-013 ScreenComponent /
E-014 Artifact (workspace_scoped).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────
# Screen / MockSummary
# ──────────────────────────────────────────────────────────────────────


class ScreenSummary(BaseModel):
    """Screen entity surface (E-011) for list response."""

    screen_id: str = Field(..., description="screen logical id (e.g. S-023)")
    name: str = Field(..., description="display name")
    workspace_id: int = Field(..., ge=1)
    version: int = Field(..., ge=0)
    updated_at: str = Field(default="", description="ISO8601 UTC")
    html_url: str = Field(..., description="URL to fetch latest html")


class MockListResponse(BaseModel):
    """GET /api/workspaces/{id}/mocks response."""

    mocks: list[ScreenSummary]
    total: int = Field(..., ge=0)


# ──────────────────────────────────────────────────────────────────────
# Screen detail
# ──────────────────────────────────────────────────────────────────────


class ScreenDetail(BaseModel):
    id: str
    name: str
    workspace_id: int = Field(..., ge=1)


class MockDetailResponse(BaseModel):
    """GET /api/workspaces/{id}/mocks/{screen_id} response."""

    screen: ScreenDetail
    html_url: str
    version: int = Field(..., ge=0)


# ──────────────────────────────────────────────────────────────────────
# HTML GET / PUT
# ──────────────────────────────────────────────────────────────────────


class MockHtmlResponse(BaseModel):
    """GET /api/workspaces/{id}/mocks/{screen_id}/html response."""

    html: str
    version: int = Field(..., ge=0)


class MockHtmlPutRequest(BaseModel):
    """PUT /api/workspaces/{id}/mocks/{screen_id}/html request body.

    F-005b policy: max_size_per_screen_mb = 1 (enforced in service layer to
    return 422 with code mocks.html_too_large).
    """

    html: str = Field(..., description="raw HTML body (utf-8, up to 1MB)")
    # optional display name (creates record on first PUT)
    name: Optional[str] = Field(default=None, max_length=200)

    @field_validator("html")
    @classmethod
    def _html_must_be_string(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("html must be string")
        # NOTE: 1MB upper bound is enforced in service layer for stable error
        # code (mocks.html_too_large -> 422). Pydantic side keeps a generous
        # length guard so DoS-style payloads still 422 even if service is
        # bypassed in unit tests.
        if len(v) > 4 * 1024 * 1024:  # 4MB char-level safety net
            raise ValueError("html exceeds safety cap (4MB chars)")
        return v


class MockHtmlPutResponse(BaseModel):
    """PUT /api/workspaces/{id}/mocks/{screen_id}/html response."""

    new_version: int = Field(..., ge=1)
    updated_at: str


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-09: ai-edit
# ──────────────────────────────────────────────────────────────────────


class MockAiEditRequest(BaseModel):
    """POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit request body."""

    prompt: str = Field(..., min_length=1, max_length=8000)

    @field_validator("prompt")
    @classmethod
    def _prompt_not_blank(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("prompt must not be blank")
        return v


class MockAiEditResponse(BaseModel):
    """POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit response."""

    diff: str
    new_html: str
    tokens_used: int = Field(..., ge=0)
