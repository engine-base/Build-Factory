"""T-V3-B-27 / F-024: Global search service.

This module powers ``GET /api/search`` (Cmd+K modal). It aggregates ranked hits
across four sources:

  - tasks         (table: bf_tasks)
  - artifacts     (table: artifacts)
  - knowledge     (table: knowledge_base via embedding_service)
  - audit         (table: audit_logs)

Score = combined FTS-style score + vector similarity, normalised to [0, 1].
Where vector embedding is unavailable (no OPENAI_API_KEY / table not migrated),
the service degrades to LIKE-based text matching only. This keeps the service
testable in the SQLite dev DB while the Postgres + pgvector path is reserved
for production migrations.

## AC mapping (T-V3-B-27 functional Tier)

  AC-F1 EVENT-DRIVEN : ``global_search(q, ...)`` returns hits ranked by combined
                       FTS + vector similarity. ``_combined_score`` blends text
                       overlap with vector cosine when an embedding is provided.
  AC-F2 UNWANTED     : ``_validate_query`` raises ``InvalidSearchQuery`` for
                       ``q > 500`` chars or empty. Router maps this to 422.
  AC-F3 UNWANTED     : ``RateLimiter`` enforces 60 req/min/user. Router maps a
                       ``RateLimitExceeded`` to 429.
  AC-F5 EVENT-DRIVEN : Public ``global_search`` returns ``dict`` matching the
                       openapi.yaml#/api/search response shape (hits/total/
                       categories).

The service is intentionally self-contained (no LangGraph / LangChain) per the
ADR-010 / ADR-012 main-path lint rules (rule_id 6, 7).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────

MIN_QUERY_CHARS = 1
MAX_QUERY_CHARS = 500
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

VALID_CATEGORIES: tuple[str, ...] = ("tasks", "artifacts", "knowledge", "audit")

# Rate limiting: 60 req / minute / user (F-024 contract).
RATE_LIMIT_WINDOW_SEC = 60.0
RATE_LIMIT_MAX_REQUESTS = 60


# ─────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────


class InvalidSearchQuery(ValueError):
    """422: query validation failed (empty / too long / bad category)."""

    def __init__(self, message: str, *, field: str = "q") -> None:
        super().__init__(message)
        self.field = field


class RateLimitExceeded(RuntimeError):
    """429: per-user rate limit exceeded."""

    def __init__(self, *, retry_after_sec: float) -> None:
        super().__init__(f"rate limit exceeded, retry after {retry_after_sec:.1f}s")
        self.retry_after_sec = retry_after_sec


# ─────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────


def _validate_query(raw: Any) -> str:
    if raw is None:
        raise InvalidSearchQuery("query 'q' is required")
    if not isinstance(raw, str):
        raise InvalidSearchQuery(
            f"query 'q' must be string, got {type(raw).__name__}"
        )
    s = raw.strip()
    if len(s) < MIN_QUERY_CHARS:
        raise InvalidSearchQuery("query 'q' must not be empty")
    if len(s) > MAX_QUERY_CHARS:
        raise InvalidSearchQuery(
            f"query 'q' must be <= {MAX_QUERY_CHARS} chars, got {len(s)}"
        )
    return s


def _validate_category(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise InvalidSearchQuery(
            f"category must be string, got {type(raw).__name__}",
            field="category",
        )
    norm = raw.strip().lower()
    if not norm:
        return None
    if norm not in VALID_CATEGORIES:
        raise InvalidSearchQuery(
            f"category must be one of {VALID_CATEGORIES}, got {raw!r}",
            field="category",
        )
    return norm


def _validate_limit(raw: Any) -> int:
    if raw is None:
        return DEFAULT_LIMIT
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise InvalidSearchQuery(
            f"limit must be int, got {type(raw).__name__}", field="limit",
        )
    if raw <= 0 or raw > MAX_LIMIT:
        raise InvalidSearchQuery(
            f"limit must be in (0, {MAX_LIMIT}], got {raw}", field="limit",
        )
    return raw


# ─────────────────────────────────────────────────────────────────────
# Rate limiter (in-memory sliding window per user)
# ─────────────────────────────────────────────────────────────────────


class RateLimiter:
    """Sliding-window rate limiter, per-user, in-process.

    Phase 1 dogfood deployment is single-instance so an in-process limiter is
    sufficient. Multi-instance deployments should swap this for Redis-backed
    state in Phase 2 — the public ``check`` API stays stable.
    """

    def __init__(
        self,
        *,
        max_requests: int = RATE_LIMIT_MAX_REQUESTS,
        window_sec: float = RATE_LIMIT_WINDOW_SEC,
    ) -> None:
        self._max = max_requests
        self._window = window_sec
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, user_key: str, *, now: Optional[float] = None) -> int:
        """Register one hit. Raises RateLimitExceeded if over budget.

        Returns the remaining quota in the current window (for debug headers).
        """
        ts = now if now is not None else time.time()
        with self._lock:
            bucket = self._buckets.setdefault(user_key, deque())
            cutoff = ts - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                retry = max(0.0, self._window - (ts - bucket[0]))
                raise RateLimitExceeded(retry_after_sec=retry)
            bucket.append(ts)
            return self._max - len(bucket)

    def reset(self, user_key: Optional[str] = None) -> None:
        """Test helper: clear bucket(s)."""
        with self._lock:
            if user_key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(user_key, None)


# Singleton rate limiter (per-process)
_DEFAULT_LIMITER = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _DEFAULT_LIMITER


# ─────────────────────────────────────────────────────────────────────
# Score: blended FTS + vector similarity
# ─────────────────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _text_overlap_score(query: str, doc: str) -> float:
    """Cheap FTS-style score in [0, 1] based on token overlap.

    This is intentionally lightweight so the service stays portable across
    sqlite/postgres dev environments. Production deployments should bridge to
    pg_trgm / tsvector in ``_fetch_*`` helpers; the return shape is unchanged.
    """
    if not query or not doc:
        return 0.0
    q_tokens = set(t.lower() for t in _WORD_RE.findall(query))
    d_tokens = set(t.lower() for t in _WORD_RE.findall(doc))
    if not q_tokens or not d_tokens:
        return 0.0
    overlap = len(q_tokens & d_tokens)
    return min(1.0, overlap / max(1, len(q_tokens)))


def _combined_score(
    *,
    fts_score: float,
    vector_score: Optional[float],
    fts_weight: float = 0.6,
    vector_weight: float = 0.4,
) -> float:
    """Blend FTS + vector cosine. Vector contribution is dropped when None."""
    f = max(0.0, min(1.0, fts_score))
    if vector_score is None:
        return f
    v = max(0.0, min(1.0, vector_score))
    total_w = fts_weight + vector_weight
    return (f * fts_weight + v * vector_weight) / total_w


# ─────────────────────────────────────────────────────────────────────
# Source fetchers (thin DB wrappers, designed to be monkeypatch-friendly)
# ─────────────────────────────────────────────────────────────────────


async def _fetch_tasks(query: str, *, workspace_ids: Iterable[int], limit: int) -> list[dict]:
    """LIKE-based fetch over bf_tasks. Best-effort; returns [] on DB errors."""
    try:
        from services import bf_db
    except Exception as e:  # pragma: no cover
        logger.warning("bf_db unavailable: %s", e)
        return []
    like = f"%{query}%"
    ws_list = list(workspace_ids)
    try:
        if ws_list:
            placeholders = ",".join(["?"] * len(ws_list))
            rows = bf_db.fetchall(
                f"SELECT id, title, description, project_id, status "
                f"FROM bf_tasks WHERE project_id IN ({placeholders}) "
                f"AND (title LIKE ? OR COALESCE(description, '') LIKE ?) "
                f"ORDER BY id DESC LIMIT ?",
                (*ws_list, like, like, limit),
            )
        else:
            rows = bf_db.fetchall(
                "SELECT id, title, description, project_id, status "
                "FROM bf_tasks WHERE title LIKE ? OR COALESCE(description, '') LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (like, like, limit),
            )
    except Exception as e:
        logger.warning("tasks fetch failed: %s", e)
        return []
    out = []
    for r in rows or []:
        title = r.get("title", "") if isinstance(r, dict) else r["title"]
        desc = r.get("description", "") if isinstance(r, dict) else r["description"]
        fts = _text_overlap_score(query, f"{title} {desc or ''}")
        out.append({
            "id": str(r["id"]),
            "category": "tasks",
            "title": title,
            "snippet": (desc or "")[:160],
            "score": _combined_score(fts_score=fts, vector_score=None),
            "workspace_id": r.get("project_id") if isinstance(r, dict) else r["project_id"],
            "metadata": {"status": r.get("status") if isinstance(r, dict) else r["status"]},
        })
    return out


async def _fetch_artifacts(query: str, *, workspace_ids: Iterable[int], limit: int) -> list[dict]:
    try:
        from services import bf_db
    except Exception as e:  # pragma: no cover
        logger.warning("bf_db unavailable: %s", e)
        return []
    like = f"%{query}%"
    ws_list = list(workspace_ids)
    try:
        if ws_list:
            placeholders = ",".join(["?"] * len(ws_list))
            rows = bf_db.fetchall(
                f"SELECT id, title, type, workspace_id FROM artifacts "
                f"WHERE workspace_id IN ({placeholders}) AND title LIKE ? "
                f"ORDER BY id DESC LIMIT ?",
                (*ws_list, like, limit),
            )
        else:
            rows = bf_db.fetchall(
                "SELECT id, title, type, workspace_id FROM artifacts "
                "WHERE title LIKE ? ORDER BY id DESC LIMIT ?",
                (like, limit),
            )
    except Exception as e:
        logger.warning("artifacts fetch failed: %s", e)
        return []
    out = []
    for r in rows or []:
        title = r["title"]
        fts = _text_overlap_score(query, title or "")
        out.append({
            "id": str(r["id"]),
            "category": "artifacts",
            "title": title,
            "snippet": r.get("type", "") if isinstance(r, dict) else r["type"],
            "score": _combined_score(fts_score=fts, vector_score=None),
            "workspace_id": r.get("workspace_id") if isinstance(r, dict) else r["workspace_id"],
            "metadata": {},
        })
    return out


async def _fetch_knowledge(query: str, *, workspace_ids: Iterable[int], limit: int) -> list[dict]:
    """Bridge to existing embedding_service.search_knowledge when available."""
    ws_list = list(workspace_ids)
    try:
        from services import embedding_service as emb
        hits = await emb.search_knowledge(
            q=query,
            account_id=None,
            workspace_id=ws_list[0] if ws_list else None,
            limit=limit,
        )
    except Exception as e:
        logger.warning("knowledge fetch failed: %s", e)
        return []
    out = []
    for h in hits or []:
        title = h.get("title") or (h.get("content") or "")[:80]
        snippet = (h.get("summary") or h.get("content") or "")[:160]
        fts = _text_overlap_score(query, f"{title} {snippet}")
        vec = h.get("score") if isinstance(h.get("score"), (int, float)) else None
        out.append({
            "id": str(h.get("id", "")),
            "category": "knowledge",
            "title": title,
            "snippet": snippet,
            "score": _combined_score(fts_score=fts, vector_score=vec),
            "workspace_id": h.get("workspace_id"),
            "metadata": {"visibility": h.get("visibility")},
        })
    return out


async def _fetch_audit(query: str, *, workspace_ids: Iterable[int], limit: int) -> list[dict]:
    try:
        from services import bf_db
    except Exception as e:  # pragma: no cover
        logger.warning("bf_db unavailable: %s", e)
        return []
    like = f"%{query}%"
    ws_list = list(workspace_ids)
    try:
        if ws_list:
            placeholders = ",".join(["?"] * len(ws_list))
            rows = bf_db.fetchall(
                f"SELECT id, action, resource_type, workspace_id, created_at "
                f"FROM audit_logs WHERE workspace_id IN ({placeholders}) "
                f"AND (action LIKE ? OR COALESCE(resource_type, '') LIKE ?) "
                f"ORDER BY id DESC LIMIT ?",
                (*ws_list, like, like, limit),
            )
        else:
            rows = bf_db.fetchall(
                "SELECT id, action, resource_type, workspace_id, created_at "
                "FROM audit_logs WHERE action LIKE ? OR COALESCE(resource_type, '') LIKE ? "
                "ORDER BY id DESC LIMIT ?",
                (like, like, limit),
            )
    except Exception as e:
        logger.warning("audit fetch failed: %s", e)
        return []
    out = []
    for r in rows or []:
        title = r["action"] if not isinstance(r, dict) else r.get("action", "")
        resource = r["resource_type"] if not isinstance(r, dict) else r.get("resource_type", "")
        fts = _text_overlap_score(query, f"{title} {resource or ''}")
        out.append({
            "id": str(r["id"]),
            "category": "audit",
            "title": title,
            "snippet": f"resource={resource}",
            "score": _combined_score(fts_score=fts, vector_score=None),
            "workspace_id": r.get("workspace_id") if isinstance(r, dict) else r["workspace_id"],
            "metadata": {"created_at": str(r["created_at"]) if r.get("created_at") else None},
        })
    return out


_CATEGORY_FETCHERS = {
    "tasks": _fetch_tasks,
    "artifacts": _fetch_artifacts,
    "knowledge": _fetch_knowledge,
    "audit": _fetch_audit,
}


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


async def list_caller_workspace_ids(user_id: Optional[str]) -> list[int]:
    """Resolve the workspace ids that the caller is a member of.

    Returns ``[]`` when ``user_id`` is None (search will fall back to the global
    LIKE path; downstream RLS in production Postgres enforces visibility at the
    DB layer regardless of this helper).
    """
    if not user_id:
        return []
    try:
        from services import workspace_service as ws
        rows = await ws.list_workspaces_for_user(user_id)
    except Exception as e:
        logger.warning("list_workspaces_for_user failed for %s: %s", user_id, e)
        return []
    out: list[int] = []
    for r in rows or []:
        wid = r.get("id") if isinstance(r, dict) else None
        if isinstance(wid, int):
            out.append(wid)
    return out


async def global_search(
    q: Any,
    *,
    category: Any = None,
    limit: Any = None,
    user_id: Optional[str] = None,
    workspace_ids: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Run a cross-source global search.

    Args:
      q:            non-empty string (1..500 chars). Otherwise InvalidSearchQuery.
      category:     optional filter — one of VALID_CATEGORIES.
      limit:        optional int in (0, MAX_LIMIT]. default DEFAULT_LIMIT.
      user_id:      caller identity (used for workspace_id resolution if
                    ``workspace_ids`` is None).
      workspace_ids: explicit workspace allow-list (RLS-equivalent in dev DB).

    Returns:
      Dict matching openapi.yaml#/api/search 2xx schema::
        {hits: [...], total: int, categories: {tasks: int, ...}, query: str}
    """
    qn = _validate_query(q)
    cat = _validate_category(category)
    lim = _validate_limit(limit)

    if workspace_ids is None:
        workspace_ids = await list_caller_workspace_ids(user_id)

    started = time.time()
    fetchers = [_CATEGORY_FETCHERS[cat]] if cat else list(_CATEGORY_FETCHERS.values())
    all_hits: list[dict] = []
    for fn in fetchers:
        try:
            hits = await fn(qn, workspace_ids=workspace_ids, limit=lim)
        except Exception as e:  # pragma: no cover
            logger.warning("fetcher %s raised: %s", fn.__name__, e)
            hits = []
        all_hits.extend(hits)

    # Sort by score DESC (stable), trim to limit.
    all_hits.sort(key=lambda h: h.get("score", 0.0), reverse=True)
    all_hits = all_hits[:lim]

    cat_counts: dict[str, int] = {c: 0 for c in VALID_CATEGORIES}
    for h in all_hits:
        c = h.get("category")
        if c in cat_counts:
            cat_counts[c] += 1

    return {
        "hits": all_hits,
        "total": len(all_hits),
        "categories": cat_counts,
        "query": qn,
        "duration_ms": int((time.time() - started) * 1000),
    }
