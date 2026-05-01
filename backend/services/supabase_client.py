"""
Supabase クライアント（Auth + Storage 両用）。

ローカル開発のデフォルト設定:
    SUPABASE_URL = http://127.0.0.1:54321
    SUPABASE_ANON_KEY = supabase start で表示された Publishable key
    SUPABASE_SERVICE_KEY = supabase start で表示された Secret key
    SUPABASE_JWT_SECRET = local default (super-secret-jwt-token-with-at-least-32-characters-long)

本番では .env で上書き。
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional

import httpx
import jwt as pyjwt

SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "sb_publishable_ACJWlzQHlZjBrEguHvfOxg_3BJgxAaH",
)
SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    "sb_secret_N7UND0UgjKTVK-Uodkm0Hg_xSvEMPvz",
)
# ローカル supabase の JWT シークレット（本番では別途設定）
SUPABASE_JWT_SECRET = os.environ.get(
    "SUPABASE_JWT_SECRET",
    "super-secret-jwt-token-with-at-least-32-characters-long",
)

DEFAULT_BUCKET = os.environ.get("SUPABASE_BUCKET", "artifacts")


def auth_headers(use_service: bool = False) -> dict[str, str]:
    key = SUPABASE_SERVICE_KEY if use_service else SUPABASE_ANON_KEY
    return {"apikey": key, "Authorization": f"Bearer {key}"}


# ────────────────────────────────────────
# Auth: JWT 検証
# ────────────────────────────────────────


def verify_jwt(token: str) -> Optional[dict[str, Any]]:
    """Supabase Auth が発行した JWT を検証して claims を返す。失敗時は None。"""
    try:
        return pyjwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except Exception:
        return None


# ────────────────────────────────────────
# Storage: バケット操作
# ────────────────────────────────────────


@lru_cache(maxsize=1)
def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=60.0)


async def ensure_bucket(name: str = DEFAULT_BUCKET, public: bool = False) -> bool:
    """バケットが無ければ作る。"""
    client = _client()
    r = await client.post(
        f"{SUPABASE_URL}/storage/v1/bucket",
        headers=auth_headers(use_service=True),
        json={"id": name, "name": name, "public": public},
    )
    return r.status_code in (200, 201, 409)  # 409 = already exists


async def upload_file(
    path: str, content: bytes, content_type: str = "application/octet-stream",
    bucket: str = DEFAULT_BUCKET,
) -> str:
    """ファイルをアップロードし、storage path を返す。"""
    client = _client()
    r = await client.post(
        f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}",
        headers={
            **auth_headers(use_service=True),
            "Content-Type": content_type,
        },
        content=content,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"upload failed: {r.status_code} {r.text}")
    return f"{bucket}/{path}"


async def signed_url(path: str, expires_in: int = 3600, bucket: str = DEFAULT_BUCKET) -> str:
    client = _client()
    r = await client.post(
        f"{SUPABASE_URL}/storage/v1/object/sign/{bucket}/{path}",
        headers=auth_headers(use_service=True),
        json={"expiresIn": expires_in},
    )
    r.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1{r.json()['signedURL']}"
