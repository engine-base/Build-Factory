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
):
    if kind not in ALLOWED_KINDS:
        raise HTTPException(400, f"unknown kind: {kind}. allowed: {sorted(ALLOWED_KINDS)}")

    content = await file.read()
    try:
        result = await svc.upload_image(
            account_id=account_id,
            kind=kind,
            filename=file.filename or "untitled",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"upload failed: {e}")

    return result
