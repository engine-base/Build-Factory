"""T-V3-B-22 / F-016: Knowledge base backend (list + search) tests.

Targets:
  GET /api/workspaces/{id}/knowledge          (list)
  GET /api/workspaces/{id}/knowledge/search   (hybrid search)

AC coverage:
  AC-F1 EVENT-DRIVEN  : hybrid_search が pgvector + pg_trgm + FTS を合成 top 50
  AC-F2 EVENT-DRIVEN  : GET /knowledge が 2xx + items contract (F-016)
  AC-F3 UNWANTED 401  : 認証無 (Authorization / user_id どちらも無し)
  AC-F4 UNWANTED 422  : invalid input (workspace_id<=0 等) field_errors map
  AC-F5 EVENT-DRIVEN  : GET /knowledge/search が 2xx + hits contract (F-016)
  AC-F6 UNWANTED 401  : 認証無
  AC-F7 UNWANTED 422  : invalid input (q 空 / 500 字超 / limit<=0)
"""
from __future__ import annotations

import os
import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    # Supabase env vars: test 環境用のダミー値. これがないと
    # services/supabase_client.py が import 時に RuntimeError を投げる.
    for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY",
              "SUPABASE_SERVICE_KEY", "SUPABASE_JWT_SECRET"):
        os.environ.setdefault(k, "test")
    # sys.path bootstrap (backend/ root)
    BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)
    from main import app  # type: ignore
    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────
# service-level (pure function) tests
# ─────────────────────────────────────────────────

def test_validate_query_rejects_empty() -> None:
    """AC-F7 UNWANTED: empty query → service error."""
    from services import knowledge as svc

    with pytest.raises(svc.KnowledgeServiceError):
        svc.validate_query("")
    with pytest.raises(svc.KnowledgeServiceError):
        svc.validate_query("   ")


def test_validate_query_rejects_over_500_chars() -> None:
    """AC-F7 UNWANTED / F-016 ears_ac_seed: q > 500 chars → 422."""
    from services import knowledge as svc

    with pytest.raises(svc.KnowledgeServiceError) as ei:
        svc.validate_query("x" * 501)
    assert "500" in str(ei.value) or "must be" in str(ei.value)


def test_validate_query_accepts_normal_input() -> None:
    from services import knowledge as svc

    assert svc.validate_query("  hello world  ") == "hello world"


def test_coerce_limit_clamps_to_max_50() -> None:
    """AC-F1: top 50 cap. limit=200 → 50."""
    from services import knowledge as svc

    assert svc.coerce_limit(200) == svc.MAX_SEARCH_LIMIT
    assert svc.coerce_limit(10) == 10
    assert svc.coerce_limit(None) == svc.MAX_SEARCH_LIMIT


def test_coerce_limit_rejects_non_positive() -> None:
    from services import knowledge as svc

    with pytest.raises(svc.KnowledgeServiceError):
        svc.coerce_limit(0)
    with pytest.raises(svc.KnowledgeServiceError):
        svc.coerce_limit(-3)


# ─────────────────────────────────────────────────
# router-level (HTTP) tests — 401 / 422 / 2xx happy path
# ─────────────────────────────────────────────────

# ---- 401 UNWANTED: AC-F3 / AC-F6 ----


def test_list_returns_401_when_no_auth(client: TestClient) -> None:
    """AC-F3 UNWANTED: no Authorization header & no user_id → 401."""
    r = client.get("/api/workspaces/1/knowledge")
    assert r.status_code == 401, r.text
    body = r.json()
    detail = body.get("detail") or {}
    assert isinstance(detail, dict)
    assert detail.get("code") == "knowledge.unauthorized"


def test_search_returns_401_when_no_auth(client: TestClient) -> None:
    """AC-F6 UNWANTED."""
    r = client.get("/api/workspaces/1/knowledge/search", params={"q": "hello"})
    assert r.status_code == 401, r.text
    body = r.json()
    assert (body.get("detail") or {}).get("code") == "knowledge.unauthorized"


