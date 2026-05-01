"""Skill output records (MD files) endpoints."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, FileResponse
from pathlib import Path
import frontmatter

from db.queries import list_records, read_record, RECORDS_PATH

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("")
async def list_all(folder: str = Query(default="")):
    return list_records(folder or None)


@router.get("/folders")
async def list_folders():
    if not RECORDS_PATH.exists():
        return []
    folders = sorted(
        [str(p.relative_to(RECORDS_PATH)) for p in RECORDS_PATH.iterdir() if p.is_dir()]
    )
    return folders


@router.get("/file")
async def get_file(path: str):
    try:
        content = read_record(path)
        try:
            post = frontmatter.loads(content)
            return {
                "path": path,
                "metadata": post.metadata,
                "content": post.content,
                "raw": content,
            }
        except Exception:
            return {"path": path, "metadata": {}, "content": content, "raw": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Not found: {path}")


@router.get("/html-preview")
async def html_preview(path: str):
    """Serve HTML preview files alongside MD files."""
    html_path = RECORDS_PATH / path.replace(".md", "-preview.html")
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="No HTML preview available")
    return FileResponse(html_path, media_type="text/html")
