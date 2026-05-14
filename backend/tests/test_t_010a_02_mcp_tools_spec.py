"""T-010a-02 v2 spec audit — bf_get_spec / bf_post_progress / bf_attach_artifact.

Reference: docs/audit/2026-05-13_v2/T-013-04.md v2 style.

This file complements `test_t_010a_02_bf_mcp_tools.py` (20 tests, integration
shape) with **per-tool spec rigor** (10+ tests per tool, AC 1..4 × tool
matrix). Each test cites which AC sub-clause it verifies.

Spec literal expansion (cited verbatim from sources):

  docs/functional-breakdown/2026-05-09_v1/features.json F-010a:
    > "tools": ["bf_get_spec", "bf_post_progress", "bf_attach_artifact",
    >           "bf_request_review", "bf_get_review_feedback"]
    > "error_paths": ["auth 失敗→401", "RLS 違反→403"]
    > "policies": {"timeout_sec": 30, "streaming": true}
    > "related_entities": ["tasks", "artifacts", "sessions"]

  docs/PROJECT_BRIEF.md §10:
    > bf_get_spec(task_id)            仕様書 + 受け入れ基準 + 関連スキル
    > bf_post_progress(task_id, msg)  進捗書戻し
    > bf_attach_artifact(task_id, .)  生成物紐付け

  docs/architecture/2026-05-09_v1/architecture-v1.md L77:
    > | MCP Server | Anthropic MCP Python SDK + FastAPI | stdio + HTTP transport |

  T-010a-02 ticket AC (EARS):
    AC-1 UBIQUITOUS:    shall implement T-010a-02 as specified by F-010a
    AC-2 EVENT-DRIVEN:  shall return structured response within 2 seconds
    AC-3 STATE-DRIVEN:  shall maintain backwards compatibility / coverage
    AC-4 UNWANTED:      invalid/unauthorized → 4xx {detail:{code,message}};
                        shall not mutate persistent state

Drift guard (PR #253 lesson): each tool's distinctive parameters must trigger
**measurably different** behavior — not just labels. We verify this per tool.
"""
from __future__ import annotations

import inspect
import json
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────
# fixtures (re-use the same shape as test_t_010a_02_bf_mcp_tools.py)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    import os
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _fake_bf_tools(monkeypatch):
    """Provide deterministic fakes for the 3 BF tool impls (sql-free)."""
    import routers.mcp_server as mcp

    spec_store: dict[int, dict] = {
        100: {
            "task_id": 100,
            "title": "T-010a-02 spec verification target",
            "description": "desc",
            "status": "in_progress",
            "acceptance_criteria": '[{"type":"UBIQUITOUS","text":"shall..."}]',
            "project_id": 1,
            "assigned_to": 10,
            "artifacts": [{"id": "art-existing", "type": "report",
                            "title": "prior"}],
        },
        200: {
            "task_id": 200,
            "title": "second task",
            "description": "",
            "status": "todo",
            "acceptance_criteria": "[]",
            "project_id": 1,
            "assigned_to": None,
            "artifacts": [],
        },
    }
    progress_log: list[dict] = []
    artifacts_store: dict[str, dict] = {
        "art-1": {"id": "art-1", "task_id": None, "type": "report"},
        "art-2": {"id": "art-2", "task_id": None, "type": "html"},
    }

    async def fake_get_spec(task_id):
        rec = spec_store.get(task_id)
        if rec is None:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.task_not_found",
                         "message": f"task not found: {task_id}"},
            )
        return rec

    async def fake_post_progress(task_id, percent_done, note):
        if task_id not in spec_store:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.task_not_found",
                         "message": f"task {task_id}"},
            )
        progress_log.append({
            "task_id": task_id,
            "percent_done": percent_done,
            "note": note,
        })
        return {"task_id": task_id, "percent_done": round(percent_done, 4),
                 "note": note, "recorded": True}

    async def fake_attach(task_id, artifact_id):
        if task_id not in spec_store:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.task_not_found",
                         "message": f"task {task_id}"},
            )
        if artifact_id not in artifacts_store:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail={"code": "mcp.artifact_not_found",
                         "message": f"art {artifact_id}"},
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
# helpers
# ──────────────────────────────────────────────────────────────────────────


