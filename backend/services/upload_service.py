"""
upload_service.py — 画像アップロード (Supabase Storage)

ロゴ・印鑑・代表者写真・事例スクショ・背景画像などを Supabase Storage に保存し、
公開 URL を返す。account_settings.template_config から URL で参照する想定。

開発時は Supabase Storage が無い場合は backend/static/uploads/ にフォールバック保存。

## T-015-03 audit event 定数 (gap closure G1)

  EVENT_UPLOAD_SUCCEEDED : 'uploads.upload_succeeded'
  EVENT_UPLOAD_REJECTED  : 'uploads.upload_rejected' (invalid input)
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# T-015-03 G3: share_url TTL range (60 sec - 30 day)
MIN_SHARE_TTL_SECONDS = 60
MAX_SHARE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 日

# T-015-03 G1: audit event 公開定数
EVENT_UPLOAD_SUCCEEDED = "uploads.upload_succeeded"
EVENT_UPLOAD_REJECTED = "uploads.upload_rejected"


async def _emit_upload_audit(
    event_type: str, *,
    account_id: Optional[int],
    kind: Optional[str],
    detail: dict,
) -> None:
    """audit emit (best-effort). DB 不在環境では silent skip."""
    payload = {"account_id": account_id, "kind": kind, **detail}
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=None, detail=payload)
    except Exception as e:  # pragma: no cover
        logger.warning("upload audit emit failed event=%s: %s", event_type, e)


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
    *,
    share_ttl_seconds: int = 3600 * 24 * 7,   # 7 日間有効
    generate_markdown: bool = True,
) -> dict:
    """画像をアップロードして公開 URL + 共有リンク + Markdown スニペットを返す.

    kind: 'logo' | 'stamp' | 'ceo_photo' | 'case_study' | 'hero_bg' | 'icon' | 'other'

    Returns:
      {
        url:        永続 public URL (Supabase) or local path
        share_url:  期限付き共有リンク (有効期限 share_ttl_seconds 秒)
        markdown:   `![alt](url)` 形式の Markdown 併記 (AC-1)
        bucket / path / size / storage
      }
    """
    # T-015-03 G3: share_ttl_seconds range validation
    if not isinstance(share_ttl_seconds, int) or isinstance(share_ttl_seconds, bool):
        await _emit_upload_audit(
            EVENT_UPLOAD_REJECTED,
            account_id=account_id, kind=kind,
            detail={"reason": "invalid_ttl_type", "ttl": str(share_ttl_seconds)},
        )
        raise ValueError("share_ttl_seconds must be int")
    if share_ttl_seconds < MIN_SHARE_TTL_SECONDS or share_ttl_seconds > MAX_SHARE_TTL_SECONDS:
        await _emit_upload_audit(
            EVENT_UPLOAD_REJECTED,
            account_id=account_id, kind=kind,
            detail={"reason": "ttl_out_of_range", "ttl": share_ttl_seconds},
        )
        raise ValueError(
            f"share_ttl_seconds must be in {MIN_SHARE_TTL_SECONDS}..{MAX_SHARE_TTL_SECONDS}"
        )

    if len(content) > MAX_BYTES:
        await _emit_upload_audit(
            EVENT_UPLOAD_REJECTED,
            account_id=account_id, kind=kind,
            detail={"reason": "file_too_large", "size": len(content)},
        )
        raise ValueError(f"file too large: {len(content)} bytes (max {MAX_BYTES})")

    if content_type not in ALLOWED_MIME:
        await _emit_upload_audit(
            EVENT_UPLOAD_REJECTED,
            account_id=account_id, kind=kind,
            detail={"reason": "unsupported_content_type", "content_type": content_type},
        )
        raise ValueError(f"unsupported content type: {content_type}")

    object_path = _build_object_path(account_id, kind, filename)

    if _is_supabase_configured():
        result = await _upload_supabase(object_path, content, content_type)
    else:
        result = await _upload_local(object_path, content)

    # T-015-03 AC-1: 共有リンク (期限付き) + Markdown 併記
    result["share_url"] = await _build_share_url(
        object_path, ttl_seconds=share_ttl_seconds,
        public_fallback=result["url"],
    )
    if generate_markdown:
        alt = f"{kind}_{filename}"
        result["markdown"] = build_markdown_snippet(result["url"], alt=alt)
    result["share_ttl_seconds"] = share_ttl_seconds

    # T-015-03 G1: 成功時 audit emit
    await _emit_upload_audit(
        EVENT_UPLOAD_SUCCEEDED,
        account_id=account_id, kind=kind,
        detail={
            "path": result.get("path"),
            "size": result.get("size"),
            "storage": result.get("storage"),
            "share_ttl_seconds": share_ttl_seconds,
        },
    )
    return result


async def _build_share_url(
    object_path: str, *, ttl_seconds: int, public_fallback: str,
) -> str:
    """Supabase signed URL (有効期限付き) を生成. 失敗 / 未設定時は public URL fallback."""
    if not _is_supabase_configured():
        # ローカル fallback: query string で expires_at を hint (検証は読み出し側で)
        from datetime import datetime, timedelta, timezone
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).isoformat().replace("+00:00", "Z")
        return f"{public_fallback}?expires_at={expires_at}"

    import httpx
    sign_url = f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET_NAME}/{object_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                sign_url, headers=headers, json={"expiresIn": ttl_seconds},
            )
            resp.raise_for_status()
            data = resp.json()
            signed_path = data.get("signedURL") or data.get("signedUrl") or ""
            if signed_path:
                if signed_path.startswith("http"):
                    return signed_path
                return f"{SUPABASE_URL}/storage/v1{signed_path}"
    except Exception:
        pass
    return public_fallback


def build_markdown_snippet(url: str, *, alt: str = "image") -> str:
    """T-015-03 AC: アップロード URL を Markdown 形式に変換.

    例: `![logo_engine-base.png](https://.../path)`
    alt 内の括弧などはエスケープ.
    """
    safe_alt = (alt or "image").replace("[", "(").replace("]", ")")
    safe_url = url.replace(" ", "%20")
    return f"![{safe_alt}]({safe_url})"


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
