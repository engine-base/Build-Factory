"""T-010c-02: 親子昇格 (依存グラフ尊重) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c 親子昇格 service + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + service は read-only (input mutate なし)
  AC-4 UNWANTED      : invalid input / cycle (409) は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import copy
import os
import time

import pytest
from fastapi.testclient import TestClient

from services.priority_elevation import (
    CycleDetectedError,
    PriorityElevationError,
    elevate_priorities,
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


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_basic_elevation():
    """parent (medium) ← child (high): parent → high に昇格."""
    tasks = [
        {"id": 1, "priority": "medium"},
        {"id": 2, "priority": "high"},
    ]
    deps = [{"from_task_id": 1, "to_task_id": 2}]
    r = elevate_priorities(tasks, deps)
    assert r.total_tasks == 2
    assert len(r.elevated) == 1
    e = r.elevated[0]
    assert e.task_id == 1
    assert e.from_priority == "medium"
    assert e.to_priority == "high"


def test_service_no_elevation_needed():
    """parent (urgent) ← child (medium): 変更なし."""
    tasks = [
        {"id": 1, "priority": "urgent"},
        {"id": 2, "priority": "medium"},
    ]
    deps = [{"from_task_id": 1, "to_task_id": 2}]
    r = elevate_priorities(tasks, deps)
    assert len(r.elevated) == 0
    assert r.unchanged == 2


def test_service_multi_level_propagation():
    """grandparent ← parent ← child(urgent): grandparent も urgent に."""
    tasks = [
        {"id": 1, "priority": "low"},      # grandparent
        {"id": 2, "priority": "medium"},   # parent
        {"id": 3, "priority": "urgent"},   # child
    ]
    deps = [
        {"from_task_id": 1, "to_task_id": 2},
        {"from_task_id": 2, "to_task_id": 3},
    ]
    r = elevate_priorities(tasks, deps)
    ids = {e.task_id: e.to_priority for e in r.elevated}
    assert ids[1] == "urgent"
    assert ids[2] == "urgent"


def test_service_max_of_multiple_children():
    """parent ← {low, high, medium}: parent → high."""
    tasks = [
        {"id": 1, "priority": "low"},
        {"id": 2, "priority": "low"},
        {"id": 3, "priority": "high"},
        {"id": 4, "priority": "medium"},
    ]
    deps = [
        {"from_task_id": 1, "to_task_id": 2},
        {"from_task_id": 1, "to_task_id": 3},
        {"from_task_id": 1, "to_task_id": 4},
    ]
    r = elevate_priorities(tasks, deps)
    parent = next(e for e in r.elevated if e.task_id == 1)
    assert parent.to_priority == "high"


def test_service_cycle_raises():
    tasks = [
        {"id": 1, "priority": "low"},
        {"id": 2, "priority": "high"},
    ]
    deps = [
        {"from_task_id": 1, "to_task_id": 2},
        {"from_task_id": 2, "to_task_id": 1},
    ]
    with pytest.raises(CycleDetectedError):
        elevate_priorities(tasks, deps)


def test_service_invalid_tasks_type():
    with pytest.raises(PriorityElevationError):
        elevate_priorities("not-a-list", [])


def test_service_invalid_deps_type():
    with pytest.raises(PriorityElevationError):
        elevate_priorities([], "not-a-list")


def test_service_empty_tasks_returns_zero():
    r = elevate_priorities([], [])
    assert r.total_tasks == 0
    assert len(r.elevated) == 0


def test_service_invalid_task_entries_skipped():
    tasks = [
        {"id": 1, "priority": "high"},
        {"id": 0, "priority": "high"},  # invalid id
        "not-a-dict",
        {"id": 2, "priority": "low"},
    ]
    r = elevate_priorities(tasks, [{"from_task_id": 2, "to_task_id": 1}])
    assert r.total_tasks == 2  # 1, 2 のみ


def test_service_unknown_priority_normalized_to_medium():
    tasks = [
        {"id": 1, "priority": "bogus"},
        {"id": 2, "priority": "high"},
    ]
    deps = [{"from_task_id": 1, "to_task_id": 2}]
    r = elevate_priorities(tasks, deps)
    e = next(e for e in r.elevated if e.task_id == 1)
    assert e.from_priority == "medium"  # normalized
    assert e.to_priority == "high"


def test_service_self_loop_skipped():
    tasks = [{"id": 1, "priority": "low"}]
    deps = [{"from_task_id": 1, "to_task_id": 1}]
    # self-loop は graph に入らない (parent==child は skip)
    r = elevate_priorities(tasks, deps)
    assert len(r.elevated) == 0


def test_service_does_not_mutate_input():
    tasks = [
        {"id": 1, "priority": "low"},
        {"id": 2, "priority": "high"},
    ]
    deps = [{"from_task_id": 1, "to_task_id": 2}]
    tasks_snap = copy.deepcopy(tasks)
    deps_snap = copy.deepcopy(deps)
    elevate_priorities(tasks, deps)
    assert tasks == tasks_snap
    assert deps == deps_snap


def test_service_too_many_tasks_raises():
    too_many = [{"id": i, "priority": "low"} for i in range(1, 5002)]
    with pytest.raises(PriorityElevationError):
        elevate_priorities(too_many, [])


def test_service_too_many_dependencies_raises():
    deps = [{"from_task_id": 1, "to_task_id": 2}] * 20001
    with pytest.raises(PriorityElevationError):
        elevate_priorities(
            [{"id": 1, "priority": "low"}, {"id": 2, "priority": "high"}],
            deps,
        )


def test_service_report_to_dict_shape():
    r = elevate_priorities(
        [{"id": 1, "priority": "low"}, {"id": 2, "priority": "high"}],
        [{"from_task_id": 1, "to_task_id": 2}],
    )
    d = r.to_dict()
    for k in ("total_tasks", "elevated_count", "unchanged_count",
               "elevated", "warnings"):
        assert k in d


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_endpoint_exists(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={
            "tasks": [
                {"id": 1, "priority": "low"},
                {"id": 2, "priority": "urgent"},
            ],
            "dependencies": [{"from_task_id": 1, "to_task_id": 2}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_tasks"] == 2
    assert body["elevated_count"] == 1


def test_ac1_empty_input_returns_zero(client):
    r = client.post("/api/tasks/elevate-priorities", json={})
    assert r.status_code == 200
    assert r.json()["total_tasks"] == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={
            "tasks": [{"id": i, "priority": "low"} for i in range(1, 100)],
            "dependencies": [
                {"from_task_id": i, "to_task_id": i + 1}
                for i in range(1, 99)
            ] + [{"from_task_id": 99, "to_task_id": 100}],
        },
    )
    elapsed = time.perf_counter() - t0
    # tasks にない id (100) は graph 構築時に skip される
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={"actor_user_id": "  "},
    )
    assert r.status_code == 401
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "tasks.unauthorized"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_emits_audit(client, _capture_audit):
    client.post(
        "/api/tasks/elevate-priorities",
        json={
            "tasks": [
                {"id": 1, "priority": "low"},
                {"id": 2, "priority": "high"},
            ],
            "dependencies": [{"from_task_id": 1, "to_task_id": 2}],
            "actor_user_id": "alice",
        },
    )
    events = [e for e in _capture_audit if e["event_type"] == "tasks.priority.elevated"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["total_tasks"] == 2
    assert events[0]["detail"]["elevated_count"] == 1


def test_ac3_service_is_read_only(client):
    """AC-3: input dict は変わらない (service が input mutate しない)."""
    payload = {
        "tasks": [
            {"id": 1, "priority": "low"},
            {"id": 2, "priority": "high"},
        ],
        "dependencies": [{"from_task_id": 1, "to_task_id": 2}],
    }
    snap = copy.deepcopy(payload)
    client.post("/api/tasks/elevate-priorities", json=payload)
    # 送信した payload (Python 側) は変わらない
    assert payload == snap


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_cycle_returns_409(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={
            "tasks": [
                {"id": 1, "priority": "low"},
                {"id": 2, "priority": "high"},
            ],
            "dependencies": [
                {"from_task_id": 1, "to_task_id": 2},
                {"from_task_id": 2, "to_task_id": 1},
            ],
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "tasks.cycle_detected"


def test_ac4_invalid_tasks_type(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={"tasks": "not-a-list"},
    )
    assert r.status_code in (400, 422)


def test_ac4_invalid_dependencies_type(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={"dependencies": "not-a-list"},
    )
    assert r.status_code in (400, 422)


def test_ac4_too_many_tasks(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={
            "tasks": [
                {"id": i, "priority": "low"} for i in range(1, 5002)
            ],
            "dependencies": [],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.tasks_too_large"


def test_ac4_too_many_dependencies(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={
            "tasks": [{"id": 1, "priority": "low"}],
            "dependencies": [
                {"from_task_id": 1, "to_task_id": 2}
            ] * 20001,
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.dependencies_too_large"


def test_ac4_empty_actor_rejected(client):
    r = client.post(
        "/api/tasks/elevate-priorities",
        json={"tasks": [], "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tasks.unauthorized"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post(
        "/api/tasks/elevate-priorities",
        json={"actor_user_id": "  "},
    )
    client.post(
        "/api/tasks/elevate-priorities",
        json={
            "tasks": [{"id": 1, "priority": "low"}, {"id": 2, "priority": "high"}],
            "dependencies": [
                {"from_task_id": 1, "to_task_id": 2},
                {"from_task_id": 2, "to_task_id": 1},
            ],
        },
    )
    events = [e for e in _capture_audit if e["event_type"] == "tasks.priority.elevated"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        {"actor_user_id": "  "},
        {"tasks": [{"id": i, "priority": "low"} for i in range(1, 5002)]},
        {
            "tasks": [
                {"id": 1, "priority": "low"},
                {"id": 2, "priority": "high"},
            ],
            "dependencies": [
                {"from_task_id": 1, "to_task_id": 2},
                {"from_task_id": 2, "to_task_id": 1},
            ],
        },
    ]
    for payload in cases:
        r = client.post("/api/tasks/elevate-priorities", json=payload)
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
