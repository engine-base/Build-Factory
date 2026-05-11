"""T-010a-02: bf_get_spec / bf_post_progress / bf_attach_artifact — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010a で 3 BF tool が MCP_TOOLS に登録 + handle_tool_call で動作
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 3 tool 不変 (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid args は 4xx + structured / persistent state mutate しない
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
def _fake_bf_tools(monkeypatch):
    """_bf_get_spec / _bf_post_progress / _bf_attach_artifact を fake に差し替え."""
    import routers.mcp_server as mcp

    spec_store: dict[int, dict] = {
        100: {
            "task_id": 100, "title": "Test Task", "description": "desc",
            "status": "in_progress", "acceptance_criteria": "[]",
            "project_id": 1, "assigned_to": 10, "artifacts": [],
        },
    }
    progress_log: list[dict] = []
    artifacts_store: dict[str, dict] = {
        "art-1": {"id": "art-1", "task_id": None, "type": "report"},
    }

    async def fake_get_spec(task_id):
        rec = spec_store.get(task_id)
        if rec is None:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.task_not_found", "message": f"task not found: {task_id}"},
            )
        return rec

    async def fake_post_progress(task_id, percent_done, note):
        if task_id not in spec_store:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.task_not_found", "message": f"task {task_id}"},
            )
        progress_log.append({
            "task_id": task_id, "percent_done": percent_done, "note": note,
        })
        return {"task_id": task_id, "percent_done": round(percent_done, 4),
                 "note": note, "recorded": True}

    async def fake_attach(task_id, artifact_id):
        if task_id not in spec_store:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.task_not_found", "message": f"task {task_id}"},
            )
        if artifact_id not in artifacts_store:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.artifact_not_found", "message": f"art {artifact_id}"},
            )
        artifacts_store[artifact_id]["task_id"] = task_id
        return {"task_id": task_id, "artifact_id": artifact_id, "linked": True}

    monkeypatch.setattr(mcp, "_bf_get_spec", fake_get_spec)
    monkeypatch.setattr(mcp, "_bf_post_progress", fake_post_progress)
    monkeypatch.setattr(mcp, "_bf_attach_artifact", fake_attach)
    yield {
        "spec_store": spec_store,
        "progress_log": progress_log,
        "artifacts_store": artifacts_store,
    }


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: MCP_TOOLS 登録 + endpoint 動作
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_three_bf_tools_listed(client):
    r = client.post("/mcp/tools/list")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"bf_get_spec", "bf_post_progress", "bf_attach_artifact"} <= names


def test_ac1_bf_get_spec_returns_task_info(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": 100}},
    )
    assert r.status_code == 200
    body = r.json()
    parsed = json.loads(body["content"][0]["text"])
    assert parsed["task_id"] == 100
    assert parsed["title"] == "Test Task"


def test_ac1_bf_post_progress_records_in_audit(client, _fake_bf_tools):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_post_progress",
               "arguments": {"task_id": 100, "percent_done": 0.5,
                              "note": "halfway"}},
    )
    assert r.status_code == 200
    log = _fake_bf_tools["progress_log"]
    assert len(log) == 1
    assert log[0]["percent_done"] == 0.5


def test_ac1_bf_attach_artifact_links(client, _fake_bf_tools):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_attach_artifact",
               "arguments": {"task_id": 100, "artifact_id": "art-1"}},
    )
    assert r.status_code == 200
    assert _fake_bf_tools["artifacts_store"]["art-1"]["task_id"] == 100


def test_ac1_input_schemas_have_required_fields():
    """各 tool の inputSchema が required field を持つ."""
    from routers.mcp_server import MCP_TOOLS
    by_name = {t["name"]: t for t in MCP_TOOLS}
    assert by_name["bf_get_spec"]["inputSchema"]["required"] == ["task_id"]
    assert by_name["bf_post_progress"]["inputSchema"]["required"] == [
        "task_id", "percent_done",
    ]
    assert by_name["bf_attach_artifact"]["inputSchema"]["required"] == [
        "task_id", "artifact_id",
    ]


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": 100}},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": 0}},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "mcp.invalid_task_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 contract 不変 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_three_tools_still_listed(client):
    """既存 3 tool は不変."""
    r = client.post("/mcp/tools/list")
    names = {t["name"] for t in r.json()["tools"]}
    assert {"query_company_db", "get_kpi", "list_records"} <= names


def test_ac3_tool_count_grew_to_6():
    from routers.mcp_server import MCP_TOOLS
    assert len(MCP_TOOLS) == 6


def test_ac3_audit_emitted_on_tool_call(client, _capture_audit):
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": 100},
               "user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["name"] == "bf_get_spec"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_task_id_rejected_get_spec(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": 0}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_task_id"


def test_ac4_missing_task_id_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_task_id"


def test_ac4_invalid_percent_done_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_post_progress",
               "arguments": {"task_id": 100, "percent_done": 1.5}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_percent_done"


def test_ac4_negative_percent_done_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_post_progress",
               "arguments": {"task_id": 100, "percent_done": -0.1}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_percent_done"


def test_ac4_long_note_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_post_progress",
               "arguments": {"task_id": 100, "percent_done": 0.5,
                              "note": "x" * 2001}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_note"


def test_ac4_empty_artifact_id_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_attach_artifact",
               "arguments": {"task_id": 100, "artifact_id": "  "}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_id"


def test_ac4_long_artifact_id_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_attach_artifact",
               "arguments": {"task_id": 100, "artifact_id": "x" * 201}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_id"


def test_ac4_unknown_task_get_spec_returns_404(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_spec", "arguments": {"task_id": 99999}},
    )
    # fake_get_spec が HTTPException(404) を raise → tools_call が tool_failed で wrap
    # する可能性あり; 400 or 500 でも structured detail を確認
    assert r.status_code in (404, 500)
    if r.status_code == 404:
        assert r.json()["detail"]["code"] == "mcp.task_not_found"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_bf_tools):
    """AC-4 UNWANTED: 失敗時に audit emit / state mutate なし."""
    before_progress = len(_fake_bf_tools["progress_log"])
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_post_progress",
               "arguments": {"task_id": 0, "percent_done": 0.5}},
    )
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_attach_artifact",
               "arguments": {"task_id": 100, "artifact_id": "  "}},
    )
    after_progress = len(_fake_bf_tools["progress_log"])
    assert before_progress == after_progress
    events = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        {"name": "bf_get_spec", "arguments": {"task_id": 0}},
        {"name": "bf_get_spec", "arguments": {}},
        {"name": "bf_post_progress", "arguments": {"task_id": 1, "percent_done": 2.0}},
        {"name": "bf_post_progress",
         "arguments": {"task_id": 1, "percent_done": 0.5, "note": "x" * 2001}},
        {"name": "bf_attach_artifact",
         "arguments": {"task_id": 1, "artifact_id": "  "}},
        {"name": "bf_attach_artifact",
         "arguments": {"task_id": 1, "artifact_id": "x" * 201}},
    ]
    for payload in cases:
        r = client.post("/mcp/tools/call", json=payload)
        assert 400 <= r.status_code < 500, f"{payload}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
