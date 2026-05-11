"""T-020-04: BYOK + Anthropic prompt cache (cache_control: ephemeral) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-020 BYOK + prompt cache
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 provider_adapter API 不変 + audit emit
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       平文 API key は API response に含めない /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from services import byok_store as bs
from services.byok_store import (
    BYOKError,
    BYOKStore,
    MAX_CACHE_BREAKPOINTS,
    MAX_KEYS_PER_USER,
    MAX_KEY_LEN,
    PROVIDER_KEY_PREFIXES,
    build_anthropic_cached_payload,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    bs.reset_store()
    yield
    bs.reset_store()


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


def _valid_key(provider: str) -> str:
    prefixes = PROVIDER_KEY_PREFIXES[provider]
    return f"{prefixes[0]}testkey1234567890abcd"


# ──────────────────────────────────────────────────────────────────────────
# BYOKStore 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_set_and_get_round_trip():
    s = BYOKStore()
    plain = _valid_key("anthropic")
    rec = s.set_key("u-1", "anthropic", plain)
    assert rec.user_id == "u-1"
    assert rec.provider == "anthropic"
    assert rec.key_version == 1
    assert rec.masked_preview.startswith("sk-ant-")
    assert plain not in rec.masked_preview
    # round-trip
    got = s.get_decrypted_key("u-1", "anthropic")
    assert got == plain


def test_service_to_dict_no_plaintext():
    s = BYOKStore()
    plain = _valid_key("openai")
    rec = s.set_key("u-1", "openai", plain)
    d = rec.to_dict()
    assert plain not in str(d)
    assert "ciphertext" not in d
    assert "masked_preview" in d


def test_service_invalid_provider():
    s = BYOKStore()
    with pytest.raises(BYOKError):
        s.set_key("u-1", "bogus", _valid_key("anthropic"))


def test_service_invalid_user():
    s = BYOKStore()
    with pytest.raises(BYOKError):
        s.set_key("  ", "anthropic", _valid_key("anthropic"))
    with pytest.raises(BYOKError):
        s.set_key("x" * 201, "anthropic", _valid_key("anthropic"))


def test_service_invalid_api_key_empty():
    s = BYOKStore()
    with pytest.raises(BYOKError):
        s.set_key("u-1", "anthropic", "")


def test_service_api_key_too_long():
    s = BYOKStore()
    long = "sk-ant-" + "x" * (MAX_KEY_LEN + 1)
    with pytest.raises(BYOKError):
        s.set_key("u-1", "anthropic", long)


def test_service_api_key_prefix_mismatch():
    s = BYOKStore()
    # anthropic に sk-xxx (openai) を渡すと reject
    with pytest.raises(BYOKError):
        s.set_key("u-1", "anthropic", "sk-foo123456789abcd")


def test_service_update_preserves_created_at():
    s = BYOKStore()
    rec1 = s.set_key("u-1", "anthropic", _valid_key("anthropic"))
    time.sleep(0.01)
    rec2 = s.set_key("u-1", "anthropic", "sk-ant-newkey0987654321xyz")
    assert rec2.created_at == rec1.created_at
    assert rec2.updated_at >= rec1.updated_at


def test_service_per_user_quota():
    s = BYOKStore()
    # 3 providers 全部 set OK
    for p in ("anthropic", "openai", "gemini"):
        s.set_key("u-1", p, _valid_key(p))
    # 別 user は影響を受けない
    s.set_key("u-2", "anthropic", _valid_key("anthropic"))
    assert len(s.list_for_user("u-1")) == 3
    assert len(s.list_for_user("u-2")) == 1


def test_service_list_for_user():
    s = BYOKStore()
    s.set_key("u-1", "anthropic", _valid_key("anthropic"))
    s.set_key("u-1", "openai", _valid_key("openai"))
    s.set_key("u-2", "anthropic", _valid_key("anthropic"))
    recs = s.list_for_user("u-1")
    assert len(recs) == 2
    assert all(r.user_id == "u-1" for r in recs)


def test_service_get_returns_none_when_missing():
    s = BYOKStore()
    assert s.get_decrypted_key("u-x", "anthropic") is None
    assert s.get_record("u-x", "anthropic") is None


def test_service_delete():
    s = BYOKStore()
    s.set_key("u-1", "anthropic", _valid_key("anthropic"))
    assert s.delete_key("u-1", "anthropic") is True
    assert s.delete_key("u-1", "anthropic") is False
    assert s.get_decrypted_key("u-1", "anthropic") is None


def test_service_rotate_re_encrypts_all():
    s = BYOKStore()
    plain = _valid_key("anthropic")
    s.set_key("u-1", "anthropic", plain)
    s.set_key("u-1", "openai", _valid_key("openai"))
    new_key = Fernet.generate_key()
    updated = s.rotate(new_key)
    assert updated == 2
    # 旧 key は version 1, rotate 後は version 2 を使う
    for r in s.list_for_user("u-1"):
        assert r.key_version == 2
    # plaintext は復号できる
    assert s.get_decrypted_key("u-1", "anthropic") == plain


def test_service_rotate_invalid_key():
    s = BYOKStore()
    with pytest.raises(BYOKError):
        s.rotate(b"not-a-valid-fernet-key")


def test_service_invalid_fernet_key_init():
    with pytest.raises(BYOKError):
        BYOKStore(fernet_key=b"too-short")


def test_service_decrypt_with_missing_key_raises():
    s = BYOKStore()
    s.set_key("u-1", "anthropic", _valid_key("anthropic"))
    # 全 key を消すと decrypt 不能
    s._keys.clear()
    with pytest.raises(BYOKError):
        s.get_decrypted_key("u-1", "anthropic")


def test_service_decrypt_with_invalid_token_raises():
    s = BYOKStore()
    s.set_key("u-1", "anthropic", _valid_key("anthropic"))
    # ciphertext を壊す
    rec = s.get_record("u-1", "anthropic")
    rec.ciphertext = b"X" * 100
    with pytest.raises(BYOKError):
        s.get_decrypted_key("u-1", "anthropic")


def test_service_singleton_get_store():
    s1 = bs.get_store()
    s2 = bs.get_store()
    assert s1 is s2
    bs.reset_store()
    s3 = bs.get_store()
    assert s3 is not s1


def test_service_max_keys_per_user_quota(monkeypatch):
    monkeypatch.setattr(bs, "MAX_KEYS_PER_USER", 2)
    s = BYOKStore()
    s.set_key("u-1", "anthropic", _valid_key("anthropic"))
    s.set_key("u-1", "openai", _valid_key("openai"))
    with pytest.raises(BYOKError, match="max keys per user"):
        s.set_key("u-1", "gemini", _valid_key("gemini"))


# ──────────────────────────────────────────────────────────────────────────
# build_anthropic_cached_payload 単体
# ──────────────────────────────────────────────────────────────────────────


def test_cache_payload_basic_system_cache():
    out = build_anthropic_cached_payload(
        "claude-opus-4-7",
        [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
        ],
    )
    assert out["model"] == "claude-opus-4-7"
    assert isinstance(out["system"], list)
    assert out["system"][0]["cache_control"] == {"type": "ephemeral"}
    # user message は単純 string content
    assert out["messages"][0] == {"role": "user", "content": "hi"}


def test_cache_payload_system_cache_disabled():
    out = build_anthropic_cached_payload(
        "claude-opus-4-7",
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ],
        system_cache=False,
    )
    # plain string で cache_control 無し
    assert out["system"] == "be brief"


def test_cache_payload_message_cache_indices():
    out = build_anthropic_cached_payload(
        "claude-opus-4-7",
        [
            {"role": "user", "content": "ctx-1"},
            {"role": "user", "content": "ctx-2"},
            {"role": "user", "content": "question"},
        ],
        system_cache=False,
        message_cache_indices=[0, 1],
    )
    assert isinstance(out["messages"][0]["content"], list)
    assert out["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert isinstance(out["messages"][1]["content"], list)
    # index 2 は cache 無し → plain string
    assert out["messages"][2]["content"] == "question"


def test_cache_payload_breakpoint_limit():
    # system 1 + indices 4 = 5 > MAX_CACHE_BREAKPOINTS (4)
    msgs = [{"role": "system", "content": "sys"}]
    msgs += [{"role": "user", "content": f"m{i}"} for i in range(5)]
    with pytest.raises(BYOKError, match="cache breakpoints"):
        build_anthropic_cached_payload(
            "claude-opus-4-7", msgs,
            message_cache_indices=[0, 1, 2, 3],
        )


def test_cache_payload_invalid_index():
    msgs = [{"role": "user", "content": "x"}]
    with pytest.raises(BYOKError, match="message_cache_indices"):
        build_anthropic_cached_payload(
            "claude-opus-4-7", msgs,
            message_cache_indices=[5],
        )


def test_cache_payload_invalid_model():
    with pytest.raises(BYOKError):
        build_anthropic_cached_payload("", [{"role": "user", "content": "x"}])


def test_cache_payload_empty_messages():
    with pytest.raises(BYOKError):
        build_anthropic_cached_payload("claude-opus-4-7", [])


def test_cache_payload_invalid_max_tokens():
    with pytest.raises(BYOKError):
        build_anthropic_cached_payload(
            "claude-opus-4-7", [{"role": "user", "content": "x"}],
            max_tokens=0,
        )


def test_cache_payload_invalid_temperature():
    with pytest.raises(BYOKError):
        build_anthropic_cached_payload(
            "claude-opus-4-7", [{"role": "user", "content": "x"}],
            temperature=3.0,
        )


def test_cache_payload_breakpoint_constant():
    assert MAX_CACHE_BREAKPOINTS == 4


# ──────────────────────────────────────────────────────────────────────────
# Backwards compatibility — 既存 provider_adapter API は不変
# ──────────────────────────────────────────────────────────────────────────


def test_compat_provider_adapter_unchanged():
    from services import provider_adapter as pa
    # 既存 symbol が import 可能
    assert hasattr(pa, "compose_request")
    assert hasattr(pa, "estimate_cost_usd")
    assert hasattr(pa, "SUPPORTED_PROVIDERS")


def test_compat_provider_adapter_compose_still_works():
    from services import provider_adapter as pa
    out = pa.compose_request(
        "anthropic", "claude-opus-4-7",
        [{"role": "user", "content": "hi"}],
        cache_control=True,
    )
    assert out["route"] == "main"


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動 (4 個)
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_set_key(client):
    r = client.post("/api/byok/keys", json={
        "user_id": "u-1",
        "provider": "anthropic",
        "api_key": _valid_key("anthropic"),
        "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "u-1"
    assert body["provider"] == "anthropic"
    assert body["masked_preview"].startswith("sk-ant-")
    # AC-4: 平文 key は含まれない
    assert _valid_key("anthropic") not in str(body)


def test_ac1_list_keys(client):
    client.post("/api/byok/keys", json={
        "user_id": "u-2",
        "provider": "openai",
        "api_key": _valid_key("openai"),
    })
    r = client.get("/api/byok/keys", params={"user_id": "u-2"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["keys"][0]["provider"] == "openai"
    # AC-4: 平文 key は含まれない
    assert _valid_key("openai") not in str(body)


def test_ac1_delete_key(client):
    client.post("/api/byok/keys", json={
        "user_id": "u-3",
        "provider": "gemini",
        "api_key": _valid_key("gemini"),
    })
    r = client.delete("/api/byok/keys/gemini", params={
        "user_id": "u-3", "actor_user_id": "u-3",
    })
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_ac1_cached_compose(client):
    r = client.post("/api/byok/prompt-cache/compose", json={
        "model": "claude-opus-4-7",
        "messages": [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "main"
    assert isinstance(body["payload"]["system"], list)
    assert body["payload"]["system"][0]["cache_control"] == {"type": "ephemeral"}


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/byok/keys", json={
        "user_id": "u-1",
        "provider": "anthropic",
        "api_key": _valid_key("anthropic"),
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_invalid_provider(client):
    r = client.post("/api/byok/keys", json={
        "user_id": "u-1",
        "provider": "bogus",
        "api_key": "sk-x123",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "byok.invalid"


def test_ac2_error_shape_consistency(client):
    cases = [
        ("POST", "/api/byok/keys", {
            "user_id": "u-1", "provider": "anthropic", "api_key": "wrong-prefix",
        }),
        ("GET", "/api/byok/keys", None),  # user_id 必須 → 422
        ("DELETE", "/api/byok/keys/anthropic", None),  # user_id 必須 → 422
        ("POST", "/api/byok/prompt-cache/compose", {
            "model": "", "messages": [{"role": "user", "content": "x"}],
        }),
    ]
    for method, path, body in cases:
        if method == "GET":
            r = client.get(path)
        elif method == "DELETE":
            r = client.delete(path)
        else:
            r = client.post(path, json=body)
        assert r.status_code in (400, 401, 404, 409, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("byok."), f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_set_key_emits_audit(client, _capture_audit):
    r = client.post("/api/byok/keys", json={
        "user_id": "u-7",
        "provider": "anthropic",
        "api_key": _valid_key("anthropic"),
        "actor_user_id": "admin",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "byok.key.set"]
    assert len(events) == 1
    assert events[0]["user_id"] == "admin"
    assert events[0]["detail"]["provider"] == "anthropic"
    # AC-4: audit detail にも平文 key を含めない
    assert _valid_key("anthropic") not in str(events[0]["detail"])


def test_ac3_delete_key_emits_audit(client, _capture_audit):
    client.post("/api/byok/keys", json={
        "user_id": "u-8",
        "provider": "openai",
        "api_key": _valid_key("openai"),
    })
    r = client.delete("/api/byok/keys/openai", params={"user_id": "u-8"})
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "byok.key.deleted"]
    assert len(events) == 1
    assert events[0]["detail"]["provider"] == "openai"


def test_ac3_no_audit_on_list(client, _capture_audit):
    client.post("/api/byok/keys", json={
        "user_id": "u-9",
        "provider": "anthropic",
        "api_key": _valid_key("anthropic"),
    })
    _capture_audit.clear()
    client.get("/api/byok/keys", params={"user_id": "u-9"})
    client.post("/api/byok/prompt-cache/compose", json={
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "hi"}],
    })
    byok_events = [e for e in _capture_audit if e["event_type"].startswith("byok.")]
    assert byok_events == []


# ──────────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / 平文 leak しない / state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_user_id(client):
    r = client.post("/api/byok/keys", json={
        "user_id": "  ",
        "provider": "anthropic",
        "api_key": _valid_key("anthropic"),
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "byok.invalid"


def test_ac4_invalid_api_key_prefix(client, _capture_audit):
    r = client.post("/api/byok/keys", json={
        "user_id": "u-1",
        "provider": "anthropic",
        "api_key": "wrong-prefix-key",
    })
    assert r.status_code == 400
    # 失敗時は audit emit しない
    assert not any(
        e["event_type"] == "byok.key.set" for e in _capture_audit
    )
    # state mutate なし
    r2 = client.get("/api/byok/keys", params={"user_id": "u-1"})
    assert r2.json()["count"] == 0


def test_ac4_empty_actor_user_id_set(client):
    r = client.post("/api/byok/keys", json={
        "user_id": "u-1",
        "provider": "anthropic",
        "api_key": _valid_key("anthropic"),
        "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "byok.unauthorized"


def test_ac4_empty_actor_user_id_delete(client):
    client.post("/api/byok/keys", json={
        "user_id": "u-1",
        "provider": "anthropic",
        "api_key": _valid_key("anthropic"),
    })
    r = client.delete("/api/byok/keys/anthropic", params={
        "user_id": "u-1", "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "byok.unauthorized"


def test_ac4_delete_not_found(client):
    r = client.delete("/api/byok/keys/anthropic", params={"user_id": "u-nope"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "byok.not_found"


def test_ac4_list_empty_user_id(client):
    r = client.get("/api/byok/keys", params={"user_id": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "byok.invalid_user_id"


def test_ac4_cached_compose_too_many_breakpoints(client):
    msgs = [{"role": "system", "content": "sys"}]
    msgs += [{"role": "user", "content": f"m{i}"} for i in range(5)]
    r = client.post("/api/byok/prompt-cache/compose", json={
        "model": "claude-opus-4-7",
        "messages": msgs,
        "message_cache_indices": [0, 1, 2, 3],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "byok.invalid"


def test_ac4_pydantic_temperature_422(client):
    r = client.post("/api/byok/prompt-cache/compose", json={
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "x"}],
        "temperature": 5.0,
    })
    assert r.status_code == 422


def test_ac4_quota_exceeded(client, monkeypatch):
    monkeypatch.setattr(bs, "MAX_KEYS_PER_USER", 2)
    # MAX_KEYS_PER_USER は service module-level でチェック → store 再生成
    bs.reset_store()
    for p in ("anthropic", "openai"):
        client.post("/api/byok/keys", json={
            "user_id": "u-q",
            "provider": p,
            "api_key": _valid_key(p),
        })
    r = client.post("/api/byok/keys", json={
        "user_id": "u-q",
        "provider": "gemini",
        "api_key": _valid_key("gemini"),
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "byok.quota_exceeded"


def test_ac4_set_overwrites_existing(client):
    # 同じ provider に再 set すると update (count 増えない)
    client.post("/api/byok/keys", json={
        "user_id": "u-up",
        "provider": "anthropic",
        "api_key": "sk-ant-original123456",
    })
    client.post("/api/byok/keys", json={
        "user_id": "u-up",
        "provider": "anthropic",
        "api_key": "sk-ant-replaced098765",
    })
    r = client.get("/api/byok/keys", params={"user_id": "u-up"})
    body = r.json()
    assert body["count"] == 1
    # mask は新しい key を反映
    assert body["keys"][0]["masked_preview"].endswith("8765")
