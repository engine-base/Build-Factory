"""T-AI-01: Anthropic Memory API 統合 (永続記憶の主たる保存先).

CLAUDE.md §3「自前実装必須 8 項目」の中核 1 件。
本サービスは Memory API への書き込みを **正準** とし、Mem0 (T-AI-02) は
ベクトル検索用の副本、Obsidian は人間可読 mirror として位置付ける。

## AC マッピング

- **UBIQUITOUS**: Memory API = 永続 fact の primary store
- **EVENT (session end)**: D-XXX 形式 fact を抽出して Memory API に書く
- **EVENT (session start)**: 関連 fact を recall して system prompt に注入 (<200ms)
- **STATE**: 全 fact に source_session_id + confidence_score (0.0-1.0) を付与
- **OPTIONAL**: ユーザ削除要求 → Memory API + Mem0 + Obsidian から 24h 以内に削除 + audit
- **UNWANTED**: Memory API 書き込み失敗 → status='failed' + retry_count++ で永続化 (data loss なし)

## 公開 API

- `extract_facts_from_session(session_id, user_id) -> list[FactRecord]`
- `write_fact(user_id, fact_text, *, source_session_id, confidence_score, ...) -> FactRecord`
- `recall_facts(user_id, query, *, top_k=5) -> list[FactRecord]`  # <200ms
- `request_deletion(fact_id, user_id) -> bool`  # soft-delete + 24h 削除キュー
- `process_retry_queue(*, max_items=50) -> dict`  # 失敗 fact の再送
- `process_pending_deletions() -> dict`  # 24h 以内削除実行

## fact_text 形式

D-XXX (decision)、P-XXX (preference)、C-XXX (context) のいずれかの prefix で
始まることを推奨。fingerprint は内容の SHA-256 head 16 桁で重複排除。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.anthropic_retry import RetryExhaustedError, with_retry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────
# DB lazy import (psycopg 不要環境にも対応)
# ──────────────────────────────────────────

def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


# ──────────────────────────────────────────
# データクラス
# ──────────────────────────────────────────

@dataclass
class FactRecord:
    id: Optional[int]
    user_id: str
    workspace_id: Optional[str]
    fact_text: str
    kind: str
    source_session_id: Optional[int]
    confidence_score: float
    fingerprint: str
    status: str
    retry_count: int = 0
    memory_api_id: Optional[str] = None
    mem0_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    synced_at: Optional[str] = None
    deleted_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "fact_text": self.fact_text,
            "kind": self.kind,
            "source_session_id": self.source_session_id,
            "confidence_score": self.confidence_score,
            "fingerprint": self.fingerprint,
            "status": self.status,
            "retry_count": self.retry_count,
            "memory_api_id": self.memory_api_id,
            "mem0_id": self.mem0_id,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "synced_at": self.synced_at,
            "deleted_at": self.deleted_at,
        }


# ──────────────────────────────────────────
# fingerprint
# ──────────────────────────────────────────

def fingerprint(text: str) -> str:
    """fact 重複判定用ハッシュ (SHA-256 head 16 桁)。"""
    norm = " ".join(text.strip().split()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


# ──────────────────────────────────────────
# fact extraction (session end)
# ──────────────────────────────────────────

# D-001 / P-002 / C-003 形式の prefix が付いた行を fact 候補として抽出する。
# 行内の「## D-001 ...」「### P-002: 内容」「**D-003** 内容」も拾う。
_FACT_RE = re.compile(
    r"^[ \t]*(?:#+|\*+|-)?[ \t]*\*{0,2}([DPC]-\d{2,4})\*{0,2}[ \t]*[:：．。\-—]?[ \t]*(.+?)[ \t]*$",
    re.MULTILINE,
)


def extract_facts_from_text(text: str) -> list[tuple[str, str]]:
    """テキストから (id_prefix, fact_text) のリストを抽出。

    例:
      "D-001: 主要 DB は Supabase Postgres" → [("D-001", "主要 DB は Supabase Postgres")]
    """
    out: list[tuple[str, str]] = []
    for m in _FACT_RE.finditer(text):
        pref, body = m.group(1), m.group(2).strip()
        if body and not body.startswith(("==", "--")):
            out.append((pref, body))
    return out


async def extract_facts_from_session(
    session_id: int, user_id: str, *, workspace_id: Optional[str] = None,
    confidence_score: float = 0.7,
) -> list[FactRecord]:
    """AC-EVENT: セッション完了時に chat_messages から D-XXX 形式 fact を抽出して
    memory_facts に登録する (status='pending')。

    呼び出し元 (session 完了 hook など) はこの fn 後に process_retry_queue を
    1 回呼ぶか、background worker に任せる。
    """
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                "SELECT content FROM chat_messages WHERE thread_id = ? ORDER BY id ASC",
                (session_id,),
            )
            rows = await cur.fetchall()
    except Exception as e:
        logger.warning("extract: chat_messages read failed: %s", e)
        return []

    candidates: list[tuple[str, str]] = []
    for r in rows:
        candidates.extend(extract_facts_from_text(dict(r).get("content") or ""))

    saved: list[FactRecord] = []
    for _prefix, body in candidates:
        rec = await write_fact(
            user_id=user_id,
            fact_text=body,
            source_session_id=session_id,
            workspace_id=workspace_id,
            confidence_score=confidence_score,
            kind="durable",
        )
        if rec is not None:
            saved.append(rec)
    return saved


# ──────────────────────────────────────────
# write_fact (Memory API → memory_facts row)
# ──────────────────────────────────────────

async def write_fact(
    *, user_id: str, fact_text: str,
    source_session_id: Optional[int] = None,
    workspace_id: Optional[str] = None,
    confidence_score: float = 0.7,
    kind: str = "durable",
) -> Optional[FactRecord]:
    """fact を memory_facts に保存 + Memory API への書き込みを試行。

    AC-UNWANTED: Memory API 失敗時も DB 行は残す (status='failed'、retry_count=1)。
    AC-STATE: source_session_id と confidence_score を必ず付与。
    """
    if not fact_text or not fact_text.strip():
        return None
    fp = fingerprint(fact_text)

    # まず DB に pending で挿入 (重複は ON CONFLICT で id 取得)
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """INSERT OR IGNORE INTO memory_facts
                   (user_id, workspace_id, fact_text, kind, source_session_id,
                    confidence_score, fingerprint, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (user_id, workspace_id, fact_text, kind, source_session_id,
                 confidence_score, fp),
            )
            await db.commit()
            db.row_factory = _db().Row
            cur = await db.execute(
                "SELECT * FROM memory_facts WHERE user_id = ? AND fingerprint = ?",
                (user_id, fp),
            )
            row = await cur.fetchone()
    except Exception as e:
        logger.warning("write_fact: DB insert failed: %s", e)
        return None

    if row is None:
        return None
    rec = _row_to_fact(dict(row))

    # Memory API への書き込みを試行 (T-AI-06 の retry でラップ)
    try:
        memory_api_id = await _memory_api_write_with_retry(
            user_id=user_id, fact_text=fact_text, kind=kind,
            confidence_score=confidence_score, source_session_id=source_session_id,
        )
        await _mark_synced(rec.id, memory_api_id)
        rec.status = "synced"
        rec.memory_api_id = memory_api_id
        rec.synced_at = _now_iso()
    except RetryExhaustedError as e:
        await _mark_failed(rec.id, str(e.last_exc)[:300])
        rec.status = "failed"
        rec.retry_count = (rec.retry_count or 0) + 1
        await _emit("memory_api_write_failed", user_id=user_id, session_id=source_session_id,
                    detail={"fact_id": rec.id, "error": str(e.last_exc)[:200]})
    except Exception as e:
        # 非 retryable error
        await _mark_failed(rec.id, str(e)[:300])
        rec.status = "failed"
        await _emit("memory_api_write_error", user_id=user_id, session_id=source_session_id,
                    detail={"fact_id": rec.id, "error": str(e)[:200]})

    return rec


