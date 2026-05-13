"""T-024-02: unified search API (existing knowledge_search/embedding_service REFACTOR).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : service / router / SOURCE_HANDLERS 4 種 / 既存
                       knowledge_search + embedding_service 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : unified_search が dict 返却 / asyncio.gather 並列 / 2 秒以内 /
                       audit emit (search.unified).
  AC-3 STATE-DRIVEN  : 個別 source 失敗で全体落ちない (return_exceptions) /
                       新規 DB query なし (既存 service 経由 + LIKE) / read-only.
  AC-4 UNWANTED      : invalid query / sources / account_id / limit で ValueError /
                       hardcoded secret なし.
"""
from __future__ import annotations

import asyncio
import json as _json
import os
import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "unified_search.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "unified_search.py"
EXISTING_EMB = REPO_ROOT / "backend" / "services" / "embedding_service.py"
EXISTING_K_SEARCH = REPO_ROOT / "backend" / "routers" / "knowledge_search.py"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _stub_sources(monkeypatch):
    """全 source handler を stub. 実 DB を呼ばない."""
    from services import unified_search as us

    async def fake_knowledge(query, *, account_id, limit):
        return [{"kind": "knowledge", "id": "k1", "label": f"K:{query}",
                 "hint": "public", "group": "Knowledge"}][:limit]

    async def fake_tasks(query, *, account_id, limit):
        return [{"kind": "task", "id": "t1", "label": f"T:{query}",
                 "hint": "pending", "group": "Tasks"}][:limit]

    async def fake_employees(query, *, account_id, limit):
        return [{"kind": "employee", "id": "e1", "label": f"E:{query}",
                 "hint": "member", "group": "Employees"}][:limit]

    async def fake_screens(query, *, account_id, limit):
        return [{"kind": "screen", "id": "s1", "label": f"S:{query}",
                 "hint": "web", "group": "Screens"}][:limit]

    monkeypatch.setitem(us.SOURCE_HANDLERS, "knowledge", fake_knowledge)
    monkeypatch.setitem(us.SOURCE_HANDLERS, "tasks", fake_tasks)
    monkeypatch.setitem(us.SOURCE_HANDLERS, "employees", fake_employees)
    monkeypatch.setitem(us.SOURCE_HANDLERS, "screens", fake_screens)
    yield


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event_type": event_type, "user_id": user_id,
                         "detail": detail or {}})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_service_public_api():
    from services import unified_search as us
    for sym in (
        "unified_search", "list_valid_sources",
        "SOURCE_HANDLERS", "VALID_SOURCES",
        "MAX_QUERY_CHARS", "DEFAULT_LIMIT_PER_SOURCE", "MAX_LIMIT_PER_SOURCE",
    ):
        assert hasattr(us, sym), f"missing service.{sym}"


def test_ac1_endpoints_registered():
    from main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/api/search/unified" in paths
    assert "/api/search/sources" in paths


def test_ac1_source_handlers_4_sources():
    from services import unified_search as us
    for src in ("knowledge", "tasks", "employees", "screens"):
        assert src in us.SOURCE_HANDLERS


def test_ac1_existing_modules_unchanged():
    """knowledge_search / embedding_service に unified_search 依存なし (REUSE)."""
    assert EXISTING_EMB.exists()
    assert EXISTING_K_SEARCH.exists()
    for path in (EXISTING_EMB, EXISTING_K_SEARCH):
        src = path.read_text(encoding="utf-8")
        assert "from services.unified_search" not in src
        assert "from routers.unified_search" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: dict / parallel / audit emit / 2 秒以内
# ══════════════════════════════════════════════════════════════════════


def test_ac2_unified_search_returns_structured_dict():
    from services import unified_search as us
    result = asyncio.run(us.unified_search("test query"))
    for key in ("query", "sources_used", "results", "by_kind", "total"):
        assert key in result
    assert result["total"] >= 0


def test_ac2_all_4_sources_used_by_default():
    from services import unified_search as us
    result = asyncio.run(us.unified_search("test"))
    assert len(result["sources_used"]) == 4
    for src in ("knowledge", "tasks", "employees", "screens"):
        assert src in result["sources_used"]


