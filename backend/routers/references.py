"""
references.py — 参考資料 (PDF / DOCX / HTML / MD / TXT) アップロード API

過去の提案書・要件定義書などをアップロードして knowledge artifact 化する。
hearing / requirements / proposal / estimate / pricing / template-builder の AI が
これらを参考として参照できるようになる。
"""
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from services import document_ingest_service as ingest

router = APIRouter(prefix="/api/references", tags=["references"])


ALLOWED_DOC_TYPES = {
    "generic",
    "proposal_reference",
    "requirements_reference",
    "estimate_reference",
    "hearing_reference",
    "pricing_reference",
    "template_reference",
}


@router.post("/upload")
async def upload_reference(
    account_id: int = Form(...),
    file: UploadFile = File(...),
    doc_type: str = Form("generic"),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # カンマ区切り
):
    """
    参考資料をアップロードしてナレッジ化する。

    Body (multipart):
      account_id: アカウント ID
      file:       PDF / DOCX / HTML / MD / TXT
      doc_type:   generic / proposal_reference / requirements_reference / ...
      title:      タイトル（省略時は「参考資料: filename」）
      tags:       追加タグ（カンマ区切り）
    """
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(400, f"invalid doc_type: {doc_type}")

    content = await file.read()
    if not content:
        raise HTTPException(400, "empty file")

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    try:
        result = await ingest.ingest(
            account_id=account_id,
            filename=file.filename or "upload",
            content=content,
            content_type=file.content_type,
            doc_type=doc_type,
            title=title,
            tags=tag_list,
        )
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"ingest failed: {e}")


@router.get("")
async def list_references(
    account_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    limit: int = 100,
):
    """登録済みの参考資料一覧。"""
    items = await ingest.list_references(
        account_id=account_id, doc_type=doc_type, limit=limit
    )
    return {"items": items, "count": len(items)}


@router.get("/{artifact_id}/text")
async def get_reference_text(artifact_id: str):
    """artifact のフルテキストを返す。"""
    text = await ingest.get_reference_text(artifact_id)
    if not text:
        raise HTTPException(404, "reference not found or empty")
    return {"artifact_id": artifact_id, "text": text, "char_count": len(text)}


@router.get("/search/relevant")
async def search_relevant_references(
    keywords: str,
    doc_type: Optional[str] = None,
    limit: int = 5,
):
    """キーワード検索 (カンマ区切り)。"""
    kws = [k.strip() for k in keywords.split(",") if k.strip()]
    items = await ingest.find_relevant_references(
        keywords=kws, doc_type=doc_type, limit=limit
    )
    return {"items": items, "count": len(items)}
