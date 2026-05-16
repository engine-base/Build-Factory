"""T-V3-B-26: Account profile REST API (F-023).

Implements 4 endpoints required by openapi.yaml#F-023:

    GET    /api/me                              -> { user, settings }
    PUT    /api/me                              -> { updated_at }
    POST   /api/me/api-keys                     -> { key_id, masked_key }
    DELETE /api/me/oauth/{provider}             -> { unlinked_at }

すべて Bearer auth (services.auth_middleware.require_user) を必須とし、
未認証は 401。本人 (auth user_id) の resource のみ操作可能 (RLS 等価).

Related entities: E-002 User, E-041 UserSettings, E-006 ApiKey.
Related screens : S-009 profile_settings.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from services import me as svc
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me", tags=["me"])


def _user_id(user: dict) -> str:
    """Supabase JWT claims から user_id を取り出す.

    優先順: user_metadata.slug (legacy masato 環境) → sub → email.
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


# ──────────────────────────────────────────────────────────────────────────────
# GET /api/me
# ──────────────────────────────────────────────────────────────────────────────


@router.get("", summary="Get my profile + settings")
async def get_me(
    user: Annotated[dict, Depends(require_user)],
) -> dict[str, Any]:
    """AC-F4 EVENT-DRIVEN: GET /api/me with valid token → 200 with {user, settings}.

    AC-F5 UNWANTED: no auth token → 401 (handled by `require_user`).
    """
    uid = _user_id(user)
    return await svc.get_me(uid)


# ──────────────────────────────────────────────────────────────────────────────
# PUT /api/me
# ──────────────────────────────────────────────────────────────────────────────


class PutMeSettings(BaseModel):
    theme: Optional[Literal["light", "dark", "system"]] = None
    locale: Optional[str] = Field(default=None, max_length=16)
    notifications_enabled: Optional[bool] = None


class PutMeBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    avatar_url: Optional[str] = Field(default=None, max_length=1000)
    settings: Optional[PutMeSettings] = None


@router.put("", summary="Update my profile / settings")
async def put_me(
    body: PutMeBody,
    user: Annotated[dict, Depends(require_user)],
) -> dict[str, Any]:
    """AC-F6 EVENT-DRIVEN: PUT /api/me with valid input → 200 { updated_at }.

    AC-F7 UNWANTED: no auth token → 401.
    AC-F8 UNWANTED: invalid body → 422 with field-level error map.
    """
    uid = _user_id(user)
    try:
        return await svc.put_me(
            uid,
            name=body.name,
            avatar_url=body.avatar_url,
            settings=body.settings.model_dump(exclude_none=True) if body.settings else None,
        )
    except svc.InvalidSettingsError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "validation_error",
                "message": "field-level validation failed",
                "fields": e.args[0] if e.args else {},
            },
        )


# ──────────────────────────────────────────────────────────────────────────────
# POST /api/me/api-keys
# ──────────────────────────────────────────────────────────────────────────────


class PostApiKeyBody(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    key_plaintext: str = Field(..., min_length=1, max_length=500)


@router.post(
    "/api-keys",
    status_code=status.HTTP_201_CREATED,
    summary="Register API key (pgsodium-encrypted at rest)",
)
async def post_me_api_keys(
    body: PostApiKeyBody,
    user: Annotated[dict, Depends(require_user)],
) -> dict[str, Any]:
    """AC-F1 EVENT-DRIVEN: POST /api/me/api-keys → encrypt key plaintext before persisting.

    AC-F2 UNWANTED: provider already has a key → 409.
    AC-F9 EVENT-DRIVEN: valid input → 201 with { key_id, masked_key }.
    AC-F10 UNWANTED: no auth token → 401.
    AC-F11 UNWANTED: invalid body → 422 with field-level error map.
    """
    uid = _user_id(user)
    try:
        return await svc.register_api_key(
            uid,
            provider=body.provider,
            key_plaintext=body.key_plaintext,
        )
    except svc.ApiKeyConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "api_key_conflict",
                "message": str(e),
            },
        )
    except svc.ApiKeyValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "validation_error",
                "message": "field-level validation failed",
                "fields": e.args[0] if e.args else {},
            },
        )


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /api/me/oauth/{provider}
# ──────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/oauth/{provider}",
    summary="Revoke + unlink OAuth provider",
)
async def delete_me_oauth_by_provider(
    user: Annotated[dict, Depends(require_user)],
    provider: Annotated[
        Literal["anthropic", "github", "slack", "google"],
        Path(...),
    ],
) -> dict[str, Any]:
    """AC-F3 EVENT-DRIVEN: revoke remote token + unlink locally.

    AC-F12 EVENT-DRIVEN: valid input → 200 with { unlinked_at }.
    AC-F13 UNWANTED: no auth token → 401.
    """
    uid = _user_id(user)
    try:
        return await svc.unlink_oauth(uid, provider)
    except svc.OAuthUnknownProviderError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_provider", "message": str(e)},
        )
    except svc.OAuthNotLinkedError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_linked", "message": str(e)},
        )
