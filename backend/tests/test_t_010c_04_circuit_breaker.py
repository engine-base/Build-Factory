"""T-010c-04: circuit breaker (連続失敗 N で auto-block) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c circuit breaker endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit (open/recover/reset) + 状態遷移ルール強制
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import circuit_breaker as cb
from services.circuit_breaker import (
    CircuitBreakerError,
    CircuitBreakerRegistry,
    DEFAULT_FAILURE_THRESHOLD,
    DEFAULT_RECOVER_SECONDS,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_registry():
    cb.reset_registry(failure_threshold=3, recover_seconds=0.05)
    yield
    cb.reset_registry()


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


def test_service_initial_state_is_closed():
    r = CircuitBreakerRegistry(failure_threshold=3)
    s = r.status("svc1")
    assert s["state"] == "closed"
    assert s["consecutive_failures"] == 0


def test_service_threshold_opens_breaker():
    r = CircuitBreakerRegistry(failure_threshold=3)
    for _ in range(3):
        r.record_failure("svc1")
    assert r.status("svc1")["state"] == "open"
    # open 状態では allow=False
    assert r.allow("svc1") is False


def test_service_below_threshold_stays_closed():
    r = CircuitBreakerRegistry(failure_threshold=3)
    r.record_failure("svc1")
    r.record_failure("svc1")
    assert r.status("svc1")["state"] == "closed"


def test_service_success_resets_consecutive():
    r = CircuitBreakerRegistry(failure_threshold=3)
    r.record_failure("svc1")
    r.record_failure("svc1")
    r.record_success("svc1")
    s = r.status("svc1")
    assert s["state"] == "closed"
    assert s["consecutive_failures"] == 0


def test_service_half_open_after_recover():
    r = CircuitBreakerRegistry(failure_threshold=2, recover_seconds=0.05)
    r.record_failure("svc1")
    r.record_failure("svc1")
    assert r.status("svc1")["state"] == "open"
    assert r.allow("svc1") is False
    time.sleep(0.06)
    # recover 経過で half_open に遷移 (allow が True に)
    assert r.allow("svc1") is True
    assert r.status("svc1")["state"] == "half_open"


def test_service_half_open_success_closes():
    r = CircuitBreakerRegistry(failure_threshold=2, recover_seconds=0.05)
    r.record_failure("svc1")
    r.record_failure("svc1")
    time.sleep(0.06)
    r.allow("svc1")  # half_open に遷移
    r.record_success("svc1")
    assert r.status("svc1")["state"] == "closed"


def test_service_half_open_failure_reopens():
    r = CircuitBreakerRegistry(failure_threshold=2, recover_seconds=0.05)
    r.record_failure("svc1")
    r.record_failure("svc1")
    time.sleep(0.06)
    r.allow("svc1")  # half_open
    r.record_failure("svc1")
    assert r.status("svc1")["state"] == "open"


def test_service_independent_targets():
    """target ごとに独立した状態."""
    r = CircuitBreakerRegistry(failure_threshold=2)
    r.record_failure("svc1")
    r.record_failure("svc1")
    assert r.status("svc1")["state"] == "open"
    assert r.status("svc2")["state"] == "closed"


def test_service_reset_removes_breaker():
    r = CircuitBreakerRegistry(failure_threshold=2)
    r.record_failure("svc1")
    r.record_failure("svc1")
    assert r.reset("svc1") is True
    # 新規 = closed default
    assert r.status("svc1")["state"] == "closed"


def test_service_reset_unknown_returns_false():
    r = CircuitBreakerRegistry()
    assert r.reset("never_recorded") is False


def test_service_invalid_threshold():
    with pytest.raises(CircuitBreakerError):
        CircuitBreakerRegistry(failure_threshold=0)
    with pytest.raises(CircuitBreakerError):
        CircuitBreakerRegistry(failure_threshold=1001)


def test_service_invalid_recover_seconds():
    with pytest.raises(CircuitBreakerError):
        CircuitBreakerRegistry(failure_threshold=3, recover_seconds=0)
    with pytest.raises(CircuitBreakerError):
        CircuitBreakerRegistry(failure_threshold=3, recover_seconds=cb.MAX_RECOVER_SECONDS + 1)


def test_service_invalid_target_key():
    r = CircuitBreakerRegistry()
    with pytest.raises(CircuitBreakerError):
        r.record_failure("  ")
    with pytest.raises(CircuitBreakerError):
        r.record_success("")


def test_service_long_target_key_rejected():
    r = CircuitBreakerRegistry()
    with pytest.raises(CircuitBreakerError):
        r.record_failure("x" * 201)


def test_service_max_targets_limit():
    r = CircuitBreakerRegistry(max_targets=2)
    r.record_failure("a")
    r.record_failure("b")
    with pytest.raises(CircuitBreakerError):
        r.record_failure("c")


def test_service_list_breakers():
    r = CircuitBreakerRegistry()
    r.record_failure("a")
    r.record_failure("b")
    items = r.list_breakers()
    assert len(items) == 2
    keys = {it["target_key"] for it in items}
    assert keys == {"a", "b"}


def test_service_state_to_dict_shape():
    r = CircuitBreakerRegistry()
    r.record_failure("a")
    s = r.status("a")
    for k in ("target_key", "state", "consecutive_failures",
               "total_failures", "total_successes", "opened_at",
               "last_event_at"):
        assert k in s


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_failure_endpoint_exists(client):
    r = client.post("/api/circuit-breaker/svc1/failure", json={})
    assert r.status_code == 200
    assert r.json()["consecutive_failures"] == 1


def test_ac1_success_endpoint_exists(client):
    client.post("/api/circuit-breaker/svc1/failure", json={})
    r = client.post("/api/circuit-breaker/svc1/success", json={})
    assert r.status_code == 200
    assert r.json()["consecutive_failures"] == 0


def test_ac1_status_endpoint_exists(client):
    r = client.get("/api/circuit-breaker/svc1")
    assert r.status_code == 200
    assert r.json()["state"] == "closed"


def test_ac1_allow_endpoint_exists(client):
    r = client.get("/api/circuit-breaker/svc1/allow")
    assert r.status_code == 200
    assert r.json()["allowed"] is True


def test_ac1_list_endpoint_exists(client):
    client.post("/api/circuit-breaker/svc1/failure", json={})
    r = client.get("/api/circuit-breaker")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1


def test_ac1_reset_endpoint_exists(client):
    client.post("/api/circuit-breaker/svc1/failure", json={})
    r = client.post("/api/circuit-breaker/svc1/reset", json={})
    assert r.status_code == 200
    assert r.json()["reset"] is True


def test_ac1_configure_endpoint_exists(client):
    r = client.post(
        "/api/circuit-breaker/configure",
        json={"failure_threshold": 5, "recover_seconds": 1.0},
    )
    assert r.status_code == 200
    assert r.json()["failure_threshold"] == 5


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_failure_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/circuit-breaker/svc1/failure", json={})
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_status_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/circuit-breaker/svc1")
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/circuit-breaker/%20/failure", json={})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "circuit.invalid_target_key"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + 状態遷移ルール
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_threshold_open_emits_circuit_opened(client, _capture_audit):
    # threshold=3 を superします (fixture で 3 に設定済み)
    for _ in range(3):
        client.post("/api/circuit-breaker/svc1/failure",
                     json={"actor_user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "circuit.opened"]
    assert len(events) >= 1
    assert events[-1]["detail"]["target_key"] == "svc1"
    assert events[-1]["detail"]["state"] == "open"


def test_ac3_reset_emits_audit(client, _capture_audit):
    client.post("/api/circuit-breaker/svc1/failure", json={})
    client.post("/api/circuit-breaker/svc1/reset",
                 json={"actor_user_id": "bob"})
    events = [e for e in _capture_audit if e["event_type"] == "circuit.reset"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "bob"


def test_ac3_auto_block_via_allow(client):
    """AC-3: 連続失敗で auto-block (allow が False)."""
    for _ in range(3):
        client.post("/api/circuit-breaker/svc1/failure", json={})
    r = client.get("/api/circuit-breaker/svc1/allow")
    assert r.json()["allowed"] is False


def test_ac3_configure_emits_audit(client, _capture_audit):
    client.post(
        "/api/circuit-breaker/configure",
        json={"failure_threshold": 10, "recover_seconds": 30.0,
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "circuit.configured"]
    assert len(events) >= 1
    assert events[0]["detail"]["failure_threshold"] == 10


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_target_key_rejected(client):
    r = client.post("/api/circuit-breaker/%20/failure", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "circuit.invalid_target_key"


def test_ac4_long_target_key_rejected(client):
    long_key = "x" * 201
    r = client.post(f"/api/circuit-breaker/{long_key}/failure", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "circuit.invalid_target_key"


def test_ac4_empty_actor_failure_rejected(client):
    r = client.post(
        "/api/circuit-breaker/svc1/failure",
        json={"actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "circuit.unauthorized"


def test_ac4_empty_actor_success_rejected(client):
    r = client.post(
        "/api/circuit-breaker/svc1/success",
        json={"actor_user_id": "  "},
    )
    assert r.status_code == 401


def test_ac4_reset_unknown_returns_404(client):
    r = client.post("/api/circuit-breaker/never_existed/reset", json={})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "circuit.not_found"


def test_ac4_invalid_failure_threshold_config(client):
    r = client.post(
        "/api/circuit-breaker/configure",
        json={"failure_threshold": 0, "recover_seconds": 30.0},
    )
    assert r.status_code in (400, 422)


def test_ac4_invalid_recover_seconds_config(client):
    r = client.post(
        "/api/circuit-breaker/configure",
        json={"failure_threshold": 3, "recover_seconds": 0},
    )
    assert r.status_code in (400, 422)


def test_ac4_recover_seconds_too_large(client):
    r = client.post(
        "/api/circuit-breaker/configure",
        json={"failure_threshold": 3,
               "recover_seconds": cb.MAX_RECOVER_SECONDS + 1},
    )
    assert r.status_code in (400, 422)


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/circuit-breaker/%20/failure", json={})
    client.post("/api/circuit-breaker/svc1/failure",
                 json={"actor_user_id": "  "})
    events = [
        e for e in _capture_audit
        if e["event_type"] in ("circuit.opened", "circuit.failure",
                                  "circuit.success", "circuit.reset")
    ]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/circuit-breaker/%20/failure", {}),
        ("POST", "/api/circuit-breaker/svc/failure", {"actor_user_id": "  "}),
        ("POST", "/api/circuit-breaker/never/reset", {}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
