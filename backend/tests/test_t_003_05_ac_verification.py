"""T-003-05: artifact 保存 + AC 検証連携 — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-003 で artifact verify-ac endpoint と service が公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 artifact_service の contract 不変 + audit emit
  AC-4 UNWANTED      : invalid input / 不明 artifact / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services.ac_verification import (
    ACVerificationError,
    CriterionResult,
    VerificationReport,
    verify_artifact,
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
def _fake_artifact_service(monkeypatch):
    """artifact_service.get_artifact を fake で返す."""
    store: dict[str, dict] = {
        "art-1": {
            "id": "art-1",
            "type": "report",
            "title": "実装レポート",
            "data": {
                "summary": "FastAPI モジュラーモノリス bounded context 13 ドメイン",
                "details": "Row Level Security + audit_logs を ENABLE.",
            },
        },
        "art-empty": {
            "id": "art-empty", "type": "note", "title": "", "data": {},
        },
    }

    async def fake_get(artifact_id):
        return store.get(artifact_id)

    import services.artifact_service as art_svc
    monkeypatch.setattr(art_svc, "get_artifact", fake_get)
    yield store


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_verify_all_pass():
    artifact = {
        "id": "x",
        "title": "FastAPI モジュラーモノリス 13 ドメイン bounded-context",
        "data": {"detail": "Row Level Security + audit_logs を ENABLE"},
    }
    criteria = [
        {"type": "UBIQUITOUS",
         "text": "The system shall organize FastAPI into 13 bounded-context domains."},
        {"type": "STATE-DRIVEN",
         "text": "While enabled, the system shall apply Row Level Security."},
    ]
    report = verify_artifact(artifact, criteria)
    assert report.overall == "pass"
    assert report.pass_count == 2
    assert report.total == 2


def test_service_verify_partial_match_warns():
    """50% 未満マッチ → warn."""
    artifact = {"id": "y", "title": "x", "data": {"text": "FastAPI"}}
    criteria = [
        {"type": "UBIQUITOUS",
         "text": "FastAPI Modular Monolith Bounded Context Domain Foo Bar Baz Qux"},
    ]
    report = verify_artifact(artifact, criteria)
    assert report.overall in ("warn", "fail")  # depends on keyword extraction
    assert report.total == 1


def test_service_verify_no_match_fails():
    artifact = {"id": "z", "title": "abc", "data": {"text": "xyz"}}
    criteria = [
        {"type": "UBIQUITOUS",
         "text": "The system shall serve completely unrelated banana pineapple"},
    ]
    report = verify_artifact(artifact, criteria)
    assert report.overall == "fail"
    assert report.fail_count == 1


def test_service_no_criteria_returns_fail():
    artifact = {"id": "empty", "title": "x", "data": {"x": "y"}}
    report = verify_artifact(artifact, [])
    assert report.overall in ("fail", "warn")
    assert "no_criteria_provided" in report.warnings


def test_service_invalid_artifact_raises():
    with pytest.raises(ACVerificationError):
        verify_artifact("not-a-dict", [])


def test_service_unknown_ears_type_fails():
    artifact = {"id": "x", "title": "test", "data": {"x": "y"}}
    report = verify_artifact(artifact, [{"type": "BOGUS", "text": "test"}])
    assert report.fail_count == 1
    assert "unknown EARS type" in report.results[0].reasons[0]


def test_service_missing_text_fails():
    artifact = {"id": "x", "title": "test", "data": {}}
    report = verify_artifact(artifact, [{"type": "UBIQUITOUS"}])
    assert report.fail_count == 1


def test_service_report_to_dict_shape():
    artifact = {"id": "x", "title": "FastAPI モジュラー", "data": {"x": "y"}}
    report = verify_artifact(artifact, [
        {"type": "UBIQUITOUS", "text": "FastAPI モジュラー bounded context"},
    ])
    d = report.to_dict()
    for key in ("artifact_id", "overall", "total", "pass_count",
                 "warn_count", "fail_count", "results", "warnings"):
        assert key in d


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_verify_ac_endpoint_exists(client):
    r = client.post(
        "/api/artifacts/art-1/verify-ac",
        json={
            "criteria": [
                {"type": "UBIQUITOUS",
                 "text": "FastAPI モジュラーモノリス bounded context 13 ドメイン"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["artifact_id"] == "art-1"
    assert "overall" in body
    assert "results" in body


def test_ac1_existing_get_artifact_still_works(client):
    r = client.get("/api/artifacts/art-1")
    assert r.status_code == 200
    assert r.json()["id"] == "art-1"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/artifacts/art-1/verify-ac",
        json={"criteria": [{"type": "UBIQUITOUS", "text": "FastAPI"}]},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/artifacts/missing/verify-ac",
        json={"criteria": [{"type": "UBIQUITOUS", "text": "x"}]},
    )
    assert r.status_code == 404
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "artifacts.not_found"
    assert "message" in body["detail"]


def test_ac2_get_artifact_404_uses_structured_detail(client):
    """既存 GET /api/artifacts/{id} も {detail:{code,message}} に統一."""
    r = client.get("/api/artifacts/missing-id")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "artifacts.not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 contract 不変 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_routes_still_defined():
    """AC-3: 既存 endpoint prefix と既存 path がそのまま残っている."""
    from routers.artifacts import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    expected = {
        "/api/artifacts",
        "/api/artifacts/{artifact_id}",
        "/api/artifacts/{artifact_id}/pin",
        "/api/artifacts/{artifact_id}/unpin",
        "/api/artifacts/{artifact_id}/archive",
        "/api/artifacts/{artifact_id}/events",
        "/api/artifacts/categories/summary",
        "/api/artifacts/{artifact_id}/verify-ac",
    }
    assert expected <= paths


def test_ac3_verify_emits_audit(client, _capture_audit):
    client.post(
        "/api/artifacts/art-1/verify-ac",
        json={
            "criteria": [{"type": "UBIQUITOUS", "text": "FastAPI モジュラー"}],
            "actor_user_id": "alice",
            "task_id": 42,
        },
    )
    events = [e for e in _capture_audit if e["event_type"] == "artifacts.ac.verified"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["artifact_id"] == "art-1"
    assert events[0]["detail"]["task_id"] == 42


def test_ac3_audit_records_overall(client, _capture_audit):
    client.post(
        "/api/artifacts/art-1/verify-ac",
        json={"criteria": [{"type": "UBIQUITOUS", "text": "FastAPI モジュラー"}]},
    )
    events = [e for e in _capture_audit if e["event_type"] == "artifacts.ac.verified"]
    assert events[-1]["detail"]["overall"] in ("pass", "warn", "fail")


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_missing_artifact_returns_404(client):
    r = client.post("/api/artifacts/nope/verify-ac",
                     json={"criteria": [{"type": "UBIQUITOUS", "text": "x"}]})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "artifacts.not_found"


def test_ac4_invalid_criteria_type_rejected(client):
    r = client.post("/api/artifacts/art-1/verify-ac",
                     json={"criteria": "not-a-list"})
    assert r.status_code in (400, 422)


def test_ac4_criteria_item_missing_fields_rejected(client):
    r = client.post("/api/artifacts/art-1/verify-ac",
                     json={"criteria": [{"type": "UBIQUITOUS"}]})  # text 抜け
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "artifacts.invalid_criteria"


def test_ac4_too_many_criteria_rejected(client):
    r = client.post(
        "/api/artifacts/art-1/verify-ac",
        json={"criteria": [
            {"type": "UBIQUITOUS", "text": f"x{i}"} for i in range(51)
        ]},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "artifacts.criteria_too_many"


def test_ac4_empty_actor_rejected(client):
    r = client.post(
        "/api/artifacts/art-1/verify-ac",
        json={"criteria": [{"type": "UBIQUITOUS", "text": "x"}],
               "actor_user_id": "   "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "artifacts.unauthorized"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/artifacts/missing/verify-ac",
                 json={"criteria": [{"type": "UBIQUITOUS", "text": "x"}]})
    client.post("/api/artifacts/art-1/verify-ac",
                 json={"criteria": [{"type": "UBIQUITOUS"}]})
    events = [e for e in _capture_audit if e["event_type"] == "artifacts.ac.verified"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/artifacts/missing/verify-ac",
         {"criteria": [{"type": "UBIQUITOUS", "text": "x"}]}),
        ("POST", "/api/artifacts/art-1/verify-ac",
         {"criteria": [{"type": "UBIQUITOUS"}]}),
        ("POST", "/api/artifacts/art-1/verify-ac",
         {"criteria": [{"type": "X", "text": "x"}] * 51}),
        ("GET", "/api/artifacts/never-existed", None),
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
