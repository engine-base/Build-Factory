"""T-M30-02: 短期 layer (FIFO 直近 N=20) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 短期 layer FIFO N=20 (REUSE chat_thread_store)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 chat_thread_store / chat_threads router 不変
                       (read-only)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import chat_thread_store as cts
from services import short_term_layer as stl
from services.short_term_layer import (
    DEFAULT_WINDOW,
    MAX_WINDOW,
    MIN_WINDOW,
    ShortTermLayerError,
    VALID_ROLES,
    assemble_context,
    recent_window,
    window_stats,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    cts.reset_store()
    yield
    cts.reset_store()


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS : 短期 layer の振る舞い (service 層)
# ──────────────────────────────────────────────────────────────────────────


def test_constants_match_spec():
    """N=20 が default, MIN=1, MAX=200 (要件: 直近 N=20)."""
    assert DEFAULT_WINDOW == 20
    assert MIN_WINDOW == 1
    assert MAX_WINDOW == 200


def test_recent_window_returns_last_n_in_fifo_order():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(25):
        s.add_message(t.id, "user", f"msg-{i}")
    items = recent_window(t.id, limit=20)
    assert len(items) == 20
    # FIFO 順 (古い -> 新しい). 末尾 20 件 = msg-5..msg-24
    assert items[0].content == "msg-5"
    assert items[-1].content == "msg-24"


def test_recent_window_fewer_than_limit_returns_all():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(3):
        s.add_message(t.id, "user", f"a-{i}")
    items = recent_window(t.id, limit=20)
    assert len(items) == 3
    assert [m.content for m in items] == ["a-0", "a-1", "a-2"]


def test_recent_window_empty_thread():
    s = cts.get_store()
    t = s.create_thread()
    items = recent_window(t.id)
    assert items == []


def test_recent_window_default_limit_is_20():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(30):
        s.add_message(t.id, "user", f"x-{i}")
    items = recent_window(t.id)  # no limit -> default 20
    assert len(items) == 20
    assert items[0].content == "x-10"
    assert items[-1].content == "x-29"


def test_recent_window_role_filter_user_only():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(5):
        s.add_message(t.id, "user", f"u-{i}")
        s.add_message(t.id, "assistant", f"a-{i}")
    items = recent_window(t.id, limit=20, role_filter=["user"])
    assert all(m.role == "user" for m in items)
    assert [m.content for m in items] == [f"u-{i}" for i in range(5)]


def test_recent_window_role_filter_multi():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "system", "sys-1")
    s.add_message(t.id, "user", "u-1")
    s.add_message(t.id, "assistant", "a-1")
    s.add_message(t.id, "tool", "t-1")
    items = recent_window(t.id, limit=20, role_filter=["user", "assistant"])
    assert [m.role for m in items] == ["user", "assistant"]


def test_recent_window_limit_smaller_than_message_count():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(10):
        s.add_message(t.id, "user", f"m-{i}")
    items = recent_window(t.id, limit=3)
    assert len(items) == 3
    assert [m.content for m in items] == ["m-7", "m-8", "m-9"]


def test_assemble_context_llm_ready_shape():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "system", "sys")
    s.add_message(t.id, "user", "hello")
    s.add_message(t.id, "assistant", "world")
    ctx = assemble_context(t.id, limit=10)
    assert ctx == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_assemble_context_respects_role_filter():
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "system", "sys")
    s.add_message(t.id, "user", "u")
    s.add_message(t.id, "assistant", "a")
    ctx = assemble_context(t.id, limit=10, role_filter=["user", "assistant"])
    assert ctx == [
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ]


def test_window_stats_basic():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(15):
        s.add_message(t.id, "user", f"q-{i}")
    st = window_stats(t.id)
    assert st["thread_id"] == t.id
    assert st["total"] == 15
    assert st["default_window"] == 20
    assert st["max_window"] == 200
    assert st["fits_in_default"] is True


def test_window_stats_overflow_default():
    s = cts.get_store()
    t = s.create_thread()
    for i in range(25):
        s.add_message(t.id, "user", f"q-{i}")
    st = window_stats(t.id)
    assert st["total"] == 25
    assert st["fits_in_default"] is False


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN : 2 秒以内 + structured response
# ──────────────────────────────────────────────────────────────────────────


def test_endpoint_window_returns_within_2s(client):
    s = cts.get_store()
    t = s.create_thread(title="evt")
    for i in range(50):
        s.add_message(t.id, "user", f"e-{i}")
    start = time.perf_counter()
    r = client.get(f"/api/short-term/window?thread_id={t.id}")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 2.0
    body = r.json()
    assert body["thread_id"] == t.id
    assert body["limit"] == DEFAULT_WINDOW
    assert body["count"] == 20
    assert len(body["messages"]) == 20
    assert body["messages"][0]["content"] == "e-30"
    assert body["messages"][-1]["content"] == "e-49"


def test_endpoint_context_returns_within_2s(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "system", "sys")
    s.add_message(t.id, "user", "u")
    s.add_message(t.id, "assistant", "a")
    start = time.perf_counter()
    r = client.get(f"/api/short-term/context?thread_id={t.id}&limit=10")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 2.0
    body = r.json()
    assert body["count"] == 3
    assert body["context"][0] == {"role": "system", "content": "sys"}


def test_endpoint_stats_returns_within_2s(client):
    s = cts.get_store()
    t = s.create_thread()
    start = time.perf_counter()
    r = client.get(f"/api/short-term/stats?thread_id={t.id}")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    assert elapsed < 2.0
    assert r.json()["thread_id"] == t.id


def test_endpoint_window_custom_limit(client):
    s = cts.get_store()
    t = s.create_thread()
    for i in range(10):
        s.add_message(t.id, "user", f"c-{i}")
    r = client.get(f"/api/short-term/window?thread_id={t.id}&limit=3")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert body["limit"] == 3
    assert body["messages"][-1]["content"] == "c-9"


def test_endpoint_window_role_filter(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "system", "sys")
    s.add_message(t.id, "user", "u")
    s.add_message(t.id, "assistant", "a")
    r = client.get(
        f"/api/short-term/window?thread_id={t.id}&role_filter=user,assistant"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role_filter"] == ["user", "assistant"]
    assert body["count"] == 2
    assert {m["role"] for m in body["messages"]} == {"user", "assistant"}


def test_endpoint_context_role_filter(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "u")
    s.add_message(t.id, "tool", "tool-result")
    r = client.get(
        f"/api/short-term/context?thread_id={t.id}&role_filter=tool"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["context"] == [{"role": "tool", "content": "tool-result"}]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN : 既存 chat_thread_store / chat_threads router 不変 (read-only)
# ──────────────────────────────────────────────────────────────────────────


def test_chat_thread_store_module_symbols_unchanged():
    """既存 chat_thread_store.py の公開 API は不変."""
    for sym in (
        "ChatThread", "ChatMessage", "ChatThreadStore", "ChatThreadError",
        "get_store", "reset_store", "VALID_ROLES",
        "MAX_TITLE_LEN", "MAX_CONTENT_CHARS", "MAX_MESSAGES_PER_THREAD",
    ):
        assert hasattr(cts, sym), f"chat_thread_store.{sym} missing"


def test_chat_threads_router_endpoint_unchanged(client):
    """既存 /api/chat-threads endpoint は依然動作する."""
    r = client.post("/api/chat-threads", json={"title": "compat"})
    assert r.status_code == 200
    tid = r.json()["id"]
    r = client.post(
        f"/api/chat-threads/{tid}/messages",
        json={"role": "user", "content": "hi"},
    )
    assert r.status_code == 200
    r = client.get(f"/api/chat-threads/{tid}/messages")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_short_term_layer_is_read_only_no_state_mutation():
    """recent_window 呼び出し前後で store 内容が変化しない."""
    s = cts.get_store()
    t = s.create_thread()
    for i in range(5):
        s.add_message(t.id, "user", f"r-{i}")
    before_count = s.count_messages(t.id)
    before_ids = [m.id for m in s.list_messages(t.id, limit=100)]
    _ = recent_window(t.id, limit=3)
    _ = assemble_context(t.id, limit=3)
    _ = window_stats(t.id)
    after_count = s.count_messages(t.id)
    after_ids = [m.id for m in s.list_messages(t.id, limit=100)]
    assert before_count == after_count
    assert before_ids == after_ids


def test_window_includes_new_messages_after_add():
    """新 message 追加後の recent_window は即反映される (view-like)."""
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "first")
    before = recent_window(t.id, limit=20)
    assert len(before) == 1
    s.add_message(t.id, "assistant", "second")
    after = recent_window(t.id, limit=20)
    assert len(after) == 2
    assert after[-1].content == "second"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED : invalid input は 4xx, state mutate なし
# ──────────────────────────────────────────────────────────────────────────


def test_service_rejects_invalid_thread_id():
    with pytest.raises(ShortTermLayerError, match="thread_id must be > 0"):
        recent_window(0)
    with pytest.raises(ShortTermLayerError, match="thread_id must be > 0"):
        recent_window(-1)
    with pytest.raises(ShortTermLayerError, match="thread_id must be > 0"):
        recent_window("abc")  # type: ignore[arg-type]


def test_service_rejects_bool_thread_id_treated_as_invalid():
    # bool is int subclass; we explicitly reject it
    with pytest.raises(ShortTermLayerError):
        recent_window(True)  # type: ignore[arg-type]


def test_service_rejects_invalid_limit():
    s = cts.get_store()
    t = s.create_thread()
    with pytest.raises(ShortTermLayerError, match=r"limit must be"):
        recent_window(t.id, limit=0)
    with pytest.raises(ShortTermLayerError, match=r"limit must be"):
        recent_window(t.id, limit=MAX_WINDOW + 1)
    with pytest.raises(ShortTermLayerError, match=r"limit must be"):
        recent_window(t.id, limit=-5)


def test_service_rejects_non_int_limit():
    s = cts.get_store()
    t = s.create_thread()
    with pytest.raises(ShortTermLayerError, match="limit must be int"):
        recent_window(t.id, limit="10")  # type: ignore[arg-type]
    with pytest.raises(ShortTermLayerError, match="limit must be int"):
        recent_window(t.id, limit=True)  # bool rejected


def test_service_rejects_invalid_role_filter():
    s = cts.get_store()
    t = s.create_thread()
    with pytest.raises(ShortTermLayerError, match="invalid role"):
        recent_window(t.id, role_filter=["bogus"])
    with pytest.raises(ShortTermLayerError, match="invalid role"):
        recent_window(t.id, role_filter=["user", "ghost"])
    with pytest.raises(ShortTermLayerError, match="must be a list"):
        recent_window(t.id, role_filter="user")  # type: ignore[arg-type]
    with pytest.raises(ShortTermLayerError, match="must not be empty"):
        recent_window(t.id, role_filter=[])


def test_service_rejects_duplicate_role_filter():
    s = cts.get_store()
    t = s.create_thread()
    with pytest.raises(ShortTermLayerError, match="unique"):
        recent_window(t.id, role_filter=["user", "user"])


def test_service_rejects_unknown_thread():
    with pytest.raises(ShortTermLayerError, match="thread not found"):
        recent_window(99999)
    with pytest.raises(ShortTermLayerError, match="thread not found"):
        window_stats(99999)


def test_endpoint_4xx_for_invalid_thread_id(client):
    # gt=0 is enforced by Query => 422
    r = client.get("/api/short-term/window?thread_id=0")
    assert r.status_code == 422


def test_endpoint_4xx_for_invalid_limit(client):
    s = cts.get_store()
    t = s.create_thread()
    r = client.get(f"/api/short-term/window?thread_id={t.id}&limit=0")
    assert r.status_code == 422
    r = client.get(
        f"/api/short-term/window?thread_id={t.id}&limit={MAX_WINDOW + 1}"
    )
    assert r.status_code == 422


def test_endpoint_4xx_for_invalid_role_filter(client):
    s = cts.get_store()
    t = s.create_thread()
    r = client.get(
        f"/api/short-term/window?thread_id={t.id}&role_filter=bogus"
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "short_term.invalid"
    assert "bogus" in body["detail"]["message"]


def test_endpoint_4xx_for_empty_role_filter(client):
    s = cts.get_store()
    t = s.create_thread()
    r = client.get(
        f"/api/short-term/window?thread_id={t.id}&role_filter= "
    )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "short_term.invalid"


def test_endpoint_404_for_missing_thread(client):
    r = client.get("/api/short-term/window?thread_id=99999")
    assert r.status_code == 404
    body = r.json()
    assert body["detail"]["code"] == "short_term.not_found"
    assert "99999" in body["detail"]["message"]


def test_endpoint_404_for_missing_thread_on_context(client):
    r = client.get("/api/short-term/context?thread_id=88888")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "short_term.not_found"


def test_endpoint_404_for_missing_thread_on_stats(client):
    r = client.get("/api/short-term/stats?thread_id=77777")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "short_term.not_found"


def test_endpoint_does_not_mutate_state_on_error(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "preserved")
    before = s.count_messages(t.id)
    # invalid role_filter -> 400, no mutation
    r = client.get(
        f"/api/short-term/window?thread_id={t.id}&role_filter=bogus"
    )
    assert r.status_code == 400
    # missing thread -> 404, no mutation
    r = client.get("/api/short-term/window?thread_id=99999")
    assert r.status_code == 404
    after = s.count_messages(t.id)
    assert after == before


def test_error_responses_carry_structured_detail(client):
    s = cts.get_store()
    t = s.create_thread()
    r = client.get(
        f"/api/short-term/window?thread_id={t.id}&role_filter=ghost"
    )
    assert r.status_code == 400
    body = r.json()
    assert "detail" in body
    assert set(body["detail"].keys()) == {"code", "message"}
    assert body["detail"]["code"].startswith("short_term.")


def test_role_filter_with_trailing_whitespace_and_commas_works(client):
    s = cts.get_store()
    t = s.create_thread()
    s.add_message(t.id, "user", "u")
    s.add_message(t.id, "assistant", "a")
    # trailing comma and whitespace should be stripped
    r = client.get(
        f"/api/short-term/window?thread_id={t.id}&role_filter=user, assistant, "
    )
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_valid_roles_match_chat_thread_store():
    """short_term_layer の VALID_ROLES は chat_thread_store と一致."""
    assert VALID_ROLES == cts.VALID_ROLES
