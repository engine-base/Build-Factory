"""T-006-03: impact-analysis (downstream task 列挙) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-006 で impact-analysis endpoint + service 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit
  AC-4 UNWANTED      : invalid input / cycle / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services.impact_analyzer import (
    CycleDetectedError,
    ImpactAnalyzerError,
    ImpactReport,
    ImpactedTask,
    compute_impact,
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
    """task graph helper: parent → [children]."""
    return {}


def _make_loader(graph: dict[int, list[dict]]):
    async def loader(parent_id: int) -> list[dict]:
        return graph.get(parent_id, [])
    return loader


@pytest.fixture(autouse=True)
def _patch_default_loader(monkeypatch, _graph):
    """default loader を fake に差し替え (router 経由テスト用)."""
    import routers.impact_analyzer as ia
    monkeypatch.setattr(ia, "_default_deps_loader", _make_loader(_graph))
    yield


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_single_task_no_downstream():
    g = {1: []}
    r = asyncio.run(compute_impact(1, deps_loader=_make_loader(g)))
    assert r.task_id == 1
    assert r.total == 0
    assert r.max_depth == 0


def test_service_simple_chain():
    """1 → 2 → 3 → 4 のチェーン (downstream 3 件)."""
    g = {
        1: [{"to_task_id": 2, "dep_type": "reports_to"}],
        2: [{"to_task_id": 3}],
        3: [{"to_task_id": 4}],
    }
    r = asyncio.run(compute_impact(1, deps_loader=_make_loader(g)))
    assert r.total == 3
    assert r.max_depth == 3
    ids_by_depth = sorted([(t.depth, t.task_id) for t in r.downstream])
    assert ids_by_depth == [(1, 2), (2, 3), (3, 4)]


def test_service_branching():
    """1 → {2, 3} → 4 のような分岐."""
    g = {
        1: [{"to_task_id": 2}, {"to_task_id": 3}],
        2: [{"to_task_id": 4}],
        3: [{"to_task_id": 4}],
    }
    r = asyncio.run(compute_impact(1, deps_loader=_make_loader(g)))
    assert r.total == 3
    task_ids = {t.task_id for t in r.downstream}
    assert task_ids == {2, 3, 4}


def test_service_cycle_detected():
    """1 → 2 → 1 (起点に戻る) は raise."""
    g = {
        1: [{"to_task_id": 2}],
        2: [{"to_task_id": 1}],
    }
    with pytest.raises(CycleDetectedError):
        asyncio.run(compute_impact(1, deps_loader=_make_loader(g)))


def test_service_revisit_does_not_loop():
    """共通子 (1→2, 1→3, 2→4, 3→4) で 4 を 1 回だけ訪問."""
    g = {
        1: [{"to_task_id": 2}, {"to_task_id": 3}],
        2: [{"to_task_id": 4}],
        3: [{"to_task_id": 4}],
        4: [],
    }
    r = asyncio.run(compute_impact(1, deps_loader=_make_loader(g)))
    task_ids = [t.task_id for t in r.downstream]
    assert task_ids.count(4) == 1


def test_service_max_depth_truncates():
    g = {1: [{"to_task_id": 2}], 2: [{"to_task_id": 3}], 3: [{"to_task_id": 4}]}
    r = asyncio.run(compute_impact(1, deps_loader=_make_loader(g), max_depth=2))
    assert any("max_depth_reached" in w for w in r.warnings)


def test_service_loader_failure_warning():
    async def failing_loader(parent_id):
        raise RuntimeError("DB unavailable")

    r = asyncio.run(compute_impact(1, deps_loader=failing_loader))
    assert any("loader_failed" in w for w in r.warnings)
    assert r.total == 0


def test_service_loader_invalid_response():
    async def bad_loader(parent_id):
        return "not-a-list"

    r = asyncio.run(compute_impact(1, deps_loader=bad_loader))
    assert any("loader_invalid_response" in w for w in r.warnings)


def test_service_invalid_task_id():
    async def empty(_):
        return []

    with pytest.raises(ImpactAnalyzerError):
        asyncio.run(compute_impact(0, deps_loader=empty))


def test_service_invalid_max_depth():
    async def empty(_):
        return []

    with pytest.raises(ImpactAnalyzerError):
        asyncio.run(compute_impact(1, deps_loader=empty, max_depth=0))
    with pytest.raises(ImpactAnalyzerError):
        asyncio.run(compute_impact(1, deps_loader=empty, max_depth=101))


def test_service_dep_type_preserved():
    g = {1: [{"to_task_id": 2, "dep_type": "blocks"}]}
    r = asyncio.run(compute_impact(1, deps_loader=_make_loader(g)))
    assert r.downstream[0].dep_type == "blocks"


def test_service_report_to_dict_shape():
    g = {1: [{"to_task_id": 2}]}
    r = asyncio.run(compute_impact(1, deps_loader=_make_loader(g)))
    d = r.to_dict()
    for key in ("task_id", "total", "max_depth", "downstream", "warnings"):
        assert key in d


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_endpoint_exists(client, _graph):
    _graph[1] = [{"to_task_id": 2}]
    _graph[2] = []
    r = client.post("/api/tasks/1/impact", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == 1
    assert body["total"] >= 1


def test_ac1_returns_downstream_list(client, _graph):
    _graph[10] = [{"to_task_id": 20}, {"to_task_id": 21}]
    _graph[20] = [{"to_task_id": 30}]
    r = client.post("/api/tasks/10/impact", json={})
    body = r.json()
    ids = {t["task_id"] for t in body["downstream"]}
    assert ids == {20, 21, 30}


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client, _graph):
    _graph[1] = []
    t0 = time.perf_counter()
    r = client.post("/api/tasks/1/impact", json={})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/tasks/0/impact", json={})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "impact.invalid_task_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_emits_audit(client, _graph, _capture_audit):
    _graph[5] = [{"to_task_id": 6}]
    _graph[6] = []
    client.post("/api/tasks/5/impact", json={"actor_user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "tasks.impact.analyzed"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["task_id"] == 5
    assert events[0]["detail"]["total"] >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_task_id_rejected(client):
    r = client.post("/api/tasks/0/impact", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "impact.invalid_task_id"


def test_ac4_empty_actor_rejected(client, _graph):
    _graph[1] = []
    r = client.post("/api/tasks/1/impact", json={"actor_user_id": "  "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "impact.unauthorized"


def test_ac4_invalid_max_depth_zero_rejected(client, _graph):
    _graph[1] = []
    r = client.post("/api/tasks/1/impact", json={"max_depth": 0})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "impact.invalid_max_depth"


def test_ac4_invalid_max_depth_too_high_rejected(client, _graph):
    _graph[1] = []
    r = client.post("/api/tasks/1/impact", json={"max_depth": 101})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "impact.invalid_max_depth"


def test_ac4_cycle_returns_409(client, _graph):
    _graph[1] = [{"to_task_id": 2}]
    _graph[2] = [{"to_task_id": 1}]
    r = client.post("/api/tasks/1/impact", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "impact.cycle_detected"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _graph):
    _graph[1] = []
    client.post("/api/tasks/0/impact", json={})
    client.post("/api/tasks/1/impact", json={"actor_user_id": "  "})
    events = [e for e in _capture_audit if e["event_type"] == "tasks.impact.analyzed"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _graph):
    _graph[1] = [{"to_task_id": 2}]
    _graph[2] = [{"to_task_id": 1}]  # cycle
    cases = [
        {"path": "/api/tasks/0/impact", "json": {}},
        {"path": "/api/tasks/1/impact", "json": {"max_depth": 0}},
        {"path": "/api/tasks/1/impact", "json": {"max_depth": 101}},
        {"path": "/api/tasks/1/impact", "json": {"actor_user_id": "  "}},
        {"path": "/api/tasks/1/impact", "json": {}},  # cycle
    ]
    for c in cases:
        r = client.post(c["path"], json=c["json"])
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
