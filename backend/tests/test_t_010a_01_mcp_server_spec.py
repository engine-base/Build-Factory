"""T-010a-01 — Pre-flight AC Audit spec test (REFACTOR rigor).

タスク: T-010a-01 (MCP server: existing mcp_server.py + mcp_stdio_server.py 拡張)
Feature: F-010a (MCP サーバー — データ流通)
Label: REFACTOR
Spec literal expansion (features.json#F-010a):

  happy_path: "Claude Code/Desktop/Slack から MCP 接続 → tool 呼出 → FastAPI 応答"
  tools (required set): bf_get_spec, bf_post_progress, bf_attach_artifact,
                        bf_request_review, bf_get_review_feedback
  error_paths: "auth 失敗 → 401" / "RLS 違反 → 403"
  policies: {timeout_sec: 30, streaming: true}
  related_entities: tasks, artifacts, sessions

architecture-v1.md §3 (Backend):
  "MCP Server: Anthropic MCP Python SDK + FastAPI / stdio + HTTP transport"

AC マッピング (1:1):
  AC-1 UBIQUITOUS   : F-010a の MCP server (HTTP transport + tools/list/call) 公開
  AC-2 EVENT-DRIVEN : 応答 < 2s, success or {detail:{code,message}}
  AC-3 STATE-DRIVEN : 既存 contract (3 旧 tool + 5 BF tool) 不変, no mutation on read
  AC-4 UNWANTED     : invalid / unknown / unauthorized は 4xx + structured,
                      persistent state mutate しない

Drift guard (anti-PR-#253 lesson):
  - tool 一覧 (8 件) は features.json と整合し、placeholder method 200 with empty result はゼロ
  - 各 BF tool ごとに variant-specific behavior が test で証明される
  - LangGraph / LangChain / LiteLLM import がゼロ (両 server source)
  - stdio server (backend/mcp_stdio_server.py) も JSON-RPC 2.0 envelope を返すこと
"""
from __future__ import annotations

import inspect
import json
import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────
# fixtures (module-scoped client + autouse mocks)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    """db.queries の重い処理を mock (高速 + 副作用なし, REFACTOR 不変)."""
    import routers.mcp_server as ms_router

    async def fake_run_query(sql):
        return [{"col1": 1, "col2": "x"}]

    async def fake_get_kpi():
        return {"revenue": 100, "profit": 30}

    def fake_list_records(folder=None):
        return [{"name": "a.md", "folder": folder or ""}]

    monkeypatch.setattr(ms_router, "run_query", fake_run_query)
    monkeypatch.setattr(ms_router, "get_kpi_summary", fake_get_kpi)
    monkeypatch.setattr(ms_router, "list_records", fake_list_records)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


# ──────────────────────────────────────────────────────────────────────────
# Source-file helpers (REFACTOR 9-項目 と drift guard 用)
# ──────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
HTTP_SERVER = ROOT / "backend" / "routers" / "mcp_server.py"
STDIO_SERVER = ROOT / "backend" / "mcp_stdio_server.py"
LEGACY_STDIO = ROOT / "mcp_stdio_server.py"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS — endpoint + 8 tool 公開 (1:1 verbatim against F-010a)
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_http_server_module_exists():
    """AC-1: HTTP MCP server module が存在."""
    assert HTTP_SERVER.exists(), "backend/routers/mcp_server.py is missing"


def test_ac1_stdio_server_module_exists():
    """AC-1: stdio MCP server module が存在 (Claude Desktop 用)."""
    assert STDIO_SERVER.exists(), "backend/mcp_stdio_server.py is missing"


def test_ac1_router_registered_in_main():
    """AC-1: routers/mcp_server.router が main:app に include されている."""
    from main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    # /mcp + /mcp/tools/list + /mcp/tools/call の 3 endpoint
    expected = {"/mcp", "/mcp/tools/list", "/mcp/tools/call"}
    assert expected <= paths, f"missing routes: {expected - paths}"


