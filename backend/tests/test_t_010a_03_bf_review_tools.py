"""T-010a-03: bf_request_review / bf_get_review_feedback — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010a で 2 review tool が登録 + 動作
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + reviewer_loop と統合
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
def _fake_reviewer_loop(monkeypatch):
    """services.reviewer_loop を fake に差し替え."""
    import services.reviewer_loop as rl

    review_store: dict[int, dict] = {}
    next_id = {"v": 50}

    async def fake_request_review(*, task_id, workspace_id=None,
                                    review_kind="task_review",
                                    target_artifact_ids=None, summary=""):
        if review_kind not in ("task_review", "integration"):
            raise ValueError(f"unknown review_kind: {review_kind}")
        rid = next_id["v"]
        next_id["v"] += 1
        rec = {
            "id": rid,
            "task_id": task_id,
            "workspace_id": workspace_id,
            "status": "pending",
            "findings_json": json.dumps({
                "kind": review_kind,
                "target_artifact_ids": target_artifact_ids or [],
            }),
            "iteration": 1,
        }
        review_store[rid] = rec
        return rec

    async def fake_get_review(review_id):
        return review_store.get(review_id)

    monkeypatch.setattr(rl, "request_review", fake_request_review)
    monkeypatch.setattr(rl, "get_review", fake_get_review)
    yield {"store": review_store}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: tool 登録 + 動作
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_two_review_tools_listed(client):
    r = client.post("/mcp/tools/list")
    names = {t["name"] for t in r.json()["tools"]}
    assert {"bf_request_review", "bf_get_review_feedback"} <= names


def test_ac1_request_review_returns_review_id(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 1, "summary": "review me"}},
    )
    assert r.status_code == 200
    parsed = json.loads(r.json()["content"][0]["text"])
    assert parsed["task_id"] == 1
    assert isinstance(parsed["review_id"], int)
    assert parsed["status"] == "pending"


def test_ac1_get_review_feedback_returns_record(client):
    # まず request
    r1 = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 2}},
    )
    rid = json.loads(r1.json()["content"][0]["text"])["review_id"]

    # feedback 取得
    r2 = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_review_feedback",
               "arguments": {"review_id": rid}},
    )
    assert r2.status_code == 200
    parsed = json.loads(r2.json()["content"][0]["text"])
    assert parsed["review_id"] == rid
    assert parsed["task_id"] == 2
    assert parsed["status"] == "pending"


def test_ac1_request_review_with_artifacts(client, _fake_reviewer_loop):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {
                   "task_id": 3,
                   "workspace_id": 5,
                   "target_artifact_ids": ["art-1", "art-2"],
                   "summary": "review with artifacts",
               }},
    )
    assert r.status_code == 200
    parsed = json.loads(r.json()["content"][0]["text"])
    rid = parsed["review_id"]
    findings = json.loads(_fake_reviewer_loop["store"][rid]["findings_json"])
    assert findings["target_artifact_ids"] == ["art-1", "art-2"]


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review", "arguments": {"task_id": 1}},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review", "arguments": {"task_id": 0}},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "mcp.invalid_task_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + reviewer_loop 統合
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_audit_emitted_on_review_request(client, _capture_audit):
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 7},
               "user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "mcp.tool.called"]
    assert any(e["detail"]["name"] == "bf_request_review" for e in events)


def test_ac3_review_store_grows(client, _fake_reviewer_loop):
    before = len(_fake_reviewer_loop["store"])
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review", "arguments": {"task_id": 9}},
    )
    after = len(_fake_reviewer_loop["store"])
    assert after == before + 1


def test_ac3_get_feedback_not_found_returns_404(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_review_feedback",
               "arguments": {"review_id": 99999}},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "mcp.review_not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_task_id_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review", "arguments": {"task_id": 0}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_task_id"


def test_ac4_invalid_workspace_id_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 1, "workspace_id": 0}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_workspace_id"


def test_ac4_invalid_artifact_ids_type_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 1, "target_artifact_ids": "not-list"}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_ids"


def test_ac4_too_many_artifact_ids_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {
                   "task_id": 1,
                   "target_artifact_ids": [f"art-{i}" for i in range(51)],
               }},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_ids"


def test_ac4_empty_artifact_id_in_list_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 1, "target_artifact_ids": ["valid", "  "]}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_artifact_ids"


def test_ac4_long_summary_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 1, "summary": "x" * 4001}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_summary"


def test_ac4_invalid_review_id_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_review_feedback", "arguments": {"review_id": 0}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_review_id"


def test_ac4_missing_review_id_rejected(client):
    r = client.post(
        "/mcp/tools/call",
        json={"name": "bf_get_review_feedback", "arguments": {}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp.invalid_review_id"


def test_ac4_rejected_does_not_mutate_review_store(client, _fake_reviewer_loop):
    """AC-4: reject 時に reviewer_loop.request_review が呼ばれていない."""
    before = len(_fake_reviewer_loop["store"])
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review", "arguments": {"task_id": 0}},
    )
    client.post(
        "/mcp/tools/call",
        json={"name": "bf_request_review",
               "arguments": {"task_id": 1, "summary": "x" * 4001}},
    )
    assert len(_fake_reviewer_loop["store"]) == before


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        {"name": "bf_request_review", "arguments": {"task_id": 0}},
        {"name": "bf_request_review",
         "arguments": {"task_id": 1, "workspace_id": 0}},
        {"name": "bf_request_review",
         "arguments": {"task_id": 1, "target_artifact_ids": "no"}},
        {"name": "bf_request_review",
         "arguments": {"task_id": 1, "summary": "x" * 4001}},
        {"name": "bf_get_review_feedback", "arguments": {"review_id": 0}},
        {"name": "bf_get_review_feedback", "arguments": {"review_id": 99999}},
    ]
    for payload in cases:
        r = client.post("/mcp/tools/call", json=payload)
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