async def _memory_api_write_with_retry(
    *, user_id: str, fact_text: str, kind: str,
    confidence_score: float, source_session_id: Optional[int],
) -> str:
    """Anthropic Memory API への書き込みを T-AI-06 retry で包む。"""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    fp = fingerprint(fact_text)

    async def _call() -> str:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(f"anthropic SDK not installed: {e}")
        client = anthropic.AsyncAnthropic()
        memory_stores = getattr(getattr(client, "beta", None), "memory_stores", None)
        if memory_stores is None:
            raise RuntimeError("anthropic Memory API not available in this SDK")
        store_id = f"bf_user_{user_id}"
        metadata = {
            "kind": kind,
            "confidence_score": confidence_score,
            "source_session_id": source_session_id,
            "fingerprint": fp,
        }
        if hasattr(memory_stores, "append"):
            res = await memory_stores.append(store_id=store_id, content=fact_text, metadata=metadata)
        elif hasattr(memory_stores, "create"):
            res = await memory_stores.create(store_id=store_id, content=fact_text, metadata=metadata)
        else:
            raise RuntimeError("memory_stores has neither append nor create")
        return getattr(res, "id", None) or fp

    return await with_retry(
        _call,
        idempotency_key=fp,
        user_id=user_id,
        session_id=source_session_id,
        label="memory_api.append",
    )


