"""T-V3-B-27 / F-024: GET /api/search tests.

EARS AC coverage (functional Tier):
  AC-F1 EVENT-DRIVEN  : non-empty q returns ranked hits — test_returns_ranked_hits
  AC-F2 UNWANTED      : q empty/too long -> 422 — test_empty_q / test_too_long_q
  AC-F3 UNWANTED      : > 60 req/min -> 429 — test_rate_limit_exceeded
  AC-F5 EVENT-DRIVEN  : 2xx shape matches openapi — test_response_shape
  AC-F6 UNWANTED      : missing token -> 401 — test_requires_auth
  AC-F7 UNWANTED      : invalid category -> 422 with field map — test_invalid_category
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    os.environ["DISABLE_BACKGROUND_WORKERS"] = "1"
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    # Supabase env stubs (auth_middleware imports verify_jwt at module load)
    os.environ.setdefault("SUPABASE_URL", "https://stub.supabase.co")
    os.environ.setdefault("SUPABASE_ANON_KEY", "stub-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "stub-service-key")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "stub-jwt-secret")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Each test starts with a fresh per-process limiter bucket."""
    from services import search as search_svc
    search_svc.get_rate_limiter().reset()
    yield
    search_svc.get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def _stub_fetchers(monkeypatch):
    """Stub source fetchers so tests don't depend on real DB rows."""
    from services import search as search_svc

    async def fake_tasks(q, *, workspace_ids, limit):
        # Return some hits whose score correlates with overlap so we can
        # assert ranking determinism.
        return [
            {
                "id": "1", "category": "tasks", "title": f"Task: {q} build",
                "snippet": "do something",
                "score": 0.9, "workspace_id": 1, "metadata": {"status": "todo"},
            },
            {
                "id": "2", "category": "tasks", "title": "unrelated",
                "snippet": "noise",
                "score": 0.1, "workspace_id": 1, "metadata": {},
            },
        ][:limit]

    async def fake_artifacts(q, *, workspace_ids, limit):
        return [{
            "id": "10", "category": "artifacts", "title": f"art-{q}",
            "snippet": "spec", "score": 0.5, "workspace_id": 1, "metadata": {},
        }][:limit]

    async def fake_knowledge(q, *, workspace_ids, limit):
        return [{
            "id": "100", "category": "knowledge", "title": f"kb-{q}",
            "snippet": "content", "score": 0.7, "workspace_id": 1, "metadata": {},
        }][:limit]

    async def fake_audit(q, *, workspace_ids, limit):
        return [{
            "id": "1000", "category": "audit", "title": f"audit.{q}",
            "snippet": "resource=task", "score": 0.3, "workspace_id": 1, "metadata": {},
        }][:limit]

    monkeypatch.setitem(search_svc._CATEGORY_FETCHERS, "tasks", fake_tasks)
    monkeypatch.setitem(search_svc._CATEGORY_FETCHERS, "artifacts", fake_artifacts)
    monkeypatch.setitem(search_svc._CATEGORY_FETCHERS, "knowledge", fake_knowledge)
    monkeypatch.setitem(search_svc._CATEGORY_FETCHERS, "audit", fake_audit)

    async def fake_ids(_user_id):
        return [1]
    monkeypatch.setattr(search_svc, "list_caller_workspace_ids", fake_ids)


# ─────────────────────────────────────────────────────────────────────
# Tier 1: service-level invariants
# ─────────────────────────────────────────────────────────────────────


def test_module_files_exist():
    """Tier 3 lint-style: declared files actually exist."""
    assert (REPO_ROOT / "backend" / "routers" / "search.py").exists()
    assert (REPO_ROOT / "backend" / "services" / "search.py").exists()
    assert (REPO_ROOT / "backend" / "schemas" / "search.py").exists()


def test_no_langchain_imports():
    """ADR-010/012 main path lint — search service must not import LangChain."""
    txt = (REPO_ROOT / "backend" / "services" / "search.py").read_text(encoding="utf-8")
    # Only check actual import statements, not prose mentions in docstrings.
    for forbidden in ("langgraph", "langchain", "litellm"):
        for line in txt.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(f"import {forbidden}"), line
            assert not stripped.startswith(f"from {forbidden}"), line


