"""
user_profile.py — ユーザー（まさと等）のプロファイル管理。

毎ターン参照されるので軽量。名前・好み・最近の話題を保存。
更新は「ルール抽出」+「バックグラウンドLLM抽出」のハイブリッド。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from db import async_db as aiosqlite

from db.queries import DB_PATH


DEFAULT_KEY = "masato"   # 単一ユーザー前提（将来拡張可）

# ──────────────────────────────────────────────────────
# 取得・保存
# ──────────────────────────────────────────────────────

async def get_profile(user_key: str = DEFAULT_KEY) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM user_profile WHERE user_key = ?", (user_key,),
        )
        row = await cur.fetchone()
    if not row:
        return {"user_key": user_key}
    d = dict(row)
    for k in ("aliases", "preferences", "recent_topics"):
        v = d.get(k)
        if v:
            try: d[k] = json.loads(v)
            except: d[k] = []
        else:
            d[k] = [] if k != "preferences" else {}
    return d


async def update_profile(updates: dict, user_key: str = DEFAULT_KEY) -> None:
    """部分更新。dict/list は JSON 化。"""
    if not updates:
        return
    cols = []
    vals: list[Any] = []
    for k, v in updates.items():
        if k not in ("display_name", "aliases", "preferences", "recent_topics", "notes"):
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        cols.append(f"{k} = ?")
        vals.append(v)
    if not cols:
        return
    cols.append("updated_at = datetime('now','localtime')")
    vals.append(user_key)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE user_profile SET {', '.join(cols)} WHERE user_key = ?",
            vals,
        )
        await db.commit()


# ──────────────────────────────────────────────────────
# 抽出（ルール）
# ──────────────────────────────────────────────────────

NAME_PATTERNS = [
    re.compile(r"(?:僕|私|自分|俺)(?:の名前)?は\s*([\w぀-ゟ゠-ヿ一-鿿]{2,12})\s*です"),
    re.compile(r"^([\w぀-ゟ゠-ヿ一-鿿]{2,12})\s*と申します"),
    re.compile(r"^([\w぀-ゟ゠-ヿ一-鿿]{2,12})\s*って言う"),
]


async def rule_extract_and_update(message: str) -> dict:
    """ルールベースで抽出して即時更新する（同期に近い軽量処理）。"""
    profile = await get_profile()
    updates: dict = {}

    # 名前
    for pat in NAME_PATTERNS:
        m = pat.search(message)
        if m:
            name = m.group(1).strip()
            if name and name != profile.get("display_name"):
                aliases = list(profile.get("aliases") or [])
                if name not in aliases:
                    aliases.append(name)
                updates["display_name"] = name
                updates["aliases"] = aliases
            break

    # 直近話題（簡易）
    topic_keywords = {
        "採用": ["採用", "雇う", "メンバー追加"],
        "退職": ["退職", "やめさせる"],
        "組織": ["組織図", "体制"],
        "ナレッジ": ["ナレッジ", "知識"],
        "営業": ["営業", "商談", "案件"],
        "経理": ["経理", "請求", "支払い"],
        "マーケ": ["マーケ", "SNS", "広告"],
    }
    found_topics: list[str] = []
    for topic, kws in topic_keywords.items():
        if any(k in message for k in kws):
            found_topics.append(topic)
    if found_topics:
        recent = list(profile.get("recent_topics") or [])
        for t in found_topics:
            if t in recent:
                recent.remove(t)
            recent.insert(0, t)
        updates["recent_topics"] = recent[:8]

    if updates:
        await update_profile(updates)
    return updates


# ──────────────────────────────────────────────────────
# バックグラウンドLLM抽出（深掘り・非同期）
# ──────────────────────────────────────────────────────

LLM_EXTRACT_PROMPT = """以下のユーザー発言から、長期記憶として保存すべき情報を抽出してください。
JSON形式のみで返答（説明不要）。情報がなければ空オブジェクト {}。

抽出対象（あれば）:
- name: ユーザーの名前
- aliases: 別名・愛称（リスト）
- preferences: 好み・嗜好（オブジェクト）
- notes: その他覚えておくべき特徴・口癖・背景

例:
{"name":"まさと","aliases":["聖斗"],"preferences":{"tone":"casual"},"notes":"AI開発に詳しい"}

発言: """


async def llm_extract_async(message: str) -> None:
    """バックグラウンドで LLM で抽出して更新（応答速度に影響しない）。"""
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        return
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"user","content": LLM_EXTRACT_PROMPT + message[:500]}],
            max_tokens=200,
            temperature=0,
        )
        text = resp.choices[0].message.content or "{}"
        m = re.search(r'\{[\s\S]*\}', text)
        if not m:
            return
        data = json.loads(m.group())
        if not data:
            return
        profile = await get_profile()
        updates: dict = {}
        if data.get("name") and data["name"] != profile.get("display_name"):
            updates["display_name"] = data["name"]
        if data.get("aliases"):
            existing = list(profile.get("aliases") or [])
            for a in data["aliases"]:
                if a and a not in existing:
                    existing.append(a)
            updates["aliases"] = existing
        if data.get("preferences"):
            existing_pref = profile.get("preferences") or {}
            existing_pref.update(data["preferences"])
            updates["preferences"] = existing_pref
        if data.get("notes"):
            old_notes = profile.get("notes") or ""
            new_note = data["notes"]
            if new_note not in old_notes:
                updates["notes"] = (old_notes + " / " + new_note).strip(" /")[:1000]
        if updates:
            await update_profile(updates)
    except Exception as e:
        print(f"[user_profile] LLM抽出失敗: {e}")


async def update_from_message(message: str) -> None:
    """ユーザーメッセージからプロファイルを更新する。
    ルール抽出は即時、LLM抽出はバックグラウンド。"""
    await rule_extract_and_update(message)
    asyncio.create_task(llm_extract_async(message))


# ──────────────────────────────────────────────────────
# プロンプト用フォーマット
# ──────────────────────────────────────────────────────

def format_for_prompt(profile: dict) -> str:
    """プロンプトに注入するための短い文字列に整形。"""
    if not profile or not profile.get("display_name"):
        return ""
    parts = [f"名前: {profile['display_name']}"]
    aliases = profile.get("aliases") or []
    aliases = [a for a in aliases if a != profile.get("display_name")]
    if aliases:
        parts.append(f"別名: {', '.join(aliases[:3])}")
    if profile.get("recent_topics"):
        parts.append(f"最近の話題: {', '.join(profile['recent_topics'][:5])}")
    if profile.get("notes"):
        parts.append(f"メモ: {profile['notes'][:200]}")
    return "【ユーザープロファイル】\n" + "\n".join(parts)