def test_ac2_specific_sources_filter():
    from services import unified_search as us
    result = asyncio.run(us.unified_search("test", sources=["knowledge", "tasks"]))
    assert len(result["sources_used"]) == 2
    assert "knowledge" in result["sources_used"]
    assert "tasks" in result["sources_used"]


def test_ac2_results_have_required_fields():
    from services import unified_search as us
    result = asyncio.run(us.unified_search("test"))
    for item in result["results"]:
        for key in ("kind", "id", "label", "hint", "group"):
            assert key in item


def test_ac2_by_kind_counts():
    from services import unified_search as us
    result = asyncio.run(us.unified_search("test"))
    assert isinstance(result["by_kind"], dict)
    assert result["total"] == sum(result["by_kind"].values())


def test_ac2_within_2_seconds():
    from services import unified_search as us
    t0 = time.time()
    asyncio.run(us.unified_search("test"))
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_endpoint_emits_audit(client, _capture_audit):
    r = client.post("/api/search/unified", json={
        "query": "test query",
        "actor_user_id": "alice",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "search.unified"]
    assert len(events) == 1
    assert events[0]["detail"]["query_chars"] == len("test query")


def test_ac2_endpoint_sources(client):
    r = client.get("/api/search/sources")
    assert r.status_code == 200
    body = r.json()
    assert len(body["valid_sources"]) == 4


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: per-source failure isolation + REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac3_source_failure_does_not_crash(monkeypatch):
    """1 つの source が raise しても他の source は動く."""
    from services import unified_search as us

    async def failing(query, *, account_id, limit):
        raise RuntimeError("DB down")

    monkeypatch.setitem(us.SOURCE_HANDLERS, "tasks", failing)
    # 他 3 source は stub のまま
    result = asyncio.run(us.unified_search("test"))
    # 全体は成功
    assert "results" in result
    # tasks 失敗で 1 source 分なし (= 3 results)
    assert result["total"] == 3


def test_ac3_module_does_not_make_new_db_queries():
    """新規 DB query は LIKE in 既存 table のみ (新 table 作成なし)."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    # 新 table 作成 SQL なし
    assert "CREATE TABLE" not in code
    assert "ALTER TABLE" not in code


def test_ac3_module_does_not_write_audit_logs():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "emit_event" not in code
    assert "from services.memory_service" not in code
    # audit emit は router layer の責務


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_query_raises():
    from services import unified_search as us
    for bad in ("", "   ", None, 123, "x" * 600):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search(bad))


def test_ac4_invalid_sources_raises():
    from services import unified_search as us
    for bad in (["BOGUS"], ["knowledge", "FAKE"], "not_a_list", 123):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search("test", sources=bad))


def test_ac4_invalid_account_id_raises():
    from services import unified_search as us
    for bad in (0, -1, "1", 1.5):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search("test", account_id=bad))


def test_ac4_invalid_limit_raises():
    from services import unified_search as us
    for bad in (0, -1, 51, 100, "10", None):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search("test", limit_per_source=bad))


def test_ac4_endpoint_invalid_account_id_400(client):
    r = client.post("/api/search/unified", json={
        "query": "test", "account_id": 0,
    })
    assert r.status_code == 400


def test_ac4_endpoint_unauthorized_401(client):
    r = client.post("/api/search/unified", json={
        "query": "test", "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "search.unauthorized"


def test_ac4_no_hardcoded_secrets():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code


def test_ac4_no_hardcoded_external_urls():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "api.openai.com" not in code
    assert "api.anthropic.com" not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_024_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-02"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-024-02",
        "While refactoring for T-024-02 is in progress",
        "If invalid input or unauthorized actor is detected during T-024-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-024-02 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "unified_search.py" in full
    assert "SOURCE_HANDLERS" in full
    assert "asyncio.gather" in full


def test_tickets_t_024_02_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-02"), None)
    assert t.get("adr_link") is not None
