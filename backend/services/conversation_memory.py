"""
conversation_memory.py — 会話履歴のベクトル検索 / 圧縮 / トークン管理

- メッセージ保存時に自動 Embedding 化
- 「現在の発言に関連する過去のやり取り」を検索
- 直近 N 件 + 関連 K 件 をハイブリッドで context に入れる
- トークンバジェット監視
"""

from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite
import numpy as np

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"


async def embed_message(message_id: int) -> bool:
    """指定 conversation_log レコードを embedding 化する。"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT id, message FROM conversation_log WHERE id=?",
                (message_id,)
            )
            if not rows:
                return False
            text = rows[0]["message"]

        from services.embedding_service import embed, encode
        vec = await embed(text)
        if not vec:
            return False

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE conversation_log SET embedding=? WHERE id=?",
                (encode(vec), message_id)
            )
            await db.commit()
        return True
    except Exception as e:
        print(f"[conv_memory] embed失敗: {e}")
        return False


async def search_related_history(
    query: str,
    thread_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    top_k: int = 5,
    min_score: float = 0.5,
    exclude_recent: int = 10,
) -> list[dict]:
    """
    過去の会話メッセージから現在のクエリと類似するものを取得する。

    Args:
        query:          現在のユーザー発言
        thread_id:      指定すれば同じスレッド内のみ検索
        employee_id:    指定すれば同じ社員との会話のみ
        top_k:          返す件数
        min_score:      最低類似度
        exclude_recent: 直近 N件は除外（context に既に入っているため）
    """
    from services.embedding_service import embed, decode, cosine_similarity

    query_vec = await embed(query)
    if not query_vec:
        return []

    conds = ["embedding IS NOT NULL"]
    params: list = []
    if thread_id:
        conds.append("thread_id=?"); params.append(thread_id)
    elif employee_id:
        conds.append("with_employee=?"); params.append(employee_id)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 直近 exclude_recent 件は除外（thread_id 指定時のみ：同スレの直近）
        recent_ids: set[int] = set()
        if thread_id and exclude_recent > 0:
            recent_rows = await db.execute_fetchall(
                "SELECT id FROM conversation_log WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (thread_id, exclude_recent)
            )
            recent_ids = {r["id"] for r in recent_rows}

        # 候補取得
        rows = await db.execute_fetchall(
            f"""SELECT id, role, message, embedding, created_at, thread_id
                FROM conversation_log WHERE {" AND ".join(conds)}
                ORDER BY created_at DESC LIMIT 1000""",
            params
        )

    scored = []
    for r in rows:
        if r["id"] in recent_ids:
            continue
        try:
            score = cosine_similarity(query_vec, decode(r["embedding"]))
            if score >= min_score:
                scored.append({
                    "id":         r["id"],
                    "role":       r["role"],
                    "message":    r["message"],
                    "thread_id":  r["thread_id"],
                    "created_at": r["created_at"],
                    "score":      round(score, 3),
                })
        except Exception:
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """テキストのトークン数を概算する。"""
    try:
        import tiktoken
        encoding = tiktoken.encoding_for_model(model) if "gpt" in model else tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # フォールバック: 文字数 × 0.5（日本語ざっくり）
        return int(len(text) * 0.5)


# モデルごとの context window
CONTEXT_WINDOWS = {
    "qwen2.5:7b":           8192,
    "gemma3:4b":            8192,
    "gemma3:12b":         128000,
    "gemma4:latest":      128000,
    "claude-sonnet-4-6": 200000,
    "claude-opus-4-5":   200000,
    "claude-haiku-4-5":  200000,
    "gpt-4o":            128000,
    "gpt-4o-mini":       128000,
}


def get_context_budget(model: str, ratio: float = 0.6) -> int:
    """指定モデルで使える「実用的な」トークン数を返す（出力分を残して60%）。"""
    window = CONTEXT_WINDOWS.get(model, 8192)
    return int(window * ratio)


async def build_context_for_agent(
    user_message: str,
    thread_id: int,
    model: str,
    recent_n: int = 10,
    related_k: int = 5,
) -> dict:
    """
    Agent に渡す context を組み立てる。

    クロススレッド漏出抑制方針:
      1. 既定では同スレッドのみから related を取得（other thread を引きずらない）
      2. ユーザー発言に「先日」「以前」「あの件」など過去参照語が含まれる時のみ全スレ検索
      3. score 閾値を 0.55 → 0.65 に引き上げ（弱い類似は無視）

    Returns:
        {
          "recent_history": [...],  // 直近N件（同スレッド）
          "related_history": [...], // 既定は同スレ・過去参照時のみ全スレ
          ...
        }
    """
    # 直近履歴（同スレッドのみ・常に）
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT role, message, created_at FROM conversation_log
               WHERE thread_id=? AND role IN ('user','assistant')
               ORDER BY created_at DESC LIMIT ?""",
            (thread_id, recent_n)
        )
    recent = list(reversed([dict(r) for r in rows]))

    # 過去参照キーワードを判定（明示的な時だけ全スレ検索）
    past_ref_markers = [
        "先日", "以前", "前回", "あの件", "あの時", "この前", "昨日",
        "前話した", "前にも", "前にも言った", "過去の", "前に言って", "話した",
    ]
    looks_like_past_ref = any(m in user_message for m in past_ref_markers)

    related: list[dict] = []
    if looks_like_past_ref:
        # 全スレ検索（明示的に過去を参照している時のみ）
        related = await search_related_history(
            query=user_message,
            thread_id=None,
            top_k=related_k,
            min_score=0.65,
            exclude_recent=recent_n,
        )
    else:
        # 同スレッド内の関連だけ拾う（クロススレッド漏出を防ぐ）
        related = await search_related_history(
            query=user_message,
            thread_id=thread_id,
            top_k=max(2, related_k // 2),
            min_score=0.6,
            exclude_recent=recent_n,
        )

    budget = get_context_budget(model)
    # 簡易トークン推定
    text_total = "\n".join([h["message"] for h in recent + related])
    estimated = estimate_tokens(text_total, model)

    return {
        "recent_history":    recent,
        "related_history":   related,
        "estimated_tokens":  estimated,
        "budget":            budget,
        "should_compress":   estimated > budget,
    }