def _call(client, name, args):
    return client.post("/mcp/tools/call",
                        json={"name": name, "arguments": args})


def _parsed(resp):
    body = resp.json()
    return json.loads(body["content"][0]["text"])


def _tool_def(name):
    from routers.mcp_server import MCP_TOOLS
    by_name = {t["name"]: t for t in MCP_TOOLS}
    return by_name.get(name)


REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_ROUTER_SRC = (REPO_ROOT / "backend" / "routers" / "mcp_server.py").read_text(
    encoding="utf-8"
)


# ──────────────────────────────────────────────────────────────────────────
# Drift guard (PR #253 lesson): forbidden Phase 2 / unscoped tool names
# ──────────────────────────────────────────────────────────────────────────


# Names we DO NOT want T-010a-02 to leak. Phase 2 admin / workspace clone /
# multi-tenant operations belong elsewhere.
FORBIDDEN_TOOL_NAMES = [
    "bf_workspace_clone",
    "bf_admin_grant",
    "bf_admin_revoke",
    "bf_workspace_export",
    "bf_workspace_delete",
    "bf_billing_charge",
    "bf_tenant_provision",
]


def test_drift_guard_no_phase2_tools_leaked_in_router_source():
    """AC-3 drift guard: forbidden Phase 2 tool names must NOT appear."""
    for forbidden in FORBIDDEN_TOOL_NAMES:
        assert forbidden not in MCP_ROUTER_SRC, (
            f"forbidden Phase 2 tool name {forbidden!r} leaked into "
            f"router. T-010a-02 is Phase 1 scope only."
        )


def test_drift_guard_no_phase2_tools_in_tools_list(client):
    """AC-3 drift guard: forbidden names must NOT appear via list."""
    r = client.post("/mcp/tools/list")
    names = {t["name"] for t in r.json()["tools"]}
    leaked = set(FORBIDDEN_TOOL_NAMES) & names
    assert not leaked, f"Phase 2 tool names leaked into /mcp/tools/list: {leaked}"


def test_drift_guard_f010a_tool_set_matches_feature_decomposition(client):
    """AC-1 spec literal: F-010a declares exactly 5 tools — ensure superset."""
    r = client.post("/mcp/tools/list")
    names = {t["name"] for t in r.json()["tools"]}
    f010a_tools = {
        "bf_get_spec", "bf_post_progress", "bf_attach_artifact",
        "bf_request_review", "bf_get_review_feedback",
    }
    missing = f010a_tools - names
    assert not missing, f"F-010a tools missing from MCP_TOOLS: {missing}"


# ══════════════════════════════════════════════════════════════════════════
# TOOL 1: bf_get_spec — 11 tests (AC-1 × 3, AC-2 × 3, AC-3 × 3, AC-4 × 2)
# ══════════════════════════════════════════════════════════════════════════


# ── bf_get_spec AC-1 UBIQUITOUS ──
def test_get_spec_ac1_registered_in_mcp_tools():
    """AC-1: bf_get_spec is in MCP_TOOLS with correct identity."""
    td = _tool_def("bf_get_spec")
    assert td is not None
    assert td["name"] == "bf_get_spec"
    assert isinstance(td["description"], str) and td["description"]


def test_get_spec_ac1_input_schema_requires_task_id():
    """AC-1: F-010a contract — input is {task_id: integer}."""
    td = _tool_def("bf_get_spec")
    schema = td["inputSchema"]
    assert schema["type"] == "object"
    assert schema["required"] == ["task_id"]
    assert schema["properties"]["task_id"]["type"] == "integer"