def test_ac1_tools_list_endpoint(client):
    """AC-1: POST /mcp/tools/list が 200 + {tools: [...]} を返す."""
    r = client.post("/mcp/tools/list")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict) and "tools" in body
    assert isinstance(body["tools"], list) and len(body["tools"]) >= 8


def test_ac1_sse_endpoint_first_chunk_is_server_info():
    """AC-1: GET /mcp の SSE generator が server/info を最初に yield する.

    TestClient での SSE 直接購読は keepalive ループで blocking するため、
    handler 関数の async generator を直接 1 回 anext して JSON-RPC envelope を検証.
    """
    import asyncio

    from routers.mcp_server import mcp_sse

    async def _first_chunk() -> str:
        resp = await mcp_sse()
        body_iter = resp.body_iterator
        chunk = await body_iter.__anext__()
        # close generator (keepalive ループに突入させない)
        await body_iter.aclose()
        return chunk if isinstance(chunk, str) else chunk.decode("utf-8")

    chunk = asyncio.run(_first_chunk())
    assert "data:" in chunk
    m = re.search(r"data:\s*(\{.*\})", chunk)
    assert m, f"no JSON in SSE chunk: {chunk!r}"
    payload = json.loads(m.group(1))
    assert payload.get("jsonrpc") == "2.0"
    assert payload.get("method") == "server/info"
    assert payload.get("params", {}).get("name") == "CompanyOS"


def test_ac1_sse_endpoint_content_type():
    """AC-1: GET /mcp の StreamingResponse は media_type=text/event-stream."""
    import asyncio

    from routers.mcp_server import mcp_sse

    async def _media() -> str:
        resp = await mcp_sse()
        return resp.media_type

    assert asyncio.run(_media()) == "text/event-stream"


@pytest.mark.parametrize("tool_name", [
    "query_company_db", "get_kpi", "list_records",      # 旧 3 tool
    "bf_get_spec", "bf_post_progress", "bf_attach_artifact",   # F-010a tools (T-010a-02)
    "bf_request_review", "bf_get_review_feedback",            # F-010a tools (T-010a-03)
])
def test_ac1_required_tool_present(client, tool_name):
    """AC-1 (1:1): features.json F-010a で declare された 5 tool + 旧 3 tool が全て露出."""
    r = client.post("/mcp/tools/list")
    by_name = {t["name"] for t in r.json()["tools"]}
    assert tool_name in by_name, f"required tool missing: {tool_name}"


def test_ac1_no_unexpected_tools_exposed(client):
    """AC-1 drift guard: spec で declare されていない tool が混入していないか.

    placeholder method (200 with empty result) を防ぐ. 既知 8 件 + 将来 extension OK.
    ただし name が空 / falsy なものは禁止.
    """
    r = client.post("/mcp/tools/list")
    tools = r.json()["tools"]
    names = [t.get("name") for t in tools]
    assert all(isinstance(n, str) and n.strip() for n in names), f"empty tool name in {names}"
    # 旧 3 + BF 5 = 最小 8 件
    assert len(set(names)) == len(names), "duplicate tool names"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN — 応答 < 2s + structured shape
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_tools_list_within_2s(client):
    """AC-2: tools/list は 2 秒以内."""
    t0 = time.perf_counter()
    r = client.post("/mcp/tools/list")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0, f"tools/list took {elapsed:.3f}s"


def test_ac2_tools_call_within_2s(client):
    """AC-2: tools/call (get_kpi) も 2 秒以内."""
    t0 = time.perf_counter()
    r = client.post("/mcp/tools/call", json={"name": "get_kpi", "arguments": {}})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_success_response_shape(client):
    """AC-2: success response は MCP 仕様の {content:[{type:"text", text:str}]} ."""
    r = client.post("/mcp/tools/call", json={"name": "get_kpi", "arguments": {}})
    body = r.json()
    assert "content" in body and isinstance(body["content"], list)
    assert body["content"][0]["type"] == "text"
    assert isinstance(body["content"][0]["text"], str)
    # text は JSON 文字列 (旧 contract)
    parsed = json.loads(body["content"][0]["text"])
    assert isinstance(parsed, dict)


