"""T-005-02: 対話 UI + slot 永続化 (slot_admin REFACTOR) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-005 slot 管理 endpoint (list/reset/reset_corrupt/upsert) 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 endpoint contract 不変 + audit emit
  AC-4 UNWANTED      : invalid thread_id / 空 slot_name / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import pytest
from fastapi.testclient import TestClient


@dataclass
class _FakeSlot:
    slot_name: str = ""
    confirmed_value: Optional[str] = None
    rejected: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    history: list = field(default_factory=list)
    is_resolved: bool = False
    goal: Optional[str] = None


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
def _fake_slot_state(monkeypatch):
    """slot_state の DB 関数を in-memory fake で差し替え."""
    import services.slot_state as ss

    store: dict[tuple[int, str], _FakeSlot] = {}
    log: dict[str, int] = {"reset": 0, "reset_corrupt": 0, "upsert": 0}

    async def fake_get(thread_id):
        return [s for (tid, _), s in store.items() if tid == thread_id]

    async def fake_upsert(thread_id, slot_name, **kwargs):
        if thread_id == 9999 and slot_name == "_FORCE_ERR_":
            raise RuntimeError("simulated DB error")
        key = (thread_id, slot_name)
        slot = store.get(key) or _FakeSlot(slot_name=slot_name)
        if kwargs.get("confirmed_value") is not None:
            slot.confirmed_value = kwargs["confirmed_value"]
        if kwargs.get("goal") is not None:
            slot.goal = kwargs["goal"]
        if kwargs.get("is_resolved") is not None:
            slot.is_resolved = kwargs["is_resolved"]
        store[key] = slot
        log["upsert"] += 1

    async def fake_reset(thread_id):
        n = sum(1 for (tid, _) in list(store.keys()) if tid == thread_id)
        for key in list(store.keys()):
            if key[0] == thread_id:
                del store[key]
        log["reset"] += 1
        return n

    async def fake_reset_corrupt(thread_id):
        log["reset_corrupt"] += 1
        return 0

    def fake_is_corrupt(slot):
        return False

    monkeypatch.setattr(ss, "get_slots", fake_get)
    monkeypatch.setattr(ss, "upsert_slot", fake_upsert)
    monkeypatch.setattr(ss, "reset_slots", fake_reset)
    monkeypatch.setattr(ss, "reset_corrupt_slots", fake_reset_corrupt)
    monkeypatch.setattr(ss, "is_corrupt", fake_is_corrupt)

    yield {"store": store, "log": log}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 4 endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_list_endpoint_exists(client):
    r = client.get("/api/slots/list?thread_id=1")
    assert r.status_code == 200
    body = r.json()
    assert body["thread_id"] == 1
    assert "slots" in body
    assert "count" in body


def test_ac1_reset_endpoint_exists(client, _fake_slot_state):
    r = client.post("/api/slots/reset?thread_id=2")
    assert r.status_code == 200
    assert r.json()["thread_id"] == 2


def test_ac1_reset_corrupt_endpoint_exists(client):
    r = client.post("/api/slots/reset_corrupt?thread_id=3")
    assert r.status_code == 200


def test_ac1_upsert_endpoint_exists(client):
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 10, "slot_name": "client-name",
               "confirmed_value": "ENGINE BASE"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["slot_name"] == "client-name"
    assert body["status"] == "upserted"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_upsert_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 11, "slot_name": "test"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_list_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/slots/list?thread_id=1")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 0, "slot_name": "x"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "slots.invalid_thread_id"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 endpoint contract 不変 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_endpoints_still_defined():
    from routers.slot_admin import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    expected = {
        "/api/slots/list",
        "/api/slots/reset",
        "/api/slots/reset_corrupt",
        "/api/slots/upsert",
    }
    assert expected <= paths


def test_ac3_list_response_shape_unchanged(client):
    r = client.get("/api/slots/list?thread_id=99")
    body = r.json()
    for key in ("thread_id", "count", "slots"):
        assert key in body
    assert isinstance(body["slots"], list)


def test_ac3_reset_emits_audit(client, _capture_audit, _fake_slot_state):
    client.post("/api/slots/reset?thread_id=20&actor_user_id=alice")
    events = [e for e in _capture_audit if e["event_type"] == "slots.reset"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["thread_id"] == 20


def test_ac3_upsert_emits_audit(client, _capture_audit):
    client.post(
        "/api/slots/upsert",
        json={"thread_id": 21, "slot_name": "test-slot",
               "actor_user_id": "bob", "confirmed_value": "v"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "slots.upserted"]
    assert len(events) >= 1
    assert events[-1]["detail"]["thread_id"] == 21
    assert events[-1]["detail"]["slot_name"] == "test-slot"


def test_ac3_upsert_then_list_reflects_state(client, _fake_slot_state):
    """AC-3: upsert 後に list で同じ slot が観測できる (state 反映)."""
    client.post(
        "/api/slots/upsert",
        json={"thread_id": 30, "slot_name": "budget", "confirmed_value": "500万円"},
    )
    r = client.get("/api/slots/list?thread_id=30")
    slots = r.json()["slots"]
    assert any(s["slot_name"] == "budget" and s["confirmed_value"] == "500万円" for s in slots)


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_thread_id_upsert_rejected(client, _fake_slot_state):
    before = len(_fake_slot_state["store"])
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 0, "slot_name": "x"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slots.invalid_thread_id"
    after = len(_fake_slot_state["store"])
    assert after == before


def test_ac4_invalid_thread_id_list_rejected(client):
    r = client.get("/api/slots/list?thread_id=0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slots.invalid_thread_id"


def test_ac4_invalid_thread_id_reset_rejected(client, _fake_slot_state):
    before = _fake_slot_state["log"]["reset"]
    r = client.post("/api/slots/reset?thread_id=-1")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slots.invalid_thread_id"
    after = _fake_slot_state["log"]["reset"]
    assert after == before


def test_ac4_empty_slot_name_rejected(client):
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 1, "slot_name": "   "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slots.invalid_slot_name"


def test_ac4_long_slot_name_rejected(client):
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 1, "slot_name": "x" * 201},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slots.slot_name_too_long"


def test_ac4_long_value_rejected(client):
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 1, "slot_name": "ok",
               "confirmed_value": "x" * 5001},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slots.value_too_long"


def test_ac4_long_goal_rejected(client):
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 1, "slot_name": "ok",
               "goal": "x" * 1001},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "slots.goal_too_long"


def test_ac4_empty_actor_upsert_rejected(client):
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 1, "slot_name": "ok", "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "slots.unauthorized"


def test_ac4_empty_actor_reset_rejected(client):
    r = client.post("/api/slots/reset?thread_id=1&actor_user_id=%20%20")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "slots.unauthorized"


def test_ac4_service_error_returns_500_structured(client):
    """service 内部エラーも structured で返す."""
    r = client.post(
        "/api/slots/upsert",
        json={"thread_id": 9999, "slot_name": "_FORCE_ERR_"},
    )
    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "slots.upsert_failed"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_slot_state):
    """AC-4 UNWANTED: rejected request で slots.upserted を emit しない."""
    client.post("/api/slots/upsert", json={"thread_id": 0, "slot_name": "x"})
    client.post("/api/slots/upsert", json={"thread_id": 1, "slot_name": "   "})
    events = [e for e in _capture_audit if e["event_type"] == "slots.upserted"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/slots/upsert", {"thread_id": 0, "slot_name": "x"}),
        ("POST", "/api/slots/upsert", {"thread_id": 1, "slot_name": "   "}),
        ("POST", "/api/slots/upsert", {"thread_id": 1, "slot_name": "x" * 201}),
        ("POST", "/api/slots/upsert",
         {"thread_id": 1, "slot_name": "ok", "confirmed_value": "x" * 5001}),
        ("POST", "/api/slots/upsert",
         {"thread_id": 1, "slot_name": "ok", "actor_user_id": "   "}),
        ("GET", "/api/slots/list?thread_id=0", None),
        ("POST", "/api/slots/reset?thread_id=0", None),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        elif method == "POST" and payload is None:
            r = client.post(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 600, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