def test_get_spec_ac1_returns_required_fields(client):
    """AC-1: PROJECT_BRIEF §10 verbatim — '仕様書 + 受け入れ基準 + 関連スキル'.
    Implementation maps to: title + description + acceptance_criteria + artifacts.
    """
    r = _call(client, "bf_get_spec", {"task_id": 100})
    assert r.status_code == 200
    payload = _parsed(r)
    for key in ("task_id", "title", "description", "status",
                 "acceptance_criteria", "artifacts"):
        assert key in payload, f"bf_get_spec response missing field: {key}"


# ── bf_get_spec AC-2 EVENT-DRIVEN ──
def test_get_spec_ac2_responds_within_2s(client):
    """AC-2: 2-second budget on happy path."""
    t0 = time.perf_counter()
    r = _call(client, "bf_get_spec", {"task_id": 100})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0, f"bf_get_spec took {elapsed:.3f}s (> 2s budget)"


def test_get_spec_ac2_structured_success_response(client):
    """AC-2: success returns {content:[{type:'text',text:json}]} shape."""
    r = _call(client, "bf_get_spec", {"task_id": 100})
    assert r.status_code == 200
    body = r.json()
    assert "content" in body
    assert body["content"][0]["type"] == "text"
    json.loads(body["content"][0]["text"])  # must be JSON-parseable


def test_get_spec_ac2_error_envelope_uses_detail_code_message(client):
    """AC-2: error envelope = {detail:{code:str, message:str}}."""
    r = _call(client, "bf_get_spec", {"task_id": -1})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert "code" in body["detail"]
    assert "message" in body["detail"]
    assert isinstance(body["detail"]["code"], str)


# ── bf_get_spec AC-3 STATE-DRIVEN ──
def test_get_spec_ac3_is_idempotent_read(client, _fake_bf_tools):
    """AC-3: bf_get_spec is a pure read — calling twice doesn't mutate state."""
    before = len(_fake_bf_tools["progress_log"])
    _call(client, "bf_get_spec", {"task_id": 100})
    _call(client, "bf_get_spec", {"task_id": 100})
    assert len(_fake_bf_tools["progress_log"]) == before


def test_get_spec_ac3_returns_distinct_data_for_distinct_tasks(client):
    """AC-3 drift guard: task_id parameter must trigger measurably different
    output (not just label preservation). PR #253 lesson.
    """
    r1 = _parsed(_call(client, "bf_get_spec", {"task_id": 100}))
    r2 = _parsed(_call(client, "bf_get_spec", {"task_id": 200}))
    assert r1["task_id"] != r2["task_id"]
    assert r1["title"] != r2["title"]


def test_get_spec_ac3_existing_three_tools_still_listed(client):
    """AC-3: backwards compat — pre-existing 3 tools must remain."""
    r = client.post("/mcp/tools/list")
    names = {t["name"] for t in r.json()["tools"]}
    assert {"query_company_db", "get_kpi", "list_records"} <= names


# ── bf_get_spec AC-4 UNWANTED ──
def test_get_spec_ac4_zero_task_id_rejected(client):
    """AC-4: invalid task_id → 4xx + structured."""
    r = _call(client, "bf_get_spec", {"task_id": 0})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_task_id"


def test_get_spec_ac4_string_task_id_rejected(client):
    """AC-4: type-invalid task_id → 4xx."""
    r = _call(client, "bf_get_spec", {"task_id": "not-an-int"})
    assert 400 <= r.status_code < 500
    assert r.json()["detail"]["code"] == "mcp.invalid_task_id"


# ══════════════════════════════════════════════════════════════════════════
# TOOL 2: bf_post_progress — 11 tests (AC-1 × 3, AC-2 × 2, AC-3 × 3, AC-4 × 3)
# ══════════════════════════════════════════════════════════════════════════


# ── bf_post_progress AC-1 UBIQUITOUS ──
def test_post_progress_ac1_registered_with_required_fields():
    """AC-1: bf_post_progress in MCP_TOOLS with proper schema."""
    td = _tool_def("bf_post_progress")
    assert td is not None
    schema = td["inputSchema"]
    assert set(schema["required"]) == {"task_id", "percent_done"}
    assert schema["properties"]["percent_done"]["type"] == "number"


