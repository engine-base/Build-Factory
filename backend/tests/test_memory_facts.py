"""T-AI-01: memory_facts の AC テスト.

DB 不在環境では graceful (None / [] / {processed: 0}) を返す前提で、
本テストは fingerprint / extract_facts_from_text の純粋関数 + router smoke。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.memory_facts import (
    extract_facts_from_text, fingerprint,
)


# ──────────────────────────────────────────
# fingerprint
# ──────────────────────────────────────────

def test_fingerprint_is_16_hex_chars() -> None:
    fp = fingerprint("hello world")
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_fingerprint_normalizes_whitespace_and_case() -> None:
    """空白の差・大小は同一 fingerprint。"""
    a = fingerprint("Hello   World")
    b = fingerprint("hello world")
    c = fingerprint("HELLO\tWORLD\n")
    assert a == b == c


def test_fingerprint_differs_for_different_content() -> None:
    assert fingerprint("a") != fingerprint("b")


# ──────────────────────────────────────────
# fact extraction (D-XXX / P-XXX / C-XXX)
# ──────────────────────────────────────────

def test_extract_d_prefix_decision() -> None:
    text = "D-001: 主要 DB は Supabase Postgres"
    facts = extract_facts_from_text(text)
    assert len(facts) == 1
    assert facts[0][0] == "D-001"
    assert "Supabase" in facts[0][1]


def test_extract_p_prefix_preference() -> None:
    text = "P-002: Lucide Icons を絶対遵守"
    facts = extract_facts_from_text(text)
    assert facts[0][0] == "P-002"


def test_extract_c_prefix_context() -> None:
    text = "C-100: Phase 1 は ¥0/月 構成"
    facts = extract_facts_from_text(text)
    assert facts[0][0] == "C-100"


def test_extract_with_markdown_heading() -> None:
    """## D-001 形式も拾う。"""
    text = "## D-005: Anthropic Memory API を 永続記憶の primary"
    facts = extract_facts_from_text(text)
    assert len(facts) == 1
    assert facts[0][0] == "D-005"


def test_extract_with_bold_markup() -> None:
    text = "**D-007** AI 社員は BMAD 10 ペルソナで運用"
    facts = extract_facts_from_text(text)
    assert len(facts) == 1
    assert facts[0][0] == "D-007"


def test_extract_multiple_facts_from_block() -> None:
    text = """\
## 決定事項
D-001: 主要 DB は Supabase Postgres
D-002: AI スタックは 3 層 (claude-agent-sdk + anthropic + LiteLLM)
P-001: 絵文字禁止 (Lucide Icons のみ)
"""
    facts = extract_facts_from_text(text)
    assert len(facts) == 3
    ids = [f[0] for f in facts]
    assert ids == ["D-001", "D-002", "P-001"]


def test_extract_ignores_horizontal_rules() -> None:
    """`D-001: ===` のような区切り線は拾わない。"""
    text = "D-001: ====================="
    facts = extract_facts_from_text(text)
    assert facts == []


def test_extract_returns_empty_for_no_match() -> None:
    text = "ただのメモです。決定事項なし。"
    assert extract_facts_from_text(text) == []


