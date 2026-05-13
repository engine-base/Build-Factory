"""T-M30-02: 短期 layer (FIFO 直近 N=20 / chat_thread_store REUSE wrapper) — 4 AC.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : recent_messages / short_tier_stats / 定数 / ShortTermLayerError 公開,
                       router endpoint, 既存 chat_thread_store 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : 2 秒以内 / chronological oldest-first /
                       mid-tier summary default exclude.
  AC-3 STATE-DRIVEN  : read-only (no add_message / delete_message call) /
                       SECTION_KEYS 重定義禁止 / chat_thread_store schema 不変.
  AC-4 UNWANTED      : invalid thread_id / n / role_filter / actor → 4xx structured /
                       ChatThreadError は ShortTermLayerError に変換 (leak しない).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import chat_thread_store as cts
from services import short_term_layer as stl


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "short_term_layer.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "short_term_layer.py"
EXISTING_STORE = REPO_ROOT / "backend" / "services" / "chat_thread_store.py"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


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


_NEXT_INJECTED_MSG_ID = [10**6]


def _inject_system_summary_message(thread_id: int, content: str) -> None:
    """memory_service.persist_compaction が書く role='system_summary' を直挿入.

    chat_thread_store.VALID_ROLES に 'system_summary' は含まれない (memory_service
    は raw SQL で sqlite chat_messages に書く) ため, テストでは in-memory store に
    ChatMessage を直接挿入する mid_term_layer テストと同じ手法を用いる.
    """
    import json as _json
    store = cts.get_store()
    _NEXT_INJECTED_MSG_ID[0] += 1
    msg = cts.ChatMessage(
        id=_NEXT_INJECTED_MSG_ID[0],
        thread_id=thread_id,
        role="system_summary",
        content=content,
        compressed_summary=None,
        token_count=None,
        created_at=time.time(),
    )
    with store._lock:
        store._messages[msg.id] = msg
        store._by_thread.setdefault(thread_id, []).append(msg.id)


def _seed_thread(n_user_msgs: int = 5, with_summary: bool = False) -> int:
    """Helper: create thread + n raw messages (+ optional mid-tier summary)."""
    store = cts.get_store()
    t = store.create_thread(title="t-m30-02 test")
    for i in range(n_user_msgs):
        store.add_message(t.id, "user", f"msg-{i}")
        # ensure created_at strictly increases for deterministic ordering
        time.sleep(0.001)
    if with_summary:
        # 経路 A: role='system' + compressed_summary
        store.add_message(
            t.id, "system", "[summary marker]",
            compressed_summary={"context": ["c"], "goals": ["g"]},
        )
        time.sleep(0.001)
        # 経路 B: role='system_summary' は VALID_ROLES に無いので直接 inject
        _inject_system_summary_message(
            t.id, '{"context": ["x"], "decisions": ["d"]}',
        )
    return t.id


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_public_api():
    for sym in (
        "recent_messages", "short_tier_stats",
        "ShortTermLayerError",
        "DEFAULT_FIFO_N", "MIN_FIFO_N", "MAX_FIFO_N",
    ):
        assert hasattr(stl, sym), f"missing service.{sym}"


def test_ac1_fifo_default_is_20():
    assert stl.DEFAULT_FIFO_N == 20
    assert stl.MIN_FIFO_N == 1
    assert stl.MAX_FIFO_N == 200


def test_ac1_existing_chat_thread_store_unchanged():
    """既存 chat_thread_store.py に short_term_layer 依存追加なし (REUSE)."""
    assert EXISTING_STORE.exists()
    src = EXISTING_STORE.read_text(encoding="utf-8")
    assert "from services.short_term_layer" not in src
    assert "import services.short_term_layer" not in src
    assert "short_term_layer" not in src


def test_ac1_existing_chat_thread_store_symbols_intact():
    """主要 symbol が残る."""
    assert hasattr(cts, "ChatThread")
    assert hasattr(cts, "ChatMessage")
    assert hasattr(cts, "ChatThreadStore")
    assert hasattr(cts, "get_store")
    assert hasattr(cts, "reset_store")


def test_ac1_router_mounted(client):
    tid = _seed_thread(3)
    resp = client.get(f"/api/short-term/{tid}/recent")
    assert resp.status_code == 200, resp.text
    resp = client.get(f"/api/short-term/{tid}/stats")
    assert resp.status_code == 200, resp.text


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_recent_messages_chronological_order():
    tid = _seed_thread(5)
    r = stl.recent_messages(tid, n=20)
    assert r["count"] == 5
    contents = [m["content"] for m in r["messages"]]
    assert contents == ["msg-0", "msg-1", "msg-2", "msg-3", "msg-4"]


def test_ac2_recent_messages_takes_last_n_only():
    tid = _seed_thread(10)
    r = stl.recent_messages(tid, n=3)
    assert r["count"] == 3
    contents = [m["content"] for m in r["messages"]]
    assert contents == ["msg-7", "msg-8", "msg-9"]


def test_ac2_recent_messages_within_2_seconds():
    tid = _seed_thread(50)
    t0 = time.time()
    stl.recent_messages(tid, n=20)
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_mid_tier_summary_excluded_by_default():
    tid = _seed_thread(5, with_summary=True)
    r = stl.recent_messages(tid, n=20)
    # 5 user messages, 2 mid-tier summary messages, default excludes summaries
    assert r["count"] == 5
    for m in r["messages"]:
        assert m["role"] == "user"
        assert m["has_compressed_summary"] is False


def test_ac2_mid_tier_summary_included_when_opt_out():
    tid = _seed_thread(5, with_summary=True)
    r = stl.recent_messages(tid, n=20, exclude_summaries=False)
    # 5 user + 1 system+summary + 1 system_summary = 7
    assert r["count"] == 7


def test_ac2_role_filter():
    tid = _seed_thread(3, with_summary=True)
    r = stl.recent_messages(
        tid, n=20, role_filter=["user"], exclude_summaries=False,
    )
    assert r["count"] == 3
    for m in r["messages"]:
        assert m["role"] == "user"


def test_ac2_endpoint_returns_structured(client):
    tid = _seed_thread(3)
    resp = client.get(f"/api/short-term/{tid}/recent?n=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["thread_id"] == tid
    assert body["n"] == 2
    assert body["count"] == 2
    assert isinstance(body["messages"], list)


def test_ac2_short_tier_stats(client):
    tid = _seed_thread(5, with_summary=True)
    s = stl.short_tier_stats(tid)
    assert s["total_messages"] == 7
    assert s["summary_count"] == 2
    assert s["recent_count"] == 5
    assert s["by_role"]["user"] == 5
    assert s["by_role"]["system"] == 1
    assert s["by_role"]["system_summary"] == 1
    assert s["fifo_default_n"] == 20
    assert s["oldest_at"] is not None
    assert s["newest_at"] >= s["oldest_at"]


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_service_is_read_only_no_writes():
    """short_term_layer は add_message / delete_message を呼ばない."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert ".add_message(" not in code
    assert ".delete_message(" not in code
    assert ".create_thread(" not in code


def test_ac3_no_section_keys_redefinition():
    """G15: SECTION_KEYS は mid_term_layer の責務 / 短期では再定義禁止."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "SECTION_KEYS" not in code


def test_ac3_no_db_write_no_io():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "INSERT INTO" not in code
    assert "aiosqlite" not in code
    assert "open(" not in code


def test_ac3_no_langgraph_no_langchain():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src).lower()
    assert "langgraph" not in code
    assert "langchain" not in code


def test_ac3_calling_recent_does_not_mutate_store():
    tid = _seed_thread(5)
    store = cts.get_store()
    before = store.count_messages(tid)
    stl.recent_messages(tid, n=20)
    stl.short_tier_stats(tid)
    after = store.count_messages(tid)
    assert before == after == 5


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_thread_id", [0, -1, None, "1", 1.5, True, False])
def test_ac4_invalid_thread_id_raises(bad_thread_id):
    with pytest.raises(stl.ShortTermLayerError):
        stl.recent_messages(bad_thread_id)


def test_ac4_unknown_thread_raises_not_found():
    with pytest.raises(stl.ShortTermLayerError) as exc:
        stl.recent_messages(99999)
    assert "not found" in str(exc.value)


@pytest.mark.parametrize("bad_n", [0, -1, 201, 1000, True, "5", 5.5])
def test_ac4_invalid_n_raises(bad_n):
    tid = _seed_thread(1)
    with pytest.raises(stl.ShortTermLayerError):
        stl.recent_messages(tid, n=bad_n)


def test_ac4_invalid_role_filter_empty_string():
    tid = _seed_thread(1)
    with pytest.raises(stl.ShortTermLayerError):
        stl.recent_messages(tid, role_filter=[""])


def test_ac4_invalid_role_filter_non_string():
    tid = _seed_thread(1)
    with pytest.raises(stl.ShortTermLayerError):
        stl.recent_messages(tid, role_filter=[123])


def test_ac4_empty_role_filter_list_raises():
    tid = _seed_thread(1)
    with pytest.raises(stl.ShortTermLayerError):
        stl.recent_messages(tid, role_filter=[])


def test_ac4_empty_actor_raises():
    tid = _seed_thread(1)
    with pytest.raises(stl.ShortTermLayerError):
        stl.recent_messages(tid, actor_user_id="  ")


def test_ac4_endpoint_404_on_unknown_thread(client):
    resp = client.get("/api/short-term/99999/recent")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "short_term_layer.not_found"


def test_ac4_endpoint_422_on_n_out_of_range(client):
    tid = _seed_thread(1)
    resp = client.get(f"/api/short-term/{tid}/recent?n=999")
    assert resp.status_code == 422


def test_ac4_endpoint_401_on_empty_actor(client):
    tid = _seed_thread(1)
    resp = client.get(f"/api/short-term/{tid}/recent?actor_user_id=%20")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "short_term_layer.unauthorized"


def test_ac4_endpoint_structured_error_shape(client):
    resp = client.get("/api/short-term/99999/recent")
    detail = resp.json()["detail"]
    assert "code" in detail
    assert "message" in detail


def test_ac4_chat_thread_error_converted_to_short_term_error(monkeypatch):
    """ChatThreadError leak しない (内部例外 → 公開 Error)."""
    tid = _seed_thread(1)

    def bad_list_messages(*a, **kw):
        raise cts.ChatThreadError("simulated chat_thread_store failure")

    store = cts.get_store()
    monkeypatch.setattr(store, "list_messages", bad_list_messages)

    with pytest.raises(stl.ShortTermLayerError) as exc:
        stl.recent_messages(tid)
    assert "chat_thread_store error" in str(exc.value)


def test_ac4_no_hardcoded_secret():
    import re
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_m30_02_ac_concretized():
    import json as _json
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-M30-02"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-M30-02",
        "While the existing implementation is in use",
        "If invalid input or unauthorized actor is detected during T-M30-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-M30-02 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "short_term_layer.py" in full
    assert "recent_messages" in full
    assert "chat_thread_store" in full
    assert "ShortTermLayerError" in full


def test_tickets_t_m30_02_has_adr_link():
    import json as _json
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-M30-02"), None)
    assert t.get("adr_link") is not None
    assert "TBD" not in str(t.get("existing_files", []))
