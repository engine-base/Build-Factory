"""
obsidian_sync.py — Obsidian Vault → knowledge_base 同期サービス

Obsidian の Markdown ファイルを読み込み、knowledge_base に保存・Embedding 化する。
APScheduler から5分ごとに差分チェックを行う。
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path

import aiosqlite

DB_PATH      = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
VAULT_PATH   = Path.home() / "Documents" / "Obsidian" / "ENGINE-BASE"

# フォルダ名 → skill_tags マッピング
# NULLなら全スキル共有、値があればそのスキルのみ
FOLDER_TO_SKILL_TAGS: dict[str, str | None] = {
    "00_まさとの思考・価値観": None,        # 全スキル共有
    "01_会社・事業":           None,        # 全スキル共有
    "02_共通ナレッジ":         None,        # 全スキル共有
    "03_スキル別ナレッジ/営業":  "sales,01_sales,sales-email,pipeline-management",
    "03_スキル別ナレッジ/経理":  "finance,invoice-create,cashflow-forecast,expense-management",
    "03_スキル別ナレッジ/マーケティング": "marketing,sns-management,email-marketing,content-strategy",
    "03_スキル別ナレッジ/CS":   "cs,support-response,customer-followup",
    "04_AI社員フィードバック":  None,        # 全スキル共有
}


async def run_obsidian_sync() -> dict:
    """
    Vault の全 .md ファイルを走査し、新規・更新ファイルを knowledge_base に同期する。
    APScheduler から5分ごとに呼ばれる。
    """
    if not VAULT_PATH.exists():
        return {"synced": 0, "skipped": 0, "error": "Vault not found"}

    md_files = list(VAULT_PATH.rglob("*.md"))
    synced = skipped = 0

    for md_file in md_files:
        if md_file.name.startswith("."):
            continue
        result = await _sync_file(md_file)
        if result:
            synced += 1
        else:
            skipped += 1

    if synced > 0:
        print(f"[obsidian_sync] 同期完了: {synced}件 / スキップ: {skipped}件")

    return {"synced": synced, "skipped": skipped}


async def _sync_file(md_file: Path) -> bool:
    """
    1ファイルを knowledge_base に同期する。
    内容が変わっていなければスキップ。変わっていれば更新 + Embedding 再計算。
    """
    content = md_file.read_text(encoding="utf-8").strip()
    if not content:
        return False

    # ファイルの内容ハッシュ（変更検知用）
    content_hash = hashlib.md5(content.encode()).hexdigest()

    # タイトルはファイル名（拡張子なし）
    title = md_file.stem

    # フォルダからカテゴリと skill_tags を決定
    skill_tags = _resolve_skill_tags(md_file)
    category   = _resolve_category(md_file)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 既存レコードを確認（md_path で特定）
        existing = await db.execute_fetchall(
            "SELECT id, tags FROM knowledge_base WHERE md_path=?",
            (str(md_file),)
        )

        if existing:
            # ハッシュが一致する（内容が同じ）場合はスキップ
            ex = dict(existing[0])
            if ex.get("tags") == content_hash:
                return False

            # 更新
            await db.execute(
                """UPDATE knowledge_base
                   SET title=?, content=?, summary=?, category=?,
                       skill_tags=?, tags=?, source='obsidian',
                       last_updated=date('now','localtime'), embedding=NULL
                   WHERE id=?""",
                (title, content, content[:500], category,
                 skill_tags, content_hash, ex["id"])
            )
            kb_id = ex["id"]
        else:
            # 新規登録
            cursor = await db.execute(
                """INSERT INTO knowledge_base
                   (title, content, summary, category, skill_tags,
                    tags, md_path, source, confirmed_by_user)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'obsidian', 1)""",
                (title, content, content[:500], category,
                 skill_tags, content_hash, str(md_file))
            )
            kb_id = cursor.lastrowid

        await db.commit()

    # Embedding を非同期で計算・保存
    try:
        from services.embedding_service import embed_and_save
        await embed_and_save(kb_id)
    except Exception as e:
        print(f"[obsidian_sync] Embedding失敗 {md_file.name}: {e}")

    return True


def _resolve_skill_tags(md_file: Path) -> str | None:
    """ファイルパスからフォルダを判定して skill_tags を返す。"""
    rel = str(md_file.relative_to(VAULT_PATH))
    for folder_pattern, tags in FOLDER_TO_SKILL_TAGS.items():
        if rel.startswith(folder_pattern):
            return tags
    return None  # デフォルトは全体共有


def _resolve_category(md_file: Path) -> str:
    """ファイルパスからカテゴリを判定する。"""
    rel = str(md_file.relative_to(VAULT_PATH))
    if "まさと" in rel or "思考" in rel or "価値観" in rel:
        return "value"
    if "判断" in rel or "基準" in rel:
        return "judgment"
    if "トーン" in rel or "コミュニケーション" in rel:
        return "tone"
    if "フィードバック" in rel:
        return "correction"
    if "スキル別" in rel:
        return "pattern"
    return "knowledge"
