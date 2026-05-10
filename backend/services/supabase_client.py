"""
Supabase クライアント（Auth + Storage 両用）。

すべての Supabase 関連シークレットは環境変数経由で必須 (T-001-01)。
ハードコードフォールバックは不採用 — `.env` に未設定の場合は import 時に失敗する。

必須 env vars:
    SUPABASE_URL          (例: https://<project>.supabase.co または http://127.0.0.1:54321)
    SUPABASE_ANON_KEY     (公開可)
    SUPABASE_SERVICE_KEY  (秘匿、サーバーサイドのみ)
    SUPABASE_JWT_SECRET   (HS256 検証用)

任意:
    SUPABASE_BUCKET       (デフォルト: "artifacts")
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional

import httpx
import jwt as pyjwt

_REQUIRED = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_JWT_SECRET")
_missing = [k for k in _REQUIRED if not os.environ.get(k)]
if _missing:
    raise RuntimeError(
        "Supabase 環境変数が未設定です: "
        + ", ".join(_missing)
        + " — .env を作成し SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_KEY / "
        "SUPABASE_JWT_SECRET を設定してください (.env.example 参照)。"
    )

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY: str = os.environ["SUPABASE_ANON_KEY"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_JWT_SECRET: str = os.environ["SUPABASE_JWT_SECRET"]
DEFAULT_BUCKET: str = os.environ.get("SUPABASE_BUCKET", "artifacts")


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
