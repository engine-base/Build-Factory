"""T-M30-01: ChatThread / ChatMessage CRUD (M-30 schema) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : M-30 chat thread/message CRUD
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 threads.py / chat.py API 不変 + audit emit
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import chat_thread_store as cts
from services.chat_thread_store import (
    ChatThreadError,
    ChatThreadStore,
    MAX_CONTENT_CHARS,
    MAX_MESSAGES_PER_THREAD,
    MAX_PERSONA_LEN,
    MAX_THREADS_PER_WORKSPACE,
    MAX_TITLE_LEN,
    VALID_ROLES,
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
# Store 単体: thread CRUD
# ──────────────────────────────────────────────────────────────────────────


def test_store_create_thread_minimal():
    s = ChatThreadStore()
    t = s.create_thread()
    assert t.id == 1
    assert t.workspace_id is None
    assert t.is_archived is False
    assert t.created_at == t.updated_at


def test_store_create_thread_full():
    s = ChatThreadStore()
    t = s.create_thread(workspace_id=10, session_id=20, title="hi", persona="mary")
    assert t.workspace_id == 10
    assert t.session_id == 20
    assert t.title == "hi"
    assert t.persona == "mary"


def test_store_create_invalid_workspace():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.create_thread(workspace_id=0)
    with pytest.raises(ChatThreadError):
        s.create_thread(workspace_id=-1)


def test_store_create_invalid_session():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.create_thread(session_id=0)


def test_store_create_title_too_long():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.create_thread(title="x" * (MAX_TITLE_LEN + 1))


def test_store_create_persona_too_long():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.create_thread(persona="x" * (MAX_PERSONA_LEN + 1))


def test_store_create_persona_empty_string():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.create_thread(persona="   ")


def test_store_create_persona_non_string():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.create_thread(persona=123)


def test_store_create_title_non_string():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.create_thread(title=123)


def test_store_list_threads_filters_archived():
    s = ChatThreadStore()
    t1 = s.create_thread(title="a")
    t2 = s.create_thread(title="b")
    s.update_thread(t2.id, is_archived=True)
    threads = s.list_threads()
    assert len(threads) == 1
    assert threads[0].id == t1.id
    threads_all = s.list_threads(include_archived=True)
    assert len(threads_all) == 2


def test_store_list_threads_workspace_filter():
    s = ChatThreadStore()
    s.create_thread(workspace_id=1, title="ws1-a")
    s.create_thread(workspace_id=1, title="ws1-b")
    s.create_thread(workspace_id=2, title="ws2-a")
    s.create_thread(title="orphan")
    threads = s.list_threads(workspace_id=1)
    assert len(threads) == 2
    threads2 = s.list_threads(workspace_id=2)
    assert len(threads2) == 1


def test_store_list_threads_sorted_by_updated_at():
    s = ChatThreadStore()
    t1 = s.create_thread(title="a")
    time.sleep(0.005)
    t2 = s.create_thread(title="b")
    time.sleep(0.005)
    s.update_thread(t1.id, title="a-new")
    out = s.list_threads()
    # t1 が一番新しい
    assert out[0].id == t1.id
    assert out[1].id == t2.id


def test_store_list_threads_invalid_limit():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.list_threads(limit=0)
    with pytest.raises(ChatThreadError):
        s.list_threads(limit=10_001)


def test_store_get_thread_unknown():
    s = ChatThreadStore()
    assert s.get_thread(99) is None


def test_store_get_thread_invalid_id():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.get_thread(0)


def test_store_update_thread_fields():
    s = ChatThreadStore()
    t = s.create_thread()
    s.update_thread(t.id, title="new", persona="devon", is_archived=True)
    got = s.get_thread(t.id)
    assert got.title == "new"
    assert got.persona == "devon"
    assert got.is_archived is True


def test_store_update_thread_no_fields():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.update_thread(t.id)


def test_store_update_thread_unknown_id():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError, match="not found"):
        s.update_thread(99, title="x")


def test_store_update_thread_invalid_is_archived():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.update_thread(t.id, is_archived="yes")  # type: ignore


def test_store_delete_thread():
    s = ChatThreadStore()
    t = s.create_thread(workspace_id=1)
    s.add_message(t.id, "user", "hi")
    assert s.delete_thread(t.id) is True
    assert s.get_thread(t.id) is None
    assert s.delete_thread(t.id) is False


def test_store_delete_thread_invalid_id():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.delete_thread(0)


# ──────────────────────────────────────────────────────────────────────────
# Store 単体: message CRUD
# ──────────────────────────────────────────────────────────────────────────


def test_store_add_message_basic():
    s = ChatThreadStore()
    t = s.create_thread()
    m = s.add_message(t.id, "user", "hello")
    assert m.thread_id == t.id
    assert m.role == "user"
    assert m.content == "hello"


def test_store_add_message_invalid_role():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.add_message(t.id, "function", "x")


def test_store_add_message_empty_content():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.add_message(t.id, "user", "   ")
    with pytest.raises(ChatThreadError):
        s.add_message(t.id, "user", "")


def test_store_add_message_content_too_long():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.add_message(t.id, "user", "x" * (MAX_CONTENT_CHARS + 1))


def test_store_add_message_content_non_string():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.add_message(t.id, "user", 123)  # type: ignore


def test_store_add_message_unknown_thread():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError, match="not found"):
        s.add_message(99, "user", "x")


def test_store_add_message_invalid_thread_id():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.add_message(0, "user", "x")


def test_store_add_message_invalid_token_count():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.add_message(t.id, "user", "x", token_count=-1)


def test_store_add_message_invalid_summary():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.add_message(t.id, "user", "x", compressed_summary=[1, 2])  # type: ignore


def test_store_list_messages():
    s = ChatThreadStore()
    t = s.create_thread()
    for i in range(5):
        s.add_message(t.id, "user", f"m{i}")
    items = s.list_messages(t.id)
    assert len(items) == 5
    # offset / limit
    items2 = s.list_messages(t.id, offset=2, limit=2)
    assert [m.content for m in items2] == ["m2", "m3"]


def test_store_list_messages_unknown_thread():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.list_messages(99)


def test_store_list_messages_invalid_limit():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.list_messages(t.id, limit=0)


def test_store_list_messages_invalid_offset():
    s = ChatThreadStore()
    t = s.create_thread()
    with pytest.raises(ChatThreadError):
        s.list_messages(t.id, offset=-1)


def test_store_count_messages():
    s = ChatThreadStore()
    t = s.create_thread()
    assert s.count_messages(t.id) == 0
    s.add_message(t.id, "user", "x")
    assert s.count_messages(t.id) == 1


def test_store_get_message_invalid():
    s = ChatThreadStore()
    with pytest.raises(ChatThreadError):
        s.get_message(0)


def test_store_delete_message():
    s = ChatThreadStore()
    t = s.create_thread()
    m = s.add_message(t.id, "user", "x")
    assert s.delete_message(m.id) is True
    assert s.delete_message(m.id) is False
    assert s.count_messages(t.id) == 0


def test_store_message_to_dict_with_summary():
    s = ChatThreadStore()
    t = s.create_thread()
    summary = {"context": "x", "goals": ["a"]}
    m = s.add_message(t.id, "system", "summary",
                      compressed_summary=summary, token_count=42)
    d = m.to_dict()
    assert d["compressed_summary"] == summary
    assert d["token_count"] == 42


def test_store_singleton():
    s1 = cts.get_store()
    s2 = cts.get_store()
    assert s1 is s2
    cts.reset_store()
    s3 = cts.get_store()
    assert s3 is not s1


def test_store_quota_per_workspace(monkeypatch):
    monkeypatch.setattr(cts, "MAX_THREADS_PER_WORKSPACE", 2)
    s = ChatThreadStore()
    s.create_thread(workspace_id=1)
    s.create_thread(workspace_id=1)
    with pytest.raises(ChatThreadError, match="max threads per workspace"):
        s.create_thread(workspace_id=1)


def test_store_quota_per_thread_messages(monkeypatch):
    monkeypatch.setattr(cts, "MAX_MESSAGES_PER_THREAD", 2)
    s = ChatThreadStore()
    t = s.create_thread()
    s.add_message(t.id, "user", "x")
    s.add_message(t.id, "user", "y")
    with pytest.raises(ChatThreadError, match="max messages per thread"):
        s.add_message(t.id, "user", "z")


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_create_thread(client):
    r = client.post("/api/chat-threads", json={
        "workspace_id": 1, "title": "hello", "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "hello"
    assert body["workspace_id"] == 1


def test_ac1_list_threads(client):
    client.post("/api/chat-threads", json={"workspace_id": 1, "title": "a"})
    client.post("/api/chat-threads", json={"workspace_id": 1, "title": "b"})
    client.post("/api/chat-threads", json={"workspace_id": 2, "title": "c"})
    r = client.get("/api/chat-threads", params={"workspace_id": 1})
    body = r.json()
    assert body["count"] == 2


def test_ac1_get_thread(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    r2 = client.get(f"/api/chat-threads/{tid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == tid


def test_ac1_update_thread(client):
    r = client.post("/api/chat-threads", json={"title": "old"})
    tid = r.json()["id"]
    r2 = client.patch(f"/api/chat-threads/{tid}", json={
        "title": "new", "is_archived": True,
    })
    assert r2.status_code == 200
    body = r2.json()
    assert body["title"] == "new"
    assert body["is_archived"] is True


def test_ac1_delete_thread(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    r2 = client.delete(f"/api/chat-threads/{tid}")
    assert r2.status_code == 200
    # delete 後 GET は 404
    r3 = client.get(f"/api/chat-threads/{tid}")
    assert r3.status_code == 404


def test_ac1_add_message(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    r2 = client.post(f"/api/chat-threads/{tid}/messages", json={
        "role": "user", "content": "hi", "token_count": 10,
    })
    assert r2.status_code == 200
    assert r2.json()["role"] == "user"


def test_ac1_list_messages(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    for i in range(3):
        client.post(f"/api/chat-threads/{tid}/messages", json={
            "role": "user", "content": f"m{i}",
        })
    r2 = client.get(f"/api/chat-threads/{tid}/messages")
    body = r2.json()
    assert body["count"] == 3


def test_ac1_delete_message(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    mr = client.post(f"/api/chat-threads/{tid}/messages", json={
        "role": "user", "content": "hi",
    })
    mid = mr.json()["id"]
    r2 = client.delete(f"/api/chat-threads/{tid}/messages/{mid}")
    assert r2.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/chat-threads", json={"title": "x"})
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_invalid_workspace(client):
    r = client.post("/api/chat-threads", json={"workspace_id": 0})
    # Field(gt=0) → 422
    assert r.status_code == 422


def test_ac2_error_shape_thread_not_found(client):
    r = client.get("/api/chat-threads/99999")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "chat_thread.not_found"


def test_ac2_error_shape_consistency(client):
    cases = [
        ("POST", "/api/chat-threads", {"title": "x", "actor_user_id": "  "}),
        ("PATCH", "/api/chat-threads/99", {"title": "x"}),
        ("GET", "/api/chat-threads/99", None),
        ("DELETE", "/api/chat-threads/99", None),
    ]
    for method, path, body in cases:
        if method == "GET":
            r = client.get(path)
        elif method == "DELETE":
            r = client.delete(path)
        elif method == "PATCH":
            r = client.patch(path, json=body)
        else:
            r = client.post(path, json=body)
        assert r.status_code in (400, 401, 404, 409, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("chat_thread."), \
                f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_create_emits_audit(client, _capture_audit):
    r = client.post("/api/chat-threads", json={
        "workspace_id": 7, "title": "x", "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "chat_thread.created"]
    assert len(events) == 1
    assert events[0]["user_id"] == "u-1"
    assert events[0]["detail"]["workspace_id"] == 7


def test_ac3_update_emits_audit_with_fields(client, _capture_audit):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    _capture_audit.clear()
    client.patch(f"/api/chat-threads/{tid}", json={"title": "new"})
    events = [e for e in _capture_audit if e["event_type"] == "chat_thread.updated"]
    assert len(events) == 1
    assert events[0]["detail"]["fields"] == ["title"]


def test_ac3_message_added_emits_audit(client, _capture_audit):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    _capture_audit.clear()
    client.post(f"/api/chat-threads/{tid}/messages", json={
        "role": "user", "content": "hi",
    })
    events = [e for e in _capture_audit if e["event_type"] == "chat_message.added"]
    assert len(events) == 1
    assert events[0]["detail"]["role"] == "user"


def test_ac3_get_endpoints_no_audit(client, _capture_audit):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    _capture_audit.clear()
    client.get("/api/chat-threads")
    client.get(f"/api/chat-threads/{tid}")
    client.get(f"/api/chat-threads/{tid}/messages")
    # read endpoints は audit emit しない
    chat_events = [e for e in _capture_audit
                   if e["event_type"].startswith(("chat_thread.", "chat_message."))]
    assert chat_events == []


# ──────────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_actor_user_id_create(client, _capture_audit):
    r = client.post("/api/chat-threads", json={
        "title": "x", "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "chat_thread.unauthorized"
    # 失敗時 state mutate なし
    r2 = client.get("/api/chat-threads")
    assert r2.json()["count"] == 0
    assert not any(
        e["event_type"] == "chat_thread.created" for e in _capture_audit
    )


def test_ac4_invalid_role_message(client, _capture_audit):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    _capture_audit.clear()
    r2 = client.post(f"/api/chat-threads/{tid}/messages", json={
        "role": "function", "content": "x",
    })
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "chat_thread.invalid"
    # 失敗時 audit 非発行
    assert not any(
        e["event_type"] == "chat_message.added" for e in _capture_audit
    )


def test_ac4_empty_content_message(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    r2 = client.post(f"/api/chat-threads/{tid}/messages", json={
        "role": "user", "content": "   ",
    })
    assert r2.status_code == 400


def test_ac4_message_under_unknown_thread(client):
    r = client.post("/api/chat-threads/99999/messages", json={
        "role": "user", "content": "x",
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "chat_thread.not_found"


def test_ac4_message_delete_wrong_thread(client):
    r = client.post("/api/chat-threads", json={"title": "a"})
    tid_a = r.json()["id"]
    r2 = client.post("/api/chat-threads", json={"title": "b"})
    tid_b = r2.json()["id"]
    mr = client.post(f"/api/chat-threads/{tid_a}/messages", json={
        "role": "user", "content": "x",
    })
    mid = mr.json()["id"]
    # b の下で a の message を消そうとする → 404
    r3 = client.delete(f"/api/chat-threads/{tid_b}/messages/{mid}")
    assert r3.status_code == 404


def test_ac4_update_no_fields(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    r2 = client.patch(f"/api/chat-threads/{tid}", json={})
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "chat_thread.invalid"


def test_ac4_token_count_negative_pydantic_422(client):
    r = client.post("/api/chat-threads", json={"title": "x"})
    tid = r.json()["id"]
    r2 = client.post(f"/api/chat-threads/{tid}/messages", json={
        "role": "user", "content": "x", "token_count": -1,
    })
    assert r2.status_code == 422


def test_ac4_list_limit_over_max_pydantic_422(client):
    r = client.get("/api/chat-threads", params={"limit": 100_000})
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# Backwards compatibility — 既存 routers/threads.py は不変
# ──────────────────────────────────────────────────────────────────────────


def test_compat_legacy_threads_router_unchanged():
    # 既存 routers/threads.py の import + symbol が壊れていない
    from routers import threads as legacy
    assert hasattr(legacy, "router")
    assert hasattr(legacy, "list_threads")
    assert hasattr(legacy, "create_thread")
    assert hasattr(legacy, "get_thread")
    assert hasattr(legacy, "update_thread")
    assert hasattr(legacy, "delete_thread")
    assert hasattr(legacy, "get_or_create_thread")


def test_compat_chat_router_unchanged():
    from routers import chat
    assert hasattr(chat, "router")