# ──────────────────────────────────────────
# Router smoke (DB 不在でも 200 を返すべき endpoint のみ)
# ──────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def test_router_recall_returns_empty_for_unknown_user(client) -> None:
    r = client.get("/api/memory/facts/recall", params={"user_id": "no_such_user_zzz", "query": "anything"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_router_process_retry_queue_returns_dict(client) -> None:
    r = client.post("/api/memory/facts/process-retry-queue")
    assert r.status_code == 200
    body = r.json()
    assert "processed" in body or "success" in body


def test_router_process_deletions_dry_run(client) -> None:
    r = client.post("/api/memory/facts/process-deletions", params={"dry_run": "true"})
    assert r.status_code == 200
    body = r.json()
    assert "would_delete" in body or "deleted" in body or "processed" in body


def test_router_delete_unknown_returns_404(client) -> None:
    r = client.delete("/api/memory/facts/9999999", params={"user_id": "no_user"})
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────
# AC 全網羅 (DB / Memory API / Mem0 全て mock)
#   AC-UBIQUITOUS: Memory API primary store
#   AC-EVENT  (session end): D-XXX 抽出 → memory_facts へ書き込み
#   AC-EVENT  (session start): recall <200ms
#   AC-STATE : source_session_id + confidence_score を必ず付与
#   AC-OPTIONAL: 削除要求 → 24h 以内に物理削除 + audit
#   AC-UNWANTED: API write fail → retry queue / data loss なし
# ──────────────────────────────────────────────────────────────────────────


import asyncio
import sys
import time
import types
from typing import Any
from services import memory_facts as mf


class _FakeCursor:
    def __init__(self, rows=None, lastrowid=0, rowcount=0):
        self._rows = rows or []
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _FakeDB:
    """memory_facts.py が使う各クエリを SQL keyword で dispatch する mock."""

    Row = dict

    def __init__(self, *, chat_messages=None, facts=None, by_fp=None,
                 deleted=None, retry_queue=None):
        self.chat_messages = chat_messages or []
        self.facts_table: list[dict] = list(facts or [])
        self.by_fp = by_fp or {}
        self.deleted = deleted or []  # status='deleted' 行
        self.retry_queue = retry_queue or []  # status='failed' 行
        self.executed: list[tuple[str, tuple]] = []
        self.row_factory = None
        self._next_id = 100

    def _select_facts_by_fp(self, user_id, fp):
        row = self.by_fp.get(fp)
        return [row] if row else []

    async def execute(self, sql, *args):
        params = args[0] if args else ()
        self.executed.append((sql, params))
        s = sql.lower()
        if "insert" in s and "memory_facts" in s:
            # IGNORE 経路: by_fp に登録
            user_id, ws, fact_text, kind, ssid, cs, fp = params[:7]
            if fp not in self.by_fp:
                self._next_id += 1
                self.by_fp[fp] = {
                    "id": self._next_id, "user_id": user_id, "workspace_id": ws,
                    "fact_text": fact_text, "kind": kind,
                    "source_session_id": ssid, "confidence_score": cs,
                    "fingerprint": fp, "status": "pending",
                    "retry_count": 0, "memory_api_id": None, "mem0_id": None,
                    "last_error": None, "created_at": "2026-05-11",
                    "synced_at": None, "deleted_at": None,
                }
            return _FakeCursor(lastrowid=self.by_fp[fp]["id"])
        if "update" in s and "memory_facts" in s:
            # status='synced' / 'failed' / 'deleted' どれかの更新
            if "status = 'synced'" in s or "status='synced'" in s:
                api_id, fid = params
                for r in self.by_fp.values():
                    if r["id"] == fid:
                        r["status"] = "synced"
                        r["memory_api_id"] = api_id
                        r["synced_at"] = "2026-05-11"
            elif "status = 'failed'" in s or "status='failed'" in s:
                err, fid = params
                for r in self.by_fp.values():
                    if r["id"] == fid:
                        r["status"] = "failed"
                        r["retry_count"] = (r.get("retry_count") or 0) + 1
                        r["last_error"] = err
            elif "status = 'deleted'" in s or "status='deleted'" in s:
                fid, uid = params
                hit = False
                for r in self.by_fp.values():
                    if r["id"] == fid and r["user_id"] == uid and r["deleted_at"] is None:
                        r["status"] = "deleted"
                        r["deleted_at"] = "2026-05-11"
                        hit = True
                return _FakeCursor(rowcount=1 if hit else 0)
            return _FakeCursor()
        if "delete from memory_facts" in s:
            fid = params[0]
            self.by_fp = {k: v for k, v in self.by_fp.items() if v["id"] != fid}
            return _FakeCursor(rowcount=1)
        if "select content from chat_messages" in s:
            return _FakeCursor(rows=self.chat_messages)
        if "select * from memory_facts" in s and "fingerprint" in s:
            user_id, fp = params
            return _FakeCursor(rows=self._select_facts_by_fp(user_id, fp))
        if "select * from memory_facts" in s and "status = 'synced'" in s:
            user_id, limit = params
            synced = [r for r in self.by_fp.values()
                      if r["user_id"] == user_id
                      and r["status"] == "synced"
                      and r["deleted_at"] is None][:limit]
            return _FakeCursor(rows=synced)
        if "select * from memory_facts" in s and "status = 'deleted'" in s:
            deleted = [r for r in self.by_fp.values() if r["status"] == "deleted"]
            return _FakeCursor(rows=deleted)
        if "select * from memory_facts" in s and "status in" in s:
            rows = [r for r in self.by_fp.values() if r["status"] in ("failed", "pending")
                    and r["retry_count"] < 5 and r["deleted_at"] is None]
            return _FakeCursor(rows=rows)
        return _FakeCursor()

    async def commit(self): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


def _patch_facts_db(monkeypatch, **kwargs) -> _FakeDB:
    fake = _FakeDB(**kwargs)
    mod = types.SimpleNamespace(connect=lambda _p: fake, Row=dict)
    monkeypatch.setattr(mf, "_db", lambda: mod)
    monkeypatch.setattr(mf, "_db_path", lambda: ":memory:")
    return fake


def _install_fake_anthropic(*, available: bool = True, raise_429: bool = False,
                              raise_400: bool = False, return_id: str = "mem-store-xxx"):
    """anthropic.AsyncAnthropic を fake 化."""
    state: dict[str, Any] = {"appends": [], "deletes": []}

    class _MemoryStores:
        async def append(self, store_id, content, metadata):
            state["appends"].append({"store_id": store_id, "content": content, "metadata": metadata})
            if raise_429:
                class _Err(Exception):
                    status_code = 429
                raise _Err("rate limited")
            if raise_400:
                class _Err(Exception):
                    status_code = 400
                raise _Err("bad request")
            return types.SimpleNamespace(id=return_id)

        async def delete(self, store_id, id):
            state["deletes"].append({"store_id": store_id, "id": id})

    class _Beta:
        memory_stores = _MemoryStores() if available else None

    class AsyncAnthropic:
        def __init__(self) -> None:
            self.beta = _Beta()

    mod = types.ModuleType("anthropic")
    mod.AsyncAnthropic = AsyncAnthropic
    sys.modules["anthropic"] = mod
    return state


def _install_fake_mem0():
    state: dict[str, Any] = {"deletes": []}
    mod = types.ModuleType("services.long_term_memory")

    async def delete_user_memories(user_id, *, ids):
        state["deletes"].append({"user_id": user_id, "ids": list(ids)})

    mod.delete_user_memories = delete_user_memories
    sys.modules["services.long_term_memory"] = mod
    return state


# ----------------- AC-UBIQUITOUS: Memory API primary write -----------------


def test_write_fact_success_marks_synced_with_memory_api_id(monkeypatch) -> None:
    """AC-UBIQUITOUS + AC-STATE: 成功時 status=synced + memory_api_id + source/confidence 保持."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    api_state = _install_fake_anthropic(return_id="mem-id-001")
    _patch_facts_db(monkeypatch)

    try:
        rec = asyncio.run(mf.write_fact(
            user_id="masato", fact_text="主要 DB は Supabase Postgres",
            source_session_id=42, workspace_id="W1", confidence_score=0.9,
        ))
        assert rec is not None
        assert rec.status == "synced"
        assert rec.memory_api_id == "mem-id-001"
        assert rec.source_session_id == 42
        assert rec.confidence_score == 0.9
        # Memory API に append された
        assert len(api_state["appends"]) == 1
        ap = api_state["appends"][0]
        assert ap["store_id"] == "bf_user_masato"
        assert ap["metadata"]["source_session_id"] == 42
        assert ap["metadata"]["confidence_score"] == 0.9
    finally:
        sys.modules.pop("anthropic", None)


def test_write_fact_rejects_empty_text(monkeypatch) -> None:
    _patch_facts_db(monkeypatch)
    assert asyncio.run(mf.write_fact(user_id="u", fact_text="")) is None
    assert asyncio.run(mf.write_fact(user_id="u", fact_text="   \n  ")) is None


# ----------------- AC-UNWANTED: API write fail → retry queue / no data loss


def test_write_fact_retry_exhausted_marks_failed_but_keeps_row(monkeypatch) -> None:
    """AC-UNWANTED: 429 retry 使い果たし → status='failed' + DB 行は残る (data loss なし)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic(raise_429=True)
    fake_db = _patch_facts_db(monkeypatch)

    # tenacity sleep を short-circuit
    import asyncio as _a
    async def _instant(*a, **k): return None
    monkeypatch.setattr(_a, "sleep", _instant)

    try:
        rec = asyncio.run(mf.write_fact(
            user_id="masato", fact_text="D-001 retry exhaust test",
            source_session_id=1, confidence_score=0.5,
        ))
        assert rec is not None
        assert rec.status == "failed"
        # DB 行は残っている (data loss なし)
        assert any(r["user_id"] == "masato" for r in fake_db.by_fp.values())
    finally:
        sys.modules.pop("anthropic", None)


def test_write_fact_400_immediate_fail_no_retry(monkeypatch) -> None:
    """AC-UNWANTED: 4xx (429 以外) は即 fail + DB 行は残る (data loss なし)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic(raise_400=True)
    fake_db = _patch_facts_db(monkeypatch)

    try:
        rec = asyncio.run(mf.write_fact(
            user_id="u", fact_text="bad fact",
            source_session_id=1, confidence_score=0.5,
        ))
        assert rec is not None
        assert rec.status == "failed"
        assert any(r for r in fake_db.by_fp.values())
    finally:
        sys.modules.pop("anthropic", None)


def test_write_fact_no_api_key_marks_failed_not_lost(monkeypatch) -> None:
    """ANTHROPIC_API_KEY 未設定 → RuntimeError 経由で failed、 row は残る."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake_db = _patch_facts_db(monkeypatch)
    rec = asyncio.run(mf.write_fact(
        user_id="u", fact_text="some fact",
        source_session_id=1, confidence_score=0.5,
    ))
    assert rec is not None
    assert rec.status == "failed"
    assert len(fake_db.by_fp) == 1


# ----------------- AC-EVENT (session end): extract_facts_from_session ------


def test_extract_facts_from_session_writes_each_d_ref(monkeypatch) -> None:
    """AC-EVENT (session end): chat_messages の D-XXX を全部 write_fact に流す."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic()
    _patch_facts_db(monkeypatch, chat_messages=[
        {"content": "D-001: 採用する技術スタック確定"},
        {"content": "P-002: Lucide Icons のみ\nC-003: Phase 1 は ¥0"},
    ])
    try:
        out = asyncio.run(mf.extract_facts_from_session(
            session_id=99, user_id="masato", workspace_id="W1",
            confidence_score=0.8,
        ))
        # 3 件 (D-001 / P-002 / C-003)
        assert len(out) == 3
        assert all(r.source_session_id == 99 for r in out)
        assert all(r.confidence_score == 0.8 for r in out)  # AC-STATE
    finally:
        sys.modules.pop("anthropic", None)


def test_extract_facts_from_session_returns_empty_on_db_error(monkeypatch) -> None:
    """DB 失敗時は [] (silent skip、 呼び出し元は次回 retry)."""
    class _ErrDB(_FakeDB):
        async def execute(self, sql, *args):
            raise RuntimeError("db down")

    mod = types.SimpleNamespace(connect=lambda _p: _ErrDB(), Row=dict)
    monkeypatch.setattr(mf, "_db", lambda: mod)
    monkeypatch.setattr(mf, "_db_path", lambda: ":memory:")
    out = asyncio.run(mf.extract_facts_from_session(1, "u"))
    assert out == []


# ----------------- AC-EVENT (session start): recall <200ms -------------------


def test_recall_facts_returns_synced_only(monkeypatch) -> None:
    """AC-EVENT: synced fact のみ返す (failed/pending/deleted は除外)."""
    fake = _patch_facts_db(monkeypatch)
    # 直接 row を仕込む
    fake.by_fp["fp1"] = {
        "id": 1, "user_id": "u", "workspace_id": None, "fact_text": "ok",
        "kind": "durable", "source_session_id": 1, "confidence_score": 0.7,
        "fingerprint": "fp1", "status": "synced", "retry_count": 0,
        "memory_api_id": "m1", "mem0_id": None, "last_error": None,
        "created_at": "2026-05-11", "synced_at": "2026-05-11", "deleted_at": None,
    }
    fake.by_fp["fp2"] = {**fake.by_fp["fp1"], "id": 2, "status": "failed", "fingerprint": "fp2"}
    fake.by_fp["fp3"] = {**fake.by_fp["fp1"], "id": 3, "status": "synced",
                          "fingerprint": "fp3", "deleted_at": "2026-05-11"}
    out = asyncio.run(mf.recall_facts("u", "query", top_k=5))
    assert len(out) == 1
    assert out[0].id == 1


def test_recall_facts_within_200ms(monkeypatch) -> None:
    """AC-EVENT (200ms): DB 100 row でも recall は 200ms 以内."""
    fake = _patch_facts_db(monkeypatch)
    for i in range(100):
        fake.by_fp[f"fp{i}"] = {
            "id": i, "user_id": "u", "workspace_id": None,
            "fact_text": f"fact-{i}", "kind": "durable",
            "source_session_id": i, "confidence_score": 0.7,
            "fingerprint": f"fp{i}", "status": "synced", "retry_count": 0,
            "memory_api_id": f"m{i}", "mem0_id": None, "last_error": None,
            "created_at": "2026-05-11", "synced_at": "2026-05-11", "deleted_at": None,
        }
    t0 = time.monotonic()
    out = asyncio.run(mf.recall_facts("u", "q", top_k=5))
    dt = time.monotonic() - t0
    assert dt < 0.2, f"recall took {dt*1000:.1f}ms (limit 200ms)"
    assert len(out) == 5


def test_recall_facts_returns_empty_on_db_error(monkeypatch) -> None:
    class _ErrDB(_FakeDB):
        async def execute(self, sql, *args):
            raise RuntimeError("db down")

    mod = types.SimpleNamespace(connect=lambda _p: _ErrDB(), Row=dict)
    monkeypatch.setattr(mf, "_db", lambda: mod)
    monkeypatch.setattr(mf, "_db_path", lambda: ":memory:")
    assert asyncio.run(mf.recall_facts("u", "q")) == []


# ----------------- AC-OPTIONAL: deletion (24h grace + audit) --------------


def test_request_deletion_marks_soft_deleted(monkeypatch) -> None:
    fake = _patch_facts_db(monkeypatch)
    fake.by_fp["x"] = {
        "id": 5, "user_id": "u", "workspace_id": None, "fact_text": "f",
        "kind": "durable", "source_session_id": 1, "confidence_score": 0.7,
        "fingerprint": "x", "status": "synced", "retry_count": 0,
        "memory_api_id": "m", "mem0_id": None, "last_error": None,
        "created_at": "", "synced_at": "", "deleted_at": None,
    }
    ok = asyncio.run(mf.request_deletion(fact_id=5, user_id="u"))
    assert ok is True
    assert fake.by_fp["x"]["status"] == "deleted"
    assert fake.by_fp["x"]["deleted_at"] is not None


def test_request_deletion_returns_false_when_already_deleted(monkeypatch) -> None:
    fake = _patch_facts_db(monkeypatch)
    fake.by_fp["x"] = {
        "id": 5, "user_id": "u", "workspace_id": None, "fact_text": "f",
        "kind": "durable", "source_session_id": 1, "confidence_score": 0.7,
        "fingerprint": "x", "status": "deleted", "retry_count": 0,
        "memory_api_id": None, "mem0_id": None, "last_error": None,
        "created_at": "", "synced_at": None, "deleted_at": "2026-05-11",
    }
    ok = asyncio.run(mf.request_deletion(fact_id=5, user_id="u"))
    assert ok is False


def test_request_deletion_handles_db_exception(monkeypatch) -> None:
    class _ErrDB(_FakeDB):
        async def execute(self, sql, *args):
            raise RuntimeError("db down")

    mod = types.SimpleNamespace(connect=lambda _p: _ErrDB(), Row=dict)
    monkeypatch.setattr(mf, "_db", lambda: mod)
    monkeypatch.setattr(mf, "_db_path", lambda: ":memory:")
    assert asyncio.run(mf.request_deletion(1, "u")) is False


def test_process_pending_deletions_dry_run(monkeypatch) -> None:
    fake = _patch_facts_db(monkeypatch)
    fake.by_fp["x"] = {
        "id": 5, "user_id": "u", "workspace_id": None, "fact_text": "f",
        "kind": "durable", "source_session_id": 1, "confidence_score": 0.7,
        "fingerprint": "x", "status": "deleted", "retry_count": 0,
        "memory_api_id": "m", "mem0_id": None, "last_error": None,
        "created_at": "", "synced_at": None, "deleted_at": "2026-05-11",
    }
    out = asyncio.run(mf.process_pending_deletions(dry_run=True))
    assert out["would_delete"] == 1
    assert 5 in out["ids"]
    # 物理削除されてない
    assert any(r["id"] == 5 for r in fake.by_fp.values())


def test_process_pending_deletions_physical_delete(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    api_state = _install_fake_anthropic()
    mem0_state = _install_fake_mem0()
    fake = _patch_facts_db(monkeypatch)
    fake.by_fp["x"] = {
        "id": 5, "user_id": "u", "workspace_id": None, "fact_text": "f",
        "kind": "durable", "source_session_id": 1, "confidence_score": 0.7,
        "fingerprint": "x", "status": "deleted", "retry_count": 0,
        "memory_api_id": "m-001", "mem0_id": "mem0-001", "last_error": None,
        "created_at": "", "synced_at": None, "deleted_at": "2026-05-11",
    }
    try:
        out = asyncio.run(mf.process_pending_deletions(dry_run=False))
        assert out["deleted"] == 1
        # Memory API + Mem0 + DB row 全部削除
        assert len(api_state["deletes"]) == 1
        assert api_state["deletes"][0]["id"] == "m-001"
        assert len(mem0_state["deletes"]) == 1
        assert mem0_state["deletes"][0]["ids"] == ["mem0-001"]
        assert 5 not in [v["id"] for v in fake.by_fp.values()]
    finally:
        sys.modules.pop("anthropic", None)
        sys.modules.pop("services.long_term_memory", None)


def test_process_pending_deletions_returns_zero_on_db_error(monkeypatch) -> None:
    class _ErrDB(_FakeDB):
        async def execute(self, sql, *args):
            raise RuntimeError("db down")

    mod = types.SimpleNamespace(connect=lambda _p: _ErrDB(), Row=dict)
    monkeypatch.setattr(mf, "_db", lambda: mod)
    monkeypatch.setattr(mf, "_db_path", lambda: ":memory:")
    out = asyncio.run(mf.process_pending_deletions())
    assert out["processed"] == 0


# ----------------- AC-UNWANTED retry queue --------------------------------


def test_process_retry_queue_resubmits_failed(monkeypatch) -> None:
    """failed 行を再送して synced に遷移."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic(return_id="recovered-id")
    fake = _patch_facts_db(monkeypatch)
    fake.by_fp["x"] = {
        "id": 5, "user_id": "u", "workspace_id": None, "fact_text": "retry me",
        "kind": "durable", "source_session_id": 1, "confidence_score": 0.7,
        "fingerprint": "x", "status": "failed", "retry_count": 1,
        "memory_api_id": None, "mem0_id": None, "last_error": "previous err",
        "created_at": "", "synced_at": None, "deleted_at": None,
    }
    try:
        out = asyncio.run(mf.process_retry_queue(max_items=5))
        assert out["success"] == 1
        assert fake.by_fp["x"]["status"] == "synced"
        assert fake.by_fp["x"]["memory_api_id"] == "recovered-id"
    finally:
        sys.modules.pop("anthropic", None)


def test_process_retry_queue_keeps_failed_when_still_broken(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _install_fake_anthropic(raise_400=True)
    fake = _patch_facts_db(monkeypatch)
    fake.by_fp["x"] = {
        "id": 5, "user_id": "u", "workspace_id": None, "fact_text": "still bad",
        "kind": "durable", "source_session_id": 1, "confidence_score": 0.7,
        "fingerprint": "x", "status": "failed", "retry_count": 1,
        "memory_api_id": None, "mem0_id": None, "last_error": "x",
        "created_at": "", "synced_at": None, "deleted_at": None,
    }
    try:
        out = asyncio.run(mf.process_retry_queue(max_items=5))
        assert out["failed"] == 1
        assert fake.by_fp["x"]["status"] == "failed"
    finally:
        sys.modules.pop("anthropic", None)


def test_process_retry_queue_returns_zero_on_db_error(monkeypatch) -> None:
    class _ErrDB(_FakeDB):
        async def execute(self, sql, *args):
            raise RuntimeError("db down")

    mod = types.SimpleNamespace(connect=lambda _p: _ErrDB(), Row=dict)
    monkeypatch.setattr(mf, "_db", lambda: mod)
    monkeypatch.setattr(mf, "_db_path", lambda: ":memory:")
    out = asyncio.run(mf.process_retry_queue())
    assert out["processed"] == 0


# ----------------- helpers ----------------------------------------------


def test_row_to_fact_handles_partial_row() -> None:
    """Optional フィールドが欠落しても dataclass が壊れない."""
    rec = mf._row_to_fact({"user_id": "u", "fact_text": "t"})
    assert rec.user_id == "u"
    assert rec.confidence_score == 0.7
    assert rec.status == "pending"


def test_now_iso_returns_string() -> None:
    s = mf._now_iso()
    assert isinstance(s, str)
    assert "2026" in s or "20" in s


def test_emit_event_swallows_exceptions(monkeypatch) -> None:
    """_emit は memory_service.emit_event が落ちても crash しない."""
    mod = types.ModuleType("services.memory_service")

    async def boom(*a, **k):
        raise RuntimeError("audit down")

    mod.emit_event = boom
    sys.modules["services.memory_service"] = mod
    try:
        asyncio.run(mf._emit("test_event", user_id="u"))  # 例外を投げない
    finally:
        sys.modules.pop("services.memory_service", None)


def test_mark_synced_handles_none_id() -> None:
    """fact_id が None なら何もしない (silent skip)."""
    asyncio.run(mf._mark_synced(None, "m-001"))  # 例外を投げない


def test_mark_failed_handles_none_id() -> None:
    asyncio.run(mf._mark_failed(None, "err"))  # 例外を投げない