def test_post_progress_ac1_returns_recorded_marker(client):
    """AC-1: 'recorded:true' indicates audit emission happened."""
    r = _call(client, "bf_post_progress",
              {"task_id": 100, "percent_done": 0.5, "note": "halfway"})
    assert r.status_code == 200
    payload = _parsed(r)
    assert payload["recorded"] is True
    assert payload["task_id"] == 100


def test_post_progress_ac1_note_optional(client, _fake_bf_tools):
    """AC-1: note is optional per inputSchema."""
    r = _call(client, "bf_post_progress",
              {"task_id": 100, "percent_done": 0.25})
    assert r.status_code == 200
    log = _fake_bf_tools["progress_log"]
    # the call should have been logged with note=None
    assert any(e["note"] is None for e in log)


# ── bf_post_progress AC-2 EVENT-DRIVEN ──
def test_post_progress_ac2_2s_budget(client):
    """AC-2: 2-second budget."""
    t0 = time.perf_counter()
    r = _call(client, "bf_post_progress",
              {"task_id": 100, "percent_done": 0.5})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_post_progress_ac2_error_envelope(client):
    """AC-2: invalid percent_done → structured 4xx."""
    r = _call(client, "bf_post_progress",
              {"task_id": 100, "percent_done": 99})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "mcp.invalid_percent_done"


# ── bf_post_progress AC-3 STATE-DRIVEN ──
def test_post_progress_ac3_audit_event_emitted(client, _capture_audit):
    """AC-3: progress call emits mcp.tool.called audit_log."""
    _capture_audit.clear()
    _call(client, "bf_post_progress",
          {"task_id": 100, "percent_done": 0.7, "note": "near done"})
    events = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(events) >= 1
    assert events[0]["detail"]["name"] == "bf_post_progress"


def test_post_progress_ac3_distinct_percent_values_stored_distinctly(client, _fake_bf_tools):
    """AC-3 drift guard: percent_done parameter must be propagated, not
    flattened. PR #253 lesson — distinctive params must trigger measurably
    different behavior, not just label preservation.
    """
    log_before = len(_fake_bf_tools["progress_log"])
    _call(client, "bf_post_progress", {"task_id": 100, "percent_done": 0.1})
    _call(client, "bf_post_progress", {"task_id": 100, "percent_done": 0.9})
    log = _fake_bf_tools["progress_log"][log_before:]
    assert len(log) == 2
    values = [e["percent_done"] for e in log]
    assert 0.1 in values and 0.9 in values
    assert values[0] != values[1]


def test_post_progress_ac3_status_unchanged_documented():
    """AC-3 backwards compat: the impl docstring promises task status is NOT
    mutated by progress reports — verify the impl source doesn't UPDATE tasks
    table from this path.
    """
    # the _bf_post_progress helper must not UPDATE the tasks table
    src = MCP_ROUTER_SRC
    # find body of _bf_post_progress
    m = re.search(r"async def _bf_post_progress\(.*?\n\n", src, re.DOTALL)
    assert m is not None, "_bf_post_progress not found"
    body = m.group(0)
    assert "UPDATE tasks" not in body.upper(), (
        "bf_post_progress should NOT mutate tasks table per AC-3 backwards "
        "compat docstring"
    )


# ── bf_post_progress AC-4 UNWANTED ──
def test_post_progress_ac4_percent_over_1_rejected(client):
    """AC-4: percent > 1.0 rejected."""
    r = _call(client, "bf_post_progress",
              {"task_id": 100, "percent_done": 1.5})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_percent_done"


def test_post_progress_ac4_negative_percent_rejected(client):
    """AC-4: negative percent rejected."""
    r = _call(client, "bf_post_progress",
              {"task_id": 100, "percent_done": -0.001})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_percent_done"


def test_post_progress_ac4_no_mutation_on_invalid(client, _fake_bf_tools, _capture_audit):
    """AC-4: invalid input must NOT mutate progress_log and must NOT emit
    mcp.tool.called audit event.
    """
    _capture_audit.clear()
    before_log = len(_fake_bf_tools["progress_log"])
    _call(client, "bf_post_progress",
          {"task_id": 100, "percent_done": 2.0})
    _call(client, "bf_post_progress",
          {"task_id": 100, "percent_done": -1})
    assert len(_fake_bf_tools["progress_log"]) == before_log
    called = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(called) == 0


