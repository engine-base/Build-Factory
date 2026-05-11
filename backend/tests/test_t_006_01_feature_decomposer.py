"""T-006-01: feature-decomposition AI (Devon) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-006 feature 分解 endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit
  AC-4 UNWANTED      : invalid feature / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services.feature_decomposer import (
    DecompositionResult,
    FeatureDecomposerError,
    SubTask,
    decompose_feature,
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


def test_service_decomposes_simple_feature():
    f = {"id": "F-X1", "title": "サンプル機能", "description": "ボタンとAPI"}
    r = decompose_feature(f)
    assert r.feature_id == "F-X1"
    assert r.total >= 3
    layers = {t.layer for t in r.tasks}
    assert {"BE", "FE", "TST"} <= layers


def test_service_db_feature_has_db_layer():
    f = {"id": "F-Y", "title": "ユーザー登録",
         "description": "新規テーブル + RLS"}
    r = decompose_feature(f)
    assert any(t.layer == "DB" for t in r.tasks)
    # DB は他より前 (deps なし)
    db_task = [t for t in r.tasks if t.layer == "DB"][0]
    assert db_task.deps == []


def test_service_integration_feature_has_ops_layer():
    f = {"id": "F-Z", "title": "Slack 連携",
         "description": "Slack webhook + Bolt"}
    r = decompose_feature(f)
    assert any(t.layer == "OPS" for t in r.tasks)


def test_service_each_task_has_4_ears_ac():
    f = {"id": "F-AC", "title": "AC 検証"}
    r = decompose_feature(f)
    for t in r.tasks:
        ac_types = [c["type"] for c in t.acceptance_criteria]
        assert "UBIQUITOUS" in ac_types
        assert "EVENT-DRIVEN" in ac_types
        assert "STATE-DRIVEN" in ac_types
        assert "UNWANTED" in ac_types
        assert len(t.acceptance_criteria) == 4


def test_service_tst_depends_on_all_others():
    f = {"id": "F-DEP", "title": "依存検証",
         "description": "DB + BE + FE + Slack 連携"}
    r = decompose_feature(f)
    tst = [t for t in r.tasks if t.layer == "TST"][0]
    other_ids = [t.task_id for t in r.tasks if t.layer != "TST"]
    assert set(tst.deps) == set(other_ids)


def test_service_invalid_feature_dict_raises():
    with pytest.raises(FeatureDecomposerError):
        decompose_feature("not-a-dict")


def test_service_missing_id_raises():
    with pytest.raises(FeatureDecomposerError):
        decompose_feature({"title": "x"})


def test_service_missing_title_raises():
    with pytest.raises(FeatureDecomposerError):
        decompose_feature({"id": "F-1"})


def test_service_long_title_raises():
    with pytest.raises(FeatureDecomposerError):
        decompose_feature({"id": "F-1", "title": "x" * 201})


def test_service_long_description_raises():
    with pytest.raises(FeatureDecomposerError):
        decompose_feature({"id": "F-1", "title": "ok",
                            "description": "x" * 4001})


def test_service_empty_description_warns():
    r = decompose_feature({"id": "F-W", "title": "ok"})
    assert "description_empty" in r.warnings


def test_service_to_dict_shape():
    r = decompose_feature({"id": "F-D", "title": "Dict"})
    d = r.to_dict()
    assert d["feature_id"] == "F-D"
    assert "tasks" in d
    assert "total" in d
    assert isinstance(d["tasks"][0]["deps"], list)
    assert isinstance(d["tasks"][0]["acceptance_criteria"], list)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_endpoint_exists(client):
    r = client.post(
        "/api/features/decompose",
        json={"feature": {"id": "F-1", "title": "テスト機能"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feature_id"] == "F-1"
    assert body["total"] >= 3


def test_ac1_returns_tasks_with_4_ac(client):
    r = client.post(
        "/api/features/decompose",
        json={"feature": {"id": "F-AC2", "title": "AC test", "description": "DB / RLS"}},
    )
    body = r.json()
    for t in body["tasks"]:
        assert len(t["acceptance_criteria"]) == 4


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/features/decompose",
        json={"feature": {"id": "F-P", "title": "perf"}},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/features/decompose",
        json={"feature": {"title": "no id"}},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "features.invalid_feature"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_emits_audit(client, _capture_audit):
    client.post(
        "/api/features/decompose",
        json={"feature": {"id": "F-Au", "title": "audit", "description": "RLS migration"},
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "features.decomposed"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["feature_id"] == "F-Au"
    assert events[0]["detail"]["total_tasks"] >= 3
    assert "DB" in events[0]["detail"]["layers"]


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_feature_dict_rejected(client):
    r = client.post("/api/features/decompose", json={"feature": "not-dict"})
    assert r.status_code in (400, 422)


def test_ac4_missing_id_rejected(client):
    r = client.post("/api/features/decompose",
                     json={"feature": {"title": "x"}})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "features.invalid_feature"


def test_ac4_missing_title_rejected(client):
    r = client.post("/api/features/decompose",
                     json={"feature": {"id": "F-1"}})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "features.invalid_feature"


def test_ac4_long_title_rejected(client):
    r = client.post(
        "/api/features/decompose",
        json={"feature": {"id": "F-1", "title": "x" * 201}},
    )
    assert r.status_code == 400


def test_ac4_long_description_rejected(client):
    r = client.post(
        "/api/features/decompose",
        json={"feature": {"id": "F-1", "title": "ok", "description": "x" * 4001}},
    )
    assert r.status_code == 400


def test_ac4_empty_actor_rejected(client):
    r = client.post(
        "/api/features/decompose",
        json={"feature": {"id": "F-1", "title": "x"}, "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "features.unauthorized"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/features/decompose", json={"feature": {"title": "x"}})
    client.post("/api/features/decompose",
                 json={"feature": {"id": "F-1", "title": "x"}, "actor_user_id": "  "})
    events = [e for e in _capture_audit if e["event_type"] == "features.decomposed"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        {"feature": {"title": "x"}},
        {"feature": {"id": "F-1"}},
        {"feature": {"id": "F-1", "title": "x" * 201}},
        {"feature": {"id": "F-1", "title": "x", "description": "x" * 4001}},
        {"feature": {"id": "F-1", "title": "x"}, "actor_user_id": "  "},
    ]
    for payload in cases:
        r = client.post("/api/features/decompose", json=payload)
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
