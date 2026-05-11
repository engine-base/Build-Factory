"""T-020-02: Memory 3 tier の unified API

CLAUDE.md §3 Memory (3 tier) + ADR-010 AI スタックを統合する。
本サービスは Tier 1/2/3 を透過的に扱う唯一の入口で、呼び出し元は
個別の chat_messages / Mem0 / Memory API / Obsidian を意識しない。

## Tier 構成

- **Tier 1 (Short)**: chat_threads / chat_messages の生ログ (既存)
- **Tier 2 (Mid)** : claude-agent-sdk の auto compaction が 95% で生成する
                     9-section structured summary。chat_messages に格納し、
                     audit_logs に `memory_compacted` event を emit
- **Tier 3 (Long)**: Anthropic Memory API (primary durable storage) +
                     Mem0 (vector copy for similarity search) + Obsidian
                     Markdown mirror (opt-in)

## 公開 API

- `merge_for_session(session_id, prior_session_id, user_message)` -> str
    新セッション開始時の system prompt 末尾を組み立てる
    (SDK resume + Memory API recall + Mem0 top-5 + Constitution)

- `persist_compaction(session_id, summary_dict)` -> int
    SDK の auto compaction 完了時に呼ぶ。chat_messages に追加 +
    audit_logs に memory_compacted event を emit

- `write_fact(user_id, fact_text, *, kind="durable")` -> dict
    Tier 3 durable fact を Memory API primary + Mem0 copy で書き込む。
    Memory API 失敗時は Mem0 only + memory_degraded event を emit

- `mirror_to_obsidian(user_id, fact_text, note_title)` -> Path | None
    OPTIONAL: ~/Documents/会社運営DB/obsidian/ に Markdown 書き出し

- `emit_event(event_type, *, session_id=None, user_id=None, detail=None)` -> int
    audit_logs に event を追加 (任意の event_type)
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional


# DB import は lazy (psycopg 未導入のテスト環境を回避)
def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


# ──────────────────────────────────────────
# audit_logs (event emission)
# ──────────────────────────────────────────

async def emit_event(
    event_type: str,
    *,
    session_id: Optional[int] = None,
    user_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> int:
    """audit_logs に event を追加して id を返す。"""
    detail_json = json.dumps(detail or {}, ensure_ascii=False)
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """INSERT INTO audit_logs (event_type, session_id, user_id, detail_json)
               VALUES (?, ?, ?, ?)""",
            (event_type, session_id, user_id, detail_json),
        )
        await db.commit()
        return cur.lastrowid or 0


# ──────────────────────────────────────────
# Tier 2: 9-section summary persistence
# ──────────────────────────────────────────

async def persist_compaction(session_id: int, summary: dict) -> int:
    """SDK の auto compaction 完了時に呼ぶ。

    - chat_messages に role="system_summary" のレコードを追加
    - audit_logs に memory_compacted event を emit
    """
    content = json.dumps(summary, ensure_ascii=False)
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """INSERT INTO chat_messages (thread_id, role, content)
               VALUES (?, ?, ?)""",
            (session_id, "system_summary", content),
        )
        await db.commit()
        msg_id = cur.lastrowid or 0
    await emit_event(
        "memory_compacted",
        session_id=session_id,
        detail={"summary_message_id": msg_id, "sections": list(summary.keys())},
    )
    return msg_id


# ──────────────────────────────────────────
# Tier 3: Memory API + Mem0 + Obsidian
# ──────────────────────────────────────────

async def write_fact(
    user_id: str,
    fact_text: str,
    *,
    kind: str = "durable",
) -> dict:
    """Tier 3 fact を書き込む。Memory API primary + Mem0 copy。

    Memory API 失敗時は Mem0 only + memory_degraded event。
    """
    memory_api_ok = False
    mem0_ok = False
    errors: dict[str, str] = {}

    # Primary: Anthropic Memory API (T-AI-01 で実装、Phase 1 は stub)
    try:
        memory_api_ok = await _memory_api_write(user_id, fact_text, kind=kind)
    except Exception as e:
        errors["memory_api"] = str(e)[:300]

    # Copy: Mem0 vector store (REUSE: long_term_memory.add_conversation)
    try:
        from services.long_term_memory import add_conversation
        await add_conversation(user_id=user_id, conversation=[{"role": "system", "content": fact_text}])
        mem0_ok = True
    except Exception as e:
        errors["mem0"] = str(e)[:300]

    if not memory_api_ok:
        await emit_event(
            "memory_degraded",
            user_id=user_id,
            detail={"errors": errors, "fallback": "mem0_only" if mem0_ok else "none"},
        )

    return {
        "memory_api_ok": memory_api_ok,
        "mem0_ok": mem0_ok,
        "errors": errors or None,
    }


async def _memory_api_write(user_id: str, fact_text: str, *, kind: str) -> bool:
    """Anthropic Memory API (beta.memory_stores) への書き込み。

    user_id を memory_store_id 相当として運用する。SDK が未導入 / API キーが
    無い / Memory API が beta で利用不可な場合は False を返し、呼び出し元が
    Mem0 only fallback + memory_degraded event を emit する。
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        return False

    try:
        client = anthropic.AsyncAnthropic()
        memory_stores = getattr(getattr(client, "beta", None), "memory_stores", None)
        if memory_stores is None:
            return False
        # Memory API は beta 仕様で create / append のシグネチャが流動的。
        # 共通の "content" payload で試行し、API 変更時は例外で fallback。
        store_id = f"bf_user_{user_id}"
        if hasattr(memory_stores, "append"):
            await memory_stores.append(store_id=store_id, content=fact_text, metadata={"kind": kind})
        elif hasattr(memory_stores, "create"):
            await memory_stores.create(store_id=store_id, content=fact_text, metadata={"kind": kind})
        else:
            return False
        return True
    except Exception:
        return False


