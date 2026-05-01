"""
knowledge_curator.py — 秘書AIによるナレッジ自動分類・部分抽出サービス

承認時・ナレッジ化要求時に秘書AIに以下を依頼:
  1. 業務カテゴリ（営業/経理/マーケ/CS/法務/経営/その他）
  2. 知識タイプ（手順/判断/トーン/事例/数値/価値観）
  3. 重要度（high/medium/low）
  4. タイトル短縮（30字）と要約（100字）
  5. タグリスト
  6. 該当スキル

部分ナレッジ化の場合は、まさとの指示文を元に該当部分を抽出する。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH    = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
VAULT_PATH = Path.home() / "Documents" / "Obsidian" / "ENGINE-BASE"

# カテゴリ → Obsidianフォルダパスのマッピング
CATEGORY_TO_FOLDER = {
    "営業":   "03_スキル別ナレッジ/営業",
    "経理":   "03_スキル別ナレッジ/経理",
    "マーケ": "03_スキル別ナレッジ/マーケティング",
    "CS":     "03_スキル別ナレッジ/CS",
    "法務":   "02_共通ナレッジ",
    "経営":   "01_会社・事業",
    "価値観": "00_まさとの思考・価値観",
    "その他": "02_共通ナレッジ",
}


CLASSIFY_PROMPT = """以下のコンテンツをナレッジとして分類してください。

# 元コンテンツ
{content}

{partial_instruction}

