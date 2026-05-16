"""T-V3-B-01: Pydantic schemas for Auth endpoints (F-001).

Schemas for POST /api/auth/login, POST /api/auth/signup,
POST /api/auth/password-reset (F-001 / Build-Factory v3 Phase 1 Wave 1).

仕様の出典:
  - docs/functional-breakdown/2026-05-16_v3/features.json#F-001
  - docs/api-design/2026-05-16_v3/openapi.yaml (paths: /api/auth/login,
    /api/auth/signup, /api/auth/password-reset)

すべての schema は inputs (request body) / outputs_2xx (success response) /
outputs_4xx (error envelope) を features.json の F-001.api_endpoints と
逐語一致させる. validation error は FastAPI が 422 + field-level error map に
変換する.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# RFC 5322 ライト互換 email pattern. pydantic[email] (email-validator) を強制依存に
# しないため pattern マッチで対応する. 本格的な MX / DNS 検証は GoTrue (Supabase
# Auth) 層に委譲する.
_EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/login
# ──────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    """features.json#F-001 endpoint POST /api/auth/login の inputs.

    - email: string (required, RFC 5322 互換)
    - password: string (required, min length 8)
    - mfa_code: string? (optional, TOTP 6 桁)
    """

    email: str = Field(..., pattern=_EMAIL_PATTERN, description="user email")
    password: str = Field(..., min_length=8, description="user password (>= 8 chars)")
    mfa_code: Optional[str] = Field(
        default=None,
        min_length=6,
        max_length=8,
        description="TOTP code (6-8 digits) — required when MFA is enabled",
    )


class LoginResponse(BaseModel):
    """features.json#F-001 endpoint POST /api/auth/login の outputs_2xx."""

    access_token: str
    refresh_token: str
    user_id: str
    mfa_required: bool = False


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/signup
# ──────────────────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    """features.json#F-001 endpoint POST /api/auth/signup の inputs."""

    email: str = Field(..., pattern=_EMAIL_PATTERN, description="user email")
    password: str = Field(
        ...,
        min_length=8,
        description="user password (>= 8 chars per F-001 outputs_4xx 422)",
    )
    name: str = Field(..., min_length=1, max_length=128, description="display name")
    invitation_token: Optional[str] = Field(
        default=None,
        min_length=1,
        description="optional invitation token (F-004 連携)",
    )


class SignupResponse(BaseModel):
    """features.json#F-001 endpoint POST /api/auth/signup の outputs_2xx."""

    user_id: str
    verify_email_sent: bool


# ──────────────────────────────────────────────────────────────────────
# POST /api/auth/password-reset
# ──────────────────────────────────────────────────────────────────────


class PasswordResetRequest(BaseModel):
    """features.json#F-001 endpoint POST /api/auth/password-reset の inputs."""

    email: str = Field(..., pattern=_EMAIL_PATTERN, description="email of the user requesting reset")


class PasswordResetResponse(BaseModel):
    """features.json#F-001 endpoint POST /api/auth/password-reset の outputs_2xx.

    Security note: AC-F3 (UNWANTED ears_ac_seed) — the response status must NOT
    reveal whether the account exists. Always return 2xx with the same body.
    """

    status: str = Field(
        default="email sent if account exists",
        description="generic message — must not leak account existence",
    )
