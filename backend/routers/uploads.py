"""
uploads.py — 画像アップロード API

POST /api/uploads
  multipart/form-data:
    - file: 画像ファイル
    - account_id: int
    - kind: logo | stamp | ceo_photo | case_study | hero_bg | icon | other
"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services import upload_service as svc

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


ALLOWED_KINDS = {"logo", "stamp", "ceo_photo", "case_study", "hero_bg", "icon", "other"}


@router.post("")
async def upload(
    account_id: int = Form(...),
    kind: str = Form("other"),
    file: UploadFile = File(...),
    share_ttl_seconds: int = Form(3600 * 24 * 7),
):
    """T-015-03: Storage upload + 共有リンク + Markdown 併記.

    Response shape:
      {url, share_url, markdown, bucket, path, size, storage, share_ttl_seconds}

    Error contract (T-S0-08 統一仕様):
      4xx: {detail: {code, message}}
    """
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unknown_kind",
                "message": f"unknown kind: {kind}. allowed: {sorted(ALLOWED_KINDS)}",
            },
        )

    content = await file.read()
    try:
        result = await svc.upload_image(
            account_id=account_id,
            kind=kind,
            filename=file.filename or "untitled",
            content=content,
            content_type=file.content_type or "application/octet-stream",
            share_ttl_seconds=share_ttl_seconds,
        )
    except ValueError as e:
        # AC-4 UNWANTED: invalid input (size / mime / ttl) → 400 + machine-readable
        msg = str(e)
        if "too large" in msg:
            code = "file_too_large"
        elif "share_ttl_seconds" in msg:
            code = "invalid_ttl"
        else:
            code = "unsupported_content_type"
        raise HTTPException(
            status_code=400,
            detail={"code": code, "message": msg},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "upload_failed", "message": str(e)[:200]},
        )

    return result
