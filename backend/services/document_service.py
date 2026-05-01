"""
document_service.py — PDF・添付ファイルのナレッジ化サービス

PDFからテキスト抽出 → knowledge_base に登録 → Embedding 化
Obsidian Vault の 05_資料・添付/ 以下に保存して md_path で紐付け

使い方:
  - API: POST /api/documents/upload (multipart)
  - 関数: await ingest_pdf(file_path, category, skill_tags)
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite

import os
DB_PATH    = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
_default_vault = Path(__file__).resolve().parents[2] / "data" / "obsidian"
VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH") or _default_vault)
ATTACH_DIR = VAULT_PATH / "05_資料・添付"

# カテゴリ → サブフォルダマッピング
CATEGORY_FOLDERS = {
    "invoice":   "請求書",
    "contract":  "契約書",
    "proposal":  "提案書",
    "other":     "その他",
}


async def ingest_pdf(
    file_path: Path,
    title: Optional[str] = None,
    category: str = "other",
    skill_tags: Optional[str] = None,
    related_titles: Optional[list[str]] = None,
) -> dict:
    """
    PDFを取り込んでナレッジ化する。

    Args:
        file_path:    元のPDFパス
        title:        ナレッジタイトル（省略時はファイル名）
        category:     "invoice" | "contract" | "proposal" | "other"
        skill_tags:   "invoice-create,finance" 等。NULLなら全体共有
        related_titles: 関連ナレッジのタイトル（[[リンク]]として埋め込む）

    Returns:
        { "knowledge_id": int, "stored_path": str, "text_length": int }
    """
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    # 1. PDFテキスト抽出
    text = _extract_pdf_text(file_path)
    if not text.strip():
        raise ValueError("PDFからテキストを抽出できませんでした")

    # 2. Vault配下にコピー
    subfolder = CATEGORY_FOLDERS.get(category, "その他")
    dest_dir = ATTACH_DIR / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_pdf = dest_dir / file_path.name
    if file_path.resolve() != dest_pdf.resolve():
        shutil.copy2(file_path, dest_pdf)

    # 3. 同じフォルダに .md インデックスを作成（Obsidianで読み書き可能）
    title = title or file_path.stem
    md_file = dest_dir / f"{title}.md"
    md_content = _build_markdown_index(
        title, dest_pdf, text, category, related_titles or []
    )
    md_file.write_text(md_content, encoding="utf-8")

    # 4. knowledge_base に登録
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO knowledge_base
               (title, content, summary, category, skill_tags,
                md_path, source, confirmed_by_user)
               VALUES (?, ?, ?, ?, ?, ?, 'document', 1) RETURNING id""",
            (
                title,
                text[:8000],
                text[:300],
                category,
                skill_tags,
                str(md_file),
            )
        )
        _row = await cursor.fetchone()
        kb_id = _row["id"]
        await db.commit()

    # 5. Embedding を計算
    try:
        from services.embedding_service import embed_and_save
        await embed_and_save(kb_id)
    except Exception as e:
        print(f"[document] Embedding失敗: {e}")

    return {
        "knowledge_id": kb_id,
        "stored_path":  str(dest_pdf),
        "md_path":      str(md_file),
        "text_length":  len(text),
    }


def _extract_pdf_text(pdf_path: Path) -> str:
    """PDFからテキストを抽出する。"""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"[document] pdfplumber失敗: {e}")
        return ""


def _build_markdown_index(
    title: str,
    pdf_path: Path,
    text: str,
    category: str,
    related: list[str],
) -> str:
    """ObsidianのMarkdownインデックスを生成する。"""
    rel_pdf = pdf_path.name
    lines = [
        f"# {title}",
        "",
        f"取り込み日: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"カテゴリ: {category}",
        f"PDFファイル: ![[{rel_pdf}]]",
        "",
    ]

    if related:
        lines.append("## 関連ナレッジ")
        for r in related:
            lines.append(f"- [[{r}]]")
        lines.append("")

    lines.append("## 抽出テキスト")
    lines.append("")
    lines.append(text[:3000])
    if len(text) > 3000:
        lines.append("\n\n...（省略）...")

    return "\n".join(lines)


async def list_documents(category: Optional[str] = None, limit: int = 50) -> list[dict]:
    """登録されている資料の一覧を返す。"""
    cond = "source='document'"
    params: list = []
    if category:
        cond += " AND category=?"
        params.append(category)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""SELECT id, title, category, skill_tags, md_path,
                       summary, use_count, created_at
                FROM knowledge_base
                WHERE {cond}
                ORDER BY created_at DESC LIMIT ?""",
            (*params, limit)
        )
    return [dict(r) for r in rows]
