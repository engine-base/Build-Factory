"""T-023-05: user_lifecycle (clone opt-in + GDPR deletion) の smoke test.

DB 不在環境では graceful (False / 空 dict) を返す前提で、本テストは
service 層の純粋ロジック + router 層の E2E を確認する。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.user_lifecycle import (
    _execute_after, GRACE_DAYS, request_deletion, get_clone_optin,
    AlreadyPendingError,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def test_grace_days_constant() -> None:
    assert GRACE_DAYS == 30


def test_execute_after_formats_as_iso_30_days_later() -> None:
    s = _execute_after(30)
    # UTC ISO 文字列 → parse 可能
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    diff = dt - datetime.now()
    # ±1 hour 程度の余裕で 30 日後
    assert 29 * 24 * 60 * 60 <= diff.total_seconds() <= 31 * 24 * 60 * 60


def test_execute_after_custom_days() -> None:
    s = _execute_after(7)
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    diff = dt - datetime.now()
    assert 6 * 24 * 3600 <= diff.total_seconds() <= 8 * 24 * 3600


# ──────────────────────────────────────────
# Router E2E
# ──────────────────────────────────────────

def test_router_clone_optin_get_default_off(client) -> None:
    r = client.get("/api/user/clone-optin", params={"user_id": "fresh_user_xyz"})
    assert r.status_code == 200
    assert r.json()["opted_in"] is False


def test_router_pending_deletions_empty_list(client) -> None:
    r = client.get("/api/user/deletion/pending")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_router_execute_due_dry_run(client) -> None:
    r = client.post("/api/user/deletion/execute-due", params={"dry_run": "true"})
    assert r.status_code == 200
    body = r.json()
    # dry_run なら would_execute / ids 形式 (DB 不在でも 0 件)
    assert "would_execute" in body or "executed" in body


# ──────────────────────────────────────────
# T-023-05 AC: UNWANTED — already pending → 409
# ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_request_deletion_twice_raises_already_pending(monkeypatch) -> None:
    """DB を mock し、既存 pending row があるケースで AlreadyPendingError が出るか。"""
    # 既存 row シミュレーション: SELECT が 1 件返す
    class FakeCursor:
        def __init__(self, rows): self._rows = rows
        async def fetchone(self): return self._rows.pop(0) if self._rows else None

    class FakeConn:
        row_factory = None
        def __init__(self):
            # 1 回目の execute: SELECT (pending row あり) → 返す
            self._calls = 0
        async def execute(self, sql, *args):
            self._calls += 1
            # 最初の SELECT が pending row を返す
            if "SELECT" in sql.upper() and "pending" in sql.lower():
                return FakeCursor([{"id": 42}])
            return FakeCursor([])
        async def commit(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    class FakeDb:
        Row = dict
        def connect(self, _path): return FakeConn()

    monkeypatch.setattr("services.user_lifecycle._db", lambda: FakeDb())
    with pytest.raises(AlreadyPendingError):
        await request_deletion("user_x", reason="test")


def test_router_deletion_double_request_returns_409(client, monkeypatch) -> None:
    """router 層: AlreadyPendingError → 409 (code=already_pending)"""
    async def fake(*args, **kw):
        raise AlreadyPendingError("already pending id=1")

    monkeypatch.setattr("routers.user_lifecycle.request_deletion", fake)

    r = client.post("/api/user/deletion", json={"user_id": "u", "grace_days": 30})
    assert r.status_code == 409
    detail = r.json().get("detail")
    assert isinstance(detail, dict) and detail.get("code") == "already_pending"
