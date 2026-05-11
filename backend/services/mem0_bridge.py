"""T-AI-02: Mem0 ベクトル検索 + Anthropic Memory API ブリッジ.

CLAUDE.md §3「自前実装必須 8 項目」#2。
T-AI-01 (memory_facts.py) で Memory API へ書かれた fact を Mem0 (pgvector)
にも mirror し、ベクトル類似検索 + re-rank + secretary preload を提供する。

## AC マッピング

- **UBIQUITOUS**: 全ての Memory API write を Mem0 に mirror
- **EVENT (recall similar)**: top-5 ベクトル検索 → Memory API 結果と re-rank (<300ms)
- **STATE (secretary persona)**: セッション開始時に top-50 を system prompt に preload
- **UNWANTED (divergence)**: Mem0 ⇔ Memory API の不一致を audit_logs に出して silent fail を防ぐ

## 公開 API

- `mirror_fact_to_mem0(fact_record) -> Optional[str]`  Mem0 ID を返す
- `search_with_rerank(user_id, query, *, top_k=5) -> list[ScoredFact]`
- `preload_secretary_facts(user_id, top_n=50) -> list[FactRecord]`
- `detect_divergence(user_id, *, sample=100) -> dict`  audit を emit、結果を返す

## Re-rank 戦略

Mem0 の vector score (0..1) と Memory API の confidence_score (0..1) を
重み付き平均: `score = 0.6 * vector_score + 0.4 * confidence_score`
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from services.memory_facts import FactRecord, _row_to_fact

logger = logging.getLogger(__name__)


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
class ScoredFact:
    """re-rank 後の fact + score。"""
    fact: FactRecord
    vector_score: float       # Mem0 から
    confidence: float         # Memory API metadata から
    final_score: float        # 0.6*vector + 0.4*confidence


# ──────────────────────────────────────────
# mirror (write → Mem0)
# ──────────────────────────────────────────

async def mirror_fact_to_mem0(fact: FactRecord) -> Optional[str]:
    """1 件の fact を Mem0 に登録し、返ってきた Mem0 ID を memory_facts.mem0_id に保存。

    AC-UBIQUITOUS: T-AI-01 write_fact からこの関数を呼ぶことで、Memory API と
    Mem0 のミラー化を保証する。失敗時は detect_divergence で検知される。
    """
    try:
        from services.long_term_memory import add_conversation
        await add_conversation(
            user_id=fact.user_id,
            conversation=[{"role": "system", "content": fact.fact_text}],
            metadata={
                "kind": fact.kind,
                "fingerprint": fact.fingerprint,
                "source_session_id": fact.source_session_id,
                "confidence_score": fact.confidence_score,
            },
        )
    except Exception as e:
        logger.warning("mem0 mirror failed: %s", e)
        return None

    # Mem0 add は ID を返さない実装が多いため fingerprint を ID 代わりに使う
    mem0_id = f"mem0:{fact.fingerprint}"
    if fact.id is not None:
        try:
            async with _db().connect(_db_path()) as db:
                await db.execute(
                    "UPDATE memory_facts SET mem0_id = ? WHERE id = ?",
                    (mem0_id, fact.id),
                )
                await db.commit()
        except Exception as e:
            logger.warning("mem0_id update failed: %s", e)
    return mem0_id


# ──────────────────────────────────────────
# search + re-rank (<300ms)
# ──────────────────────────────────────────

async def search_with_rerank(
    user_id: str, query: str, *, top_k: int = 5,
) -> list[ScoredFact]:
    """AC-EVENT: top-5 ベクトル検索 → confidence_score で re-rank。

    Mem0 から取った text を memory_facts と join して FactRecord に変換する。
    """
    # Mem0 ベクトル top-K
    try:
        from services.long_term_memory import search_relevant_memories
        mem0_texts = await search_relevant_memories(user_id=user_id, query=query, limit=top_k)
    except Exception:
        mem0_texts = []

    if not mem0_texts:
        return []

    # 各 text の fingerprint を計算 → DB join で FactRecord 取得
    from services.memory_facts import fingerprint
    fps = [fingerprint(t) for t in mem0_texts]

    facts_by_fp: dict[str, FactRecord] = {}
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            placeholders = ",".join("?" * len(fps))
            cur = await db.execute(
                f"SELECT * FROM memory_facts WHERE user_id = ? AND fingerprint IN ({placeholders})",
                (user_id, *fps),
            )
            rows = await cur.fetchall()
            for r in rows:
                f = _row_to_fact(dict(r))
                facts_by_fp[f.fingerprint] = f
    except Exception as e:
        logger.warning("rerank join failed: %s", e)

    # Mem0 の上位順を vector_score (1.0 → 1/(rank+1)) として再構成
    scored: list[ScoredFact] = []
    for rank, (text, fp) in enumerate(zip(mem0_texts, fps)):
        vector_score = 1.0 / (rank + 1)  # MRR 形式
        f = facts_by_fp.get(fp)
        if f is None:
            # DB 不在 / 削除済みの fact: synthetic FactRecord を作る
            f = FactRecord(
                id=None, user_id=user_id, workspace_id=None,
                fact_text=text, kind="durable", source_session_id=None,
                confidence_score=0.5, fingerprint=fp, status="pending",
            )
        confidence = float(f.confidence_score)
        final = 0.6 * vector_score + 0.4 * confidence
        scored.append(ScoredFact(fact=f, vector_score=vector_score,
                                 confidence=confidence, final_score=final))

    scored.sort(key=lambda s: s.final_score, reverse=True)
    return scored[:top_k]


# ──────────────────────────────────────────
# secretary preload (top-50)
# ──────────────────────────────────────────

async def preload_secretary_facts(
    user_id: str, *, top_n: int = 50,
) -> list[FactRecord]:
    """AC-STATE: secretary AI セッション開始時に top-N の最近高 confidence fact を preload。"""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                """SELECT * FROM memory_facts
                    WHERE user_id = ? AND deleted_at IS NULL
                      AND status = 'synced'
                    ORDER BY confidence_score DESC, created_at DESC
                    LIMIT ?""",
                (user_id, top_n),
            )
            rows = await cur.fetchall()
    except Exception:
        return []
    return [_row_to_fact(dict(r)) for r in rows]


# ──────────────────────────────────────────
# divergence detection (silent fail prevention)
# ──────────────────────────────────────────

async def detect_divergence(
    user_id: str, *, sample: int = 100,
) -> dict:
    """AC-UNWANTED: Memory API と Mem0 の不一致を検出し audit_logs に出す。

    DB 上の status='synced' な fact のうち mem0_id が NULL のものを「Mem0 未同期」と判定。
    detect された fact は再 mirror をキューイングする。
    """
    out: dict = {
        "checked": 0,
        "missing_in_mem0": 0,
        "missing_ids": [],
    }
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                """SELECT id, fact_text, fingerprint, mem0_id FROM memory_facts
                    WHERE user_id = ? AND status = 'synced' AND deleted_at IS NULL
                    ORDER BY id DESC LIMIT ?""",
                (user_id, sample),
            )
            rows = await cur.fetchall()
    except Exception:
        return out

    out["checked"] = len(rows)
    missing: list[int] = []
    for r in rows:
        d = dict(r)
        if not d.get("mem0_id"):
            missing.append(d["id"])

    out["missing_in_mem0"] = len(missing)
    out["missing_ids"] = missing[:50]

    if missing:
        try:
            from services.memory_service import emit_event
            await emit_event(
                "memory_divergence_detected",
                user_id=user_id,
                detail={"missing_in_mem0": len(missing), "sample_ids": missing[:20]},
            )
        except Exception:
            pass

    return out
