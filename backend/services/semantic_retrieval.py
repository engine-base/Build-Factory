"""T-M28-05: semantic retrieval (existing embedding_service 活用).

M-28 (3-tier memory) の semantic retrieval を統一インターフェースで提供する.
既存の embedding_service / rag_context を thin wrapper でラップし、3 つの scope
(tier2 summary / tier3 knowledge / tier3 conversation) を横断検索する.

設計:
  - 検索 scope: tier2_summary / tier3_knowledge / tier3_conversation
  - 各 scope は既存 service を REUSE (新規 vector store は作らない)
  - 結果は (scope, score, snippet) 形式で統一・スコア降順で merge
  - min_score / top_k で枝刈り
  - 検索失敗 (embedding 不可) は空 list を返す ()
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


class SemanticRetrievalError(RuntimeError):
    pass


VALID_SCOPES = ("tier2_summary", "tier3_knowledge", "tier3_conversation")
DEFAULT_SCOPES = ("tier3_knowledge", "tier3_conversation")
MAX_QUERY_CHARS = 4000
MAX_TOP_K = 100
MAX_SCOPES = len(VALID_SCOPES)
DEFAULT_TOP_K = 10
DEFAULT_MIN_SCORE = 0.4


# ──────────────────────────────────────────────────────────────────────
# Internal helpers — それぞれ既存 service を呼ぶ
# ──────────────────────────────────────────────────────────────────────


async def _search_tier3_knowledge(
    query: str, *, top_k: int, min_score: float,
    skill_tags: Optional[list[str]] = None,
) -> list[dict]:
    try:
        from services.embedding_service import search_knowledge
        items = await search_knowledge(
            query=query, skill_tags=skill_tags,
            top_k=top_k, min_score=min_score,
        )
    except Exception as e:  # pragma: no cover - embedding 障害
        logger.warning("tier3_knowledge search failed: %s", e)
        return []
    out: list[dict] = []
    for it in items or []:
        out.append({
            "scope": "tier3_knowledge",
            "id": it.get("id"),
            "title": it.get("title") or "",
            "snippet": (it.get("content") or "")[:300],
            "score": float(it.get("score") or 0.0),
            "meta": {
                "category": it.get("category"),
                "skill_tags": it.get("skill_tags"),
            },
        })
    return out


async def _search_tier3_conversation(
    query: str, *, top_k: int, min_score: float,
    exclude_thread_id: Optional[int] = None,
) -> list[dict]:
    try:
        from services.rag_context import search_similar_messages
        items = await search_similar_messages(
            query=query, exclude_thread_id=exclude_thread_id,
            top_k=top_k, min_score=min_score,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("tier3_conversation search failed: %s", e)
        return []
    out: list[dict] = []
    for it in items or []:
        out.append({
            "scope": "tier3_conversation",
            "id": it.get("thread_id"),
            "title": f"thread:{it.get('thread_id')}" if it.get("thread_id") else "",
            "snippet": (it.get("content") or "")[:300],
            "score": float(it.get("score") or 0.0),
            "meta": {
                "role": it.get("role"),
                "created_at": it.get("created_at"),
                "thread_id": it.get("thread_id"),
            },
        })
    return out


async def _search_tier2_summary(
    query: str, *, top_k: int, min_score: float,
    session_id: Optional[int] = None,
) -> list[dict]:
    """Tier 2 (9-section summary) を section-level keyword match で検索する.

    Tier 2 は 1 セッション 1 行で量が少ないので、ベクトル検索ではなく
    section 単位の単純な部分文字列 + token-overlap スコアで返す.
    """
    try:
        from services.memory_service import _db, _db_path
        params: tuple
        if session_id is not None:
            sql = (
                "SELECT id, thread_id, content, created_at FROM chat_messages "
                "WHERE role = 'system_summary' AND thread_id = ? "
                "ORDER BY id DESC LIMIT 100"
            )
            params = (session_id,)
        else:
            sql = (
                "SELECT id, thread_id, content, created_at FROM chat_messages "
                "WHERE role = 'system_summary' ORDER BY id DESC LIMIT 100"
            )
            params = ()
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
    except Exception as e:  # pragma: no cover
        logger.warning("tier2_summary search failed: %s", e)
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    scored: list[dict] = []
    for row in rows or []:
        try:
            summary = json.loads(row[2])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(summary, dict):
            continue
        for section, body in summary.items():
            text = _stringify_section(body)
            if not text:
                continue
            score = _token_overlap_score(q_tokens, text)
            if score >= min_score:
                scored.append({
                    "scope": "tier2_summary",
                    "id": row[0],
                    "title": f"summary[{section}] (thread:{row[1]})",
                    "snippet": text[:300],
                    "score": round(score, 4),
                    "meta": {
                        "thread_id": row[1],
                        "section": section,
                        "created_at": row[3],
                    },
                })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _tokenize(text: str) -> set[str]:
    if not isinstance(text, str):
        return set()
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return {tok for tok in cleaned.split() if len(tok) >= 2}


def _token_overlap_score(q_tokens: set[str], text: str) -> float:
    t_tokens = _tokenize(text)
    if not t_tokens or not q_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    return overlap / float(len(q_tokens))


def _stringify_section(body: Any) -> str:
    if isinstance(body, str):
        return body
    if isinstance(body, list):
        return " ".join(str(x) for x in body)
    if isinstance(body, dict):
        return json.dumps(body, ensure_ascii=False)
    if body is None:
        return ""
    return str(body)


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def validate_inputs(
    query: str, scopes: Iterable[str], top_k: int, min_score: float,
) -> tuple[str, list[str]]:
    if not isinstance(query, str) or not query.strip():
        raise SemanticRetrievalError("query must not be empty")
    query = query.strip()
    if len(query) > MAX_QUERY_CHARS:
        raise SemanticRetrievalError(f"query must be <= {MAX_QUERY_CHARS} chars")
    scope_list = list(scopes)
    if not scope_list:
        raise SemanticRetrievalError("scopes must be a non-empty list")
    if len(scope_list) > MAX_SCOPES:
        raise SemanticRetrievalError(f"scopes must be <= {MAX_SCOPES}")
    for s in scope_list:
        if s not in VALID_SCOPES:
            raise SemanticRetrievalError(
                f"scope {s!r} not in {VALID_SCOPES}"
            )
    if len(set(scope_list)) != len(scope_list):
        raise SemanticRetrievalError("scopes must be unique")
    if not isinstance(top_k, int) or top_k <= 0:
        raise SemanticRetrievalError("top_k must be > 0")
    if top_k > MAX_TOP_K:
        raise SemanticRetrievalError(f"top_k must be <= {MAX_TOP_K}")
    if not isinstance(min_score, (int, float)) or not (0.0 <= min_score <= 1.0):
        raise SemanticRetrievalError("min_score must be 0.0..1.0")
    return query, scope_list


async def search(
    query: str,
    *,
    scopes: Iterable[str] = DEFAULT_SCOPES,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
    skill_tags: Optional[list[str]] = None,
    session_id: Optional[int] = None,
    exclude_thread_id: Optional[int] = None,
) -> dict:
    """3-tier memory を統一インターフェースで横断検索する."""
    query, scope_list = validate_inputs(query, scopes, top_k, min_score)

    if skill_tags is not None:
        if not isinstance(skill_tags, list) or not all(
            isinstance(t, str) and t.strip() for t in skill_tags
        ):
            raise SemanticRetrievalError("skill_tags must be a list of non-empty strings")
        if len(skill_tags) > 20:
            raise SemanticRetrievalError("skill_tags must be <= 20")
    if session_id is not None and (not isinstance(session_id, int) or session_id <= 0):
        raise SemanticRetrievalError("session_id must be > 0")
    if exclude_thread_id is not None and (
        not isinstance(exclude_thread_id, int) or exclude_thread_id <= 0
    ):
        raise SemanticRetrievalError("exclude_thread_id must be > 0")

    # 並列実行
    coros = []
    for s in scope_list:
        if s == "tier3_knowledge":
            coros.append(_search_tier3_knowledge(
                query, top_k=top_k, min_score=min_score, skill_tags=skill_tags,
            ))
        elif s == "tier3_conversation":
            coros.append(_search_tier3_conversation(
                query, top_k=top_k, min_score=min_score,
                exclude_thread_id=exclude_thread_id,
            ))
        elif s == "tier2_summary":
            coros.append(_search_tier2_summary(
                query, top_k=top_k, min_score=min_score, session_id=session_id,
            ))
    results = await asyncio.gather(*coros, return_exceptions=True)

    merged: list[dict] = []
    per_scope: dict[str, int] = {}
    errors: dict[str, str] = {}
    for s, res in zip(scope_list, results):
        if isinstance(res, Exception):
            errors[s] = str(res)[:300]
            per_scope[s] = 0
            continue
        per_scope[s] = len(res)
        merged.extend(res)

    merged.sort(key=lambda x: x["score"], reverse=True)
    merged = merged[:top_k]

    return {
        "query": query,
        "scopes": scope_list,
        "count": len(merged),
        "per_scope_count": per_scope,
        "results": merged,
        "errors": errors or None,
    }