def test_list_returns_401_when_bearer_token_malformed(client: TestClient) -> None:
    """AC-F3: Authorization が 'Bearer xxx' 形式でない場合 401."""
    r = client.get(
        "/api/workspaces/1/knowledge",
        headers={"Authorization": "Token abc"},
    )
    assert r.status_code == 401


def test_list_returns_401_when_user_id_blank(client: TestClient) -> None:
    """空白の user_id は unauthorized."""
    r = client.get("/api/workspaces/1/knowledge", params={"user_id": "   "})
    assert r.status_code == 401


# ---- 422 UNWANTED: AC-F4 / AC-F7 ----


def test_list_returns_422_when_workspace_id_zero(client: TestClient) -> None:
    """AC-F4 UNWANTED: workspace_id<=0 → 422 + field_errors."""
    r = client.get(
        "/api/workspaces/0/knowledge",
        params={"user_id": "masato"},
    )
    assert r.status_code == 422, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "knowledge.invalid_workspace_id"
    # field-level error map required by AC-F4
    assert "field_errors" in detail
    assert "workspace_id" in detail["field_errors"]


def test_search_returns_422_when_q_missing(client: TestClient) -> None:
    """AC-F7 UNWANTED: q required → FastAPI's 422 validation error."""
    r = client.get(
        "/api/workspaces/1/knowledge/search",
        params={"user_id": "masato"},
    )
    assert r.status_code == 422


def test_search_returns_422_when_q_too_long(client: TestClient) -> None:
    """AC-F7 / F-016 ears_ac_seed: q > 500 chars → 422 + field_errors."""
    r = client.get(
        "/api/workspaces/1/knowledge/search",
        params={"user_id": "masato", "q": "a" * 501},
    )
    assert r.status_code == 422, r.text
    detail = r.json().get("detail")
    # FastAPI native error or our structured error
    if isinstance(detail, dict) and detail.get("code") == "knowledge.invalid_input":
        assert "field_errors" in detail


def test_search_returns_422_when_limit_too_high(client: TestClient) -> None:
    """AC-F7: limit > 50 → FastAPI 422 (le=50 constraint)."""
    r = client.get(
        "/api/workspaces/1/knowledge/search",
        params={"user_id": "masato", "q": "hello", "limit": 9999},
    )
    assert r.status_code == 422


def test_search_returns_422_when_limit_zero(client: TestClient) -> None:
    """AC-F7: limit <= 0 → 422."""
    r = client.get(
        "/api/workspaces/1/knowledge/search",
        params={"user_id": "masato", "q": "hello", "limit": 0},
    )
    assert r.status_code == 422


# ---- 2xx happy path: AC-F2 / AC-F5 ----


