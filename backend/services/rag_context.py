"""
rag_context.py — Agent 実行前に毎ターン自動 RAG 注入する。

階層プロンプトの Layer 4（Context）を構築：
  - ユーザープロファイル（名前等）
  - 直近10ターン履歴
  - 全スレッド横断の類似過去会話（top-K, 高閾値）
  - スコープ付きナレッジ（業務モード時のみ）

モデルが search_* ツールを呼ばなくても、コンテキスト先頭に必要情報が入る。
"""

from __future__ import annotations

from typing import Optional

from db import async_db as aiosqlite

from db.queries import DB_PATH


# ──────────────────────────────────────────────────────
# 直近履歴
# ──────────────────────────────────────────────────────

async def get_recent_messages(thread_id: int, n: int = 10) -> list[dict]:
    if not thread_id:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT role, message FROM conversation_log "
            "WHERE thread_id = ? AND role IN ('user','assistant') "
            "ORDER BY created_at DESC LIMIT ?",
            (thread_id, n),
        )
        rows = await cur.fetchall()
    return [{"role": r["role"], "content": r["message"]}
            for r in reversed(list(rows))]


# ──────────────────────────────────────────────────────
# 全スレッド横断の類似メッセージ
# ──────────────────────────────────────────────────────

async def search_similar_messages(
    query: str,
    exclude_thread_id: Optional[int] = None,
    top_k: int = 3,
    min_score: float = 0.7,
) -> list[dict]:
    """全スレッド横断で類似メッセージをベクトル検索。"""
    try:
        from services.conversation_memory import search_related_history
        results = await search_related_history(
            query=query,
            thread_id=exclude_thread_id,
            top_k=top_k,
            min_score=min_score,
            exclude_recent=0,
        )
        # 形式統一
        return [
            {"role": r.get("role", "user"),
             "content": (r.get("message") or "")[:200],
             "thread_id": r.get("thread_id"),
             "created_at": r.get("created_at"),
             "score": r.get("score")}
            for r in (results or [])
        ]
    except Exception as e:
        print(f"[rag_context] similar search 失敗: {e}")
        return []


# ──────────────────────────────────────────────────────
# スコープ付きナレッジ
# ──────────────────────────────────────────────────────

async def search_relevant_knowledge(
    employee_id: int,
    query: str,
    top_k: int = 2,
    min_score: float = 0.7,
) -> list[dict]:
    try:
        from services.scoped_knowledge import search_in_scope
        items = await search_in_scope(
            employee_id=employee_id, query=query,
            top_k=top_k, min_score=min_score,
        )
        return items or []
    except Exception as e:
        print(f"[rag_context] knowledge search 失敗: {e}")
        return []


# ──────────────────────────────────────────────────────
# 統合: 自動 RAG コンテキスト
# ──────────────────────────────────────────────────────

async def build_context(
    message: str,
    thread_id: Optional[int],
    employee_id: int,
    mode: str = "chat",   # "chat" | "task"
) -> dict:
    """毎ターン呼び出される RAG コンテキスト構築。"""
    from services.user_profile import get_profile

    # 1. プロファイル（毎ターン）
    profile = await get_profile()

    # 2. 直近履歴（毎ターン）
    recent = await get_recent_messages(thread_id or 0, n=10) if thread_id else []

    # 3. 類似メッセージ（雑談でも有効・名前/話題引当）
    similar = await search_similar_messages(
        query=message, exclude_thread_id=thread_id, top_k=3, min_score=0.7,
    )

    # 4. ナレッジ（業務モード時のみ・閾値高め）
    kb: list[dict] = []
    if mode == "task" and message:
        kb = await search_relevant_knowledge(
            employee_id=employee_id, query=message, top_k=3, min_score=0.65,
        )

    return {
        "profile": profile,
        "recent": recent,
        "similar": similar,
        "kb": kb,
    }


# ──────────────────────────────────────────────────────
# プロンプト用フォーマット
# ──────────────────────────────────────────────────────

def format_for_prompt(ctx: dict, mode: str = "chat") -> str:
    """RAG コンテキストをプロンプト末尾に注入する文字列にする。"""
    from services.user_profile import format_for_prompt as fmt_profile

    parts: list[str] = []

    profile_text = fmt_profile(ctx.get("profile") or {})
    if profile_text:
        parts.append(profile_text)

    similar = ctx.get("similar") or []
    if similar:
        sim_lines = ["【関連する過去の会話】"]
        for s in similar[:3]:
            sim_lines.append(f"- [{s.get('role','?')}] {s.get('content','')[:120]}")
        parts.append("\n".join(sim_lines))

    if mode == "task":
        kb = ctx.get("kb") or []
        if kb:
            kb_lines = ["【関連ナレッジ】"]
            for k in kb[:3]:
                kb_lines.append(f"- {k.get('title','?')}: {k.get('content','')[:120]}")
            parts.append("\n".join(kb_lines))

    return "\n\n".join(parts) if parts else ""
