"""
documents.py — 資料アップロード API

PDFをアップロードしてナレッジ化する。
"""

from pathlib import Path
import tempfile
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services.document_service import ingest_pdf, list_documents

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: str = Form("other"),
    skill_tags: Optional[str] = Form(None),
    related: Optional[str] = Form(None),  # カンマ区切り
):
    """
    PDFをアップロードしてナレッジに登録する。

    Body (multipart):
      file:       PDFファイル
      title:      タイトル（省略時はファイル名）
      category:   invoice / contract / proposal / other
      skill_tags: "invoice-create,finance" 等。空なら全体共有
      related:    関連ナレッジのタイトル（カンマ区切り）
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDFのみアップロード可能です")

    # 一時ファイルに保存
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        related_list = [r.strip() for r in (related or "").split(",") if r.strip()]
        # 元のファイル名で取り込み
        named_path = tmp_path.parent / file.filename
        tmp_path.rename(named_path)

        result = await ingest_pdf(
            file_path=named_path,
            title=title,
            category=category,
            skill_tags=skill_tags or None,
            related_titles=related_list,
        )
        return {"status": "ingested", **result}
    finally:
        # 一時ファイル削除
        try:
            if named_path.exists():
                named_path.unlink()
        except Exception:
            pass


@router.get("")
async def list_docs(category: Optional[str] = None, limit: int = 50):
    """登録済みの資料一覧。"""
    return await list_documents(category=category, limit=limit)
