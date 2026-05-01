"""
long_term_memory.py — Phase 4: Mem0 ラッパー

会話のたびに人物・好み・出来事を自動抽出して長期記憶に蓄積する。
プロンプト構築時に関連記憶を取得して RAG として注入。

使い方:
  - .env: USE_MEM0=1 で有効化
  - 既存の user_profile.py は残しつつ、Mem0 が補完する関係
  - 失敗してもアプリは止めない（no-op フォールバック）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────
# Mem0 シングルトン
# ──────────────────────────────────────────

_MEM: object = None
_INIT_TRIED: bool = False


def _get_mem():
    """Mem0 を lazy 初期化。失敗時は None。"""
    global _MEM, _INIT_TRIED
    if _MEM is not None:
        return _MEM
    if _INIT_TRIED:
        return None
    _INIT_TRIED = True

    if os.environ.get("USE_MEM0", "0") != "1":
        return None

    try:
        from mem0 import Memory
        # ローカル運用前提: SQLite + ローカル埋め込み or OpenAI 埋め込み
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "engine_base_memory",
                    "host": os.environ.get("QDRANT_HOST", "localhost"),
                    "port": int(os.environ.get("QDRANT_PORT", "6333")),
                },
            } if os.environ.get("USE_QDRANT") == "1" else {
                "provider": "chroma",
                "config": {
                    "collection_name": "engine_base_memory",
                    "path": str(Path(__file__).resolve().parents[2] / "data" / "db" / "mem0_chroma"),
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": os.environ.get("MEM0_LLM_MODEL", "gpt-4o-mini"),
                    "api_key": os.environ.get("OPENAI_API_KEY"),
                },
            } if os.environ.get("OPENAI_API_KEY") else None,
        }
        _MEM = Memory.from_config(config) if config.get("llm") else Memory()
        print("[long_term_memory] Mem0 initialized")
        return _MEM
    except Exception as e:
        print(f"[long_term_memory] Mem0 init 失敗: {e}")
        return None


# ──────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────

async def add_conversation(
    user_id: str,
    messages: list[dict],
    metadata: Optional[dict] = None,
) -> None:
    """会話を Mem0 に蓄積（自動で重要情報を抽出）。"""
    m = _get_mem()
    if not m:
        return
    try:
        # mem0 は同期 API なので run_in_executor で逃がす
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: m.add(messages, user_id=user_id, metadata=metadata or {}),
        )
    except Exception as e:
        print(f"[long_term_memory.add] {e}")


async def search_relevant_memories(
    user_id: str,
    query: str,
    limit: int = 5,
) -> list[str]:
    """関連記憶を検索して string list で返す。"""
    m = _get_mem()
    if not m:
        return []
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: m.search(query=query, user_id=user_id, limit=limit),
        )
        if isinstance(result, dict):
            items = result.get("results") or result.get("memories") or []
        else:
            items = result or []
        out: list[str] = []
        for item in items:
            if isinstance(item, dict):
                text = item.get("memory") or item.get("text") or item.get("content")
                if text:
                    out.append(str(text))
            elif isinstance(item, str):
                out.append(item)
        return out
    except Exception as e:
        print(f"[long_term_memory.search] {e}")
        return []


async def all_memories(user_id: str) -> list[dict]:
    """全記憶を取得（デバッグ用）。"""
    m = _get_mem()
    if not m:
        return []
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: m.get_all(user_id=user_id))
        if isinstance(result, dict):
            return result.get("results") or result.get("memories") or []
        return result or []
    except Exception as e:
        print(f"[long_term_memory.all_memories] {e}")
        return []
