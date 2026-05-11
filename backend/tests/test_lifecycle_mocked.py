"""T-023-05 追加 DB-mocked テスト.

Phase 1 ゲート (coverage 70%) を満たすため、 user_lifecycle.py の
DB を伴う関数を mock 接続で網羅する。

AC reference:
  - UBIQUITOUS: user_clone_optin / user_deletion_requests テーブル
  - EVENT:      deletion_requested / cancel / clone toggle
  - STATE:      pending 期間中
"""
from __future__ import annotations

from datetime import datetime, timedelta
import pytest

from services import user_lifecycle as ulc


# ─────────────────────────────────────────────────────────
# DB mock helper
# ─────────────────────────────────────────────────────────
class FakeCursor:
    def __init__(self, rows=None, rowcount=0):
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self.lastrowid = 1

    async def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    async def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class FakeConn:
    def __init__(self, rows_by_keyword=None, rowcount=1):
        # rows_by_keyword: dict {SQL substring: rows-to-return}
        self._rows_by_kw = rows_by_keyword or {}
        self._rowcount = rowcount
        self.row_factory = None

    async def execute(self, sql, *args):
        for kw, rows in self._rows_by_kw.items():
            if kw.lower() in sql.lower():
                return FakeCursor(rows=rows, rowcount=self._rowcount)
        return FakeCursor(rows=[], rowcount=self._rowcount)

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


class FakeDb:
    Row = dict

    def __init__(self, rows_by_keyword=None, rowcount=1):
        self._rows = rows_by_keyword
        self._rowcount = rowcount

    def connect(self, _path):
        return FakeConn(self._rows, self._rowcount)


# ─────────────────────────────────────────────────────────
# set_clone_optin
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_set_clone_optin_true_returns_ok(monkeypatch) -> None:
    monkeypatch.setattr(ulc, "_db", lambda: FakeDb())
    result = await ulc.set_clone_optin("user_x", True)
    assert result["ok"] is True
    assert result["opted_in"] is True


@pytest.mark.asyncio
async def test_set_clone_optin_false_returns_ok(monkeypatch) -> None:
    monkeypatch.setattr(ulc, "_db", lambda: FakeDb())
    result = await ulc.set_clone_optin("user_y", False)
    assert result["ok"] is True
    assert result["opted_in"] is False


@pytest.mark.asyncio
async def test_set_clone_optin_db_failure_returns_error(monkeypatch) -> None:
    class FailDb(FakeDb):
        def connect(self, _path):
            raise RuntimeError("db down")

    monkeypatch.setattr(ulc, "_db", lambda: FailDb())
    result = await ulc.set_clone_optin("user_z", True)
    assert result["ok"] is False
    assert "error" in result


# ─────────────────────────────────────────────────────────
# get_clone_optin
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_clone_optin_returns_true_when_row_exists(monkeypatch) -> None:
    monkeypatch.setattr(ulc, "_db", lambda: FakeDb({"select": [{"opted_in": 1}]}))
    assert await ulc.get_clone_optin("user_x") is True


@pytest.mark.asyncio
async def test_get_clone_optin_returns_false_when_no_row(monkeypatch) -> None:
    monkeypatch.setattr(ulc, "_db", lambda: FakeDb({"select": []}))
    assert await ulc.get_clone_optin("user_x") is False


@pytest.mark.asyncio
async def test_get_clone_optin_returns_false_on_db_error(monkeypatch) -> None:
    class FailDb(FakeDb):
        def connect(self, _path):
            raise RuntimeError("db down")

    monkeypatch.setattr(ulc, "_db", lambda: FailDb())
    assert await ulc.get_clone_optin("user_x") is False


# ─────────────────────────────────────────────────────────
# request_deletion
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_request_deletion_creates_row_when_no_pending(monkeypatch) -> None:
    """既存 pending なし → 新規 INSERT → ok=True"""
    monkeypatch.setattr(ulc, "_db", lambda: FakeDb({"pending": []}))
    result = await ulc.request_deletion("user_x", reason="test")
    assert result["ok"] is True
    assert result["user_id"] == "user_x"
    assert "execute_after" in result


# ─────────────────────────────────────────────────────────
# cancel_deletion
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cancel_deletion_returns_true_on_pending_row(monkeypatch) -> None:
    monkeypatch.setattr(
        ulc, "_db",
        lambda: FakeDb({"select user_id": [{"user_id": "user_x"}]}, rowcount=1),
    )
    assert await ulc.cancel_deletion(1) is True


@pytest.mark.asyncio
async def test_cancel_deletion_returns_false_on_db_failure(monkeypatch) -> None:
    class FailDb(FakeDb):
        def connect(self, _path):
            raise RuntimeError("down")

    monkeypatch.setattr(ulc, "_db", lambda: FailDb())
    assert await ulc.cancel_deletion(999) is False


# ─────────────────────────────────────────────────────────
# list_pending_deletions
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_pending_due_only_filters(monkeypatch) -> None:
    monkeypatch.setattr(
        ulc, "_db",
        lambda: FakeDb({"select": [{"id": 1, "status": "pending"}, {"id": 2}]}),
    )
    rows = await ulc.list_pending_deletions(due_only=True)
    assert isinstance(rows, list)
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_list_pending_returns_empty_on_failure(monkeypatch) -> None:
    class FailDb(FakeDb):
        def connect(self, _path):
            raise RuntimeError("down")

    monkeypatch.setattr(ulc, "_db", lambda: FailDb())
    assert await ulc.list_pending_deletions() == []


# ─────────────────────────────────────────────────────────
# execute_due_deletions
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_execute_due_dry_run_with_no_due(monkeypatch) -> None:
    monkeypatch.setattr(ulc, "_db", lambda: FakeDb({"select": []}))
    result = await ulc.execute_due_deletions(dry_run=True)
    assert result.get("would_execute") == 0


@pytest.mark.asyncio
async def test_execute_due_dry_run_with_due_items(monkeypatch) -> None:
    monkeypatch.setattr(
        ulc, "_db",
        lambda: FakeDb({"select": [{"id": 1}, {"id": 2}, {"id": 3}]}),
    )
    result = await ulc.execute_due_deletions(dry_run=True)
    assert result.get("would_execute") == 3


@pytest.mark.asyncio
async def test_execute_due_no_items_returns_zero(monkeypatch) -> None:
    monkeypatch.setattr(ulc, "_db", lambda: FakeDb({"select": []}))
    result = await ulc.execute_due_deletions(dry_run=False)
    assert result.get("executed") == 0


# ─────────────────────────────────────────────────────────
# _now_iso / _execute_after pure functions
# ─────────────────────────────────────────────────────────
def test_now_iso_format() -> None:
    s = ulc._now_iso()
    datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def test_execute_after_zero_days() -> None:
    s = ulc._execute_after(0)
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    delta = abs((dt - datetime.utcnow()).total_seconds())
    assert delta < 60