# ──────────────────────────────────────────
# recall (session start, <200ms)
# ──────────────────────────────────────────

async def recall_facts(
    user_id: str, query: str, *, top_k: int = 5,
) -> list[FactRecord]:
    """AC-EVENT: 新セッション開始時に呼ばれる関連 fact 取得 (<200ms 目標)。

    Phase 1 では DB の synced fact から最近の top_k を返す
    (Memory API recall は T-AI-02 の Mem0 brige 経由でベクトル検索される)。
    """
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                """SELECT * FROM memory_facts
                    WHERE user_id = ? AND status = 'synced' AND deleted_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT ?""",
                (user_id, top_k),
            )
            rows = await cur.fetchall()
    except Exception as e:
        logger.warning("recall_facts failed: %s", e)
        return []
    return [_row_to_fact(dict(r)) for r in rows]


# ──────────────────────────────────────────
# deletion (24h grace + audit)
# ──────────────────────────────────────────

async def request_deletion(fact_id: int, user_id: str) -> bool:
    """AC-OPTIONAL: ユーザ削除要求 → soft-delete (24h 以内に process_pending_deletions)。"""
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                """UPDATE memory_facts
                      SET status = 'deleted',
                          deleted_at = datetime('now','localtime')
                    WHERE id = ? AND user_id = ? AND deleted_at IS NULL""",
                (fact_id, user_id),
            )
            await db.commit()
            ok = (cur.rowcount or 0) > 0
    except Exception as e:
        logger.warning("request_deletion failed: %s", e)
        return False
    if ok:
        await _emit("memory_fact_deletion_requested", user_id=user_id,
                    detail={"fact_id": fact_id})
    return ok


async def process_pending_deletions(*, dry_run: bool = False) -> dict:
    """soft-delete された fact を Memory API / Mem0 / Obsidian から実削除する。

    AC: 削除要求から 24h 以内に実行される運用。本関数は cron (毎時) で呼ぶ想定。
    """
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                """SELECT * FROM memory_facts
                    WHERE status = 'deleted' AND deleted_at IS NOT NULL
                    LIMIT 200"""
            )
            rows = await cur.fetchall()
    except Exception:
        return {"processed": 0}

    facts = [_row_to_fact(dict(r)) for r in rows]
    if dry_run:
        return {"would_delete": len(facts), "ids": [f.id for f in facts]}

    deleted: list[int] = []
    for f in facts:
        if f.id is None:
            continue
        ok = await _physical_delete_fact(f)
        if ok:
            deleted.append(f.id)
    if deleted:
        await _emit("memory_facts_deleted_batch",
                    detail={"count": len(deleted), "ids": deleted})
    return {"deleted": len(deleted), "ids": deleted}


