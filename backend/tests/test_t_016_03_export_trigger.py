"""T-016-03: export trigger (manual/realtime/hourly/on_completion) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-016 4 trigger type + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + last_fired_at / fire_count 更新
  AC-4 UNWANTED      : invalid input / disabled / not_found は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import export_trigger as et
from services.export_trigger import (
    ExportTriggerError,
    ExportTriggerStore,
    FireResult,
    HOURLY_INTERVAL_SEC,
    SCHEDULED_TYPES,
    Trigger,
    VALID_TRIGGER_TYPES,
    fire_trigger,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    et.reset_store()
    yield
    et.reset_store()


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
def _fake_default_export(monkeypatch):
    sent: list[str] = []

    async def fake(artifact_id):
        sent.append(artifact_id)
        return {"path": f"/tmp/{artifact_id}.md", "size": 100}

    import routers.export_trigger as router_et
    monkeypatch.setattr(router_et, "_default_export", fake)
    yield {"sent": sent}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_valid_trigger_types():
    assert set(VALID_TRIGGER_TYPES) == {
        "manual", "realtime", "hourly", "on_completion",
    }


def test_service_register_basic():
    s = ExportTriggerStore()
    t = s.register("art-1", "manual")
    assert t.artifact_id == "art-1"
    assert t.trigger_type == "manual"
    assert t.enabled is True


def test_service_duplicate_register_raises():
    s = ExportTriggerStore()
    s.register("art-1", "manual")
    with pytest.raises(ExportTriggerError):
        s.register("art-1", "manual")


def test_service_same_artifact_different_type_allowed():
    s = ExportTriggerStore()
    s.register("art-1", "manual")
    t2 = s.register("art-1", "hourly")
    assert t2.trigger_type == "hourly"


def test_service_invalid_artifact_id():
    s = ExportTriggerStore()
    with pytest.raises(ExportTriggerError):
        s.register("  ", "manual")
    with pytest.raises(ExportTriggerError):
        s.register("x" * 201, "manual")


def test_service_invalid_trigger_type():
    s = ExportTriggerStore()
    with pytest.raises(ExportTriggerError):
        s.register("art-1", "bogus")


def test_service_scheduled_at_only_for_scheduled_types():
    s = ExportTriggerStore()
    # hourly は OK
    s.register("art-1", "hourly", scheduled_at=time.time())
    # manual で scheduled_at は禁止
    with pytest.raises(ExportTriggerError):
        s.register("art-2", "manual", scheduled_at=time.time())


def test_service_invalid_scheduled_at():
    s = ExportTriggerStore()
    with pytest.raises(ExportTriggerError):
        s.register("art-1", "hourly", scheduled_at=-1)


def test_service_max_triggers_limit():
    s = ExportTriggerStore(max_triggers=2)
    s.register("a", "manual")
    s.register("b", "manual")
    with pytest.raises(ExportTriggerError):
        s.register("c", "manual")


def test_service_list_filters():
    s = ExportTriggerStore()
    s.register("a", "manual")
    s.register("a", "hourly")
    s.register("b", "manual")
    assert len(s.list(artifact_id="a")) == 2
    assert len(s.list(trigger_type="hourly")) == 1
    assert len(s.list(artifact_id="a", trigger_type="manual")) == 1


def test_service_get_unknown():
    s = ExportTriggerStore()
    assert s.get(99) is None
    assert s.get(0) is None  # invalid id


def test_service_delete():
    s = ExportTriggerStore()
    t = s.register("a", "manual")
    assert s.delete(t.id) is True
    assert s.delete(t.id) is False


def test_service_disable():
    s = ExportTriggerStore()
    t = s.register("a", "manual")
    assert s.disable(t.id) is True
    assert s.get(t.id).enabled is False


def test_service_disable_invalid_id():
    s = ExportTriggerStore()
    with pytest.raises(ExportTriggerError):
        s.disable(0)


def test_service_due_triggers_initial():
    """hourly は last_fired_at=None なら即 due."""
    s = ExportTriggerStore()
    s.register("a", "hourly")
    due = s.due_triggers()
    assert len(due) == 1


def test_service_due_triggers_not_yet():
    """fired 直後は due でない."""
    s = ExportTriggerStore()
    t = s.register("a", "hourly")
    s.mark_fired(t.id)
    due = s.due_triggers()
    assert due == []


def test_service_due_triggers_after_interval():
    s = ExportTriggerStore()
    t = s.register("a", "hourly")
    s.mark_fired(t.id)
    # interval 経過した now を渡す
    later = time.time() + HOURLY_INTERVAL_SEC + 1
    due = s.due_triggers(now=later)
    assert len(due) == 1


def test_service_due_only_hourly():
    s = ExportTriggerStore()
    s.register("a", "manual")
    s.register("b", "realtime")
    s.register("c", "on_completion")
    assert s.due_triggers() == []


def test_service_disabled_not_in_due():
    s = ExportTriggerStore()
    t = s.register("a", "hourly", enabled=False)
    assert s.due_triggers() == []


def test_service_fire_trigger_calls_export_fn():
    sent: list[str] = []

    async def fake(aid):
        sent.append(aid)
        return {"path": "/x"}

    s = ExportTriggerStore()
    et.reset_store()
    # singleton get_store を上書き
    import services.export_trigger as et_mod
    et_mod._store = s

    t = s.register("art-x", "manual")
    result = asyncio.run(fire_trigger(t.id, export_fn=fake))
    assert result.success is True
    assert sent == ["art-x"]
    assert s.get(t.id).fire_count == 1
    assert s.get(t.id).last_fired_at is not None


def test_service_fire_records_failure():
    async def bad(aid):
        raise RuntimeError("boom")

    s = ExportTriggerStore()
    import services.export_trigger as et_mod
    et_mod._store = s

    t = s.register("art-x", "manual")
    result = asyncio.run(fire_trigger(t.id, export_fn=bad))
    assert result.success is False
    assert "boom" in result.detail["error"]
    # fire_count は失敗でも + 1
    assert s.get(t.id).fire_count == 1


def test_service_fire_disabled_raises():
    s = ExportTriggerStore()
    import services.export_trigger as et_mod
    et_mod._store = s

    t = s.register("a", "manual", enabled=False)
    with pytest.raises(ExportTriggerError):
        asyncio.run(fire_trigger(t.id))


def test_service_fire_unknown_raises():
    et.reset_store()
    with pytest.raises(ExportTriggerError):
        asyncio.run(fire_trigger(9999))


def test_service_fire_invalid_id():
    with pytest.raises(ExportTriggerError):
        asyncio.run(fire_trigger(0))


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tt", ["manual", "realtime", "on_completion"])
def test_ac1_register_endpoint_per_type(client, tt):
    r = client.post(
        "/api/export-triggers",
        json={"artifact_id": f"art-{tt}", "trigger_type": tt},
    )
    assert r.status_code == 200
    assert r.json()["trigger_type"] == tt


def test_ac1_register_hourly(client):
    r = client.post(
        "/api/export-triggers",
        json={"artifact_id": "art-h", "trigger_type": "hourly"},
    )
    assert r.status_code == 200


def test_ac1_list_endpoint(client):
    client.post("/api/export-triggers",
                 json={"artifact_id": "art-list", "trigger_type": "manual"})
    r = client.get("/api/export-triggers?artifact_id=art-list")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_ac1_get_endpoint(client):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "art-g", "trigger_type": "manual"}).json()
    r = client.get(f"/api/export-triggers/{res['id']}")
    assert r.status_code == 200


def test_ac1_fire_endpoint(client, _fake_default_export):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "art-f", "trigger_type": "manual"}).json()
    r = client.post(f"/api/export-triggers/{res['id']}/fire", json={})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert "art-f" in _fake_default_export["sent"]


def test_ac1_disable_endpoint(client):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "art-d", "trigger_type": "manual"}).json()
    r = client.post(f"/api/export-triggers/{res['id']}/disable", json={})
    assert r.status_code == 200


def test_ac1_delete_endpoint(client):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "art-del", "trigger_type": "manual"}).json()
    r = client.delete(f"/api/export-triggers/{res['id']}")
    assert r.status_code == 200


def test_ac1_scan_due_endpoint(client, _fake_default_export):
    client.post("/api/export-triggers",
                 json={"artifact_id": "art-due", "trigger_type": "hourly"})
    r = client.post("/api/export-triggers/scan-due", json={})
    assert r.status_code == 200
    assert r.json()["count"] >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_register_within_2s(client):
    t0 = time.perf_counter()
    r = client.post("/api/export-triggers",
                     json={"artifact_id": "perf", "trigger_type": "manual"})
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_fire_within_2s(client, _fake_default_export):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "perf2", "trigger_type": "manual"}).json()
    t0 = time.perf_counter()
    r = client.post(f"/api/export-triggers/{res['id']}/fire", json={})
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/export-triggers",
        json={"artifact_id": "", "trigger_type": "manual"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "export.invalid_artifact_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + state 更新
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_register_emits_audit(client, _capture_audit):
    client.post(
        "/api/export-triggers",
        json={"artifact_id": "audit", "trigger_type": "manual",
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "export.trigger.registered"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"


def test_ac3_fire_updates_state(client, _fake_default_export):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "state", "trigger_type": "manual"}).json()
    client.post(f"/api/export-triggers/{res['id']}/fire", json={})
    r = client.get(f"/api/export-triggers/{res['id']}")
    body = r.json()
    assert body["fire_count"] == 1
    assert body["last_fired_at"] is not None


def test_ac3_fire_emits_audit(client, _capture_audit, _fake_default_export):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "fire", "trigger_type": "manual"}).json()
    client.post(f"/api/export-triggers/{res['id']}/fire",
                 json={"actor_user_id": "bob"})
    events = [e for e in _capture_audit if e["event_type"] == "export.trigger.fired"]
    assert len(events) >= 1


def test_ac3_disable_emits_audit(client, _capture_audit):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "dis", "trigger_type": "manual"}).json()
    client.post(f"/api/export-triggers/{res['id']}/disable", json={})
    events = [e for e in _capture_audit if e["event_type"] == "export.trigger.disabled"]
    assert len(events) >= 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_trigger_type(client):
    r = client.post(
        "/api/export-triggers",
        json={"artifact_id": "x", "trigger_type": "bogus"},
    )
    assert r.status_code == 400


def test_ac4_duplicate_returns_409(client):
    client.post("/api/export-triggers",
                 json={"artifact_id": "dup", "trigger_type": "manual"})
    r = client.post("/api/export-triggers",
                     json={"artifact_id": "dup", "trigger_type": "manual"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "export.duplicate"


def test_ac4_fire_unknown_returns_404(client):
    r = client.post("/api/export-triggers/99999/fire", json={})
    assert r.status_code == 404


def test_ac4_fire_disabled_returns_409(client):
    res = client.post("/api/export-triggers",
                       json={"artifact_id": "x", "trigger_type": "manual"}).json()
    client.post(f"/api/export-triggers/{res['id']}/disable", json={})
    r = client.post(f"/api/export-triggers/{res['id']}/fire", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "export.disabled"


def test_ac4_invalid_id_zero(client):
    r = client.post("/api/export-triggers/0/fire", json={})
    assert r.status_code == 400


def test_ac4_get_unknown(client):
    r = client.get("/api/export-triggers/99999")
    assert r.status_code == 404


def test_ac4_delete_unknown(client):
    r = client.delete("/api/export-triggers/99999")
    assert r.status_code == 404


def test_ac4_disable_unknown(client):
    r = client.post("/api/export-triggers/99999/disable", json={})
    assert r.status_code == 404


def test_ac4_empty_actor(client):
    r = client.post(
        "/api/export-triggers",
        json={"artifact_id": "x", "trigger_type": "manual",
               "actor_user_id": " "},
    )
    assert r.status_code == 401


def test_ac4_list_invalid_trigger_type(client):
    r = client.get("/api/export-triggers?trigger_type=bogus")
    assert r.status_code == 400


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/export-triggers",
                 json={"artifact_id": " ", "trigger_type": "manual"})
    client.post("/api/export-triggers",
                 json={"artifact_id": "x", "trigger_type": "bogus"})
    events = [e for e in _capture_audit
              if e["event_type"] == "export.trigger.registered"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/export-triggers",
         {"artifact_id": " ", "trigger_type": "manual"}),
        ("POST", "/api/export-triggers",
         {"artifact_id": "x", "trigger_type": "bogus"}),
        ("POST", "/api/export-triggers/99999/fire", {}),
        ("POST", "/api/export-triggers/0/fire", {}),
        ("GET", "/api/export-triggers?trigger_type=bogus", None),
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
