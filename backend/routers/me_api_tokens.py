"""T-V3-D-10: personal API token REST endpoints (F-030, E-030 APIKey).

openapi.yaml#F-030 で定義された 3 endpoint を実装する:

    GET    /api/me/api-tokens        -> { tokens: ApiToken[] }
    POST   /api/me/api-tokens        -> 201 + { token_id, plaintext_token_shown_once,
                                                 token_hint, expires_at, ... }
    DELETE /api/me/api-tokens/{id}   -> { token_id, revoked_at }

すべて Bearer auth (services.auth_middleware.require_user) を必須とし、
未認証は 401。本人 (auth user_id) の token のみ操作可能.

drift fix mapping (api-drift-summary.md#high-詳細-method-mismatch):
    `POST /api/me/api-tokens` は backend missing だった (T-V3-DRIFT-F-030-01).
    本 router で新規実装し、display-once (AC-F4) を保証する.

Related entities: E-030 APIKey (api_keys / api_tokens).
Related screens : S-063 api-tokens, S-064 api-tokens-create.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from services import api_token_service as svc
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me/api-tokens", tags=["me", "api-tokens"])


def _user_id(user: dict) -> str:
    """Supabase JWT claims から user_id を取り出す.

    優先順: user_metadata.slug → sub → email.
    """
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="unauthenticated")
    meta = user.get("user_metadata") or {}
    if isinstance(meta, dict) and meta.get("slug"):
        return str(meta["slug"])
    if user.get("sub"):
        return str(user["sub"])
    if user.get("email"):
        return str(user["email"])
    raise HTTPException(status_code=401, detail="unauthenticated")


class PostApiTokenBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    scopes: list[str] = Field(..., min_length=1)
    expires_at: Optional[str] = Field(
        default=None,
        description="ISO8601 UTC; omit → default 90 days",
    )


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/me/api-tokens
# ──────────────────────────────────────────────────────────────────────────────


@router.get("", summary="List my API tokens (hint-only)")
async def get_me_api_tokens(
    user: Annotated[dict, Depends(require_user)],
) -> dict[str, Any]:
    """AC-F4 enforcement: plaintext_token_shown_once は **絶対に** 含めない."""
    uid = _user_id(user)
    tokens = await svc.list_tokens(uid)
    return {"tokens": tokens}


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/me/api-tokens
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create new API token (display-once)",
)
async def post_me_api_tokens(
    body: PostApiTokenBody,
    user: Annotated[dict, Depends(require_user)],
) -> dict[str, Any]:
    """AC-F1 EVENT-DRIVEN: POST /api/me/api-tokens with valid scope → 201 with
    `{ token_id, plaintext_token_shown_once, token_hint, expires_at, ... }`.
    token hash (sha256) は api_tokens に persist; plaintext は **このレスポンス
    でのみ** 返す.

    AC-F4 UNWANTED: 平文 token は二度と返さない (test で list endpoint を
    検査して回帰防止).
    Errors: 401 (no auth) / 422 (validation) / 429 (rate-limit).
    """
    uid = _user_id(user)
    try:
        return await svc.create_token(
            uid,
            name=body.name,
            scopes=list(body.scopes),
            expires_at=body.expires_at,
        )
    except svc.ApiTokenValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "api_token.validation_error",
                "message": "field-level validation failed",
                "fields": e.args[0] if e.args else {},
            },
        )
    except svc.ApiTokenRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail={"code": "api_token.rate_limited", "message": str(e)},
        )


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /api/me/api-tokens/{id}
# ──────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/{id}",
    summary="Revoke an API token",
)
async def delete_me_api_tokens_by_id(
    user: Annotated[dict, Depends(require_user)],
    id: Annotated[str, Path(..., min_length=1)],
) -> dict[str, Any]:
    """対象 token を revoke (soft-delete).

    本人所有でない場合は 404 (情報漏洩防止のため 403 にしない).
    """
    uid = _user_id(user)
    try:
        return await svc.revoke_token(uid, id)
    except svc.ApiTokenNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "api_token.not_found", "message": str(e)},
        )