def mirror_to_obsidian(user_id: str, fact_text: str, note_title: str) -> Optional[Path]:
    """OPTIONAL: ~/Documents/会社運営DB/obsidian/ に Markdown を書き出す。

    opt-in 制御は呼び出し側で行う (例: env OBSIDIAN_SYNC=1)。
    """
    if os.environ.get("OBSIDIAN_SYNC", "0") != "1":
        return None
    base = Path(os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "Documents" / "会社運営DB" / "obsidian")))
    safe = "".join(c for c in note_title if c.isalnum() or c in "-_ ")[:120].strip() or "note"
    target = base / user_id / f"{safe}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {note_title}\n\n{fact_text}\n"
    target.write_text(content, encoding="utf-8")
    return target


# ──────────────────────────────────────────
# Recall / merge: 新セッション開始時の system prompt 末尾を組み立てる
# ──────────────────────────────────────────

async def merge_for_session(
    session_id: int,
    prior_session_id: Optional[int],
    user_message: str,
    *,
    user_id: Optional[str] = None,
    top_k: int = 5,
) -> str:
    """新セッション開始時に system prompt へ注入する memory block を組み立てる。

    優先順位:
      1. SDK session resume (prior_session_id があれば claude-agent-sdk が自動)
      2. Memory API recall (Phase 1 stub)
      3. Mem0 top-K similarity (REUSE long_term_memory.search_relevant_memories)
      4. Constitution (Phase 1: env or default)
    """
    parts: list[str] = []

    # 1. SDK session resume はランナー側で session_id を渡せば自動なので、ここでは
    #    prior_session_id をマーカーとして残すだけ (T-S0-08 ClaudeAgentRunner と接続)
    if prior_session_id:
        parts.append(f"【前セッション継続】session_id={prior_session_id}")

    # 2. Memory API recall (Phase 1 stub)
    api_facts = await _memory_api_recall(user_id, user_message)
    if api_facts:
        parts.append("【Memory API】\n" + "\n".join(f"- {f}" for f in api_facts))

    # 3. Mem0 top-K (REUSE)
    try:
        from services.long_term_memory import search_relevant_memories
        mem0 = await search_relevant_memories(
            user_id=user_id or "masato",
            query=user_message,
            limit=top_k,
        )
        if mem0:
            parts.append("【長期記憶 (Mem0)】\n" + "\n".join(f"- {m}" for m in mem0))
    except Exception:
        pass

    # 4. Constitution (Phase 1: env CONSTITUTION_TEXT or default empty)
    const = os.environ.get("CONSTITUTION_TEXT", "")
    if const:
        parts.append("【Constitution】\n" + const)

    return "\n\n".join(parts)


async def _memory_api_recall(user_id: Optional[str], query: str) -> list[str]:
    """Anthropic Memory API recall。

    Memory API が利用可能なら top-K fact を返す。失敗時は空 list を返し、
    呼び出し元は Mem0 vector に依存する。
    """
    if not os.environ.get("ANTHROPIC_API_KEY") or not user_id:
        return []
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        return []

    try:
        client = anthropic.AsyncAnthropic()
        memory_stores = getattr(getattr(client, "beta", None), "memory_stores", None)
        if memory_stores is None:
            return []
        store_id = f"bf_user_{user_id}"
        # API の query / search メソッドが流動的なので両方試す
        result = None
        if hasattr(memory_stores, "query"):
            result = await memory_stores.query(store_id=store_id, query=query, limit=5)
        elif hasattr(memory_stores, "search"):
            result = await memory_stores.search(store_id=store_id, query=query, limit=5)
        else:
            return []
        items = getattr(result, "items", None) or getattr(result, "data", None) or []
        facts: list[str] = []
        for it in items:
            text = getattr(it, "content", None) or getattr(it, "text", None) or ""
            if isinstance(text, str) and text:
                facts.append(text)
        return facts
    except Exception:
        return []


# ──────────────────────────────────────────
# 補助: 体系的なファクト ID (重複判定用)
# ──────────────────────────────────────────

def fact_fingerprint(text: str) -> str:
    """fact の fingerprint (重複判定用ハッシュ)。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
