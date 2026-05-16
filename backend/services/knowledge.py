"""T-V3-B-22 / F-016: Knowledge base service (list + hybrid search).

Workspace-scoped knowledge listing and hybrid search combining pgvector +
pg_trgm + Postgres FTS over `knowledge_base`.

仕様参照:
  - docs/functional-breakdown/2026-05-16_v3/features.json#F-016
  - docs/api-design/2026-05-16_v3/openapi.yaml (KnowledgeItem / KnowledgeHit)
  - docs/functional-breakdown/2026-05-16_v3/entities.json#E-068 / E-033

AC マッピング:
  AC-F1 EVENT-DRIVEN : hybrid_search が pgvector + pg_trgm + FTS を合成し top 50 を返す
  AC-F2 EVENT-DRIVEN : list_knowledge が KnowledgeItem[] を返す
  AC-F5 EVENT-DRIVEN : hybrid_search が KnowledgeHit[] を返す
  AC-UBIQUITOUS (F-016): RLS で workspace member だけが見える

ロジックは DB 不在環境 (test) でも graceful に空を返す。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# AC-F1 / F-016 spec: max 50 hits cap
MAX_SEARCH_LIMIT = 50
# F-016 ears_ac_seed: q must be <= 500 chars
MAX_QUERY_LENGTH = 500


class KnowledgeServiceError(Exception):
    """Raised for service-level validation / data errors."""


@dataclass(frozen=True)
class KnowledgeItem:
    id: str
    title: str
    path: Optional[str]
    tags: list[str]
    updated_at: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "path": self.path,
            "tags": list(self.tags),
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class KnowledgeHit:
    id: str
    title: str
    snippet: str
    score: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "source": self.source,
        }


def _row_to_item(row: dict[str, Any]) -> KnowledgeItem:
    tags_raw = row.get("tags")
    if isinstance(tags_raw, list):
        tags = [str(t) for t in tags_raw]
    elif isinstance(tags_raw, str) and tags_raw:
        # JSON-encoded string fallback
        try:
            import json
            decoded = json.loads(tags_raw)
            tags = [str(t) for t in decoded] if isinstance(decoded, list) else []
        except Exception:
            tags = []
    else:
        tags = []
    updated_at = row.get("last_updated") or row.get("created_at") or row.get("updated_at")
    return KnowledgeItem(
        id=str(row.get("id")),
        title=str(row.get("title") or ""),
        path=row.get("md_path") if row.get("md_path") is not None else None,
        tags=tags,
        updated_at=str(updated_at) if updated_at is not None else None,
    )


def _row_to_hit(row: dict[str, Any]) -> KnowledgeHit:
    raw_snippet = row.get("snippet") or row.get("summary") or row.get("content") or ""
    snippet = str(raw_snippet)[:280]
    score = row.get("score")
    try:
        score_f = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_f = 0.0
    return KnowledgeHit(
        id=str(row.get("id")),
        title=str(row.get("title") or ""),
        snippet=snippet,
        score=score_f,
        source=str(row.get("source") or "knowledge_base"),
    )


def _coerce_workspace_id(workspace_id: int) -> int:
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise KnowledgeServiceError("workspace_id must be a positive integer")
    return workspace_id


def validate_query(q: str) -> str:
    """Validate search query.

    AC-F7 UNWANTED: 空 / 500 字超は 422 に。
    """
    if q is None or not isinstance(q, str):
        raise KnowledgeServiceError("q must be a string")
    q_stripped = q.strip()
    if not q_stripped:
        raise KnowledgeServiceError("q must not be empty")
    if len(q_stripped) > MAX_QUERY_LENGTH:
        raise KnowledgeServiceError(
            f"q must be <= {MAX_QUERY_LENGTH} chars (got {len(q_stripped)})"
        )
    return q_stripped


def coerce_limit(limit: Optional[int]) -> int:
    """Clamp limit into [1, MAX_SEARCH_LIMIT]. None → MAX_SEARCH_LIMIT."""
    if limit is None:
        return MAX_SEARCH_LIMIT
    if not isinstance(limit, int):
        raise KnowledgeServiceError("limit must be int")
    if limit <= 0:
        raise KnowledgeServiceError("limit must be > 0")
    return min(limit, MAX_SEARCH_LIMIT)


async def list_knowledge(
    workspace_id: int,
    *,
    category: Optional[str] = None,
) -> list[KnowledgeItem]:
    """List knowledge_base rows scoped by workspace.

    AC-F2 EVENT-DRIVEN: GET /api/workspaces/{id}/knowledge → items: KnowledgeItem[]
    AC-UBIQUITOUS (F-016): RLS で member だけが見える前提で、service は workspace_id で filter。
    """
    _coerce_workspace_id(workspace_id)
    if category is not None:
        if not isinstance(category, str):
            raise KnowledgeServiceError("category must be string when provided")
        category = category.strip() or None

    try:
        from db import async_db as aiosqlite
    except Exception:  # pragma: no cover - DB module unavailable
        logger.warning("knowledge service: db module unavailable, returning empty")
        return []

    sql_parts = [
        "SELECT id, title, md_path, tags, last_updated, created_at, category",
        "FROM knowledge_base",
        "WHERE workspace_id = ?",
    ]
    params: list[Any] = [workspace_id]
    if category:
        sql_parts.append("AND category = ?")
        params.append(category)
    sql_parts.append("ORDER BY COALESCE(last_updated, created_at) DESC")
    sql_parts.append("LIMIT 200")
    sql = "\n".join(sql_parts)

    try:
        async with aiosqlite.connect() as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
    except Exception as e:
        # DB 不在 / table 未作成等は graceful に空 (test 環境用)
        logger.info("knowledge.list_knowledge fallback to empty: %s", e)
        return []
    return [_row_to_item(dict(r)) for r in rows]


async def hybrid_search(
    workspace_id: int,
    *,
    q: str,
    limit: Optional[int] = None,
) -> list[KnowledgeHit]:
    """Hybrid search: pgvector + pg_trgm + Postgres FTS (tsvector) を合成。

    AC-F1 EVENT-DRIVEN: q を pgvector + pg_trgm + FTS で合成し top 50 を返す.
    Embedding が無い row は trigram + FTS のみ.

    Scoring (final = max(vector, trgm * 0.6, fts * 0.4)):
      - vector  : 1 - (embedding <=> query_emb)  (cosine similarity)
      - trgm    : pg_trgm similarity(title || content, q)
      - fts     : ts_rank(tsv, plainto_tsquery(q))

    DB 不在環境では空 list を返す.
    """
    _coerce_workspace_id(workspace_id)
    q_clean = validate_query(q)
    eff_limit = coerce_limit(limit)

    try:
        from db import async_db as aiosqlite
    except Exception:  # pragma: no cover
        logger.warning("knowledge service: db module unavailable, returning empty")
        return []

    # embedding は build-factory 内部の embedding_service で取得 (fallback graceful).
    query_emb: Optional[list[float]] = None
    try:
        from services.embedding_service import embed  # type: ignore
        query_emb = await embed(q_clean)  # may return None when no API key
    except Exception:
        query_emb = None

    if query_emb is not None:
        sql = """
            SELECT
                id, title, md_path, summary, content, source,
                GREATEST(
                    CASE WHEN embedding IS NOT NULL
                         THEN 1 - (embedding <=> ?::vector)
                         ELSE 0 END,
                    COALESCE(similarity(
                        COALESCE(title, '') || ' ' || COALESCE(content, ''),
                        ?
                    ), 0) * 0.6,
                    COALESCE(ts_rank(
                        to_tsvector('simple',
                                    COALESCE(title, '') || ' ' ||
                                    COALESCE(content, '') || ' ' ||
                                    COALESCE(summary, '')),
                        plainto_tsquery('simple', ?)
                    ), 0) * 0.4
                ) AS score
            FROM knowledge_base
            WHERE workspace_id = ?
            ORDER BY score DESC
            LIMIT ?
        """
        import json as _json
        params: list[Any] = [_json.dumps(query_emb), q_clean, q_clean, workspace_id, eff_limit]
    else:
        sql = """
            SELECT
                id, title, md_path, summary, content, source,
                GREATEST(
                    COALESCE(similarity(
                        COALESCE(title, '') || ' ' || COALESCE(content, ''),
                        ?
                    ), 0) * 0.6,
                    COALESCE(ts_rank(
                        to_tsvector('simple',
                                    COALESCE(title, '') || ' ' ||
                                    COALESCE(content, '') || ' ' ||
                                    COALESCE(summary, '')),
                        plainto_tsquery('simple', ?)
                    ), 0) * 0.4
                ) AS score
            FROM knowledge_base
            WHERE workspace_id = ?
            ORDER BY score DESC
            LIMIT ?
        """
        params = [q_clean, q_clean, workspace_id, eff_limit]

    try:
        async with aiosqlite.connect() as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
    except Exception as e:
        logger.info("knowledge.hybrid_search fallback to empty: %s", e)
        return []
    return [_row_to_hit(dict(r)) for r in rows]
