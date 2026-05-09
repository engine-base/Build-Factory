"""
upload_service.py — 画像アップロード (Supabase Storage)

ロゴ・印鑑・代表者写真・事例スクショ・背景画像などを Supabase Storage に保存し、
公開 URL を返す。account_settings.template_config から URL で参照する想定。

開発時は Supabase Storage が無い場合は backend/static/uploads/ にフォールバック保存。
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────
# 設定
# ──────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")
BUCKET_NAME = os.environ.get("BF_UPLOAD_BUCKET", "bf-uploads")

LOCAL_FALLBACK_DIR = Path(__file__).resolve().parents[1] / "static" / "uploads"
LOCAL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

# 1 ファイルあたり最大サイズ (15 MB)
MAX_BYTES = 15 * 1024 * 1024
ALLOWED_MIME = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml",
}


def _is_supabase_configured() -> bool:
    return bool(SUPABASE_URL) and bool(SUPABASE_SERVICE_KEY)


def _build_object_path(account_id: int, kind: str, filename: str) -> str:
    """account_id/kind/timestamp_hash.ext の形式でパス生成。"""
    safe_name = filename.replace("/", "_").replace("..", "_")
    ext = "." + safe_name.rsplit(".", 1)[-1] if "." in safe_name else ""
    h = hashlib.sha1(f"{time.time_ns()}-{safe_name}".encode()).hexdigest()[:10]
    return f"{account_id}/{kind}/{int(time.time())}_{h}{ext}"


# ──────────────────────────────────────────
# アップロード本体
# ──────────────────────────────────────────
async def upload_image(
    account_id: int,
    kind: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> dict:
    """画像をアップロードして公開 URL を返す。

    kind: 'logo' | 'stamp' | 'ceo_photo' | 'case_study' | 'hero_bg' | 'icon' | 'other'
    """
    if len(content) > MAX_BYTES:
        raise ValueError(f"file too large: {len(content)} bytes (max {MAX_BYTES})")

    if content_type not in ALLOWED_MIME:
        raise ValueError(f"unsupported content type: {content_type}")

    object_path = _build_object_path(account_id, kind, filename)

    if _is_supabase_configured():
        return await _upload_supabase(object_path, content, content_type)

    # フォールバック: ローカル保存
    return await _upload_local(object_path, content)


async def _upload_supabase(object_path: str, content: bytes, content_type: str) -> dict:
    """Supabase Storage REST API でアップロード。"""
    import httpx
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_NAME}/{object_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(upload_url, headers=headers, content=content)
        resp.raise_for_status()

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{object_path}"
    return {
        "url": public_url,
        "bucket": BUCKET_NAME,
        "path": object_path,
        "size": len(content),
        "storage": "supabase",
    }


async def _upload_local(object_path: str, content: bytes) -> dict:
    """ローカル static/uploads/ にフォールバック保存。"""
    target = LOCAL_FALLBACK_DIR / object_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    # static は FastAPI で /static にマウントされている前提
    return {
        "url": f"/static/uploads/{object_path}",
        "bucket": "local",
        "path": object_path,
        "size": len(content),
        "storage": "local",
    }


async def ensure_bucket() -> None:
    """Supabase Storage に bucket が無ければ作成。起動時に呼ばれる想定。"""
    if not _is_supabase_configured():
        return
    import httpx
    create_url = f"{SUPABASE_URL}/storage/v1/bucket"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    body = {"id": BUCKET_NAME, "name": BUCKET_NAME, "public": True}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.post(create_url, headers=headers, json=body)
            if resp.status_code == 200:
                return
            # Duplicate (既に存在) は無視
            if resp.status_code in (400, 409):
                return
        except Exception as e:
            print(f"[upload] bucket ensure failed: {e}")