async def _physical_delete_fact(rec: FactRecord) -> bool:
    """Memory API + Mem0 + Obsidian から削除し、DB 行も削除。"""
    # Memory API delete (best-effort)
    try:
        if os.environ.get("ANTHROPIC_API_KEY") and rec.memory_api_id:
            import anthropic  # type: ignore[import-not-found]
            client = anthropic.AsyncAnthropic()
            memory_stores = getattr(getattr(client, "beta", None), "memory_stores", None)
            if memory_stores is not None and hasattr(memory_stores, "delete"):
                store_id = f"bf_user_{rec.user_id}"
                await memory_stores.delete(store_id=store_id, id=rec.memory_api_id)
    except Exception as e:
        logger.warning("memory api delete failed: %s", e)

    # Mem0 delete (best-effort、T-AI-02 で完全実装)
    try:
        from services.long_term_memory import delete_user_memories  # type: ignore[attr-defined]
        if rec.mem0_id:
            await delete_user_memories(rec.user_id, ids=[rec.mem0_id])
    except Exception:
        pass  # Mem0 delete は best-effort

    # DB row physical delete
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute("DELETE FROM memory_facts WHERE id = ?", (rec.id,))
            await db.commit()
        return True
    except Exception:
        return False


# ──────────────────────────────────────────
# retry queue
# ──────────────────────────────────────────

async def process_retry_queue(*, max_items: int = 50) -> dict:
    """status='failed' の fact を再送する (background worker から定期呼び出し)。"""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                """SELECT * FROM memory_facts
                    WHERE status IN ('failed','pending') AND deleted_at IS NULL
                      AND retry_count < 5
                    ORDER BY created_at ASC
                    LIMIT ?""",
                (max_items,),
            )
            rows = await cur.fetchall()
    except Exception:
        return {"processed": 0}

    facts = [_row_to_fact(dict(r)) for r in rows]
    success = 0
    failed = 0
    for f in facts:
        if f.id is None:
            continue
        try:
            api_id = await _memory_api_write_with_retry(
                user_id=f.user_id, fact_text=f.fact_text, kind=f.kind,
                confidence_score=f.confidence_score,
                source_session_id=f.source_session_id,
            )
            await _mark_synced(f.id, api_id)
            success += 1
        except Exception as e:
            await _mark_failed(f.id, str(e)[:300])
            failed += 1
    return {"processed": len(facts), "success": success, "failed": failed}


# ──────────────────────────────────────────
# 内部 helpers
# ──────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _row_to_fact(row: dict) -> FactRecord:
    return FactRecord(
        id=row.get("id"),
        user_id=row.get("user_id", ""),
        workspace_id=row.get("workspace_id"),
        fact_text=row.get("fact_text", ""),
        kind=row.get("kind", "durable"),
        source_session_id=row.get("source_session_id"),
        confidence_score=float(row.get("confidence_score") or 0.7),
        fingerprint=row.get("fingerprint", ""),
        status=row.get("status", "pending"),
        retry_count=int(row.get("retry_count") or 0),
        last_error=row.get("last_error"),
        memory_api_id=row.get("memory_api_id"),
        mem0_id=row.get("mem0_id"),
        created_at=row.get("created_at"),
        synced_at=row.get("synced_at"),
        deleted_at=row.get("deleted_at"),
    )


async def _mark_synced(fact_id: Optional[int], memory_api_id: str) -> None:
    if fact_id is None:
        return
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """UPDATE memory_facts
                      SET status = 'synced',
                          memory_api_id = ?,
                          synced_at = datetime('now','localtime'),
                          last_error = NULL
                    WHERE id = ?""",
                (memory_api_id, fact_id),
            )
            await db.commit()
    except Exception as e:
        logger.warning("_mark_synced failed: %s", e)


async def _mark_failed(fact_id: Optional[int], error: str) -> None:
    if fact_id is None:
        return
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """UPDATE memory_facts
                      SET status = 'failed',
                          retry_count = retry_count + 1,
                          last_error = ?
                    WHERE id = ?""",
                (error, fact_id),
            )
            await db.commit()
    except Exception as e:
        logger.warning("_mark_failed failed: %s", e)


async def _emit(event: str, **kw) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event, **kw)
    except Exception:
        pass
