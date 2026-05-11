"""T-008-03: ゲート達成判定 + auto unlock — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-008 で gate 評価 endpoint + service 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + auto_unlock 時の atomic 操作
  AC-4 UNWANTED      : invalid input / phase not_found / gate 未達成での unlock は 4xx +
                       structured かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services.phase_gate_evaluator import (
    GateCriterionResult,
    GateEvaluation,
    GateRule,
    PhaseGateError,
    auto_unlock_next,
    evaluate_gate,
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
def _fake_phase_service(monkeypatch):
    """phase_service を fake in-memory に置換."""
    import services.phase_service as ps

    phases: dict[int, dict] = {
        1: {"id": 1, "project_id": 1, "phase_no": 1, "name": "Phase 1",
            "status": "in_progress"},
        2: {"id": 2, "project_id": 1, "phase_no": 2, "name": "Phase 2",
            "status": "not_started"},
    }
    completed: list[int] = []
    started: list[int] = []

    async def fake_get(phase_id):
        return phases.get(phase_id)

    async def fake_complete(phase_id):
        p = phases.get(phase_id)
        if p is None:
            raise ps.PhaseNotFound(f"not found: {phase_id}")
        p["status"] = "completed"
        completed.append(phase_id)
        return p

    async def fake_start(phase_id):
        p = phases.get(phase_id)
        if p is None:
            raise ps.PhaseNotFound(f"not found: {phase_id}")
        p["status"] = "in_progress"
        started.append(phase_id)
        return p

    monkeypatch.setattr(ps, "get_phase", fake_get)
    monkeypatch.setattr(ps, "complete_phase", fake_complete)
    monkeypatch.setattr(ps, "start_phase", fake_start)
    yield {"phases": phases, "completed": completed, "started": started}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_gate_all_pass():
    phase = {"id": 1}
    tasks = [{"status": "completed"}] * 5
    ev = evaluate_gate(phase, tasks)
    assert ev.overall == "pass"
    assert ev.completion_rate == 1.0
    assert ev.can_auto_unlock is True


def test_service_gate_fail_incomplete():
    phase = {"id": 1}
    tasks = [{"status": "completed"}] * 3 + [{"status": "pending"}] * 2
    ev = evaluate_gate(phase, tasks)
    assert ev.overall == "fail"
    assert ev.completion_rate == 0.6
    assert ev.can_auto_unlock is False
    assert ev.blockers


def test_service_gate_required_artifacts():
    phase = {"id": 1}
    tasks = [{"status": "completed"}]
    rule = GateRule(required_artifact_types=["spec_doc", "design"])
    artifacts = [{"type": "spec_doc"}]  # design 欠落
    ev = evaluate_gate(phase, tasks, rules=rule, artifacts=artifacts)
    assert ev.overall == "fail"
    assert any("design" in b for b in ev.blockers)


def test_service_gate_required_approvals():
    phase = {"id": 1}
    tasks = [{"status": "completed"}]
    rule = GateRule(required_reviewer_approvals=2)
    ev = evaluate_gate(phase, tasks, rules=rule, approvals=1)
    assert ev.overall == "fail"


def test_service_gate_allow_partial_warns():
    phase = {"id": 1}
    tasks = [{"status": "completed"}] * 4 + [{"status": "pending"}]
    rule = GateRule(min_completion_rate=1.0, allow_partial=True)
    ev = evaluate_gate(phase, tasks, rules=rule)
    assert ev.overall == "warn"
    # warn は can_auto_unlock=False (pass のみ unlock 可)
    assert ev.can_auto_unlock is False


def test_service_gate_empty_tasks():
    phase = {"id": 1}
    ev = evaluate_gate(phase, [])
    assert ev.completion_rate == 0.0
    assert ev.total_tasks == 0


def test_service_invalid_phase_raises():
    with pytest.raises(PhaseGateError):
        evaluate_gate("not-dict", [])


def test_service_invalid_phase_id():
    with pytest.raises(PhaseGateError):
        evaluate_gate({"id": 0}, [])


def test_service_invalid_tasks():
    with pytest.raises(PhaseGateError):
        evaluate_gate({"id": 1}, "not-list")


def test_service_invalid_rules():
    with pytest.raises(PhaseGateError):
        GateRule(min_completion_rate=1.5).validate()
    with pytest.raises(PhaseGateError):
        GateRule(required_reviewer_approvals=-1).validate()


def test_service_auto_unlock_next_only_current():
    called: dict[str, int] = {}

    async def complete_fn(pid):
        called["complete"] = pid
        return {"id": pid, "status": "completed"}

    async def start_fn(pid):
        called["start"] = pid
        return {"id": pid, "status": "in_progress"}

    result = asyncio.run(auto_unlock_next(
        1, None, complete_fn=complete_fn, start_fn=start_fn,
    ))
    assert called == {"complete": 1}
    assert result["next_started"] is None


def test_service_auto_unlock_same_id_raises():
    async def fn(_):
        return {}

    with pytest.raises(PhaseGateError):
        asyncio.run(auto_unlock_next(1, 1, complete_fn=fn, start_fn=fn))


def test_service_evaluation_to_dict_shape():
    ev = evaluate_gate({"id": 1}, [{"status": "completed"}])
    d = ev.to_dict()
    for key in ("phase_id", "overall", "completion_rate", "total_tasks",
                 "completed_tasks", "blockers", "criteria", "can_auto_unlock"):
        assert key in d


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_evaluate_gate_endpoint_exists(client):
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [{"status": "completed"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["evaluation"]["phase_id"] == 1
    assert body["evaluation"]["overall"] == "pass"


def test_ac1_with_custom_rules(client):
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={
            "tasks": [{"status": "completed"}] * 9 + [{"status": "pending"}],
            "rules": {"min_completion_rate": 0.8},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["evaluation"]["overall"] == "pass"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/phases/1/evaluate-gate", json={"tasks": []})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/phases/0/evaluate-gate", json={"tasks": []})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "invalid_phase_no"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + auto_unlock atomic
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_evaluation_emits_audit(client, _capture_audit):
    client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [{"status": "completed"}], "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "phases.gate.evaluated"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["phase_id"] == 1
    assert events[0]["detail"]["overall"] == "pass"


def test_ac3_auto_unlock_marks_complete_and_starts_next(client, _fake_phase_service):
    """AC-3: auto_unlock で current → completed, next → in_progress."""
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={
            "tasks": [{"status": "completed"}] * 3,
            "auto_unlock": True,
            "next_phase_id": 2,
            "actor_user_id": "alice",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["unlocked"]["completed_id"] == 1
    assert body["unlocked"]["next_started_id"] == 2
    # state mutate 確認
    assert 1 in _fake_phase_service["completed"]
    assert 2 in _fake_phase_service["started"]


def test_ac3_auto_unlock_no_next_only_completes(client, _fake_phase_service):
    """next_phase_id 無しの auto_unlock は complete のみ."""
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [{"status": "completed"}], "auto_unlock": True},
    )
    assert r.status_code == 200
    assert r.json()["unlocked"]["next_started_id"] is None
    assert 1 in _fake_phase_service["completed"]


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_phase_id_rejected(client):
    r = client.post("/api/phases/0/evaluate-gate", json={"tasks": []})
    assert r.status_code == 400


def test_ac4_phase_not_found(client):
    r = client.post("/api/phases/99999/evaluate-gate", json={"tasks": []})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "phase_not_found"


def test_ac4_empty_actor_rejected(client):
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [], "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "unauthorized"


def test_ac4_negative_approvals_rejected(client):
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [], "approvals": -1},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_approvals"


def test_ac4_invalid_min_completion_rate_rejected(client):
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [], "rules": {"min_completion_rate": 1.5}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "gate_evaluation_invalid"


def test_ac4_too_many_tasks_rejected(client):
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [{"status": "completed"}] * 5001},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tasks_too_many"


def test_ac4_invalid_next_phase_id_rejected(client):
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={"tasks": [{"status": "completed"}],
               "auto_unlock": True, "next_phase_id": 0},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_next_phase_id"


def test_ac4_auto_unlock_when_gate_fails_returns_409(client, _fake_phase_service):
    """AC-4 UNWANTED: gate 未達成での auto_unlock は 409 + state mutate なし."""
    r = client.post(
        "/api/phases/1/evaluate-gate",
        json={
            "tasks": [{"status": "pending"}],  # 0% → fail
            "auto_unlock": True,
            "next_phase_id": 2,
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "gate_not_passed"
    # mutate なし
    assert 1 not in _fake_phase_service["completed"]
    assert 2 not in _fake_phase_service["started"]


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_phase_service):
    """AC-4: 失敗時に evaluation audit emit なし."""
    client.post("/api/phases/0/evaluate-gate", json={"tasks": []})
    client.post("/api/phases/99999/evaluate-gate", json={"tasks": []})
    events = [e for e in _capture_audit if e["event_type"] == "phases.gate.evaluated"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        {"path": "/api/phases/0/evaluate-gate", "json": {"tasks": []}},
        {"path": "/api/phases/99999/evaluate-gate", "json": {"tasks": []}},
        {"path": "/api/phases/1/evaluate-gate",
         "json": {"tasks": [], "actor_user_id": "  "}},
        {"path": "/api/phases/1/evaluate-gate",
         "json": {"tasks": [], "approvals": -1}},
        {"path": "/api/phases/1/evaluate-gate",
         "json": {"tasks": [{"status": "pending"}],
                   "auto_unlock": True, "next_phase_id": 2}},
    ]
    for c in cases:
        r = client.post(c["path"], json=c["json"])
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
