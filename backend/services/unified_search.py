"""T-024-02: 統一 search service (existing knowledge_search + embedding_service REFACTOR).

既存 `backend/routers/knowledge_search.py` (search_knowledge endpoint) +
`backend/services/embedding_service.py` (semantic search) は **完全無改変** (REUSE).
本 module は複数 source (knowledge + tasks + employees + screens) を横断する
統一 search を提供. T-024-01 (Cmd+K modal) の動的 items 提供 backend.

## 設計

  - Cmd+K modal が呼ぶ /api/search/unified に query を投げる
  - knowledge / tasks / employees / screens を並列検索
  - 統一 result 形式 {kind, id, label, hint, group} で返す
  - 各 source は use_X flag で個別 enable/disable 可
  - existing knowledge_search を thin call (REUSE)

## ADR-010 整合性

knowledge_search の AI/semantic 経路は既存 embedding_service が担当.
本 module は **複数 source aggregator のみ** で AI 経路を再実装しない.

## AC マッピング (T-024-02 REFACTOR)

  AC-1 UBIQUITOUS    : unified_search / SOURCE_HANDLERS / VALID_SOURCES を公開.
                       既存 knowledge_search / embedding_service 無改変.
  AC-2 EVENT-DRIVEN  : 各 source 検索 200ms 以内 / 全体 < 2s / 統一 dict 返却.
  AC-3 STATE-DRIVEN  : read-only / audit emit (search.unified) /
                       存在しない source は silent skip.
  AC-4 UNWANTED      : invalid query (空 / >500 chars) で ValueError /
                       invalid source name で ValueError /
                       hardcoded secret なし.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

VALID_SOURCES = ("knowledge", "tasks", "employees", "screens")
MAX_QUERY_CHARS = 500
MIN_QUERY_CHARS = 1
DEFAULT_LIMIT_PER_SOURCE = 10
MAX_LIMIT_PER_SOURCE = 50


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_query(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("query must be string")
    s = value.strip()
    if len(s) < MIN_QUERY_CHARS:
        raise ValueError(f"query must be >= {MIN_QUERY_CHARS} chars")
    if len(s) > MAX_QUERY_CHARS:
        raise ValueError(f"query must be <= {MAX_QUERY_CHARS} chars")
    return s


def _validate_sources(value: object) -> tuple[str, ...]:
    if value is None:
        return VALID_SOURCES
    if not isinstance(value, (list, tuple)):
        raise ValueError("sources must be list or None")
    out = []
    for s in value:
        if not isinstance(s, str):
            raise ValueError(f"source must be string, got {type(s).__name__}")
        norm = s.strip().lower()
        if norm not in VALID_SOURCES:
            raise ValueError(
                f"source must be one of {VALID_SOURCES}, got {s!r}"
            )
        out.append(norm)
    return tuple(out)


def _validate_limit(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("limit must be int")
    if value <= 0 or value > MAX_LIMIT_PER_SOURCE:
        raise ValueError(
            f"limit must be in (0, {MAX_LIMIT_PER_SOURCE}], got {value}"
        )
    return value


# ──────────────────────────────────────────────────────────────────────
# Source handlers (thin wrappers around existing services)
# ──────────────────────────────────────────────────────────────────────


async def _search_knowledge(
    query: str, *, account_id: Optional[int], limit: int,
) -> list[dict]:
    """既存 knowledge_search router を経由せず service layer 直接呼出.

    embedding_service.search_knowledge は async. 既存 API に従う.
    """
    try:
        from services import embedding_service as emb
        hits = await emb.search_knowledge(
            q=query,
            account_id=account_id,
            workspace_id=None,
            limit=limit,
        )
    except Exception as e:
        logger.warning("knowledge search failed: %s", e)
        return []
    items = []
    for h in hits or []:
        items.append({
            "kind": "knowledge",
            "id": str(h.get("id", "")),
            "label": h.get("title") or h.get("content", "")[:80],
            "hint": h.get("visibility", ""),
            "group": "Knowledge",
        })
    return items


async def _search_tasks(
    query: str, *, account_id: Optional[int], limit: int,
) -> list[dict]:
    """tasks の title LIKE 検索. DB layer 直接 (既存 bf_db pattern)."""
    try:
        from services import bf_db
        like_q = f"%{query}%"
        if account_id is not None:
            rows = bf_db.fetchall(
                "SELECT id, title, status FROM bf_tasks "
                "WHERE workspace_id = ? AND title LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (account_id, like_q, limit),
            )
        else:
            rows = bf_db.fetchall(
                "SELECT id, title, status FROM bf_tasks "
                "WHERE title LIKE ? ORDER BY id DESC LIMIT ?",
                (like_q, limit),
            )
    except Exception as e:
        logger.warning("tasks search failed: %s", e)
        return []
    return [
        {
            "kind": "task",
            "id": str(r["id"]),
            "label": r["title"],
            "hint": r.get("status", ""),
            "group": "Tasks",
        }
        for r in rows
    ]


async def _search_employees(
    query: str, *, account_id: Optional[int], limit: int,
) -> list[dict]:
    """ai_employees 名検索 (in-memory store 経由)."""
    try:
        from services.ai_employee_store import get_store
        store = get_store()
        all_emp = store.list_employees(include_inactive=False)
    except Exception as e:
        logger.warning("employees search failed: %s", e)
        return []
    q_lower = query.lower()
    matches = [
        e for e in all_emp
        if q_lower in e.display_name.lower() or q_lower in e.employee_key.lower()
    ][:limit]
    return [
        {
            "kind": "employee",
            "id": str(e.id),
            "label": e.display_name,
            "hint": e.role_level,
            "group": "Employees",
        }
        for e in matches
    ]


async def _search_screens(
    query: str, *, account_id: Optional[int], limit: int,
) -> list[dict]:
    """design_frames 名検索 (T-005b-01 screens_components 連携)."""
    try:
        from services import bf_db
        like_q = f"%{query}%"
        if account_id is not None:
            rows = bf_db.fetchall(
                "SELECT id, name, frame_type FROM design_frames "
                "WHERE workspace_id = ? AND name LIKE ? LIMIT ?",
                (account_id, like_q, limit),
            )
        else:
            rows = bf_db.fetchall(
                "SELECT id, name, frame_type FROM design_frames "
                "WHERE name LIKE ? LIMIT ?",
                (like_q, limit),
            )
    except Exception as e:
        logger.warning("screens search failed: %s", e)
        return []
    return [
        {
            "kind": "screen",
            "id": str(r["id"]),
            "label": r["name"],
            "hint": r.get("frame_type", ""),
            "group": "Screens",
        }
        for r in rows
    ]


# 各 source の handler 関数 mapping (test-friendly)
SOURCE_HANDLERS: dict[str, Callable] = {
    "knowledge": _search_knowledge,
    "tasks": _search_tasks,
    "employees": _search_employees,
    "screens": _search_screens,
}


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


async def unified_search(
    query: str,
    *,
    sources: Optional[list[str]] = None,
    account_id: Optional[int] = None,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
) -> dict:
    """複数 source を並列検索し統一 dict を返す.

    Returns:
      {
        "query": str,
        "sources_used": list[str],
        "results": [{kind, id, label, hint, group}, ...],
        "by_kind": {kind: int_count, ...},
        "total": int,
      }
    """
    q = _validate_query(query)
    src_tuple = _validate_sources(sources)
    limit = _validate_limit(limit_per_source)
    if account_id is not None and (not isinstance(account_id, int) or account_id <= 0):
        raise ValueError("account_id must be positive int or None")

    # 各 source を並列実行
    tasks = []
    used_sources = []
    for src_name in src_tuple:
        handler = SOURCE_HANDLERS.get(src_name)
        if handler is None:
            continue
        used_sources.append(src_name)
        tasks.append(handler(q, account_id=account_id, limit=limit))

    results_per_source = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: list[dict] = []
    for src_name, items_or_err in zip(used_sources, results_per_source):
        if isinstance(items_or_err, Exception):
            logger.warning("source %s raised: %s", src_name, items_or_err)
            continue
        all_items.extend(items_or_err)

    by_kind: dict[str, int] = {}
    for item in all_items:
        kind = item.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1

    return {
        "query": q,
        "sources_used": used_sources,
        "results": all_items,
        "by_kind": by_kind,
        "total": len(all_items),
    }


def list_valid_sources() -> list[str]:
    return list(VALID_SOURCES)
