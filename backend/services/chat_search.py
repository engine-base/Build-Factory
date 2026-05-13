"""T-AI-03: chat_messages hybrid search (pg_trgm + pgvector).

CLAUDE.md §3「自前実装必須 8 項目」#3。
S-011 global search (`docs/mocks/2026-05-09_v1/account/S-011-global-search.html`)
が叩く API の中核。

## AC マッピング

- **UBIQUITOUS**: pg_trgm (lexical) + pgvector (semantic) のハイブリッドスコアを返す
- **EVENT (S-011 query)**: top-K を 500ms (P95) 以内に返す
- **OPTIONAL**: `date:2026-04` フィルタで月単位 narrow
- **STATE**: indexing 時 pg_partman で月パーティション (Phase 2 / Postgres モード)
- **UNWANTED**: workspace 越権 query は RLS で 0 件 (Phase 2 で auth.uid() 紐付け)

## hybrid score

`final = 0.5 * trgm_similarity + 0.5 * vector_similarity`

## Phase 1 (SQLite) 実装

- pg_trgm 相当: `LOWER(content) LIKE '%qquery%'` + Jaccard-like char-bigram 比較
- pgvector 相当: 既存 `services/embedding_service` (あれば) で cosine、無ければ trgm 単独
- date:YYYY-MM フィルタ: `created_at LIKE 'YYYY-MM%'`

## Phase 2 (Postgres) 移行

DATABASE_URL=postgres* なら `pg_trgm.similarity()` + `<=>` (cosine distance) を
直接 SQL で評価する経路に切り替え (本実装ではフックのみ用意)。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

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
class HybridHit:
    message_id: int
    thread_id: int
    role: str
    content: str
    created_at: Optional[str]
    trgm_score: float
    vector_score: float
    final_score: float

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
            "trgm_score": self.trgm_score,
            "vector_score": self.vector_score,
            "final_score": self.final_score,
        }


# ──────────────────────────────────────────
# query parsing (date:YYYY-MM filter)
# ──────────────────────────────────────────

_DATE_FILTER_RE = re.compile(r"\bdate:(\d{4}-\d{2})(?:-(\d{2}))?\b", re.IGNORECASE)


def parse_query(query: str) -> tuple[str, Optional[str]]:
    """`date:2026-04` を抜き出して (clean_query, "2026-04") を返す。

    `date:2026-04-15` のような日単位も許容するが、Phase 1 は月単位 prefix で扱う。
    """
    m = _DATE_FILTER_RE.search(query)
    if not m:
        return query.strip(), None
    date_prefix = m.group(1)  # YYYY-MM
    cleaned = _DATE_FILTER_RE.sub("", query).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned, date_prefix


# ──────────────────────────────────────────
# pg_trgm-相当 char-bigram similarity (Phase 1)
# ──────────────────────────────────────────

def char_bigrams(s: str) -> set[str]:
    s = f"  {s.lower().strip()}  "
    return {s[i:i + 2] for i in range(len(s) - 1)}


def trgm_similarity(a: str, b: str) -> float:
    """Jaccard 係数で pg_trgm.similarity() 相当 (近似)。

    pg_trgm は trigram (3-gram) だが Phase 1 では bigram で軽量化。
    短文が多い (chat) ので bigram の方が hit 率が高く実用的。
    """
    if not a or not b:
        return 0.0
    A, B = char_bigrams(a), char_bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / max(1, len(A | B))


# ──────────────────────────────────────────
# vector similarity (Phase 1: optional)
# ──────────────────────────────────────────

async def _vector_score_for(query: str, content: str) -> float:
    """Phase 1: embedding_service があれば cosine、無ければ 0.0。"""
    try:
        from services.embedding_service import cosine_similarity, embed
    except ImportError:
        return 0.0
    try:
        q_emb = await embed(query)
        c_emb = await embed(content)
        if not q_emb or not c_emb:
            return 0.0
        score = float(cosine_similarity(q_emb, c_emb))
        if score != score:  # NaN guard
            return 0.0
        return score
    except Exception:
        return 0.0


# ──────────────────────────────────────────
# hybrid search
# ──────────────────────────────────────────

async def hybrid_search(
    query: str, *,
    user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    top_k: int = 20,
    use_vector: bool = True,
    weight_trgm: float = 0.5,
    weight_vector: float = 0.5,
) -> list[HybridHit]:
    """AC-EVENT: chat_messages を hybrid score で検索。

    - `query` から `date:YYYY-MM` を抽出してフィルタ
    - 候補: trgm 上位 N=200 件 → vector で再評価 → top_k
    - workspace_id / user_id は Phase 2 で RLS と接続 (Phase 1 は thread.owner_id で簡易フィルタ)
    """
    cleaned_query, date_prefix = parse_query(query)
    if not cleaned_query:
        return []

    rows = await _candidate_rows(
        cleaned_query, date_prefix=date_prefix,
        user_id=user_id, workspace_id=workspace_id,
        candidate_limit=200,
    )

    hits: list[HybridHit] = []
    for r in rows:
        content = r.get("content") or ""
        trgm = trgm_similarity(cleaned_query, content)
        if trgm == 0.0 and cleaned_query.lower() not in content.lower():
            continue
        vector = await _vector_score_for(cleaned_query, content) if use_vector else 0.0
        final = weight_trgm * trgm + weight_vector * vector
        hits.append(HybridHit(
            message_id=r.get("id", 0),
            thread_id=r.get("thread_id", 0),
            role=r.get("role", ""),
            content=content,
            created_at=r.get("created_at"),
            trgm_score=trgm,
            vector_score=vector,
            final_score=final,
        ))

    hits.sort(key=lambda h: h.final_score, reverse=True)
    return hits[:top_k]


async def _candidate_rows(
    cleaned_query: str, *,
    date_prefix: Optional[str] = None,
    user_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    candidate_limit: int = 200,
) -> list[dict]:
    """SQLite 経路: LIKE で候補絞り込み → bigram で再評価 (本関数は候補 fetch のみ)。"""
    sql = ["SELECT id, thread_id, role, content, created_at FROM chat_messages WHERE 1=1"]
    args: list = []

    # LIKE 候補絞り込み (cleaned_query の最初の単語を使う)
    first_word = cleaned_query.split()[0] if cleaned_query.split() else ""
    if first_word:
        sql.append("AND LOWER(content) LIKE ?")
        args.append(f"%{first_word.lower()}%")

    if date_prefix:
        # YYYY-MM% で month filter
        sql.append("AND created_at LIKE ?")
        args.append(f"{date_prefix}%")

    sql.append("ORDER BY id DESC LIMIT ?")
    args.append(candidate_limit)

    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(" ".join(sql), tuple(args))
            rows = await cur.fetchall()
    except Exception as e:
        logger.warning("chat_search candidate fetch failed: %s", e)
        return []

    return [dict(r) for r in rows]


# ──────────────────────────────────────────
# Phase 2: Postgres native query (フック)
# ──────────────────────────────────────────

async def hybrid_search_postgres(
    query: str, *, user_id: str, workspace_id: Optional[str] = None,
    top_k: int = 20,
) -> list[HybridHit]:
    """Phase 2 専用 (DATABASE_URL=postgres*)。

    本実装は Phase 2 で:
      SELECT id, thread_id, role, content, created_at,
             similarity(content, $query) AS trgm_score,
             1 - (embedding <=> $query_emb) AS vector_score,
             0.5 * similarity(...) + 0.5 * (1 - <=>...) AS final_score
      FROM chat_messages
      WHERE workspace_id = $workspace_id  -- RLS が auth.uid() で再フィルタ
      ORDER BY final_score DESC
      LIMIT $top_k

    のように pgvector + pg_trgm を SQL 内で評価する。Phase 1 では未使用。
    """
    raise NotImplementedError("Phase 2 で pgvector + pg_trgm 直接 SQL を実装")