# ─────────────────────────────────────────────────────────────────────
# Tier 2: functional EARS AC
# ─────────────────────────────────────────────────────────────────────


def test_returns_ranked_hits(client):
    """AC-F1: hits returned, ordered by combined score DESC."""
    r = client.get("/api/search", params={"q": "build"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "hits" in body and len(body["hits"]) >= 1
    scores = [h["score"] for h in body["hits"]]
    assert scores == sorted(scores, reverse=True), f"unsorted: {scores}"


def test_response_shape(client):
    """AC-F5: openapi 2xx shape — hits + total + categories + query."""
    r = client.get("/api/search", params={"q": "spec"})
    assert r.status_code == 200
    body = r.json()
    for key in ("hits", "total", "categories", "query"):
        assert key in body, f"missing key: {key}"
    cats = body["categories"]
    assert set(cats.keys()) >= {"tasks", "artifacts", "knowledge", "audit"}
    assert isinstance(body["total"], int)
    assert body["total"] == len(body["hits"])


def test_empty_q_returns_422(client):
    """AC-F2 UNWANTED: empty q -> 422 + field-level error map."""
    r = client.get("/api/search", params={"q": "   "})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    # FastAPI built-in validation may fire first if Query has min_length;
    # we declared Query(...) without min_length so service-level catches it.
    assert "errors" in detail or "msg" in str(detail).lower()


def test_too_long_q_returns_422(client):
    """AC-F2 UNWANTED: q > 500 chars -> 422."""
    r = client.get("/api/search", params={"q": "x" * 501})
    assert r.status_code == 422, r.text


def test_invalid_category_returns_422(client):
    """AC-F7: invalid category -> 422 with field map."""
    r = client.get("/api/search", params={"q": "x", "category": "bogus"})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "errors" in detail and "category" in detail["errors"]


def test_category_filter_narrows_result(client):
    """AC-F1 / AC-F5: category=tasks limits hits to tasks only."""
    r = client.get("/api/search", params={"q": "build", "category": "tasks"})
    assert r.status_code == 200, r.text
    body = r.json()
    cats = {h["category"] for h in body["hits"]}
    assert cats == {"tasks"}, cats
    assert body["categories"]["artifacts"] == 0


def test_limit_caps_results(client):
    """AC-F5: limit caps the number of hits returned."""
    r = client.get("/api/search", params={"q": "build", "limit": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["hits"]) <= 2


def test_rate_limit_exceeded_returns_429(client):
    """AC-F3 UNWANTED: > 60 req/min -> 429 with Retry-After header."""
    from services import search as search_svc
    # Force the limiter to register 60 hits for the dev user, then assert
    # the 61st request is rejected with 429.
    limiter = search_svc.get_rate_limiter()
    for _ in range(search_svc.RATE_LIMIT_MAX_REQUESTS):
        try:
            limiter.check("00000000-0000-0000-0000-000000000001")
        except search_svc.RateLimitExceeded:
            pytest.fail("limiter should not refuse before max_requests")
    r = client.get("/api/search", params={"q": "build"})
    assert r.status_code == 429, r.text
    assert "Retry-After" in r.headers
    body = r.json()
    assert body["detail"]["code"] == "rate_limit_exceeded"


def test_requires_auth_when_bypass_off(client, monkeypatch):
    """AC-F6 UNWANTED: when DEV_BYPASS is off and no token, require_user -> 401.

    We patch the module-level ``DEV_BYPASS`` flag rather than re-instantiating
    the FastAPI app (which would re-run the lifespan and hit Postgres).
    """
    from services import auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/search", params={"q": "anything"})
    assert r.status_code == 401, r.text


def test_query_echoed_back_normalised(client):
    """AC-F5: response.query is the normalised (stripped) query."""
    r = client.get("/api/search", params={"q": "  hello  "})
    assert r.status_code == 200
    assert r.json()["query"] == "hello"


def test_score_in_valid_range(client):
    """AC-F1: every hit.score is in [0.0, 1.0]."""
    r = client.get("/api/search", params={"q": "spec"})
    assert r.status_code == 200
    for h in r.json()["hits"]:
        assert 0.0 <= h["score"] <= 1.0, h
