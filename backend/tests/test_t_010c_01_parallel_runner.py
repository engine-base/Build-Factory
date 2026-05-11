"""T-010c-01: asyncio.Semaphore + Queue (task_executor 拡張) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c で並列実行 service + observation endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + audit emit
  AC-3 STATE-DRIVEN  : 既存 task_executor API 不変 (backwards compat) + service 高 cov
  AC-4 UNWANTED      : invalid max_concurrency / task_id / 空 actor は 4xx +
                       structured / persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import parallel_task_runner as ptr
from services.parallel_task_runner import (
    ParallelRunner,
    ParallelRunnerError,
    RunnerClosedError,
    TaskOutcome,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_runner():
    ptr.reset_runner(max_concurrency=4)
    yield
    ptr.reset_runner(max_concurrency=4)


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


def test_service_invalid_max_concurrency():
    with pytest.raises(ParallelRunnerError):
        ParallelRunner(max_concurrency=0)
    with pytest.raises(ParallelRunnerError):
        ParallelRunner(max_concurrency=101)


def test_service_submit_runs_coro():
    r = ParallelRunner(max_concurrency=2)

    async def coro():
        return 42

    outcome = asyncio.run(r.submit(1, coro))
    assert outcome.status == "done"
    assert outcome.result == 42
    assert outcome.task_id == 1


def test_service_submit_records_error():
    r = ParallelRunner(max_concurrency=1)

    async def boom():
        raise RuntimeError("oops")

    outcome = asyncio.run(r.submit(1, boom))
    assert outcome.status == "failed"
    assert outcome.error == "oops"


def test_service_duplicate_task_id_raises():
    r = ParallelRunner(max_concurrency=1)

    async def coro():
        return None

    asyncio.run(r.submit(1, coro))
    with pytest.raises(ParallelRunnerError):
        asyncio.run(r.submit(1, coro))


def test_service_closed_runner_rejects():
    async def run():
        r = ParallelRunner(max_concurrency=1)
        await r.close()

        async def coro():
            return 1

        with pytest.raises(RunnerClosedError):
            await r.submit(1, coro)

    asyncio.run(run())


def test_service_invalid_task_id_raises():
    r = ParallelRunner(max_concurrency=1)

    async def coro():
        return None

    with pytest.raises(ParallelRunnerError):
        asyncio.run(r.submit(0, coro))


def test_service_invalid_coro_fn_raises():
    r = ParallelRunner(max_concurrency=1)
    with pytest.raises(ParallelRunnerError):
        asyncio.run(r.submit(1, "not-callable"))


def test_service_concurrency_limit_respected():
    """max_concurrency=2 で 4 件投入したら同時実行は最大 2 件."""
    async def run():
        r = ParallelRunner(max_concurrency=2)
        peak = {"v": 0}
        running = {"v": 0}

        async def slow(tid):
            running["v"] += 1
            peak["v"] = max(peak["v"], running["v"])
            await asyncio.sleep(0.05)
            running["v"] -= 1
            return tid

        outcomes = await asyncio.gather(*[
            r.submit(i, (lambda i=i: slow(i))) for i in range(1, 5)
        ])
        return peak["v"], outcomes

    peak, outs = asyncio.run(run())
    assert peak <= 2
    assert all(o.status == "done" for o in outs)


def test_service_stats_progression():
    r = ParallelRunner(max_concurrency=2)
    s0 = r.stats()
    assert s0["queued"] == 0
    assert s0["running"] == 0
    assert s0["max_concurrency"] == 2

    async def coro():
        return 1

    asyncio.run(r.submit(1, coro))
    s1 = r.stats()
    assert s1["done"] == 1
    assert s1["total_submitted"] == 1


def test_service_get_outcome_and_list():
    r = ParallelRunner(max_concurrency=1)

    async def coro():
        return "x"

    asyncio.run(r.submit(5, coro))
    o = r.get_outcome(5)
    assert o is not None and o.task_id == 5
    assert len(r.list_outcomes()) == 1
    assert r.get_outcome(9999) is None


def test_service_outcome_to_dict_shape():
    r = ParallelRunner(max_concurrency=1)

    async def coro():
        return 1

    out = asyncio.run(r.submit(1, coro))
    d = out.to_dict()
    for k in ("task_id", "status", "error", "queued_at",
               "started_at", "completed_at", "duration_sec"):
        assert k in d


def test_service_duration_sec_positive():
    r = ParallelRunner(max_concurrency=1)

    async def coro():
        await asyncio.sleep(0.01)
        return 1

    out = asyncio.run(r.submit(1, coro))
    assert out.duration_sec is not None
    assert out.duration_sec >= 0.005


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_stats_endpoint_exists(client):
    r = client.get("/api/parallel-runner/stats")
    assert r.status_code == 200
    body = r.json()
    for k in ("max_concurrency", "queued", "running", "done", "failed"):
        assert k in body


def test_ac1_configure_endpoint_exists(client):
    r = client.post(
        "/api/parallel-runner/configure",
        json={"max_concurrency": 8},
    )
    assert r.status_code == 200
    assert r.json()["max_concurrency"] == 8


def test_ac1_submit_noop_endpoint_exists(client):
    r = client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 1, "delay_ms": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == 1
    assert body["status"] == "done"


def test_ac1_get_outcome_endpoint(client):
    client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 2, "delay_ms": 0},
    )
    r = client.get("/api/parallel-runner/outcomes/2")
    assert r.status_code == 200
    assert r.json()["task_id"] == 2


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_stats_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/parallel-runner/stats")
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_submit_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 10, "delay_ms": 50},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_configure_emits_audit(client, _capture_audit):
    client.post(
        "/api/parallel-runner/configure",
        json={"max_concurrency": 6, "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "parallel.runner.configured"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["max_concurrency"] == 6


def test_ac2_submit_emits_audit(client, _capture_audit):
    client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 20, "delay_ms": 0, "actor_user_id": "bob"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "parallel.task.submitted"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "bob"
    assert events[0]["detail"]["task_id"] == 20


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 task_executor 不変 (backwards compat)
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_task_executor_module_intact():
    """AC-3: 既存 workers.task_executor が import error 無く読める."""
    from workers import task_executor as te
    assert hasattr(te, "process_pending_tasks")
    assert hasattr(te, "execute_task_now")


def test_ac3_existing_workflow_service_module_intact():
    """AC-3: 既存 services.workflow_service が無傷."""
    import services.workflow_service as ws  # noqa: F401


def test_ac3_state_reflected_via_stats(client):
    """AC-3: submit 後に stats で total_submitted が増える."""
    before = client.get("/api/parallel-runner/stats").json()["total_submitted"]
    client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 30, "delay_ms": 0},
    )
    after = client.get("/api/parallel-runner/stats").json()["total_submitted"]
    assert after == before + 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_max_concurrency_zero(client):
    r = client.post(
        "/api/parallel-runner/configure",
        json={"max_concurrency": 0},
    )
    assert r.status_code in (400, 422)


def test_ac4_invalid_max_concurrency_too_high(client):
    r = client.post(
        "/api/parallel-runner/configure",
        json={"max_concurrency": 101},
    )
    assert r.status_code in (400, 422)


def test_ac4_invalid_task_id_submit(client):
    r = client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 0},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "parallel.invalid_task_id"


def test_ac4_invalid_task_id_outcome(client):
    r = client.get("/api/parallel-runner/outcomes/0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "parallel.invalid_task_id"


def test_ac4_outcome_not_found(client):
    r = client.get("/api/parallel-runner/outcomes/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "parallel.outcome_not_found"


def test_ac4_empty_actor_configure(client):
    r = client.post(
        "/api/parallel-runner/configure",
        json={"max_concurrency": 4, "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "parallel.unauthorized"


def test_ac4_empty_actor_submit(client):
    r = client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 50, "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "parallel.unauthorized"


def test_ac4_long_delay_rejected(client):
    r = client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 1, "delay_ms": 10001},
    )
    assert r.status_code in (400, 422)


def test_ac4_duplicate_task_id_returns_400(client):
    client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 60, "delay_ms": 0},
    )
    r = client.post(
        "/api/parallel-runner/submit-noop",
        json={"task_id": 60, "delay_ms": 0},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "parallel.submit_failed"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/parallel-runner/submit-noop", json={"task_id": 0})
    client.post("/api/parallel-runner/configure",
                 json={"max_concurrency": 4, "actor_user_id": "  "})
    bad = [
        e for e in _capture_audit
        if e["event_type"] in ("parallel.task.submitted", "parallel.runner.configured")
    ]
    assert len(bad) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/parallel-runner/configure",
         {"max_concurrency": 4, "actor_user_id": " "}),
        ("POST", "/api/parallel-runner/submit-noop", {"task_id": 0}),
        ("GET", "/api/parallel-runner/outcomes/0", None),
        ("GET", "/api/parallel-runner/outcomes/99999", None),
        ("POST", "/api/parallel-runner/submit-noop",
         {"task_id": 1, "actor_user_id": " "}),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
