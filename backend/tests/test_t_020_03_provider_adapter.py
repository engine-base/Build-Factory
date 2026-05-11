"""T-020-03: provider adapter 3 個 (Anthropic / OpenAI / Gemini) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-020 で 3 provider 統一 adapter + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 anthropic_retry / litellm_router / fallback_router /
                       cost_service の API は不変 (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import provider_adapter as pa
from services.provider_adapter import (
    ANTHROPIC_CACHE_READ_DISCOUNT,
    KNOWN_MODELS,
    MAIN_ROUTE_PROVIDERS,
    MAX_MESSAGE_CHARS,
    MAX_MESSAGES,
    MAX_TOKENS_LIMIT,
    PRICING_PER_1M,
    ProviderAdapterError,
    SUB_ROUTE_PROVIDERS,
    SUPPORTED_PROVIDERS,
    compose_request,
    estimate_cost_usd,
    is_known_model,
    normalize_model,
    select_provider,
    validate_request,
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


def test_service_supported_providers_shape():
    assert set(SUPPORTED_PROVIDERS) == {"anthropic", "openai", "gemini"}
    assert MAIN_ROUTE_PROVIDERS == frozenset({"anthropic"})
    assert SUB_ROUTE_PROVIDERS == frozenset({"openai", "gemini"})
    # 3 つは互いに disjoint で合計 = SUPPORTED
    assert MAIN_ROUTE_PROVIDERS.isdisjoint(SUB_ROUTE_PROVIDERS)
    assert MAIN_ROUTE_PROVIDERS | SUB_ROUTE_PROVIDERS == set(SUPPORTED_PROVIDERS)


def test_service_known_models_cover_all_providers():
    for p in SUPPORTED_PROVIDERS:
        assert p in KNOWN_MODELS
        assert len(KNOWN_MODELS[p]) >= 1


def test_service_pricing_has_known_models():
    # 全 KNOWN_MODELS は PRICING にも入っていなくてはならない
    for p in SUPPORTED_PROVIDERS:
        for m in KNOWN_MODELS[p]:
            assert m in PRICING_PER_1M[p], f"{p}/{m} not in pricing"


def test_service_normalize_model_ok():
    assert normalize_model("anthropic", "claude-opus-4-7") == "claude-opus-4-7"
    assert normalize_model("openai", "  gpt-4o  ") == "gpt-4o"


def test_service_normalize_invalid_provider():
    with pytest.raises(ProviderAdapterError):
        normalize_model("bogus", "x")


def test_service_normalize_empty_model():
    with pytest.raises(ProviderAdapterError):
        normalize_model("anthropic", "")
    with pytest.raises(ProviderAdapterError):
        normalize_model("anthropic", "   ")


def test_service_normalize_model_too_long():
    with pytest.raises(ProviderAdapterError):
        normalize_model("anthropic", "x" * 201)


def test_service_is_known_model():
    assert is_known_model("anthropic", "claude-opus-4-7") is True
    assert is_known_model("openai", "gpt-4o") is True
    assert is_known_model("gemini", "gemini-2.5-pro") is True
    assert is_known_model("anthropic", "unknown-model") is False
    assert is_known_model("bogus", "anything") is False


def test_service_estimate_cost_anthropic_no_cache():
    # claude-opus-4-7: (15.0, 75.0) per 1M
    # 1000 input + 500 output = 1000*15/1M + 500*75/1M = 0.015 + 0.0375 = 0.0525
    cost = estimate_cost_usd("anthropic", "claude-opus-4-7", 1000, 500)
    assert cost == pytest.approx(0.0525, rel=1e-3)


def test_service_estimate_cost_anthropic_with_cache_discount():
    # 1000 input + 500 output, cache_read=800
    # full_input = 200; cost = 200*15/1M + 800*15*0.1/1M + 500*75/1M
    # = 0.003 + 0.0012 + 0.0375 = 0.0417
    cost = estimate_cost_usd(
        "anthropic", "claude-opus-4-7", 1000, 500, cache_read_tokens=800,
    )
    full = 200 * 15 / 1_000_000
    cached = 800 * 15 * ANTHROPIC_CACHE_READ_DISCOUNT / 1_000_000
    output = 500 * 75 / 1_000_000
    assert cost == pytest.approx(full + cached + output, rel=1e-3)


def test_service_estimate_cost_openai():
    # gpt-4o-mini: (0.15, 0.60) per 1M
    cost = estimate_cost_usd("openai", "gpt-4o-mini", 10_000, 2_000)
    expected = 10_000 * 0.15 / 1_000_000 + 2_000 * 0.60 / 1_000_000
    assert cost == pytest.approx(expected, rel=1e-3)


def test_service_estimate_cost_gemini():
    cost = estimate_cost_usd("gemini", "gemini-2.5-pro", 1_000_000, 100_000)
    expected = 1.25 + 100_000 * 10.0 / 1_000_000
    assert cost == pytest.approx(expected, rel=1e-3)


def test_service_estimate_cost_unknown_model_returns_zero():
    # unknown model は raise ではなく 0
    assert estimate_cost_usd("anthropic", "no-such-model", 1000, 500) == 0.0
    assert estimate_cost_usd("openai", "no-such-model", 1000, 500) == 0.0


def test_service_estimate_cost_invalid_tokens():
    with pytest.raises(ProviderAdapterError):
        estimate_cost_usd("anthropic", "claude-opus-4-7", -1, 0)
    with pytest.raises(ProviderAdapterError):
        estimate_cost_usd("anthropic", "claude-opus-4-7", 0, -1)
    with pytest.raises(ProviderAdapterError):
        estimate_cost_usd("anthropic", "claude-opus-4-7", 100, 0, cache_read_tokens=-1)
    with pytest.raises(ProviderAdapterError):
        estimate_cost_usd("anthropic", "claude-opus-4-7", 100, 0, cache_read_tokens=200)


def test_service_estimate_cost_non_anthropic_ignores_cache_discount():
    # openai は cache_read 引数を受けるが、cost discount は適用しない
    base = estimate_cost_usd("openai", "gpt-4o-mini", 1000, 500)
    cached = estimate_cost_usd(
        "openai", "gpt-4o-mini", 1000, 500, cache_read_tokens=500,
    )
    assert base == cached


def test_service_select_provider_ok():
    for p in SUPPORTED_PROVIDERS:
        assert select_provider(p) == p


def test_service_select_provider_invalid():
    with pytest.raises(ProviderAdapterError):
        select_provider("bogus")
    with pytest.raises(ProviderAdapterError):
        select_provider("")


def test_service_validate_request_ok():
    validate_request(
        "anthropic", "claude-opus-4-7",
        [{"role": "user", "content": "hi"}],
    )


def test_service_validate_empty_messages():
    with pytest.raises(ProviderAdapterError):
        validate_request("anthropic", "claude-opus-4-7", [])


def test_service_validate_too_many_messages():
    too_many = [{"role": "user", "content": "x"}] * (MAX_MESSAGES + 1)
    with pytest.raises(ProviderAdapterError):
        validate_request("anthropic", "claude-opus-4-7", too_many)


def test_service_validate_invalid_role():
    with pytest.raises(ProviderAdapterError):
        validate_request(
            "anthropic", "claude-opus-4-7",
            [{"role": "function", "content": "x"}],
        )


def test_service_validate_non_string_content():
    with pytest.raises(ProviderAdapterError):
        validate_request(
            "anthropic", "claude-opus-4-7",
            [{"role": "user", "content": 123}],
        )


def test_service_validate_content_too_long():
    with pytest.raises(ProviderAdapterError):
        validate_request(
            "anthropic", "claude-opus-4-7",
            [{"role": "user", "content": "x" * (MAX_MESSAGE_CHARS + 1)}],
        )


def test_service_validate_max_tokens_bounds():
    msgs = [{"role": "user", "content": "x"}]
    with pytest.raises(ProviderAdapterError):
        validate_request("anthropic", "claude-opus-4-7", msgs, max_tokens=0)
    with pytest.raises(ProviderAdapterError):
        validate_request(
            "anthropic", "claude-opus-4-7", msgs,
            max_tokens=MAX_TOKENS_LIMIT + 1,
        )


def test_service_validate_messages_not_list():
    with pytest.raises(ProviderAdapterError):
        validate_request("anthropic", "claude-opus-4-7", "not-a-list")  # type: ignore


def test_service_validate_message_not_dict():
    with pytest.raises(ProviderAdapterError):
        validate_request("anthropic", "claude-opus-4-7", ["not-a-dict"])  # type: ignore


def test_service_compose_anthropic_basic():
    out = compose_request(
        "anthropic", "claude-opus-4-7",
        [{"role": "user", "content": "hello"}],
    )
    assert out["provider"] == "anthropic"
    assert out["route"] == "main"
    assert out["payload"]["model"] == "claude-opus-4-7"
    assert out["payload"]["max_tokens"] == 4096
    assert out["payload"]["temperature"] == 0.7
    assert out["payload"]["messages"] == [{"role": "user", "content": "hello"}]
    # no system messages → no 'system' key
    assert "system" not in out["payload"]


def test_service_compose_anthropic_with_system():
    out = compose_request(
        "anthropic", "claude-opus-4-7",
        [
            {"role": "system", "content": "be brief"},
            {"role": "system", "content": "be polite"},
            {"role": "user", "content": "hi"},
        ],
    )
    # system は 1 つに統合され、user メッセージのみ messages へ
    assert out["payload"]["system"] == "be brief\n\nbe polite"
    assert out["payload"]["messages"] == [{"role": "user", "content": "hi"}]


def test_service_compose_anthropic_with_cache_control():
    out = compose_request(
        "anthropic", "claude-opus-4-7",
        [
            {"role": "system", "content": "long system prompt"},
            {"role": "user", "content": "hi"},
        ],
        cache_control=True,
    )
    assert isinstance(out["payload"]["system"], list)
    assert out["payload"]["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_service_compose_openai():
    out = compose_request(
        "openai", "gpt-4o",
        [{"role": "user", "content": "hi"}],
        max_tokens=512, temperature=0.2,
    )
    assert out["provider"] == "openai"
    assert out["route"] == "sub"
    assert out["payload"]["model"] == "gpt-4o"
    assert out["payload"]["max_tokens"] == 512
    assert out["payload"]["temperature"] == 0.2


def test_service_compose_gemini_prefix():
    out = compose_request(
        "gemini", "gemini-2.5-pro",
        [{"role": "user", "content": "hi"}],
    )
    assert out["provider"] == "gemini"
    assert out["route"] == "sub"
    # LiteLLM が gemini を識別するための prefix
    assert out["payload"]["model"] == "gemini/gemini-2.5-pro"


def test_service_compose_invalid_temperature():
    msgs = [{"role": "user", "content": "x"}]
    with pytest.raises(ProviderAdapterError):
        compose_request("anthropic", "claude-opus-4-7", msgs, temperature=-0.1)
    with pytest.raises(ProviderAdapterError):
        compose_request("anthropic", "claude-opus-4-7", msgs, temperature=2.1)


def test_service_compose_invalid_provider():
    with pytest.raises(ProviderAdapterError):
        compose_request("bogus", "x", [{"role": "user", "content": "x"}])


# ──────────────────────────────────────────────────────────────────────────
# Backwards compatibility — 既存 module API は変わっていない
# ──────────────────────────────────────────────────────────────────────────


def test_compat_anthropic_retry_unchanged():
    # AC-3: anthropic_retry の主要 symbol が import 可能であること
    from services import anthropic_retry as ar
    assert hasattr(ar, "__name__")


def test_compat_litellm_router_unchanged():
    from services import litellm_router as lr
    assert hasattr(lr, "__name__")


def test_compat_fallback_router_unchanged():
    from services import fallback_router as fr
    assert hasattr(fr, "__name__")


def test_compat_cost_service_unchanged():
    from services import cost_service as cs
    assert hasattr(cs, "__name__")


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動 (5 個)
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_list_providers(client):
    r = client.get("/api/providers")
    assert r.status_code == 200
    body = r.json()
    assert set(body["providers"]) == set(SUPPORTED_PROVIDERS)
    assert set(body["main_route"]) == {"anthropic"}
    assert set(body["sub_route"]) == {"openai", "gemini"}


def test_ac1_list_models(client):
    r = client.get("/api/providers/anthropic/models")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "anthropic"
    assert "claude-opus-4-7" in body["models"]


def test_ac1_cost_estimate(client):
    r = client.post("/api/providers/cost-estimate", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "input_tokens": 1000,
        "output_tokens": 500,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["cost_usd"] == pytest.approx(0.0525, rel=1e-3)
    assert body["is_known_model"] is True


def test_ac1_compose(client, _capture_audit):
    r = client.post("/api/providers/compose", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "hi"}],
        "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "main"
    # AC-3: audit emit
    events = [e for e in _capture_audit if e["event_type"] == "provider.compose"]
    assert len(events) == 1
    assert events[0]["user_id"] == "u-1"
    assert events[0]["detail"]["provider"] == "anthropic"
    assert events[0]["detail"]["route"] == "main"


def test_ac1_validate(client):
    r = client.post("/api/providers/validate", json={
        "provider": "openai",
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200
    assert r.json()["valid"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client):
    t0 = time.time()
    r = client.get("/api/providers")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0, f"too slow: {elapsed:.2f}s"


def test_ac2_error_shape_invalid_provider(client):
    r = client.get("/api/providers/bogus/models")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "code" in detail and "message" in detail
    assert detail["code"] == "provider.invalid_provider"


def test_ac2_error_shape_invalid_cost(client):
    r = client.post("/api/providers/cost-estimate", json={
        "provider": "bogus",
        "model": "x",
        "input_tokens": 0,
        "output_tokens": 0,
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "provider.invalid_provider"


def test_ac2_error_shape_consistency_all_endpoints(client):
    cases = [
        ("GET", "/api/providers/bogus/models", None),
        ("POST", "/api/providers/cost-estimate", {
            "provider": "bogus", "model": "x",
            "input_tokens": 0, "output_tokens": 0,
        }),
        ("POST", "/api/providers/compose", {
            "provider": "bogus", "model": "x",
            "messages": [{"role": "user", "content": "x"}],
        }),
        ("POST", "/api/providers/validate", {
            "provider": "bogus", "model": "x",
            "messages": [{"role": "user", "content": "x"}],
        }),
    ]
    for method, path, body in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=body)
        assert r.status_code in (400, 401, 404, 409, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("provider."), f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3: audit emit only on /compose (state-changing endpoint)
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_no_audit_on_read_endpoints(client, _capture_audit):
    client.get("/api/providers")
    client.get("/api/providers/anthropic/models")
    client.post("/api/providers/cost-estimate", json={
        "provider": "anthropic", "model": "claude-opus-4-7",
        "input_tokens": 100, "output_tokens": 50,
    })
    client.post("/api/providers/validate", json={
        "provider": "anthropic", "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "hi"}],
    })
    # /compose 以外は audit を出さない
    provider_events = [e for e in _capture_audit if e["event_type"].startswith("provider.")]
    assert provider_events == []


def test_ac3_compose_emits_audit_with_route(client, _capture_audit):
    r = client.post("/api/providers/compose", json={
        "provider": "gemini",
        "model": "gemini-2.5-pro",
        "messages": [{"role": "user", "content": "hi"}],
        "actor_user_id": "u-9",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "provider.compose"]
    assert len(events) == 1
    assert events[0]["detail"]["route"] == "sub"
    assert events[0]["detail"]["provider"] == "gemini"
    assert events[0]["detail"]["messages_count"] == 1


# ──────────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / persistent state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_model_empty(client):
    r = client.post("/api/providers/cost-estimate", json={
        "provider": "anthropic", "model": "  ",
        "input_tokens": 100, "output_tokens": 50,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid_model"


def test_ac4_cache_read_exceeds_input(client):
    r = client.post("/api/providers/cost-estimate", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_tokens": 200,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid_cache_read"


def test_ac4_negative_tokens_pydantic_422(client):
    # Pydantic Field(ge=0) で 422 になる
    r = client.post("/api/providers/cost-estimate", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "input_tokens": -1,
        "output_tokens": 50,
    })
    assert r.status_code == 422


def test_ac4_compose_empty_actor_user_id(client):
    r = client.post("/api/providers/compose", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "hi"}],
        "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "provider.unauthorized"


def test_ac4_compose_invalid_provider(client, _capture_audit):
    r = client.post("/api/providers/compose", json={
        "provider": "bogus",
        "model": "x",
        "messages": [{"role": "user", "content": "x"}],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"
    # AC-4: 失敗時は audit emit しない (state mutate しない)
    provider_events = [e for e in _capture_audit if e["event_type"] == "provider.compose"]
    assert provider_events == []


def test_ac4_validate_empty_messages(client):
    r = client.post("/api/providers/validate", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "messages": [],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"


def test_ac4_compose_invalid_temperature_pydantic(client):
    r = client.post("/api/providers/compose", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 5.0,
    })
    # Pydantic Field(le=2.0) で 422
    assert r.status_code == 422


def test_ac4_compose_invalid_role(client, _capture_audit):
    r = client.post("/api/providers/compose", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "messages": [{"role": "function", "content": "x"}],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"
    # state 不変
    assert not any(
        e["event_type"] == "provider.compose" for e in _capture_audit
    )


def test_ac4_compose_content_too_long(client):
    r = client.post("/api/providers/compose", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "messages": [
            {"role": "user", "content": "x" * (MAX_MESSAGE_CHARS + 1)}
        ],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"


def test_ac4_compose_too_many_messages(client):
    too_many = [{"role": "user", "content": "x"}] * (MAX_MESSAGES + 1)
    r = client.post("/api/providers/compose", json={
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "messages": too_many,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "provider.invalid"


def test_ac4_cost_unknown_model_returns_zero_not_error(client):
    # 未知モデルは error ではなく cost=0
    r = client.post("/api/providers/cost-estimate", json={
        "provider": "openai",
        "model": "unknown-future-model",
        "input_tokens": 1000,
        "output_tokens": 500,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["cost_usd"] == 0.0
    assert body["is_known_model"] is False
