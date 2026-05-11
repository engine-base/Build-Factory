"""T-010c-05: crash detection — 4 AC 全網羅.

検出する 3 観点:
  1. heartbeat: 最終 heartbeat から timeout_seconds (default 30 min) 経過
  2. memory: memory_mb が threshold (default 4096) 超え
  3. unexpected_exit: status=exited で exit_code != 0

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c crash detection 3 観点 + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit (heartbeat_timeout / memory_threshold_exceeded /
                       unexpected_exit) + state 遷移ルール強制
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import crash_detector as cd
from services.crash_detector import (
    CrashDetector,
    CrashDetectorError,
    REASON_HEARTBEAT,
    REASON_MEMORY,
    REASON_UNEXPECTED_EXIT,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_detector():
    cd.reset_detector()
    yield
    cd.reset_detector()


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


def test_service_register_records_session():
    d = CrashDetector()
    w = d.register_session(1, heartbeat_timeout=300, memory_limit_mb=2048)
    assert w.session_id == 1
    assert w.status == "running"
    assert w.heartbeat_timeout == 300


def test_service_duplicate_register_raises():
    d = CrashDetector()
    d.register_session(1)
    with pytest.raises(CrashDetectorError):
        d.register_session(1)


def test_service_invalid_session_id():
    d = CrashDetector()
    with pytest.raises(CrashDetectorError):
        d.register_session(0)


def test_service_invalid_heartbeat_timeout():
    d = CrashDetector()
    with pytest.raises(CrashDetectorError):
        d.register_session(1, heartbeat_timeout=0)
    with pytest.raises(CrashDetectorError):
        d.register_session(2, heartbeat_timeout=cd.MAX_HEARTBEAT_TIMEOUT_SEC + 1)


def test_service_invalid_memory_limit():
    d = CrashDetector()
    with pytest.raises(CrashDetectorError):
        d.register_session(1, memory_limit_mb=0)
    with pytest.raises(CrashDetectorError):
        d.register_session(2, memory_limit_mb=cd.MAX_MEMORY_LIMIT_MB + 1)


def test_service_heartbeat_updates_timestamp():
    d = CrashDetector()
    d.register_session(1)
    w0 = d.get_session(1)
    time.sleep(0.01)
    d.record_heartbeat(1, memory_mb=512.5)
    w1 = d.get_session(1)
    assert w1["last_heartbeat_at"] > w0["last_heartbeat_at"]
    assert w1["last_memory_mb"] == 512.5


def test_service_heartbeat_unknown_session_raises():
    d = CrashDetector()
    with pytest.raises(CrashDetectorError):
        d.record_heartbeat(99)


def test_service_heartbeat_negative_memory_raises():
    d = CrashDetector()
    d.register_session(1)
    with pytest.raises(CrashDetectorError):
        d.record_heartbeat(1, memory_mb=-1)


def test_service_record_exit_clean():
    d = CrashDetector()
    d.register_session(1)
    w = d.record_exit(1, 0)
    assert w.status == "exited"
    assert w.exit_code == 0
    assert w.crash_reason is None


def test_service_record_exit_unexpected_sets_reason():
    d = CrashDetector()
    d.register_session(1)
    w = d.record_exit(1, 137)
    assert w.crash_reason == REASON_UNEXPECTED_EXIT
    assert w.exit_code == 137


def test_service_record_exit_unknown_raises():
    d = CrashDetector()
    with pytest.raises(CrashDetectorError):
        d.record_exit(99, 0)


# AC-1: 3 crash detection 観点
def test_service_detect_heartbeat_timeout():
    d = CrashDetector()
    d.register_session(1, heartbeat_timeout=0.01)
    time.sleep(0.02)
    reports = d.detect_crashes()
    assert len(reports) == 1
    assert reports[0].reason == REASON_HEARTBEAT
    assert d.get_session(1)["status"] == "crashed"


def test_service_detect_memory_threshold():
    d = CrashDetector()
    d.register_session(1, memory_limit_mb=100)
    d.record_heartbeat(1, memory_mb=150)
    reports = d.detect_crashes()
    assert len(reports) == 1
    assert reports[0].reason == REASON_MEMORY
    assert d.get_session(1)["status"] == "crashed"


def test_service_detect_unexpected_exit():
    d = CrashDetector()
    d.register_session(1)
    d.record_exit(1, 1)
    reports = d.detect_crashes()
    assert any(r.reason == REASON_UNEXPECTED_EXIT for r in reports)


def test_service_clean_exit_no_crash_report():
    d = CrashDetector()
    d.register_session(1)
    d.record_exit(1, 0)
    reports = d.detect_crashes()
    assert reports == []


def test_service_independent_sessions():
    d = CrashDetector()
    d.register_session(1, heartbeat_timeout=0.01)
    d.register_session(2)
    d.record_heartbeat(2)
    time.sleep(0.02)
    reports = d.detect_crashes()
    # session 1 のみ crash
    assert len(reports) == 1
    assert reports[0].session_id == 1


def test_service_crashed_session_no_heartbeat_update():
    d = CrashDetector()
    d.register_session(1, heartbeat_timeout=0.01)
    time.sleep(0.02)
    d.detect_crashes()  # session 1 が crashed に
    with pytest.raises(CrashDetectorError):
        d.record_heartbeat(1)


def test_service_max_sessions_limit():
    d = CrashDetector(max_sessions=2)
    d.register_session(1)
    d.register_session(2)
    with pytest.raises(CrashDetectorError):
        d.register_session(3)


def test_service_reset_removes_session():
    d = CrashDetector()
    d.register_session(1)
    assert d.reset(1) is True
    assert d.get_session(1) is None
    assert d.reset(1) is False


def test_service_list_sessions():
    d = CrashDetector()
    d.register_session(1)
    d.register_session(2)
    items = d.list_sessions()
    assert len(items) == 2


def test_service_report_to_dict_shape():
    d = CrashDetector()
    d.register_session(1, heartbeat_timeout=0.01)
    time.sleep(0.02)
    reports = d.detect_crashes()
    r = reports[0].to_dict()
    for k in ("session_id", "reason", "detected_at", "detail"):
        assert k in r


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_register_endpoint(client):
    r = client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "heartbeat_timeout": 300, "memory_limit_mb": 2048},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == 1
    assert body["status"] == "running"


def test_ac1_heartbeat_endpoint(client):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    r = client.post(
        "/api/crash-detector/sessions/1/heartbeat",
        json={"memory_mb": 512.5},
    )
    assert r.status_code == 200
    assert r.json()["last_memory_mb"] == 512.5


def test_ac1_exit_endpoint(client):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    r = client.post(
        "/api/crash-detector/sessions/1/exit",
        json={"exit_code": 137},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "exited"


def test_ac1_get_session_endpoint(client):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    r = client.get("/api/crash-detector/sessions/1")
    assert r.status_code == 200
    assert r.json()["session_id"] == 1


def test_ac1_list_endpoint(client):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    client.post("/api/crash-detector/sessions", json={"session_id": 2})
    r = client.get("/api/crash-detector/sessions")
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_ac1_scan_endpoint(client):
    client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "heartbeat_timeout": 0.01},
    )
    time.sleep(0.02)
    r = client.post("/api/crash-detector/scan", json={})
    assert r.status_code == 200
    assert r.json()["count"] >= 1


def test_ac1_reset_endpoint(client):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    r = client.post("/api/crash-detector/sessions/1/reset", json={})
    assert r.status_code == 200
    assert r.json()["reset"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_register_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1},
    )
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_scan_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/crash-detector/scan", json={})
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 0},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "crash.invalid_session_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + state 遷移ルール
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_heartbeat_timeout_emits_audit(client, _capture_audit):
    client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "heartbeat_timeout": 0.01},
    )
    time.sleep(0.02)
    client.post("/api/crash-detector/scan",
                 json={"actor_user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "crash.heartbeat_timeout"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"


def test_ac3_memory_threshold_emits_audit(client, _capture_audit):
    client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "memory_limit_mb": 100},
    )
    client.post(
        "/api/crash-detector/sessions/1/heartbeat",
        json={"memory_mb": 200},
    )
    client.post("/api/crash-detector/scan", json={})
    events = [e for e in _capture_audit
              if e["event_type"] == "crash.memory_threshold_exceeded"]
    assert len(events) >= 1


def test_ac3_unexpected_exit_emits_audit(client, _capture_audit):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    client.post(
        "/api/crash-detector/sessions/1/exit",
        json={"exit_code": 137, "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "crash.unexpected_exit"]
    assert len(events) >= 1
    assert events[0]["detail"]["exit_code"] == 137


def test_ac3_clean_exit_no_audit(client, _capture_audit):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    client.post(
        "/api/crash-detector/sessions/1/exit",
        json={"exit_code": 0},
    )
    events = [e for e in _capture_audit if e["event_type"] == "crash.unexpected_exit"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_session_id_register(client):
    r = client.post("/api/crash-detector/sessions",
                     json={"session_id": 0})
    assert r.status_code == 400


def test_ac4_duplicate_register_returns_409(client):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    r = client.post("/api/crash-detector/sessions", json={"session_id": 1})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "crash.already_registered"


def test_ac4_heartbeat_unknown_returns_404(client):
    r = client.post(
        "/api/crash-detector/sessions/99/heartbeat",
        json={},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "crash.session_not_found"


def test_ac4_heartbeat_crashed_returns_409(client):
    client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "heartbeat_timeout": 0.01},
    )
    time.sleep(0.02)
    client.post("/api/crash-detector/scan", json={})
    r = client.post("/api/crash-detector/sessions/1/heartbeat", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "crash.invalid_state"


def test_ac4_exit_unknown_returns_404(client):
    r = client.post(
        "/api/crash-detector/sessions/99/exit",
        json={"exit_code": 0},
    )
    assert r.status_code == 404


def test_ac4_get_unknown_returns_404(client):
    r = client.get("/api/crash-detector/sessions/99")
    assert r.status_code == 404


def test_ac4_reset_unknown_returns_404(client):
    r = client.post("/api/crash-detector/sessions/99/reset", json={})
    assert r.status_code == 404


def test_ac4_invalid_heartbeat_timeout(client):
    r = client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "heartbeat_timeout": 0},
    )
    assert r.status_code in (400, 422)


def test_ac4_invalid_memory_limit(client):
    r = client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "memory_limit_mb": 0},
    )
    assert r.status_code in (400, 422)


def test_ac4_negative_memory_in_heartbeat(client):
    client.post("/api/crash-detector/sessions", json={"session_id": 1})
    r = client.post(
        "/api/crash-detector/sessions/1/heartbeat",
        json={"memory_mb": -1},
    )
    assert r.status_code in (400, 422)


def test_ac4_empty_actor_register(client):
    r = client.post(
        "/api/crash-detector/sessions",
        json={"session_id": 1, "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "crash.unauthorized"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/crash-detector/sessions",
                 json={"session_id": 0})
    client.post("/api/crash-detector/sessions/99/heartbeat",
                 json={})
    events = [
        e for e in _capture_audit
        if e["event_type"].startswith("crash.")
    ]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/crash-detector/sessions", {"session_id": 0}),
        ("POST", "/api/crash-detector/sessions/99/heartbeat", {}),
        ("POST", "/api/crash-detector/sessions/99/exit",
         {"exit_code": 0}),
        ("GET", "/api/crash-detector/sessions/99", None),
        ("POST", "/api/crash-detector/sessions/99/reset", {}),
        ("POST", "/api/crash-detector/sessions",
         {"session_id": 1, "actor_user_id": "  "}),
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
