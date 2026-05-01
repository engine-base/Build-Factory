"""
FastAPI 用 Supabase Auth ミドルウェア。

ヘッダ `Authorization: Bearer <jwt>` を検証し、claims を request.state.user に格納する。
未認証アクセスはこのミドルウェアでは拒否しない（保護したいエンドポイントは
個別に `Depends(require_user)` を使う）。

開発環境では `BUILD_FACTORY_DEV_BYPASS_AUTH=1` で常に dummy user (masato) を渡す。
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.supabase_client import verify_jwt

DEV_BYPASS = os.environ.get("BUILD_FACTORY_DEV_BYPASS_AUTH", "1") == "1"

DEV_USER = {
    "sub": "00000000-0000-0000-0000-000000000001",
    "email": "info@engine-base.com",
    "user_metadata": {"slug": "masato", "name": "高本まさと"},
    "role": "authenticated",
}

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Optional[dict]:
    """JWT があれば検証して claims を返す。なければ None。"""
    if DEV_BYPASS and not credentials:
        return DEV_USER
    if not credentials:
        return None
    claims = verify_jwt(credentials.credentials)
    if not claims and DEV_BYPASS:
        return DEV_USER
    return claims


async def require_user(user: Optional[dict] = Depends(get_current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthenticated")
    return user