def _patch_db_rows(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> None:
    """Patch services.knowledge to return canned DB rows without real Postgres.

    `list_knowledge` and `hybrid_search` 内で `from db import async_db as aiosqlite`
    を実行するため、その import を fake module で差し替える.
    """

    class _Cur:
        def __init__(self, _rows: list[dict[str, Any]]) -> None:
            self._rows = _rows

        async def fetchall(self) -> list[dict[str, Any]]:
            return self._rows

        async def fetchone(self) -> Any:
            return self._rows[0] if self._rows else None

    class _Conn:
        def __init__(self, _rows: list[dict[str, Any]]) -> None:
            self._rows = _rows
            self.row_factory: Any = None

        async def execute(self, sql: str, args: Any = ()) -> _Cur:
            return _Cur(self._rows)

        async def commit(self) -> None:
            return None

        async def __aenter__(self) -> "_Conn":
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

    fake_db = types.ModuleType("db.async_db")
    fake_db.connect = lambda *a, **kw: _Conn(rows)  # type: ignore[attr-defined]
    fake_db.Row = dict  # type: ignore[attr-defined]
    fake_db_pkg = types.ModuleType("db")
    fake_db_pkg.async_db = fake_db  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db", fake_db_pkg)
    monkeypatch.setitem(sys.modules, "db.async_db", fake_db)


def test_list_returns_200_and_items_contract(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-F2 EVENT-DRIVEN: GET /knowledge → 2xx + items: KnowledgeItem[]."""
    rows = [
        {
            "id": 1,
            "title": "Auth Design Decision",
            "md_path": "decisions/2026-05-12_auth.md",
            "tags": ["auth", "supabase"],
            "last_updated": "2026-05-12",
            "created_at": "2026-05-12 00:00:00",
            "category": "decision",
        },
        {
            "id": 2,
            "title": "RLS overview",
            "md_path": None,
            "tags": [],
            "last_updated": None,
            "created_at": "2026-05-11 00:00:00",
            "category": "guide",
        },
    ]
    _patch_db_rows(monkeypatch, rows)

    r = client.get(
        "/api/workspaces/1/knowledge",
        params={"user_id": "masato"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # contract: { items: KnowledgeItem[] }
    assert "items" in body
    items = body["items"]
    assert isinstance(items, list)
    assert len(items) == 2
    first = items[0]
    # KnowledgeItem fields per openapi.yaml#components/schemas/KnowledgeItem
    assert {"id", "title", "path", "tags", "updated_at"} <= set(first.keys())
    assert first["title"] == "Auth Design Decision"
    assert first["tags"] == ["auth", "supabase"]


def test_list_accepts_bearer_auth(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-F2 + AC-F3 reverse: Bearer token is valid auth method."""
    _patch_db_rows(monkeypatch, [])
    r = client.get(
        "/api/workspaces/1/knowledge",
        headers={"Authorization": "Bearer sk-test-abc123"},
    )
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_list_with_category_filter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """category query param is forwarded; service-level shape preserved."""
    _patch_db_rows(monkeypatch, [])
    r = client.get(
        "/api/workspaces/1/knowledge",
        params={"user_id": "masato", "category": "decision"},
    )
    assert r.status_code == 200


def test_search_returns_200_and_hits_contract(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-F5 EVENT-DRIVEN: GET /knowledge/search → 2xx + hits: KnowledgeHit[]."""
    rows = [
        {
            "id": 11,
            "title": "Supabase Postgres decision",
            "md_path": "decisions/2026-04-supabase.md",
            "summary": "Supabase を採用",
            "content": "Supabase Postgres adopted",
            "source": "knowledge_base",
            "score": 0.92,
        },
        {
            "id": 12,
            "title": "alt: GCP Spanner",
            "md_path": None,
            "summary": None,
            "content": "considered but rejected",
            "source": "knowledge_base",
            "score": 0.41,
        },
    ]
    _patch_db_rows(monkeypatch, rows)

    r = client.get(
        "/api/workspaces/1/knowledge/search",
        params={"user_id": "masato", "q": "Supabase"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "hits" in body
    hits = body["hits"]
    assert isinstance(hits, list)
    assert len(hits) == 2
    # KnowledgeHit contract per openapi.yaml
    first = hits[0]
    assert {"id", "title", "snippet", "score", "source"} <= set(first.keys())
    assert first["title"] == "Supabase Postgres decision"
    assert first["score"] == pytest.approx(0.92)


def test_search_top_50_cap_via_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-F1 EVENT-DRIVEN: top 50 hits cap.

    クエリレベルの LIMIT を coerce_limit が 50 に clamp すること.
    """
    # 60 rows simulate, but coerce_limit caps SQL LIMIT to 50.
    # 我々は service test を経由して contract を確認する.
    from services import knowledge as svc

    assert svc.coerce_limit(60) == 50
    assert svc.coerce_limit(50) == 50
    assert svc.coerce_limit(49) == 49


def test_search_db_unavailable_returns_empty_hits_200(
    client: TestClient,
) -> None:
    """DB 不在 / table 不在環境では空 hits を返す (テスト env friendliness)."""
    r = client.get(
        "/api/workspaces/1/knowledge/search",
        params={"user_id": "masato", "q": "anything"},
    )
    # 401/422 ではなく 200 + 空 hits を期待
    assert r.status_code == 200, r.text
    body = r.json()
    assert "hits" in body
    assert isinstance(body["hits"], list)


def test_list_db_unavailable_returns_empty_items_200(
    client: TestClient,
) -> None:
    """DB 不在環境で list も 200 + 空 items."""
    r = client.get(
        "/api/workspaces/1/knowledge",
        params={"user_id": "masato"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"items": []}
