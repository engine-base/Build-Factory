"""T-009-03: 影響範囲 AI ハイライト — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-009 で highlight endpoint + service 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit
  AC-4 UNWANTED      : invalid input / cycle は 4xx + structured / persistent state 不変
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services.impact_highlight import (
    HighlightedTask,
    HighlightReport,
    ImpactHighlightError,
    compute_highlights,
)


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


@pytest.fixture
def _graph():
    return {}


def _make_loader(graph: dict[int, list[dict]]):
    async def loader(parent_id: int) -> list[dict]:
        return graph.get(parent_id, [])
    return loader


@pytest.fixture(autouse=True)
def _patch_loader(monkeypatch, _graph):
    import routers.impact_highlight as ih
    monkeypatch.setattr(ih, "_default_deps_loader", _make_loader(_graph))
    yield


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_classifies_depth_1_as_high():
    report = {
        "task_id": 1,
        "downstream": [
            {"task_id": 2, "depth": 1, "dep_type": "blocks"},
        ],
    }
    h = compute_highlights(report)
    assert h.high_count == 1
    assert h.highlights[0].severity == "high"
    assert h.highlights[0].suggested_action == "re-test-immediately"


def test_service_classifies_depth_2_3_as_medium():
    report = {
        "task_id": 1,
        "downstream": [
            {"task_id": 3, "depth": 2, "dep_type": "blocks"},
            {"task_id": 4, "depth": 3, "dep_type": "delegates_to"},
        ],
    }
    h = compute_highlights(report)
    assert h.medium_count == 2
    assert all(x.severity == "medium" for x in h.highlights)


def test_service_classifies_depth_4_plus_as_low():
    report = {
        "task_id": 1,
        "downstream": [
            {"task_id": 5, "depth": 4, "dep_type": "blocks"},
            {"task_id": 6, "depth": 7, "dep_type": "reports_to"},
        ],
    }
    h = compute_highlights(report)
    assert h.low_count == 2


def test_service_sorts_severity_high_first():
    report = {
        "task_id": 1,
        "downstream": [
            {"task_id": 10, "depth": 5, "dep_type": "reports_to"},  # low
            {"task_id": 11, "depth": 1, "dep_type": "blocks"},      # high
            {"task_id": 12, "depth": 2, "dep_type": "blocks"},      # medium
        ],
    }
    h = compute_highlights(report)
    severities = [x.severity for x in h.highlights]
    assert severities == ["high", "medium", "low"]


def test_service_groups_by_phase():
    report = {
        "task_id": 1,
        "downstream": [
            {"task_id": 20, "depth": 1, "dep_type": "blocks"},
            {"task_id": 21, "depth": 2, "dep_type": "blocks"},
            {"task_id": 22, "depth": 3, "dep_type": "blocks"},
        ],
    }
    meta = {
        20: {"phase_id": 1, "title": "T20"},
        21: {"phase_id": 1, "title": "T21"},
        22: {"phase_id": 2, "title": "T22"},
    }
    h = compute_highlights(report, tasks_meta=meta)
    assert h.grouped_by_phase == {1: 2, 2: 1}


def test_service_meta_attaches_title_status():
    report = {"task_id": 1, "downstream": [
        {"task_id": 30, "depth": 1, "dep_type": "blocks"},
    ]}
    h = compute_highlights(report, tasks_meta={
        30: {"title": "Critical Fix", "status": "pending"},
    })
    assert h.highlights[0].title == "Critical Fix"
    assert h.highlights[0].status == "pending"


def test_service_invalid_report_raises():
    with pytest.raises(ImpactHighlightError):
        compute_highlights("not-a-dict")


def test_service_invalid_task_id_raises():
    with pytest.raises(ImpactHighlightError):
        compute_highlights({"task_id": 0, "downstream": []})


def test_service_invalid_downstream_raises():
    with pytest.raises(ImpactHighlightError):
        compute_highlights({"task_id": 1, "downstream": "not-list"})


def test_service_empty_downstream_returns_zero():
    h = compute_highlights({"task_id": 1, "downstream": []})
    assert h.total == 0
    assert h.high_count == 0


def test_service_skips_invalid_entries():
    report = {"task_id": 1, "downstream": [
        {"task_id": 1, "depth": 1, "dep_type": "blocks"},  # valid
        {"task_id": 0, "depth": 1},                          # invalid id
        "not-a-dict",                                         # invalid entry
        {"depth": 1},                                          # missing id
    ]}
    h = compute_highlights(report)
    assert h.total == 1


def test_service_to_dict_shape():
    h = compute_highlights({"task_id": 1, "downstream": [
        {"task_id": 2, "depth": 1, "dep_type": "blocks"},
    ]})
    d = h.to_dict()
    for key in ("source_task_id", "total", "high_count", "medium_count",
                 "low_count", "highlights", "grouped_by_phase", "warnings"):
        assert key in d


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_endpoint_exists(client, _graph):
    _graph[1] = [{"to_task_id": 2}]
    _graph[2] = []
    r = client.post("/api/tasks/1/impact/highlight", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["source_task_id"] == 1
    assert "highlights" in body
    assert "high_count" in body


def test_ac1_with_tasks_meta(client, _graph):
    _graph[10] = [{"to_task_id": 11, "dep_type": "blocks"}]
    _graph[11] = []
    r = client.post(
        "/api/tasks/10/impact/highlight",
        json={"tasks_meta": {"11": {"title": "Important", "phase_id": 5}}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["highlights"][0]["title"] == "Important"
    assert body["highlights"][0]["phase_id"] == 5
    assert "5" in body["grouped_by_phase"]


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client, _graph):
    _graph[20] = []
    t0 = time.perf_counter()
    r = client.post("/api/tasks/20/impact/highlight", json={})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/tasks/0/impact/highlight", json={})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "impact.invalid_task_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_emits_audit(client, _graph, _capture_audit):
    _graph[30] = [{"to_task_id": 31, "dep_type": "blocks"}]
    _graph[31] = []
    client.post(
        "/api/tasks/30/impact/highlight",
        json={"actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "tasks.impact.highlighted"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["task_id"] == 30
    assert events[0]["detail"]["high_count"] >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_task_id_rejected(client):
    r = client.post("/api/tasks/0/impact/highlight", json={})
    assert r.status_code == 400


def test_ac4_empty_actor_rejected(client, _graph):
    _graph[40] = []
    r = client.post(
        "/api/tasks/40/impact/highlight",
        json={"actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "impact.unauthorized"


def test_ac4_invalid_max_depth_rejected(client, _graph):
    _graph[41] = []
    r = client.post("/api/tasks/41/impact/highlight", json={"max_depth": 0})
    assert r.status_code in (400, 422)


def test_ac4_invalid_tasks_meta_type_rejected(client):
    r = client.post(
        "/api/tasks/1/impact/highlight",
        json={"tasks_meta": "not-dict"},
    )
    assert r.status_code in (400, 422)


def test_ac4_too_many_tasks_meta_rejected(client):
    r = client.post(
        "/api/tasks/1/impact/highlight",
        json={"tasks_meta": {str(i): {"title": "x"} for i in range(5001)}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "impact.tasks_meta_too_large"


def test_ac4_cycle_returns_409(client, _graph):
    _graph[50] = [{"to_task_id": 51}]
    _graph[51] = [{"to_task_id": 50}]
    r = client.post("/api/tasks/50/impact/highlight", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "impact.cycle_detected"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _graph):
    _graph[60] = []
    client.post("/api/tasks/0/impact/highlight", json={})
    client.post("/api/tasks/60/impact/highlight", json={"actor_user_id": " "})
    events = [e for e in _capture_audit if e["event_type"] == "tasks.impact.highlighted"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _graph):
    _graph[70] = [{"to_task_id": 71}]
    _graph[71] = [{"to_task_id": 70}]  # cycle
    cases = [
        ("POST", "/api/tasks/0/impact/highlight", {}),
        ("POST", "/api/tasks/70/impact/highlight", {}),  # cycle
        ("POST", "/api/tasks/1/impact/highlight",
         {"actor_user_id": "  "}),
        ("POST", "/api/tasks/1/impact/highlight",
         {"tasks_meta": {str(i): {} for i in range(5001)}}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
