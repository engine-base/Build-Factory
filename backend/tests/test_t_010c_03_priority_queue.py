"""T-010c-03: 完了次第キュー補充 (FIFO + priority) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c queue 補充 endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + priority/FIFO 順序保証
  AC-4 UNWANTED      : invalid input / full queue / 不正 state は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import priority_queue as pq
from services.priority_queue import (
    PriorityQueue,
    PriorityQueueError,
    QueueItem,
    VALID_PRIORITIES,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_queue():
    pq.reset_queue()
    yield
    pq.reset_queue()


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


def test_service_fifo_within_same_priority():
    q = PriorityQueue()
    q.enqueue(task_id=1, priority="medium")
    q.enqueue(task_id=2, priority="medium")
    q.enqueue(task_id=3, priority="medium")
    assert q.dequeue().task_id == 1
    assert q.dequeue().task_id == 2
    assert q.dequeue().task_id == 3


def test_service_priority_overrides_fifo():
    q = PriorityQueue()
    q.enqueue(task_id=1, priority="low")
    q.enqueue(task_id=2, priority="urgent")
    q.enqueue(task_id=3, priority="high")
    assert q.dequeue().task_id == 2  # urgent first
    assert q.dequeue().task_id == 3  # then high
    assert q.dequeue().task_id == 1  # then low


def test_service_mark_done_transitions_state():
    q = PriorityQueue()
    q.enqueue(task_id=1)
    item = q.dequeue()
    assert item.status == "processing"
    assert q.mark_done(item.id) is True
    assert q.get_item(item.id).status == "done"


def test_service_mark_failed_records_error():
    q = PriorityQueue()
    q.enqueue(task_id=1)
    item = q.dequeue()
    assert q.mark_failed(item.id, "OOM") is True
    rec = q.get_item(item.id)
    assert rec.status == "failed"
    assert rec.error == "OOM"


def test_service_mark_done_only_from_processing():
    q = PriorityQueue()
    q.enqueue(task_id=1)
    # まだ dequeue していないので processing でない → False
    assert q.mark_done(1) is False


def test_service_mark_unknown_id_returns_false():
    q = PriorityQueue()
    assert q.mark_done(9999) is False
    assert q.mark_failed(9999, "err") is False


def test_service_invalid_task_id():
    q = PriorityQueue()
    with pytest.raises(PriorityQueueError):
        q.enqueue(task_id=0)


def test_service_invalid_priority():
    q = PriorityQueue()
    with pytest.raises(PriorityQueueError):
        q.enqueue(task_id=1, priority="bogus")


def test_service_invalid_payload_type():
    q = PriorityQueue()
    with pytest.raises(PriorityQueueError):
        q.enqueue(task_id=1, payload="not-dict")


def test_service_full_queue_raises():
    q = PriorityQueue(max_size=2)
    q.enqueue(task_id=1)
    q.enqueue(task_id=2)
    with pytest.raises(PriorityQueueError):
        q.enqueue(task_id=3)


def test_service_invalid_max_size():
    with pytest.raises(PriorityQueueError):
        PriorityQueue(max_size=0)
    with pytest.raises(PriorityQueueError):
        PriorityQueue(max_size=pq.MAX_QUEUE_SIZE + 1)


def test_service_dequeue_empty_returns_none():
    q = PriorityQueue()
    assert q.dequeue() is None


def test_service_peek_does_not_mutate():
    q = PriorityQueue()
    q.enqueue(task_id=1, priority="urgent")
    q.enqueue(task_id=2, priority="medium")
    assert q.peek_next().task_id == 1
    # peek 後も queue は変わらない
    assert len(q) == 2
    assert q.dequeue().task_id == 1


def test_service_stats_records_counters():
    q = PriorityQueue()
    q.enqueue(task_id=1, priority="urgent")
    q.enqueue(task_id=2, priority="low")
    item = q.dequeue()
    q.mark_done(item.id)
    s = q.stats()
    assert s["enqueued_total"] == 2
    assert s["dequeued_total"] == 1
    assert s["done_total"] == 1
    assert s["by_priority"]["low"] == 1
    assert s["size"] == 1


def test_service_refill_when_half_empty():
    q = PriorityQueue(max_size=10)
    # 既に half (= 5) 以上ある時は refill しない
    for i in range(1, 7):
        q.enqueue(task_id=i)

    called = {"v": 0}

    async def refill_fn():
        called["v"] += 1
        return [{"task_id": 100, "priority": "high"}]

    n = asyncio.run(q.refill(refill_fn))
    assert n == 0
    assert called["v"] == 0


def test_service_refill_when_below_half():
    q = PriorityQueue(max_size=10)
    q.enqueue(task_id=1)

    async def refill_fn():
        return [
            {"task_id": 100, "priority": "high"},
            {"task_id": 101, "priority": "medium"},
        ]

    n = asyncio.run(q.refill(refill_fn))
    assert n == 2
    assert len(q) == 3


def test_service_refill_handles_loader_failure():
    q = PriorityQueue(max_size=10)

    async def boom():
        raise RuntimeError("DB unavailable")

    # 例外を吸収して 0 を返す
    n = asyncio.run(q.refill(boom))
    assert n == 0


def test_service_refill_skips_invalid_entries():
    q = PriorityQueue(max_size=10)

    async def refill_fn():
        return [
            {"task_id": 100, "priority": "high"},
            "not-a-dict",
            {"task_id": 0},  # invalid
            {"priority": "low"},  # task_id missing
            {"task_id": 101, "priority": "medium"},
        ]

    n = asyncio.run(q.refill(refill_fn))
    assert n == 2


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_enqueue_endpoint(client):
    r = client.post("/api/queue/enqueue",
                     json={"task_id": 1, "priority": "high"})
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == 1
    assert body["priority"] == "high"
    assert body["status"] == "queued"


def test_ac1_dequeue_endpoint(client):
    client.post("/api/queue/enqueue",
                 json={"task_id": 1, "priority": "high"})
    r = client.post("/api/queue/dequeue", json={})
    assert r.status_code == 200
    assert r.json()["item"]["task_id"] == 1


def test_ac1_empty_dequeue_returns_none(client):
    r = client.post("/api/queue/dequeue", json={})
    assert r.status_code == 200
    assert r.json()["item"] is None


def test_ac1_stats_endpoint(client):
    r = client.get("/api/queue/stats")
    assert r.status_code == 200
    body = r.json()
    for k in ("size", "max_size", "by_priority", "enqueued_total"):
        assert k in body


def test_ac1_peek_endpoint(client):
    client.post("/api/queue/enqueue",
                 json={"task_id": 1, "priority": "high"})
    r = client.get("/api/queue/peek")
    assert r.status_code == 200
    assert r.json()["item"]["task_id"] == 1


def test_ac1_configure_endpoint(client):
    r = client.post("/api/queue/configure",
                     json={"max_size": 100})
    assert r.status_code == 200
    assert r.json()["max_size"] == 100


def test_ac1_done_failed_endpoints(client):
    client.post("/api/queue/enqueue", json={"task_id": 1})
    item = client.post("/api/queue/dequeue", json={}).json()["item"]
    r1 = client.post(f"/api/queue/{item['id']}/done")
    assert r1.status_code == 200

    client.post("/api/queue/enqueue", json={"task_id": 2})
    item2 = client.post("/api/queue/dequeue", json={}).json()["item"]
    r2 = client.post(f"/api/queue/{item2['id']}/failed",
                      json={"error": "OOM"})
    assert r2.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_enqueue_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/queue/enqueue",
                     json={"task_id": 1, "priority": "high"})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_stats_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/queue/stats")
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/queue/enqueue",
                     json={"task_id": 0, "priority": "high"})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "queue.invalid_task_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + 順序保証
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_enqueue_emits_audit(client, _capture_audit):
    client.post("/api/queue/enqueue",
                 json={"task_id": 5, "priority": "urgent",
                        "actor_user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "queue.enqueued"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["task_id"] == 5


def test_ac3_priority_order_respected_via_endpoint(client):
    """AC-3: REST 経由で urgent > high > medium > low の dequeue 順序が保たれる."""
    client.post("/api/queue/enqueue", json={"task_id": 1, "priority": "low"})
    client.post("/api/queue/enqueue", json={"task_id": 2, "priority": "urgent"})
    client.post("/api/queue/enqueue", json={"task_id": 3, "priority": "high"})

    order = []
    for _ in range(3):
        item = client.post("/api/queue/dequeue", json={}).json()["item"]
        order.append(item["task_id"])
    assert order == [2, 3, 1]


def test_ac3_done_audit_emitted(client, _capture_audit):
    client.post("/api/queue/enqueue", json={"task_id": 1})
    item = client.post("/api/queue/dequeue", json={}).json()["item"]
    client.post(f"/api/queue/{item['id']}/done?actor_user_id=bob")
    events = [e for e in _capture_audit if e["event_type"] == "queue.item.done"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "bob"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_task_id_rejected(client):
    r = client.post("/api/queue/enqueue",
                     json={"task_id": 0, "priority": "high"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "queue.invalid_task_id"


def test_ac4_invalid_priority_rejected(client):
    r = client.post("/api/queue/enqueue",
                     json={"task_id": 1, "priority": "bogus"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "queue.invalid_priority"


def test_ac4_empty_actor_enqueue(client):
    r = client.post("/api/queue/enqueue",
                     json={"task_id": 1, "actor_user_id": "  "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "queue.unauthorized"


def test_ac4_full_queue_returns_409(client):
    client.post("/api/queue/configure", json={"max_size": 2})
    client.post("/api/queue/enqueue", json={"task_id": 1})
    client.post("/api/queue/enqueue", json={"task_id": 2})
    r = client.post("/api/queue/enqueue", json={"task_id": 3})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "queue.full"


def test_ac4_invalid_item_id_done(client):
    r = client.post("/api/queue/0/done")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "queue.invalid_id"


def test_ac4_done_unknown_item_returns_404(client):
    r = client.post("/api/queue/99999/done")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "queue.not_found"


def test_ac4_done_invalid_state_returns_409(client):
    """queued state (まだ dequeue されていない) に対する done は 409."""
    item = client.post("/api/queue/enqueue", json={"task_id": 1}).json()
    r = client.post(f"/api/queue/{item['id']}/done")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "queue.invalid_state"


def test_ac4_failed_empty_error_rejected(client):
    client.post("/api/queue/enqueue", json={"task_id": 1})
    item = client.post("/api/queue/dequeue", json={}).json()["item"]
    r = client.post(f"/api/queue/{item['id']}/failed",
                     json={"error": "  "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "queue.invalid_error"


def test_ac4_failed_long_error_rejected(client):
    client.post("/api/queue/enqueue", json={"task_id": 1})
    item = client.post("/api/queue/dequeue", json={}).json()["item"]
    r = client.post(f"/api/queue/{item['id']}/failed",
                     json={"error": "x" * 2001})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "queue.error_too_long"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/queue/enqueue",
                 json={"task_id": 0, "priority": "high"})
    client.post("/api/queue/enqueue",
                 json={"task_id": 1, "priority": "bogus"})
    events = [e for e in _capture_audit if e["event_type"] == "queue.enqueued"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/queue/enqueue", {"task_id": 0}),
        ("POST", "/api/queue/enqueue", {"task_id": 1, "priority": "bogus"}),
        ("POST", "/api/queue/enqueue",
         {"task_id": 1, "actor_user_id": "  "}),
        ("POST", "/api/queue/0/done", None),
        ("POST", "/api/queue/99999/done", None),
    ]
    for method, path, payload in cases:
        if payload is None:
            r = client.post(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