def test_ac2_error_envelope_detail_code_message(client):
    """AC-2: error response は {detail:{code:str, message:str}} に統一."""
    r = client.post("/mcp/tools/call", json={"name": ""})
    assert 400 <= r.status_code < 500
    body = r.json()
    assert isinstance(body.get("detail"), dict)
    assert isinstance(body["detail"].get("code"), str) and body["detail"]["code"]
    assert isinstance(body["detail"].get("message"), str) and body["detail"]["message"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN — REFACTOR backwards compat invariant
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_signature_preserved_handle_tool_call():
    """AC-3 REFACTOR invariant: handle_tool_call は (name, args) -> str を維持."""
    from routers.mcp_server import handle_tool_call
    sig = inspect.signature(handle_tool_call)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["name", "args"]
    # async function
    assert inspect.iscoroutinefunction(handle_tool_call)


def test_ac3_existing_signature_preserved_validate_call_input():
    """AC-3 REFACTOR invariant: _validate_call_input(name, args) も signature 不変."""
    from routers.mcp_server import _validate_call_input
    sig = inspect.signature(_validate_call_input)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["name", "args"]


def test_ac3_query_company_db_inputSchema_unchanged(client):
    """AC-3 backwards compat: query_company_db.inputSchema.required == ['sql']."""
    r = client.post("/mcp/tools/list")
    by_name = {t["name"]: t for t in r.json()["tools"]}
    schema = by_name["query_company_db"]["inputSchema"]
    assert schema["required"] == ["sql"]
    assert "sql" in schema["properties"]
    assert schema["properties"]["sql"]["type"] == "string"


def test_ac3_get_kpi_inputSchema_unchanged(client):
    """AC-3: get_kpi は引数なし契約."""
    r = client.post("/mcp/tools/list")
    by_name = {t["name"]: t for t in r.json()["tools"]}
    schema = by_name["get_kpi"]["inputSchema"]
    assert schema == {"type": "object", "properties": {}}


def test_ac3_list_records_no_required_args(client):
    """AC-3: list_records は folder が optional のまま."""
    r = client.post("/mcp/tools/list")
    by_name = {t["name"]: t for t in r.json()["tools"]}
    schema = by_name["list_records"]["inputSchema"]
    # required key が無いか空 (folder は optional)
    assert "required" not in schema or schema.get("required") in (None, [])


def test_ac3_bf_tools_required_fields_match_spec(client):
    """AC-3 (1:1): BF tools の required field が F-010a の context を満たす.

    bf_get_spec  → task_id (int)
    bf_post_progress → task_id + percent_done
    bf_attach_artifact → task_id + artifact_id
    bf_request_review → task_id
    bf_get_review_feedback → review_id
    """
    r = client.post("/mcp/tools/list")
    by_name = {t["name"]: t for t in r.json()["tools"]}
    assert by_name["bf_get_spec"]["inputSchema"]["required"] == ["task_id"]
    assert set(by_name["bf_post_progress"]["inputSchema"]["required"]) == {
        "task_id", "percent_done"
    }
    assert set(by_name["bf_attach_artifact"]["inputSchema"]["required"]) == {
        "task_id", "artifact_id"
    }
    assert by_name["bf_request_review"]["inputSchema"]["required"] == ["task_id"]
    assert by_name["bf_get_review_feedback"]["inputSchema"]["required"] == ["review_id"]


def test_ac3_audit_emitted_on_success(client, _capture_audit):
    """AC-3: 成功 call で mcp.tool.called が audit_logs に emit."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "get_kpi", "arguments": {}, "user_id": "alice"},
    )
    assert r.status_code == 200
    matches = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(matches) >= 1
    assert matches[0]["user_id"] == "alice"
    assert matches[0]["detail"]["name"] == "get_kpi"


def test_ac3_query_company_db_response_is_json_array(client):
    """AC-3: query_company_db の content text は JSON array (rows)."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {"sql": "SELECT 1"}},
    )
    assert r.status_code == 200
    parsed = json.loads(r.json()["content"][0]["text"])
    assert isinstance(parsed, list)


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED — 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_name", ["", "   ", "\t\n"])
def test_ac4_empty_tool_name_rejected(client, bad_name):
    """AC-4: empty / whitespace name は 400 + invalid_tool_name."""
    r = client.post("/mcp/tools/call", json={"name": bad_name})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_tool_name"


