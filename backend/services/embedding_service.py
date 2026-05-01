"""
embedding_service.py — Embedding 生成サービス

優先順位:
  1. Ollama (nomic-embed-text) — ローカル・無料
  2. OpenAI (text-embedding-3-small) — PC停止中・Ollama落ちている時の自動フォールバック
"""

import json
import os
import struct
from pathlib import Path
from typing import Optional

import aiosqlite
import numpy as np

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

OLLAMA_URL   = "http://localhost:11434"
OLLAMA_MODEL = "nomic-embed-text"
OPENAI_MODEL = "text-embedding-3-small"
EMBED_DIM    = 768   # nomic-embed-text の次元数（OpenAIは1536だが正規化後に使う）


# ── 公開API ──────────────────────────────────────────────────────────────

async def embed(text: str) -> Optional[list[float]]:
    """テキストをベクトルに変換する。Ollama → OpenAI の順で試みる。"""
    vec = await _embed_ollama(text)
    if vec:
        return vec
    vec = await _embed_openai(text)
    return vec


def encode(vec: list[float]) -> bytes:
    """float リストを BLOB (bytes) に変換する。"""
    return struct.pack(f"{len(vec)}f", *vec)


def decode(blob: bytes) -> list[float]:
    """BLOB を float リストに戻す。"""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """コサイン類似度を計算する（-1〜1、高いほど類似）。"""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


async def search_knowledge(
    query: str,
    skill_tags: Optional[list[str]] = None,
    top_k: int = 15,
    min_score: float = 0.4,
) -> list[dict]:
    """
    knowledge_base からクエリに類似したナレッジを取得する。

    Args:
        query:      検索クエリ（自然文）
        skill_tags: 対象スキルのタグリスト（Noneなら全体共有のみ）
                    例: ["invoice-create", "finance"]
        top_k:      返す件数の上限
        min_score:  最低類似度スコア（これ未満は除外）

    Returns:
        類似度スコア付きのナレッジリスト（スコア降順）
    """
    query_vec = await embed(query)
    if not query_vec:
        return await _fallback_keyword_search(query, skill_tags, top_k)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # skill_tags フィルタ: skill_tags が NULL（全体共有）または指定スキルを含むもの
        if skill_tags:
            tag_conditions = " OR ".join(["skill_tags LIKE ?"] * len(skill_tags))
            params: list = [f"%{t}%" for t in skill_tags]
            rows = await db.execute_fetchall(
                f"""SELECT id, title, category, tags, summary, content,
                           skill_tags, confidence, embedding
                    FROM knowledge_base
                    WHERE embedding IS NOT NULL
                      AND (skill_tags IS NULL OR {tag_conditions})
                    ORDER BY use_count DESC""",
                params
            )
        else:
            rows = await db.execute_fetchall(
                """SELECT id, title, category, tags, summary, content,
                          skill_tags, confidence, embedding
                   FROM knowledge_base
                   WHERE embedding IS NOT NULL AND skill_tags IS NULL
                   ORDER BY use_count DESC"""
            )

    if not rows:
        return await _fallback_keyword_search(query, skill_tags, top_k)

    scored = []
    for r in rows:
        try:
            row_vec = decode(r["embedding"])
            score = cosine_similarity(query_vec, row_vec)
            # 信頼度でスコアを補正
            adjusted = score * float(r["confidence"] or 1.0)
            if adjusted >= min_score:
                scored.append({
                    "id":         r["id"],
                    "title":      r["title"],
                    "category":   r["category"],
                    "content":    (r["content"] or r["summary"] or "")[:300],
                    "skill_tags": r["skill_tags"],
                    "score":      round(adjusted, 4),
                })
        except Exception:
            continue

    # スコア降順・上位 top_k 件
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


async def embed_and_save(knowledge_id: int) -> bool:
    """
    knowledge_base の指定レコードの embedding を計算して保存する。
    Returns True if successful.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, title, content, summary FROM knowledge_base WHERE id=?",
            (knowledge_id,)
        )
        if not rows:
            return False
        r = rows[0]
        text = f"{r['title']}\n{r['content'] or r['summary'] or ''}"

    vec = await embed(text)
    if not vec:
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE knowledge_base SET embedding=? WHERE id=?",
            (encode(vec), knowledge_id)
        )
        await db.commit()
    return True


# ── プライベート ──────────────────────────────────────────────────────────

async def _embed_ollama(text: str) -> Optional[list[float]]:
    """Ollama の nomic-embed-text でベクトル化する。"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": OLLAMA_MODEL, "prompt": text},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("embedding")
    except Exception:
        return None


async def _embed_openai(text: str) -> Optional[list[float]]:
    """OpenAI の text-embedding-3-small でベクトル化する（フォールバック）。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": OPENAI_MODEL, "input": text[:8000]},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                vec = data["data"][0]["embedding"]
                # 1536次元を768次元に正規化（Ollamaと次元を合わせる）
                if len(vec) != EMBED_DIM:
                    arr = np.array(vec[:EMBED_DIM], dtype=np.float32)
                    norm = np.linalg.norm(arr)
                    vec = (arr / norm).tolist() if norm > 0 else arr.tolist()
                return vec
    except Exception:
        return None


async def _fallback_keyword_search(
    query: str,
    skill_tags: Optional[list[str]],
    top_k: int,
) -> list[dict]:
    """Embedding が使えない時のキーワードフォールバック検索。"""
    keywords = [w for w in query.split() if len(w) >= 2][:5]
    if not keywords:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        like_cond = " OR ".join(["title LIKE ? OR content LIKE ? OR tags LIKE ?"] * len(keywords))
        params: list = []
        for kw in keywords:
            params += [f"%{kw}%", f"%{kw}%", f"%{kw}%"]
        rows = await db.execute_fetchall(
            f"""SELECT id, title, category, content, summary, skill_tags, confidence
                FROM knowledge_base
                WHERE {like_cond}
                ORDER BY use_count DESC, confidence DESC
                LIMIT ?""",
            (*params, top_k)
        )
    return [
        {
            "id":         r["id"],
            "title":      r["title"],
            "category":   r["category"],
            "content":    (r["content"] or r["summary"] or "")[:300],
            "skill_tags": r["skill_tags"],
            "score":      0.5,  # キーワードマッチのデフォルトスコア
        }
        for r in rows
    ]
