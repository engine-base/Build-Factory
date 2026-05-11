"""T-007-02: task_list view (table + sort + 一括操作) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-007 list-view + bulk-update endpoint
  AC-2 EVENT-DRIVEN  : UI 操作 → backend state 反映 + 2 秒以内
  AC-3 STATE-DRIVEN  : audit_logs emit + RLS は migration
  AC-4 UNWANTED      : invalid filter / sort / updates / actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services.task_list_view import (
    BulkUpdateResult,
    Pagination,
    TaskListViewError,
    bulk_update,
    filter_and_sort,
    paginate,
    validate_bulk_updates,
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


@pytest.fixture(autouse=True)
def _fake_db(monkeypatch):
    """default loader/updater を fake に置換."""
    import routers.task_list_view as tlv

    tasks_store: list[dict] = [
        {"id": 1, "title": "Setup", "status": "completed",
         "priority": "high", "assigned_to": 10, "project_id": 1,
         "created_at": "2026-01-01"},
        {"id": 2, "title": "Design", "status": "in_progress",
         "priority": "medium", "assigned_to": 11, "project_id": 1,
         "created_at": "2026-01-02"},
        {"id": 3, "title": "Implement", "status": "pending",
         "priority": "high", "assigned_to": 10, "project_id": 2,
         "created_at": "2026-01-03"},
        {"id": 4, "title": "Test", "status": "pending",
         "priority": "low", "assigned_to": None, "project_id": 1,
         "created_at": "2026-01-04"},
    ]
    update_log: list[dict] = []

    async def fake_load(*, status, assigned_to, project_id):
        return [dict(t) for t in tasks_store]

    async def fake_update(task_id, updates):
        if task_id == 999:
            raise RuntimeError("simulated update failure")
        for t in tasks_store:
            if t["id"] == task_id:
                t.update(updates)
                update_log.append({"task_id": task_id, **updates})
                return t
        raise RuntimeError(f"task not found: {task_id}")

    monkeypatch.setattr(tlv, "_default_load_tasks", fake_load)
    monkeypatch.setattr(tlv, "_default_update_task", fake_update)
    yield {"store": tasks_store, "update_log": update_log}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_filter_by_status():
    tasks = [{"id": 1, "status": "completed"},
             {"id": 2, "status": "pending"}]
    out = filter_and_sort(tasks, status="completed", sort_by="id", sort_order="asc")
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_service_sort_asc_desc():
    tasks = [{"id": 1, "created_at": "2026-01-01"},
             {"id": 2, "created_at": "2026-01-03"},
             {"id": 3, "created_at": "2026-01-02"}]
    asc = filter_and_sort(tasks, sort_order="asc")
    assert [t["id"] for t in asc] == [1, 3, 2]
    desc = filter_and_sort(tasks, sort_order="desc")
    assert [t["id"] for t in desc] == [2, 3, 1]


def test_service_invalid_sort_by():
    with pytest.raises(TaskListViewError):
        filter_and_sort([], sort_by="bogus")


def test_service_invalid_sort_order():
    with pytest.raises(TaskListViewError):
        filter_and_sort([], sort_order="random")


def test_service_invalid_status():
    with pytest.raises(TaskListViewError):
        filter_and_sort([], status="bogus_status")


def test_service_paginate_basic():
    items = [{"id": i} for i in range(1, 11)]
    p = paginate(items, page=2, page_size=3)
    assert p.total == 10
    assert p.total_pages == 4
    assert [t["id"] for t in p.items] == [4, 5, 6]


def test_service_paginate_empty():
    p = paginate([], page=1, page_size=10)
    assert p.total == 0
    assert p.total_pages == 0
    assert p.items == []


def test_service_paginate_invalid():
    with pytest.raises(TaskListViewError):
        paginate([], page=0)
    with pytest.raises(TaskListViewError):
        paginate([], page=1, page_size=0)
    with pytest.raises(TaskListViewError):
        paginate([], page=1, page_size=501)


def test_service_validate_updates_rejects_unknown_field():
    with pytest.raises(TaskListViewError):
        validate_bulk_updates({"title": "x"})  # title is not in VALID_BULK_FIELDS


def test_service_validate_updates_rejects_invalid_status():
    with pytest.raises(TaskListViewError):
        validate_bulk_updates({"status": "bogus"})


def test_service_validate_updates_rejects_invalid_priority():
    with pytest.raises(TaskListViewError):
        validate_bulk_updates({"priority": "super-high"})


def test_service_bulk_update_partial_failure():
    update_log: list[int] = []

    async def fake_update(tid, updates):
        if tid == 2:
            raise RuntimeError("simulated")
        update_log.append(tid)
        return {"task_id": tid, **updates}

    result = asyncio.run(bulk_update(
        [1, 2, 3], {"status": "completed"}, update_fn=fake_update,
    ))
    assert result.total == 3
    assert result.updated == [1, 3]
    assert len(result.failed) == 1
    assert result.failed[0]["task_id"] == 2


def test_service_bulk_update_empty_ids_raises():
    async def f(t, u):
        return {}

    with pytest.raises(TaskListViewError):
        asyncio.run(bulk_update([], {"status": "completed"}, update_fn=f))


def test_service_bulk_update_duplicate_ids_raises():
    async def f(t, u):
        return {}

    with pytest.raises(TaskListViewError):
        asyncio.run(bulk_update([1, 1, 2], {"status": "completed"}, update_fn=f))


def test_service_bulk_update_too_many_raises():
    async def f(t, u):
        return {}

    with pytest.raises(TaskListViewError):
        asyncio.run(bulk_update(
            list(range(1, 202)), {"status": "completed"}, update_fn=f,
        ))


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_list_view_endpoint_exists(client):
    r = client.get("/api/task-list/view")
    assert r.status_code == 200
    body = r.json()
    for key in ("items", "total", "page", "page_size", "total_pages"):
        assert key in body


def test_ac1_bulk_update_endpoint_exists(client, _fake_db):
    r = client.post(
        "/api/task-list/bulk-update",
        json={"task_ids": [1, 2], "updates": {"status": "completed"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success_count"] == 2
    assert body["failure_count"] == 0


def test_ac1_sort_by_id_asc(client):
    r = client.get("/api/task-list/view?sort_by=id&sort_order=asc")
    body = r.json()
    ids = [t["id"] for t in body["items"]]
    assert ids == sorted(ids)


def test_ac1_filter_by_status(client):
    r = client.get("/api/task-list/view?status=pending")
    body = r.json()
    for t in body["items"]:
        assert t["status"] == "pending"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: UI 操作 → backend state 反映 + 2 秒以内
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_bulk_update_reflects_state(client, _fake_db):
    """AC-2: POST 後 GET で同じ status が観測できる."""
    client.post(
        "/api/task-list/bulk-update",
        json={"task_ids": [3], "updates": {"status": "in_progress"}},
    )
    r = client.get("/api/task-list/view")
    item = next(t for t in r.json()["items"] if t["id"] == 3)
    assert item["status"] == "in_progress"


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/task-list/view")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_bulk_update_within_2s(client, _fake_db):
    t0 = time.perf_counter()
    r = client.post("/api/task-list/bulk-update",
                     json={"task_ids": [1], "updates": {"priority": "low"}})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/task-list/bulk-update", json={"task_ids": [], "updates": {}})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "tasks.invalid_task_ids"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_bulk_update_emits_audit(client, _fake_db, _capture_audit):
    client.post(
        "/api/task-list/bulk-update",
        json={
            "task_ids": [1, 2], "updates": {"status": "completed"},
            "actor_user_id": "alice",
        },
    )
    events = [e for e in _capture_audit if e["event_type"] == "tasks.bulk.updated"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["success_count"] == 2
    assert "status" in events[0]["detail"]["fields"]


def test_ac3_partial_failure_recorded_in_audit(client, _fake_db, _capture_audit):
    """999 は fake で常に fail. partial 結果でも audit 1 件 + failure_count に反映."""
    client.post(
        "/api/task-list/bulk-update",
        json={"task_ids": [1, 999], "updates": {"priority": "low"}},
    )
    events = [e for e in _capture_audit if e["event_type"] == "tasks.bulk.updated"]
    assert events[-1]["detail"]["success_count"] == 1
    assert events[-1]["detail"]["failure_count"] == 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_task_ids_rejected(client, _fake_db):
    before = len(_fake_db["update_log"])
    r = client.post("/api/task-list/bulk-update",
                     json={"task_ids": [], "updates": {"status": "completed"}})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.invalid_task_ids"
    after = len(_fake_db["update_log"])
    assert before == after


def test_ac4_empty_updates_rejected(client):
    r = client.post("/api/task-list/bulk-update",
                     json={"task_ids": [1], "updates": {}})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.invalid_updates"


def test_ac4_invalid_update_field_rejected(client):
    r = client.post(
        "/api/task-list/bulk-update",
        json={"task_ids": [1], "updates": {"title": "no"}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.invalid_updates"


def test_ac4_invalid_status_value_rejected(client):
    r = client.post(
        "/api/task-list/bulk-update",
        json={"task_ids": [1], "updates": {"status": "bogus"}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.invalid_updates"


def test_ac4_too_many_task_ids_rejected(client):
    r = client.post(
        "/api/task-list/bulk-update",
        json={"task_ids": list(range(1, 202)),
               "updates": {"status": "completed"}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.bulk_too_large"


def test_ac4_empty_actor_rejected(client):
    r = client.post(
        "/api/task-list/bulk-update",
        json={"task_ids": [1], "updates": {"status": "completed"},
               "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tasks.unauthorized"


def test_ac4_invalid_sort_by_rejected(client):
    r = client.get("/api/task-list/view?sort_by=bogus")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.invalid_list_view"


def test_ac4_invalid_sort_order_rejected(client):
    r = client.get("/api/task-list/view?sort_order=random")
    assert r.status_code == 400


def test_ac4_invalid_assigned_to_rejected(client):
    r = client.get("/api/task-list/view?assigned_to=0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks.invalid_assigned_to"


def test_ac4_invalid_project_id_rejected(client):
    r = client.get("/api/task-list/view?project_id=-1")
    assert r.status_code in (400, 422)


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/task-list/bulk-update",
                 json={"task_ids": [], "updates": {}})
    client.post("/api/task-list/bulk-update",
                 json={"task_ids": [1], "updates": {}})
    events = [e for e in _capture_audit if e["event_type"] == "tasks.bulk.updated"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/task-list/bulk-update",
         {"task_ids": [], "updates": {"status": "completed"}}),
        ("POST", "/api/task-list/bulk-update",
         {"task_ids": [1], "updates": {}}),
        ("POST", "/api/task-list/bulk-update",
         {"task_ids": [1], "updates": {"title": "x"}}),
        ("POST", "/api/task-list/bulk-update",
         {"task_ids": [1], "updates": {"status": "bogus"}}),
        ("POST", "/api/task-list/bulk-update",
         {"task_ids": [1], "updates": {"status": "completed"},
          "actor_user_id": "  "}),
        ("GET", "/api/task-list/view?sort_by=bogus", None),
        ("GET", "/api/task-list/view?assigned_to=0", None),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
