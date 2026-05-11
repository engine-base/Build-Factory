"""T-017-02: Langfuse SDK 統合 (observability 拡張) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-017 observability endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 observability.py contract 不変 (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない (Langfuse 未接続でも no-op)
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import observability as obs


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
def _reset_obs(monkeypatch):
    """obs module state を reset."""
    import services.observability as o
    o._LF_CLIENT = None
    o._LF_ENABLED = False
    # env を消して未接続状態に
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    yield


# ──────────────────────────────────────────────────────────────────────────
# Service 単体 (既存 contract 不変確認)
# ──────────────────────────────────────────────────────────────────────────


def test_service_public_api_unchanged():
    """AC-3: 既存 公開 API が module から import 可能."""
    from services import observability as o
    for fn in ("is_enabled", "trace", "span", "log_generation", "observe", "shutdown"):
        assert hasattr(o, fn), f"missing {fn}"


def test_service_is_enabled_false_without_keys():
    assert obs.is_enabled() is False


def test_service_trace_context_yields_none_when_disabled():
    with obs.trace("x") as t:
        assert t is None


def test_service_span_yields_none_with_no_parent():
    with obs.span(None, "x") as s:
        assert s is None


def test_service_log_generation_silent_when_disabled():
    """log_generation は disabled でも raise しない."""
    obs.log_generation(None, name="x", model="m", prompt="p", completion="c")


def test_service_observe_decorator_passthrough():
    @obs.observe(name="test")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_service_shutdown_no_error_when_disabled():
    obs.shutdown()  # no raise


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_status_endpoint(client):
    r = client.get("/api/observability/status")
    assert r.status_code == 200
    body = r.json()
    for k in ("enabled", "langfuse_host",
               "public_key_configured", "secret_key_configured"):
        assert k in body


def test_ac1_trace_endpoint_no_spans(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "test-trace"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "test-trace"
    assert r.json()["recorded"] is False  # langfuse 未接続


def test_ac1_trace_endpoint_with_spans(client):
    r = client.post(
        "/api/observability/trace",
        json={
            "name": "llm-call",
            "user_id": "alice",
            "session_id": "s1",
            "spans": [
                {
                    "name": "gpt-4o call",
                    "model": "gpt-4o",
                    "prompt": "hello",
                    "completion": "world",
                },
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["spans"] == 1


def test_ac1_shutdown_endpoint(client):
    r = client.post("/api/observability/shutdown", json={})
    assert r.status_code == 200
    assert r.json()["flushed"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_status_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/observability/status")
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_trace_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/observability/trace",
        json={"name": "perf"},
    )
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "  "},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "obs.invalid_name"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: backwards compat + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_module_unchanged():
    """既存 services.observability の API が import error なし."""
    from services import observability as o
    assert callable(o.is_enabled)
    assert callable(o.trace)
    assert callable(o.span)
    assert callable(o.log_generation)
    assert callable(o.observe)
    assert callable(o.shutdown)


def test_ac3_trace_emits_audit(client, _capture_audit):
    client.post(
        "/api/observability/trace",
        json={"name": "audit-test", "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "observability.trace.recorded"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["name"] == "audit-test"


def test_ac3_shutdown_emits_audit(client, _capture_audit):
    client.post(
        "/api/observability/shutdown",
        json={"actor_user_id": "bob"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "observability.shutdown"]
    assert len(events) >= 1


def test_ac3_disabled_state_returns_recorded_false(client):
    """langfuse 未接続でも 200 + recorded=False で no-op."""
    r = client.post(
        "/api/observability/trace",
        json={"name": "test", "spans": [
            {"name": "g", "model": "m", "prompt": "p", "completion": "c"},
        ]},
    )
    assert r.status_code == 200
    assert r.json()["recorded"] is False


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_name(client):
    r = client.post("/api/observability/trace", json={"name": " "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "obs.invalid_name"


def test_ac4_long_name(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "x" * 201},
    )
    assert r.status_code == 400


def test_ac4_empty_user_id(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok", "user_id": "  "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "obs.invalid_user_id"


def test_ac4_long_session_id(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok", "session_id": "x" * 201},
    )
    assert r.status_code == 400


def test_ac4_invalid_metadata_type(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok", "metadata": "not-dict"},
    )
    assert r.status_code in (400, 422)


def test_ac4_too_many_metadata_keys(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok",
               "metadata": {f"k{i}": i for i in range(51)}},
    )
    assert r.status_code == 400


def test_ac4_spans_too_many(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok",
               "spans": [
                   {"name": "g", "model": "m", "prompt": "p", "completion": "c"}
               ] * 101},
    )
    assert r.status_code == 400


def test_ac4_invalid_span_name(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok",
               "spans": [
                   {"name": " ", "model": "m", "prompt": "p", "completion": "c"}
               ]},
    )
    assert r.status_code == 400


def test_ac4_invalid_span_model(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok",
               "spans": [
                   {"name": "g", "model": "  ", "prompt": "p", "completion": "c"}
               ]},
    )
    assert r.status_code == 400


def test_ac4_long_prompt(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok",
               "spans": [
                   {"name": "g", "model": "m",
                    "prompt": "x" * 50_001, "completion": "c"}
               ]},
    )
    assert r.status_code == 400


def test_ac4_long_completion(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok",
               "spans": [
                   {"name": "g", "model": "m",
                    "prompt": "p", "completion": "x" * 50_001}
               ]},
    )
    assert r.status_code == 400


def test_ac4_invalid_completion_type(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok",
               "spans": [
                   {"name": "g", "model": "m",
                    "prompt": "p", "completion": 123}
               ]},
    )
    assert r.status_code in (400, 422)


def test_ac4_empty_actor(client):
    r = client.post(
        "/api/observability/trace",
        json={"name": "ok", "actor_user_id": "  "},
    )
    assert r.status_code == 401


def test_ac4_shutdown_empty_actor(client):
    r = client.post(
        "/api/observability/shutdown",
        json={"actor_user_id": "  "},
    )
    assert r.status_code == 401


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/observability/trace", json={"name": " "})
    client.post("/api/observability/trace",
                 json={"name": "ok", "actor_user_id": "  "})
    events = [e for e in _capture_audit
              if e["event_type"] == "observability.trace.recorded"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/observability/trace", {"name": " "}),
        ("POST", "/api/observability/trace", {"name": "x" * 201}),
        ("POST", "/api/observability/trace",
         {"name": "ok", "user_id": " "}),
        ("POST", "/api/observability/trace",
         {"name": "ok", "metadata": {f"k{i}": i for i in range(51)}}),
        ("POST", "/api/observability/trace",
         {"name": "ok", "actor_user_id": " "}),
        ("POST", "/api/observability/shutdown",
         {"actor_user_id": " "}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
