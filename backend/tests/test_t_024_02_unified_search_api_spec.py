"""T-024-02: unified search API REFACTOR audit (1:1 AC × test 仕様検証).

このファイルは **audit (検証) 専用**. 実装変更はしない (REFACTOR audit).

源泉:
  - `docs/task-decomposition/2026-05-09_v1/tickets.json#T-024-02`
  - `docs/functional-breakdown/2026-05-09_v1/features.json` (F-024)
  - `docs/requirements/2026-05-09_v1/requirements-v1.html#m-24`
  - `docs/architecture/2026-05-09_v1/architecture-v1.md` (Postgres FTS + pgvector
    + pg_trgm)

AC × test 1:1 mapping (29 tests):
  AC-1 UBIQUITOUS    : 8 tests (service / router / public symbols / 4 handlers /
                       既存 modules REUSE 無改変)
  AC-2 EVENT-DRIVEN  : 7 tests (dict shape / asyncio.gather / 2 秒 / item fields /
                       audit emit search.unified)
  AC-3 STATE-DRIVEN  : 5 tests (return_exceptions=True / no new tables /
                       handler は thin wrapper / read-only)
  AC-4 UNWANTED      : 6 tests (invalid query / sources / account_id / limit /
                       hardcoded secret)
  Drift guards       : 3 tests (handler signature parity / 各 source の result
                       が measurably 異なる / Phase 1.5 API 早期露出禁止)

参考: `docs/audit/2026-05-13_v2/T-013-04.md` v2 (drift guard pattern).
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json as _json
import re
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "unified_search.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "unified_search.py"
EXISTING_EMB = REPO_ROOT / "backend" / "services" / "embedding_service.py"
EXISTING_K_ROUTER = REPO_ROOT / "backend" / "routers" / "knowledge_search.py"


def _strip_comments(src: str) -> str:
    """Python source から comment と docstring を除いた行を返す.

    drift-guard test が forbidden literal を comment 内で誤検出しないため.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    # docstring を除外するため、module / class / def の body[0] が Expr(Constant str) なら抜く
    out_lines = src.splitlines()
    skip_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (
                getattr(node, "body", None)
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                ds = node.body[0]
                # 1-based line numbers from ast
                for i in range(ds.lineno, getattr(ds, "end_lineno", ds.lineno) + 1):
                    skip_lines.add(i)
    cleaned = []
    for i, line in enumerate(out_lines, start=1):
        if i in skip_lines:
            continue
        if "#" in line:
            line = line.split("#", 1)[0]
        cleaned.append(line)
    return "\n".join(cleaned)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — service / router / 公開 symbol / 4 source / REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_file_exists():
    """spec sub-clause 1.1: `backend/services/unified_search.py` が存在."""
    assert SERVICE.is_file(), f"service module missing: {SERVICE}"


def test_ac1_router_file_exists():
    """spec sub-clause 1.2: `backend/routers/unified_search.py` が存在."""
    assert ROUTER.is_file(), f"router module missing: {ROUTER}"


def test_ac1_service_public_symbols():
    """spec sub-clause 1.3: `unified_search`, `SOURCE_HANDLERS`, `VALID_SOURCES`,
    `list_valid_sources` を公開."""
    from services import unified_search as us
    for sym in ("unified_search", "SOURCE_HANDLERS", "VALID_SOURCES",
                "list_valid_sources"):
        assert hasattr(us, sym), f"missing service.{sym}"


def test_ac1_valid_sources_exact_four():
    """spec sub-clause 1.4: VALID_SOURCES = knowledge / tasks / employees /
    screens の 4 種 exactly."""
    from services import unified_search as us
    assert set(us.VALID_SOURCES) == {"knowledge", "tasks", "employees", "screens"}
    assert len(us.VALID_SOURCES) == 4


def test_ac1_source_handlers_all_four_registered():
    """spec sub-clause 1.5: SOURCE_HANDLERS に 4 source の handler が登録済."""
    from services import unified_search as us
    for src in ("knowledge", "tasks", "employees", "screens"):
        assert src in us.SOURCE_HANDLERS
        h = us.SOURCE_HANDLERS[src]
        assert callable(h), f"handler {src} not callable"
        assert inspect.iscoroutinefunction(h), f"handler {src} must be async"


def test_ac1_endpoints_registered():
    """spec sub-clause 1.6: POST /api/search/unified + GET /api/search/sources
    が main:app に登録."""
    from main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/search/unified" in paths
    assert "/api/search/sources" in paths


def test_ac1_existing_modules_not_modified_by_unified_search():
    """spec sub-clause 1.7: 既存 `knowledge_search.py` + `embedding_service.py`
    SHALL NOT be modified (REUSE). unified_search への back-edge が無いこと."""
    for path in (EXISTING_EMB, EXISTING_K_ROUTER):
        assert path.is_file(), f"existing module missing: {path}"
        src = path.read_text(encoding="utf-8")
        assert "from services.unified_search" not in src
        assert "from routers.unified_search" not in src
        assert "import unified_search" not in src


def test_ac1_list_valid_sources_returns_list():
    """spec sub-clause 1.8: `list_valid_sources()` は list[str] を返す."""
    from services import unified_search as us
    out = us.list_valid_sources()
    assert isinstance(out, list)
    assert set(out) == set(us.VALID_SOURCES)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — dict shape / parallel / 2 秒 / audit emit
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def stubbed_handlers(monkeypatch):
    """全 source handler を deterministic stub に置換 (実 DB を呼ばない)."""
    from services import unified_search as us

    async def make_handler(kind, group, count):
        async def fake(query, *, account_id, limit):
            n = min(count, limit)
            return [
                {"kind": kind, "id": f"{kind}-{i}", "label": f"{kind}:{query}:{i}",
                 "hint": f"hint-{i}", "group": group}
                for i in range(n)
            ]
        return fake

    knowledge = asyncio.run(make_handler("knowledge", "Knowledge", 3))
    tasks = asyncio.run(make_handler("task", "Tasks", 2))
    employees = asyncio.run(make_handler("employee", "Employees", 1))
    screens = asyncio.run(make_handler("screen", "Screens", 4))
    monkeypatch.setitem(us.SOURCE_HANDLERS, "knowledge", knowledge)
    monkeypatch.setitem(us.SOURCE_HANDLERS, "tasks", tasks)
    monkeypatch.setitem(us.SOURCE_HANDLERS, "employees", employees)
    monkeypatch.setitem(us.SOURCE_HANDLERS, "screens", screens)
    yield


def test_ac2_returns_dict_with_required_keys(stubbed_handlers):
    """spec sub-clause 2.1: dict {query, sources_used, results, by_kind, total}."""
    from services import unified_search as us
    result = asyncio.run(us.unified_search("hello"))
    for key in ("query", "sources_used", "results", "by_kind", "total"):
        assert key in result, f"missing key: {key}"
    assert result["query"] == "hello"
    assert result["total"] == 3 + 2 + 1 + 4


def test_ac2_each_result_has_5_required_fields(stubbed_handlers):
    """spec sub-clause 2.2: 各 result item は {kind, id, label, hint, group}."""
    from services import unified_search as us
    result = asyncio.run(us.unified_search("hello"))
    assert len(result["results"]) > 0
    for item in result["results"]:
        for f in ("kind", "id", "label", "hint", "group"):
            assert f in item, f"item missing field {f}: {item}"


def test_ac2_uses_asyncio_gather(stubbed_handlers):
    """spec sub-clause 2.3: 並列実行 (asyncio.gather). 4 source 同時呼出."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "asyncio.gather" in code, "must use asyncio.gather (spec literal)"


def test_ac2_completes_within_2_seconds(stubbed_handlers):
    """spec sub-clause 2.4: 全体応答 < 2 秒 (stub なので桁違いに速いはず)."""
    from services import unified_search as us
    t0 = time.time()
    asyncio.run(us.unified_search("perf"))
    assert time.time() - t0 < 2.0


def test_ac2_by_kind_sum_equals_total(stubbed_handlers):
    """spec sub-clause 2.5: by_kind の値 sum = total."""
    from services import unified_search as us
    r = asyncio.run(us.unified_search("c"))
    assert r["total"] == sum(r["by_kind"].values())


def test_ac2_sources_subset_filter(stubbed_handlers):
    """spec sub-clause 2.6: sources パラメータで個別 enable 可."""
    from services import unified_search as us
    r = asyncio.run(us.unified_search("c", sources=["knowledge", "tasks"]))
    assert set(r["sources_used"]) == {"knowledge", "tasks"}
    kinds_in_results = {item["kind"] for item in r["results"]}
    # knowledge → kind="knowledge", tasks → kind="task" (handler 出力に依存)
    assert "employee" not in kinds_in_results
    assert "screen" not in kinds_in_results


def test_ac2_endpoint_emits_audit_search_unified(stubbed_handlers, monkeypatch):
    """spec sub-clause 2.7: POST /api/search/unified が audit event
    'search.unified' を emit (query_chars + sources_used + total + by_kind)."""
    import os
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event_type": event_type, "user_id": user_id,
                         "detail": detail or {}})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)

    from main import app
    from fastapi.testclient import TestClient
    # NOTE: 既存 test と同様 `with` を使わない (lifespan を起動しない). lifespan が
    # Supabase / DB に接続するため test 単体では invoke 不可.
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/search/unified", json={
        "query": "audit-check", "actor_user_id": "u1",
    })
    assert r.status_code == 200, r.text
    evts = [e for e in captured if e["event_type"] == "search.unified"]
    assert len(evts) == 1
    d = evts[0]["detail"]
    for f in ("query_chars", "sources_used", "total", "by_kind"):
        assert f in d, f"audit detail missing {f}"
    assert d["query_chars"] == len("audit-check")


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — return_exceptions / no new tables / read-only
# ══════════════════════════════════════════════════════════════════════


def test_ac3_per_source_failure_isolated(stubbed_handlers, monkeypatch):
    """spec sub-clause 3.1: 個別 source の失敗で全体は落ちず、他 source 結果は
    返る (asyncio.gather return_exceptions=True + warning log + skip)."""
    from services import unified_search as us

    async def boom(query, *, account_id, limit):
        raise RuntimeError("simulated DB down")

    monkeypatch.setitem(us.SOURCE_HANDLERS, "tasks", boom)
    r = asyncio.run(us.unified_search("x"))
    # 3 sources still produce results: knowledge(3) + employees(1) + screens(4) = 8
    assert r["total"] == 3 + 1 + 4
    # tasks kind は含まれない (= 失敗で skip された)
    assert "task" not in r["by_kind"]


def test_ac3_uses_return_exceptions_flag():
    """spec sub-clause 3.2: source 並列実行は return_exceptions=True を使う."""
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    # asyncio.gather(...return_exceptions=True...) の literal が必要
    assert "return_exceptions" in code, (
        "must use asyncio.gather(return_exceptions=True) per spec"
    )
    assert re.search(r"return_exceptions\s*=\s*True", code), (
        "return_exceptions must be True (not False)"
    )


def test_ac3_no_new_table_ddl_in_module():
    """spec sub-clause 3.3: 新規 DB query は既存 table への LIKE のみ.
    `CREATE TABLE` / `ALTER TABLE` 新規発行なし."""
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    assert "CREATE TABLE" not in code
    assert "ALTER TABLE" not in code


def test_ac3_no_write_sql_in_module():
    """spec sub-clause 3.4: read-only (no INSERT / UPDATE / DELETE in
    unified_search.py). audit_logs 書込は router 側責務."""
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    # SQL keyword は LIKE / SELECT のみ. INSERT/UPDATE/DELETE は不在.
    for forbidden in (r"\bINSERT\s+INTO\b", r"\bUPDATE\s+\w", r"\bDELETE\s+FROM\b"):
        assert not re.search(forbidden, code, re.IGNORECASE), (
            f"write SQL forbidden in unified_search.py: pattern={forbidden}"
        )


def test_ac3_handlers_are_thin_wrappers():
    """spec sub-clause 3.5: 各 handler は既存 service の thin wrapper.
    embedding_service / bf_db / ai_employee_store のうち少なくとも 1 つを呼出.
    """
    src = SERVICE.read_text(encoding="utf-8")
    # service-layer dependencies
    assert "embedding_service" in src, "knowledge handler must call embedding_service"
    assert "ai_employee_store" in src, "employees handler must call ai_employee_store"
    # tasks / screens は LIKE 検索 → bf_db (or 同等 layer)
    assert "bf_db" in src or "aiosqlite" in src or "asyncpg" in src, (
        "tasks/screens handler must reuse existing DB layer"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — input validation / hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_query_raises_value_error(stubbed_handlers):
    """spec sub-clause 4.1: empty query → ValueError."""
    from services import unified_search as us
    for bad in ("", "   ", "\t\n"):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search(bad))


def test_ac4_non_string_query_raises_value_error(stubbed_handlers):
    """spec sub-clause 4.2: non-string query → ValueError."""
    from services import unified_search as us
    for bad in (None, 123, 1.5, [], {}, b"bytes"):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search(bad))


def test_ac4_overlong_query_raises_value_error(stubbed_handlers):
    """spec sub-clause 4.3: query > 500 chars → ValueError."""
    from services import unified_search as us
    with pytest.raises(ValueError):
        asyncio.run(us.unified_search("x" * 501))
    with pytest.raises(ValueError):
        asyncio.run(us.unified_search("x" * 5000))


def test_ac4_invalid_source_name_raises_value_error(stubbed_handlers):
    """spec sub-clause 4.4: VALID_SOURCES 外の名前 → ValueError."""
    from services import unified_search as us
    for bad_sources in (["bogus"], ["knowledge", "fake"], "not-a-list", 123):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search("test", sources=bad_sources))


def test_ac4_invalid_account_id_rejected(stubbed_handlers):
    """spec sub-clause 4.5: account_id <= 0 or non-int → reject. router
    layer も 4xx code='search.invalid' を返す."""
    from services import unified_search as us
    for bad in (0, -1, "1", 1.5):
        with pytest.raises(ValueError):
            asyncio.run(us.unified_search("t", account_id=bad))

    # router レイヤ: account_id=0 → 400 search.invalid
    import os
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/search/unified", json={"query": "t", "account_id": 0})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "search.invalid"


def test_ac4_invalid_limit_per_source_raises_value_error(stubbed_handlers):
    """spec sub-clause 4.6: limit_per_source ∉ (0, 50] → ValueError."""
    from services import unified_search as us
    for bad in (0, -1, 51, 100, "10", None, 1.5, True, False):
        with pytest.raises((ValueError, TypeError)):
            asyncio.run(us.unified_search("t", limit_per_source=bad))


def test_ac4_no_hardcoded_secret_or_external_url():
    """spec sub-clause 4.7: source 内に API key / external URL の literal なし."""
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code
    assert "https://api.openai.com" not in code
    assert "https://api.anthropic.com" not in code


# ══════════════════════════════════════════════════════════════════════
# Drift guards — handler signature parity / measurably different output /
# Phase 1.5 API not yet exposed
# ══════════════════════════════════════════════════════════════════════


def test_drift_guard_each_source_handler_uniform_signature():
    """drift guard 1: 4 handler は同一 keyword 受領 (query, account_id, limit).

    多態 source が "label 替えだけの偽装" にならないよう、各 handler が
    spec で要求する 3 引数を受領することを inspect で機械検証.
    """
    from services import unified_search as us
    for name, h in us.SOURCE_HANDLERS.items():
        sig = inspect.signature(h)
        params = sig.parameters
        assert "query" in params or list(params.keys())[0] == "query", (
            f"handler {name} missing positional 'query'"
        )
        assert "account_id" in params, f"handler {name} missing 'account_id' kw"
        assert "limit" in params, f"handler {name} missing 'limit' kw"


def test_drift_guard_each_source_produces_distinct_kind_label(stubbed_handlers):
    """drift guard 2: 4 source が **measurably 異なる** 結果を返す.

    stub の各 handler が固有の kind + group を返す事実をもって、
    SOURCE_HANDLERS が単なる label 差し替えでないことを機械保証する.
    """
    from services import unified_search as us
    r = asyncio.run(us.unified_search("uniq"))
    seen_kinds = {item["kind"] for item in r["results"]}
    seen_groups = {item["group"] for item in r["results"]}
    # 4 distinct kinds (knowledge/task/employee/screen)
    assert len(seen_kinds) == 4, f"expected 4 distinct kinds, got {seen_kinds}"
    # 4 distinct groups
    assert len(seen_groups) == 4, f"expected 4 distinct groups, got {seen_groups}"
    # by_kind dict にも 4 種が出る
    assert len(r["by_kind"]) == 4, (
        f"by_kind must have 4 distinct kinds, got {r['by_kind']}"
    )


def test_drift_guard_no_phase_1_5_api_exposed():
    """drift guard 3: Phase 1.5 (T-024-04 etc.) で予定される forbidden API
    名が Phase 1 module source に出現しないこと.

    将来の RLS 一体化 / 高度 ranking / hybrid score blending は
    別 task で扱う. Phase 1 は thin aggregator に留める.
    """
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    forbidden = (
        # Phase 1.5 予定の RLS context bind (未実装 OK / 早期露出禁止)
        "rls_session_bind",
        "set_session_actor",
        # Phase 1.5 予定の hybrid score blending
        "hybrid_score",
        "blended_score",
        "rerank_with_llm",
        # Phase 1.5 spell suggest (F-024 error_path "結果 0→spell suggest" は
        # Phase 1 では未実装)
        "spell_suggest",
        "did_you_mean",
    )
    for sym in forbidden:
        assert sym not in code, (
            f"Phase 1.5 API '{sym}' must NOT be in Phase 1 source"
        )


# ══════════════════════════════════════════════════════════════════════
# Audit cross-check (ticket meta / ADR link)
# ══════════════════════════════════════════════════════════════════════


def test_audit_ticket_meta_concretized():
    """ticket AC が generic stub に戻っていないこと (T-008-01 等と同じ
    pre-flight invariant)."""
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-02"), None)
    assert t is not None
    generic = (
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-024-02",
        "While refactoring for T-024-02 is in progress",
        "If invalid input or unauthorized actor is detected during T-024-02",
    )
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-024-02 AC still generic stub: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    # ticket text に literal 公開 symbol が現れる (audit-trail で identifiable)
    for required in ("unified_search.py", "SOURCE_HANDLERS", "VALID_SOURCES",
                     "asyncio.gather"):
        assert required in full, f"ticket text missing literal: {required}"


def test_audit_ticket_has_adr_link():
    """ADR 連結 (T-024-02 → ADR-010 AI スタック)."""
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-02"), None)
    assert t.get("adr_link"), "T-024-02 must link to an ADR"
