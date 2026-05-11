"""T-010a-01: MCP server (REFACTOR) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010a MCP server endpoint 公開 (GET /mcp, POST /mcp/tools/{list,call})
  AC-2 EVENT-DRIVEN  : 2 秒以内に success or {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 contract (tool name / arguments / response shape) 不変
  AC-4 UNWANTED      : invalid input / unknown tool / 非 SELECT は 4xx + structured,
                       persistent state mutate しない
"""
from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


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


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    """db.queries の重い処理を mock (高速 + 副作用なし)."""
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


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_tools_list_endpoint_exists(client):
    """AC-1: POST /mcp/tools/list が tool 一覧を返す."""
    r = client.post("/mcp/tools/list")
    assert r.status_code == 200
    body = r.json()
    assert "tools" in body
    names = {t["name"] for t in body["tools"]}
    assert {"query_company_db", "get_kpi", "list_records"} <= names


def test_ac1_tools_call_endpoint_exists(client):
    """AC-1: POST /mcp/tools/call が tool を呼び出せる."""
    r = client.post("/mcp/tools/call", json={"name": "get_kpi", "arguments": {}})
    assert r.status_code == 200
    body = r.json()
    assert "content" in body
    assert body["content"][0]["type"] == "text"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured shape
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_tools_list_returns_within_2s(client):
    """AC-2: tools/list が 2 秒以内."""
    t0 = time.perf_counter()
    r = client.post("/mcp/tools/list")
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_tools_call_returns_within_2s(client):
    """AC-2: tools/call も 2 秒以内."""
    t0 = time.perf_counter()
    r = client.post("/mcp/tools/call", json={"name": "list_records", "arguments": {}})
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    """AC-2: error response は {detail:{code,message}} 形式."""
    r = client.post("/mcp/tools/call", json={"name": ""})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "mcp.invalid_tool_name"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 contract (backwards compat)
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_tool_contract_unchanged(client):
    """AC-3: tools/list の tool 数 + name + inputSchema が既存と同じ."""
    r = client.post("/mcp/tools/list")
    tools = r.json()["tools"]
    assert len(tools) == 3
    by_name = {t["name"]: t for t in tools}
    # 既存 inputSchema が保持されている
    assert by_name["query_company_db"]["inputSchema"]["required"] == ["sql"]
    assert "sql" in by_name["query_company_db"]["inputSchema"]["properties"]
    assert by_name["get_kpi"]["inputSchema"] == {"type": "object", "properties": {}}


def test_ac3_existing_response_shape_unchanged(client):
    """AC-3: tools/call response は {content:[{type, text}]} で text は JSON 文字列."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {"sql": "SELECT 1"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["content"][0]["type"] == "text"
    # JSON parse できる文字列
    parsed = json.loads(body["content"][0]["text"])
    assert isinstance(parsed, list)
    assert parsed[0]["col1"] == 1


def test_ac3_arguments_optional_for_no_arg_tools(client):
    """AC-3: arguments を省略しても旧 contract 通り動作 (get_kpi は引数不要)."""
    r = client.post("/mcp/tools/call", json={"name": "get_kpi"})
    assert r.status_code == 200


def test_ac3_audit_emitted_on_success(client, _capture_audit):
    """AC-3 + 監査: 成功 call で audit_logs に mcp.tool.called を emit."""
    client.post("/mcp/tools/call", json={"name": "get_kpi", "arguments": {}, "user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["name"] == "get_kpi"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + {detail:{code,message}} + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_tool_name_rejected(client, _capture_audit):
    """AC-4: empty name は 400 + invalid_tool_name."""
    r = client.post("/mcp/tools/call", json={"name": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_tool_name"
    # AC-4: state mutate なし — audit emit も無し
    called = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(called) == 0


def test_ac4_unknown_tool_rejected(client):
    """AC-4: unknown tool は 404 + unknown_tool."""
    r = client.post("/mcp/tools/call", json={"name": "nonexistent_tool"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "mcp.unknown_tool"


def test_ac4_invalid_arguments_type_rejected(client):
    """AC-4: arguments が dict 以外は 400 + invalid_arguments."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "get_kpi", "arguments": "not_a_dict"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_arguments"


def test_ac4_missing_required_sql_rejected(client):
    """AC-4: query_company_db で sql 欠落は 400 + invalid_sql."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_sql"


def test_ac4_non_select_sql_rejected(client, monkeypatch):
    """AC-4 UNWANTED: 非 SELECT 系は 403 + sql_not_readonly (persistent state mutate 防止)."""
    import routers.mcp_server as ms_router
    called = {"n": 0}

    async def fake_run(sql):
        called["n"] += 1
        return []

    monkeypatch.setattr(ms_router, "run_query", fake_run)
    for sql in ["DELETE FROM kpi_records", "DROP TABLE x", "UPDATE x SET y=1", "INSERT INTO x VALUES (1)"]:
        r = client.post(
            "/mcp/tools/call",
            json={"name": "query_company_db", "arguments": {"sql": sql}},
        )
        assert r.status_code == 403, f"{sql}: status={r.status_code}"
        assert r.json()["detail"]["code"] == "mcp.sql_not_readonly"
    # AC-4: 一度も run_query は呼ばれない (mutate 防止)
    assert called["n"] == 0


def test_ac4_select_sql_allowed(client):
    """AC-4 補助: SELECT は通る."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {"sql": "SELECT * FROM kpi_records"}},
    )
    assert r.status_code == 200


def test_ac4_with_cte_allowed(client):
    """AC-4 補助: WITH cte は通る (read-only 扱い)."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "query_company_db", "arguments": {"sql": "WITH t AS (SELECT 1) SELECT * FROM t"}},
    )
    assert r.status_code == 200


def test_ac4_empty_user_id_rejected(client):
    """AC-4: 空 user_id は 401 + unauthorized."""
    r = client.post(
        "/mcp/tools/call",
        json={"name": "get_kpi", "arguments": {}, "user_id": "   "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "mcp.unauthorized"


def test_ac4_no_audit_on_rejected_call(client, _capture_audit):
    """AC-4: rejected call は mcp.tool.called を emit しない (mutate なし)."""
    client.post("/mcp/tools/call", json={"name": "unknown_x"})
    client.post("/mcp/tools/call", json={"name": "query_company_db", "arguments": {"sql": "DROP TABLE x"}})
    called = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(called) == 0


# ──────────────────────────────────────────────────────────────────────────
# 補助: error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    """全 error response が {detail:{code:str, message:str}} の shape."""
    cases = [
        {"name": ""},
        {"name": "unknown_x"},
        {"name": "get_kpi", "arguments": "not_dict"},
        {"name": "query_company_db", "arguments": {}},
        {"name": "query_company_db", "arguments": {"sql": "DELETE FROM x"}},
        {"name": "get_kpi", "user_id": "   "},
    ]
    for payload in cases:
        r = client.post("/mcp/tools/call", json=payload)
        assert 400 <= r.status_code < 500, f"{payload}: status={r.status_code}"
        body = r.json()
        assert isinstance(body.get("detail"), dict), f"{payload}: detail not dict"
        assert isinstance(body["detail"].get("code"), str)
        assert isinstance(body["detail"].get("message"), str)