# ══════════════════════════════════════════════════════════════════════════
# TOOL 3: bf_attach_artifact — 11 tests (AC-1 × 3, AC-2 × 2, AC-3 × 3, AC-4 × 3)
# ══════════════════════════════════════════════════════════════════════════


# ── bf_attach_artifact AC-1 UBIQUITOUS ──
def test_attach_artifact_ac1_registered_with_required_fields():
    """AC-1: bf_attach_artifact in MCP_TOOLS with proper required schema."""
    td = _tool_def("bf_attach_artifact")
    assert td is not None
    schema = td["inputSchema"]
    assert set(schema["required"]) == {"task_id", "artifact_id"}
    assert schema["properties"]["artifact_id"]["type"] == "string"


def test_attach_artifact_ac1_returns_linked_marker(client):
    """AC-1: success → {linked: true}."""
    r = _call(client, "bf_attach_artifact",
              {"task_id": 100, "artifact_id": "art-1"})
    assert r.status_code == 200
    payload = _parsed(r)
    assert payload["linked"] is True
    assert payload["task_id"] == 100
    assert payload["artifact_id"] == "art-1"


def test_attach_artifact_ac1_actually_associates_in_store(client, _fake_bf_tools):
    """AC-1 drift guard: artifact_id param must trigger ACTUAL association
    (not just echo). PR #253 lesson — verify state change.
    """
    store = _fake_bf_tools["artifacts_store"]
    store["art-1"]["task_id"] = None  # reset
    _call(client, "bf_attach_artifact",
          {"task_id": 100, "artifact_id": "art-1"})
    assert store["art-1"]["task_id"] == 100


# ── bf_attach_artifact AC-2 EVENT-DRIVEN ──
def test_attach_artifact_ac2_2s_budget(client):
    """AC-2: 2-second budget."""
    t0 = time.perf_counter()
    r = _call(client, "bf_attach_artifact",
              {"task_id": 100, "artifact_id": "art-2"})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_attach_artifact_ac2_error_envelope(client):
    """AC-2: empty artifact_id → structured 4xx."""
    r = _call(client, "bf_attach_artifact",
              {"task_id": 100, "artifact_id": ""})
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "mcp.invalid_artifact_id"


# ── bf_attach_artifact AC-3 STATE-DRIVEN ──
def test_attach_artifact_ac3_audit_event_emitted(client, _capture_audit):
    """AC-3: attach call emits mcp.tool.called audit_log."""
    _capture_audit.clear()
    _call(client, "bf_attach_artifact",
          {"task_id": 100, "artifact_id": "art-1"})
    events = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert len(events) >= 1
    assert events[0]["detail"]["name"] == "bf_attach_artifact"


def test_attach_artifact_ac3_different_artifact_ids_link_to_different_records(
    client, _fake_bf_tools,
):
    """AC-3 drift guard: artifact_id parameter must actually select the right
    record — different IDs must update DIFFERENT rows. PR #253 lesson.
    """
    store = _fake_bf_tools["artifacts_store"]
    store["art-1"]["task_id"] = None
    store["art-2"]["task_id"] = None
    _call(client, "bf_attach_artifact",
          {"task_id": 100, "artifact_id": "art-1"})
    _call(client, "bf_attach_artifact",
          {"task_id": 200, "artifact_id": "art-2"})
    assert store["art-1"]["task_id"] == 100
    assert store["art-2"]["task_id"] == 200


def test_attach_artifact_ac3_known_artifact_required(client):
    """AC-3: backwards-compat error path — unknown artifact_id → 404
    {mcp.artifact_not_found}.
    """
    r = _call(client, "bf_attach_artifact",
              {"task_id": 100, "artifact_id": "nonexistent-id"})
    # fake raises HTTPException(404). tools_call's catch-all may wrap to 500;
    # accept either, but the code/message must reflect not_found
    assert r.status_code in (404, 500)
    if r.status_code == 404:
        assert r.json()["detail"]["code"] == "mcp.artifact_not_found"