# 出力形式（JSONのみ・コードブロック不要）
{{
  "title_short": "30字以内のタイトル",
  "summary": "100字以内の要約",
  "category": "営業|経理|マーケ|CS|法務|経営|価値観|その他",
  "knowledge_type": "手順|判断|トーン|事例|数値|価値観",
  "importance": "high|medium|low",
  "tags": ["#タグ1", "#タグ2"],
  "related_skills": ["skill_name1"],
  "extracted_content": "抽出されたコンテンツ（部分指定なければ元のまま）"{reasoning_field}
}}
"""


async def classify_and_save(
    content: str,
    masato_memo: Optional[str] = None,
    source_skill: Optional[str] = None,
    source: str = "approval",
    source_id: Optional[int] = None,
    full_content: bool = True,
) -> dict:
    """
    コンテンツをナレッジ化する（秘書AIによる自動分類）。

    Args:
        content:      ナレッジにしたいコンテンツ
        masato_memo:  まさとの指示（部分抽出する場合の指示文）
        source_skill: 元のスキル名（タグ付け用）
        source:       'approval' | 'manual' | 'partial' 等
        source_id:    関連するtask_id等
        full_content: True=全体, False=部分抽出
    """
    # 秘書AIに分類を依頼
    classification = await _ask_secretary_to_classify(content, masato_memo, full_content)
    if not classification:
        # フォールバック: 簡易分類
        classification = _fallback_classify(content, masato_memo)

    extracted = classification.get("extracted_content") or content
    if not full_content and not extracted:
        extracted = content

    # knowledge_base に保存
    title    = classification.get("title_short", "ナレッジ")[:200]
    summary  = classification.get("summary", extracted[:200])
    category = classification.get("category", "その他")
    ktype    = classification.get("knowledge_type", "事例")
    importance = classification.get("importance", "medium")
    tags = classification.get("tags", [])
    related = classification.get("related_skills", [])

    # skill_tags は related_skills から作る
    skill_tags = ",".join(related) if related else (source_skill or "")
    tag_str    = ",".join(tags) if tags else ""

    confidence_map = {"high": 1.0, "medium": 0.85, "low": 0.7}
    confidence = confidence_map.get(importance, 0.85)

    # Obsidian Vaultに書き戻し
    md_path = await _write_to_obsidian(
        title=title, content=extracted, category=category,
        ktype=ktype, importance=importance, tags=tags,
        masato_memo=masato_memo, source=source,
    )

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO knowledge_base
               (title, content, summary, category, skill_tags, tags, md_path,
                source, source_execution_id, confidence, confirmed_by_user)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                title, extracted, summary, ktype, skill_tags or None,
                tag_str or None, str(md_path) if md_path else None,
                source, source_id, confidence,
            )
        )
        kb_id = cursor.lastrowid
        await db.commit()

    # Embedding 計算
    try:
        from services.embedding_service import embed_and_save
        await embed_and_save(kb_id)
    except Exception as e:
        print(f"[curator] embed失敗: {e}")

    return {
        "knowledge_id": kb_id,
        "title": title,
        "category": category,
        "knowledge_type": ktype,
        "importance": importance,
        "md_path": str(md_path) if md_path else None,
        "extracted_chars": len(extracted),
    }


async def _ask_secretary_to_classify(
    content: str, masato_memo: Optional[str], full_content: bool
) -> Optional[dict]:
    """秘書AIに分類JSONを返させる。"""
    if masato_memo:
        partial_instruction = (
            f"# まさとの指示\n"
            f"{masato_memo}\n\n"
            f"上記指示に該当する部分を元コンテンツから抽出して "
            f"`extracted_content` に入れてください。"
        )
        reasoning_field = ',\n  "reasoning": "なぜその部分を選んだか（30字以内）"'
    else:
        partial_instruction = ""
        reasoning_field = ""

    prompt = CLASSIFY_PROMPT.format(
        content=content[:3000],
        partial_instruction=partial_instruction,
        reasoning_field=reasoning_field,
    )

    try:
        # 秘書スキルを使うが、再帰的なナレッジ注入を避けるため軽量実行
        import os
        from llm.config import get_openai_client, LLMProvider
        provider_str = os.environ.get("AI_LLM_OVERRIDE_PROVIDER", "ollama")
        model_str    = os.environ.get("AI_LLM_OVERRIDE_MODEL", "qwen2.5:7b")
        try:
            provider_enum = LLMProvider(provider_str)
        except ValueError:
            provider_enum = LLMProvider.OLLAMA
        client = get_openai_client(provider_enum, dict(os.environ))
        response = await client.chat.completions.create(
            model=model_str,
            messages=[
                {"role": "system", "content": "あなたはENGINE BASEの秘書AIです。ナレッジを分類してJSONで返してください。"},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"[curator] 分類失敗: {e}")
    return None


def _fallback_classify(content: str, memo: Optional[str]) -> dict:
    """LLM分類失敗時のフォールバック。"""
    return {
        "title_short": (memo or content)[:60],
        "summary": content[:150],
        "category": "その他",
        "knowledge_type": "事例",
        "importance": "medium",
        "tags": [],
        "related_skills": [],
        "extracted_content": content,
    }


async def _write_to_obsidian(
    title: str, content: str, category: str, ktype: str,
    importance: str, tags: list[str], masato_memo: Optional[str],
    source: str,
) -> Optional[Path]:
    """Obsidian Vault の適切なフォルダにMDファイルを書く。"""
    try:
        folder = CATEGORY_TO_FOLDER.get(category, "02_共通ナレッジ")
        dest_dir = VAULT_PATH / folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        # ファイル名: 重複しない形式
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        # タイトルからファイル名安全化
        safe_title = re.sub(r'[/\\:*?"<>|]', "_", title)[:60]
        filename = f"{ts}-{safe_title}.md"
        path = dest_dir / filename

        # YAMLフロントマター + 本文
        body = f"""---
created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
category: {category}
knowledge_type: {ktype}
importance: {importance}
source: {source}
tags: [{", ".join(tags)}]
---

# {title}
"""
        if masato_memo:
            body += f"\n> 📝 まさとのメモ: {masato_memo}\n"
        body += f"\n## 内容\n\n{content}\n"

        path.write_text(body, encoding="utf-8")
        return path
    except Exception as e:
        print(f"[curator] Obsidian書き戻し失敗: {e}")
        return None