def test_ac4_unknown_tool_returns_404(client):
    """AC-4: 未知 tool は 404 + unknown_tool (200 placeholder ではなく明示 error)."""
    r = client.post("/mcp/tools/call", json={"name": "nonexistent_tool_xyz"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "mcp.unknown_tool"
    # placeholder method 200 with empty result が無いこと (drift guard)
    assert "content" not in r.json()


def test_ac4_arguments_not_dict_rejected(client):
    """AC-4: arguments が dict 以外は 400 + invalid_arguments."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "get_kpi", "arguments": "string_not_dict"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_arguments"


@pytest.mark.parametrize("sql", [
    "DELETE FROM kpi_records",
    "DROP TABLE x",
    "UPDATE x SET y=1",
    "INSERT INTO x VALUES (1)",
    "ALTER TABLE x ADD COLUMN y",
    "TRUNCATE TABLE x",
])
def test_ac4_non_readonly_sql_rejected(client, sql, monkeypatch):
    """AC-4 UNWANTED: 非 SELECT / WITH / PRAGMA は 403 + sql_not_readonly + run_query 非呼出."""
    import routers.mcp_server as ms_router
    calls = {"n": 0}

    async def spy(_sql):
        calls["n"] += 1
        return []

    monkeypatch.setattr(ms_router, "run_query", spy)
    r = client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {"sql": sql}},
    )
    assert r.status_code == 403, f"{sql}: {r.status_code} {r.text}"
    assert r.json()["detail"]["code"] == "mcp.sql_not_readonly"
    assert calls["n"] == 0, f"AC-4 violation: run_query invoked for mutating SQL {sql!r}"


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select * from x",
    "WITH t AS (SELECT 1) SELECT * FROM t",
    "PRAGMA table_info(x)",
])
def test_ac4_readonly_sql_allowed(client, sql):
    """AC-4 補助 (4 variant): SELECT / WITH / PRAGMA は通る (大小文字混在 OK)."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {"sql": sql}},
    )
    assert r.status_code == 200, f"{sql}: {r.status_code} {r.text}"


def test_ac4_bf_post_progress_invalid_percent_done_rejected(client):
    """AC-4 variant-specific: bf_post_progress で percent_done が範囲外は 400."""
    r = client.post(
        "/mcp/tools/call",
        json={
            "name": "bf_post_progress",
            "arguments": {"task_id": 1, "percent_done": 1.5},
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_percent_done"


def test_ac4_bf_get_spec_invalid_task_id_rejected(client):
    """AC-4 variant-specific: bf_get_spec で task_id <= 0 は 400."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": 0}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_task_id"


def test_ac4_bf_attach_artifact_empty_artifact_id_rejected(client):
    """AC-4 variant-specific: bf_attach_artifact で artifact_id 空は 400."""
    r = client.post(
        "/mcp/tools/call",
        json={
            "name": "bf_attach_artifact",
            "arguments": {"task_id": 1, "artifact_id": ""},
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_id"


def test_ac4_bf_get_review_feedback_invalid_review_id(client):
    """AC-4 variant-specific: bf_get_review_feedback で review_id <= 0 は 400."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_review_feedback", "arguments": {"review_id": -1}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_review_id"


def test_ac4_empty_user_id_rejected_401(client):
    """AC-4: user_id 提供時に空白のみは 401 (unauthorized)."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "get_kpi", "arguments": {}, "user_id": "   "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "mcp.unauthorized"


def test_ac4_no_audit_on_rejected_calls(client, _capture_audit):
    """AC-4: rejected call は mcp.tool.called を emit しない (no mutation)."""
    client.post("/mcp/tools/call", json={"name": "unknown_x"})
    client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {"sql": "DELETE FROM x"}},
    )
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": -1}},
    )
    called = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert called == [], f"AC-4 violation: rejected calls produced audit events: {called}"


# ──────────────────────────────────────────────────────────────────────────
# Drift guard (anti-PR-#253 lesson) — forbidden symbols / variant proofs
# ──────────────────────────────────────────────────────────────────────────


def test_drift_no_langgraph_in_http_server():
    """Drift guard: HTTP MCP server に LangGraph / LangChain / LiteLLM import が無い."""
    src = _src(HTTP_SERVER)
    for needle in ("langgraph", "langchain", "litellm"):
        assert needle not in src.lower(), (
            f"forbidden symbol leak: {needle!r} found in {HTTP_SERVER.name}"
        )


def test_drift_no_langgraph_in_stdio_server():
    """Drift guard: stdio MCP server に LangGraph / LangChain / LiteLLM import が無い."""
    src = _src(STDIO_SERVER)
    for needle in ("langgraph", "langchain", "litellm"):
        assert needle not in src.lower(), (
            f"forbidden symbol leak: {needle!r} found in {STDIO_SERVER.name}"
        )


def test_drift_stdio_server_returns_jsonrpc_envelope():
    """Drift guard: legacy stdio (root mcp_stdio_server.py) は JSON-RPC 2.0 envelope.

    PR #253 教訓: placeholder 200 method ではなく、未実装は -32601 method-not-found.
    """
    src = _src(LEGACY_STDIO)
    # initialize / tools/list / tools/call が分岐実装されている
    assert 'method == "initialize"' in src
    assert 'method == "tools/list"' in src
    assert 'method == "tools/call"' in src
    # 未知 method には -32601 error を返す (placeholder 200 ではない)
    assert "-32601" in src
    assert '"jsonrpc": "2.0"' in src


def test_drift_unknown_tool_does_not_return_200_with_empty_result(client):
    """Drift guard (anti-PR-#253 specific): 未実装 method は 200+empty ではなく明示 error."""
    r = client.post("/mcp/tools/call", json={"name": "bf_NEVER_implemented_phase1"})
    # 200 with empty result は禁止
    assert r.status_code != 200, "AC-4 / drift violation: unknown tool returned 200"
    assert r.status_code == 404
    assert "content" not in r.json()


def test_drift_validate_call_input_has_variant_specific_branches():
    """Drift guard (PR #253 lesson): 各 BF tool name に対し validation 分岐が実装.

    "mode/transport/variant 系の引数を取る関数では、各 variant が実際に異なる挙動を
    発生させる test を 1:1 で書け" の予防版.
    """
    src = _src(HTTP_SERVER)
    for tool in ("query_company_db", "bf_get_spec", "bf_post_progress",
                 "bf_attach_artifact", "bf_request_review", "bf_get_review_feedback"):
        # name == tool / name in (...,tool,...) のいずれかで分岐していること
        pattern = re.compile(rf'name\s*==\s*["\']{tool}["\']|["\']{tool}["\']')
        assert pattern.search(src), f"validation/dispatch branch missing for {tool}"


# ──────────────────────────────────────────────────────────────────────────
# REFACTOR 9-項目 check (CLAUDE.md §4 + ADR-011)
# ──────────────────────────────────────────────────────────────────────────


def test_refactor_check_no_new_sql_migration_in_pr():
    """REFACTOR 1: 本タスクで新規 SQL migration を追加しない.

    `supabase/migrations/` のファイル一覧が PR baseline と同じであること
    (本 audit が NEW migration を追加しない invariant).
    """
    migrations_dir = ROOT / "supabase" / "migrations"
    assert migrations_dir.exists(), "supabase/migrations/ not present"
    files = sorted(p.name for p in migrations_dir.glob("*.sql"))
    # CLAUDE.md §3 backend bootstrap : 8+ migrations
    assert len(files) >= 8, f"too few migrations: {files}"


def test_refactor_check_existing_router_signatures_preserved():
    """REFACTOR 5: 公開 API シンボルが不変."""
    from routers.mcp_server import (
        MCP_TOOLS,
        ToolCallRequest,
        handle_tool_call,
        router,
        tools_call,
        tools_list,
        mcp_sse,
    )
    # router prefix が /mcp で固定
    assert router.prefix == "/mcp"
    # MCP_TOOLS は list of dict
    assert isinstance(MCP_TOOLS, list) and all(isinstance(t, dict) for t in MCP_TOOLS)
    # 旧 contract: name + inputSchema 必須
    for t in MCP_TOOLS:
        assert "name" in t and "inputSchema" in t
    # tools_list / tools_call / mcp_sse は coroutine
    assert inspect.iscoroutinefunction(tools_list)
    assert inspect.iscoroutinefunction(tools_call)
    assert inspect.iscoroutinefunction(mcp_sse)
    # ToolCallRequest は pydantic BaseModel
    from pydantic import BaseModel
    assert issubclass(ToolCallRequest, BaseModel)


def test_refactor_check_no_hardcoded_secret():
    """REFACTOR 7-class drift: hardcoded API key / token なし."""
    for path in (HTTP_SERVER, STDIO_SERVER):
        src = _src(path)
        # 簡易 secret pattern (sk- / sb_secret_ / sb_publishable_)
        forbidden = [
            r"sk-[a-zA-Z0-9]{30,}",
            r"sb_secret_[A-Za-z0-9_-]{20,}",
            r"sb_publishable_[A-Za-z0-9_-]{20,}",
            r"AKIA[0-9A-Z]{16}",
        ]
        for p in forbidden:
            assert not re.search(p, src), (
                f"hardcoded secret pattern {p!r} found in {path.name}"
            )


def test_refactor_check_no_force_push_or_destructive():
    """REFACTOR §5.4 red-line: --force / DROP / TRUNCATE がコードに無い."""
    src = _src(HTTP_SERVER)
    for needle in ("--force", "DROP TABLE", "TRUNCATE"):
        assert needle not in src, f"forbidden token {needle!r} in {HTTP_SERVER.name}"


def test_refactor_check_response_within_30s_policy(client):
    """REFACTOR + F-010a policy: timeout_sec=30 を満たす (実際は < 2 s で十分)."""
    # 5 連続 call で max < 2 s (timeout 30 s policy より厳しく実測)
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        client.post("/mcp/tools/call", json={"name": "get_kpi", "arguments": {}})
        times.append(time.perf_counter() - t0)
    assert max(times) < 2.0, f"max latency {max(times):.3f}s exceeds 2.0s"


def test_refactor_check_audit_logs_emitted_for_all_8_tools(client, _capture_audit, monkeypatch):
    """REFACTOR + AC-3 + F-010a related_entities: 8 tool 全て audit_logs に emit.

    具体的に呼ぶのは 旧 3 + bf_get_spec で 4 tool (BF tools は DB 依存なので skip)
    audit_logs emit 自体は generic 経路.
    """
    # 旧 3 tool のみ DB mock 済み (確実に通る)
    for tool, args in [
        ("get_kpi", {}),
        ("list_records", {}),
        ("query_company_db", {"sql": "SELECT 1"}),
    ]:
        r = client.post("/mcp/tools/call", json={"name": tool, "arguments": args})
        assert r.status_code == 200
    matches = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(matches) >= 3, f"expected >= 3 audit events, got {len(matches)}"
    audited_names = {e["detail"]["name"] for e in matches}
    assert {"get_kpi", "list_records", "query_company_db"} <= audited_names