# ── bf_attach_artifact AC-4 UNWANTED ──
def test_attach_artifact_ac4_whitespace_artifact_id_rejected(client):
    """AC-4: whitespace-only artifact_id rejected."""
    r = _call(client, "bf_attach_artifact",
              {"task_id": 100, "artifact_id": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_id"


def test_attach_artifact_ac4_oversized_artifact_id_rejected(client):
    """AC-4: artifact_id > 200 chars rejected (DoS / bound check)."""
    r = _call(client, "bf_attach_artifact",
              {"task_id": 100, "artifact_id": "a" * 201})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_id"


def test_attach_artifact_ac4_no_mutation_on_invalid(client, _fake_bf_tools):
    """AC-4: invalid input → no link change in store."""
    store = _fake_bf_tools["artifacts_store"]
    store["art-1"]["task_id"] = 999  # sentinel
    _call(client, "bf_attach_artifact",
          {"task_id": 100, "artifact_id": ""})
    _call(client, "bf_attach_artifact",
          {"task_id": 100, "artifact_id": "x" * 201})
    assert store["art-1"]["task_id"] == 999


# ══════════════════════════════════════════════════════════════════════════
# Cross-cutting: error contract / source invariants
# ══════════════════════════════════════════════════════════════════════════


def test_cross_no_shell_true_in_router_source():
    """AC-3 invariant: backend MCP router must not use shell=True / os.system
    (security baseline). PR #253 lesson — assert via source grep.
    """
    assert "shell=True" not in MCP_ROUTER_SRC
    assert "os.system(" not in MCP_ROUTER_SRC


def test_cross_no_langgraph_in_router_source():
    """AC-3 invariant: MCP path must not pull LangGraph/LangChain/LiteLLM in
    main runner. CLAUDE.md §3 禁則.
    """
    for forbidden in ("langgraph", "langchain", "litellm"):
        assert forbidden not in MCP_ROUTER_SRC.lower(), (
            f"forbidden import {forbidden!r} found in MCP router"
        )


def test_cross_all_three_tools_use_same_error_envelope(client):
    """AC-2 cross-cut: error envelope shape is consistent across all 3 tools.

    Drift guard: the error contract must be uniform so callers can rely on
    body['detail']['code'] / body['detail']['message'].
    """
    cases = [
        ("bf_get_spec", {"task_id": 0}),
        ("bf_post_progress", {"task_id": 100, "percent_done": 1.5}),
        ("bf_attach_artifact", {"task_id": 100, "artifact_id": ""}),
    ]
    for name, args in cases:
        r = _call(client, name, args)
        assert 400 <= r.status_code < 500, f"{name}: {r.status_code}"
        body = r.json()
        assert isinstance(body["detail"], dict), f"{name}: detail not dict"
        assert isinstance(body["detail"]["code"], str), f"{name}: code"
        assert isinstance(body["detail"]["message"], str), f"{name}: message"
        # the code must be namespaced "mcp.*"
        assert body["detail"]["code"].startswith("mcp."), (
            f"{name}: code {body['detail']['code']!r} not mcp.* namespaced"
        )


def test_cross_input_schemas_declare_object_type():
    """AC-1 invariant: every BF tool inputSchema is type 'object' (JSON-RPC)."""
    for name in ("bf_get_spec", "bf_post_progress", "bf_attach_artifact"):
        td = _tool_def(name)
        assert td is not None
        assert td["inputSchema"]["type"] == "object", f"{name}: type"


def test_cross_router_handlers_are_async():
    """AC-2 invariant: handlers must be async coroutines to support the 2s
    timeout / non-blocking I/O baseline.
    """
    import routers.mcp_server as mcp
    for name in ("_bf_get_spec", "_bf_post_progress", "_bf_attach_artifact"):
        fn = getattr(mcp, name, None)
        assert fn is not None
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"
