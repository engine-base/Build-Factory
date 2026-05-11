"""T-023-04: OAuth 連携 REST API.

- GET    /api/oauth/providers              対応プロバイダ一覧
- GET    /api/oauth/{provider}/authorize   authorize URL を生成
- POST   /api/oauth/{provider}/callback    code → token 交換 + 保管
- GET    /api/oauth/{provider}/status      連携状態 (owner_id ベース)
- DELETE /api/oauth/{provider}             解除
"""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.oauth_providers import (
    PROVIDERS, UnknownProviderError, OAuthConfigError,
    build_authorize_url, exchange_code, save_token, load_token,
    delete_token, list_providers,
)


router = APIRouter(prefix="/api/oauth", tags=["oauth"])


@router.get("/providers")
async def get_providers() -> dict:
    return {"providers": list_providers()}


class AuthorizeRequest(BaseModel):
    redirect_uri: str = Field(..., min_length=1)
    scope: Optional[str] = None
    state: Optional[str] = None  # 指定がなければサーバ生成


@router.get("/{provider}/authorize")
async def authorize(
    provider: str,
    redirect_uri: str,
    scope: Optional[str] = None,
) -> dict:
    state = secrets.token_urlsafe(24)
    try:
        url = build_authorize_url(
            provider, state=state, redirect_uri=redirect_uri, scope=scope,
        )
    except UnknownProviderError:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    except OAuthConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"authorize_url": url, "state": state}


class CallbackRequest(BaseModel):
    code: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., min_length=1)
    owner_id: str = Field(..., min_length=1)
    expected_state: Optional[str] = None
    received_state: Optional[str] = None


@router.post("/{provider}/callback")
async def callback(provider: str, body: CallbackRequest) -> dict:
    # T-023-04 AC-UNWANTED: CSRF state 検証 (caller 側で生成・保持した state と一致するか)
    if body.expected_state and body.received_state and body.expected_state != body.received_state:
        await _audit("oauth.csrf_rejected", body.owner_id, {"provider": provider})
        raise HTTPException(status_code=400, detail={"code": "csrf_mismatch"})

    try:
        token = await exchange_code(
            provider, code=body.code, redirect_uri=body.redirect_uri,
        )
    except UnknownProviderError:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    except OAuthConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        await _audit("oauth.callback_failed", body.owner_id, {"provider": provider, "error": str(e)[:200]})
        raise HTTPException(status_code=502, detail=f"token exchange failed: {e}")

    save_token(provider, body.owner_id, token)
    await _audit("oauth.connected", body.owner_id, {"provider": provider})
    return {"ok": True, "provider": provider, "scopes": token.get("scope")}


@router.get("/{provider}/status")
async def status(provider: str, owner_id: str) -> dict:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    token = load_token(provider, owner_id)
    return {"provider": provider, "owner_id": owner_id, "connected": token is not None}


@router.delete("/{provider}")
async def disconnect(provider: str, owner_id: str) -> dict:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")
    ok = delete_token(provider, owner_id)
    if ok:
        await _audit("oauth.disconnected", owner_id, {"provider": provider})
    return {"ok": ok}


# ──────────────────────────────────────────
# audit_logs helper (T-023-04)
# ──────────────────────────────────────────
async def _audit(event_type: str, user_id: Optional[str], detail: dict) -> None:
    """audit_logs に event を流す。失敗してもアプリは止めない。"""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:
        print(f"[oauth] audit emit failed: {event_type} -- {e}")
