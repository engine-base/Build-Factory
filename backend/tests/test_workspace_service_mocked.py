"""T-021 / T-004-05 追加 DB-mocked テスト.

Phase 1 ゲート (coverage 70%) を満たすため、 workspace_service.py の
DB を伴う関数を mock 接続で網羅する。
"""
from __future__ import annotations

import pytest

from services import workspace_service as ws


# ─────────────────────────────────────────────────────────
# DB mock
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
    def __init__(self, rows_by_kw=None, rowcount=1, row_factory=None):
        self._rows = rows_by_kw or {}
        self._rowcount = rowcount
        self.row_factory = row_factory

    async def execute_fetchall(self, sql, *args):
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return rows
        return []

    async def execute(self, sql, *args):
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return FakeCursor(rows=rows, rowcount=self._rowcount)
        return FakeCursor(rows=[], rowcount=self._rowcount)

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


class FakeAiosqlite:
    """workspace_service.py が `import aiosqlite` で参照する Row + connect を模す。"""
    Row = dict

    def __init__(self, rows_by_kw=None, rowcount=1):
        self._rows = rows_by_kw
        self._rowcount = rowcount

    def connect(self, _path):
        return FakeConn(self._rows, self._rowcount, row_factory=dict)


@pytest.fixture
def mock_db(monkeypatch):
    """workspace_service の aiosqlite を mock 化するヘルパー。"""
    def _apply(rows_by_kw=None, rowcount=1):
        fake = FakeAiosqlite(rows_by_kw=rows_by_kw, rowcount=rowcount)
        monkeypatch.setattr(ws, "aiosqlite", fake)
        return fake
    return _apply


# ─────────────────────────────────────────────────────────
# list_workspaces_by_account
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_workspaces_by_account_returns_rows(mock_db) -> None:
    mock_db({"select": [
        {"id": 1, "account_id": 5, "name": "WS A", "status": "active"},
        {"id": 2, "account_id": 5, "name": "WS B", "status": "active"},
    ]})
    rows = await ws.list_workspaces_by_account(5)
    assert isinstance(rows, list)
    assert len(rows) >= 1


# ─────────────────────────────────────────────────────────
# get_workspace
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_workspace_returns_row(mock_db) -> None:
    mock_db({"select": [{"id": 7, "name": "X", "status": "active"}]})
    result = await ws.get_workspace(7)
    assert result is not None
    assert result.get("id") == 7


@pytest.mark.asyncio
async def test_get_workspace_returns_none_for_missing(mock_db) -> None:
    mock_db({"select": []})
    result = await ws.get_workspace(99999)
    assert result is None


# ─────────────────────────────────────────────────────────
# update_workspace + audit
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_update_workspace_no_fields_returns_existing(mock_db) -> None:
    mock_db({"select": [{"id": 1, "name": "WS"}]})
    result = await ws.update_workspace(1)
    # fields 空 → get_workspace 経由で row を返す
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_update_workspace_with_fields_emits_audit(mock_db, monkeypatch) -> None:
    mock_db({"select": [{"id": 1, "name": "X"}]})
    events: list[tuple] = []

    async def fake_emit(event_type: str, **kw):
        events.append((event_type, kw))
        return 1

    monkeypatch.setattr("services.memory_service.emit_event", fake_emit)
    await ws.update_workspace(1, name="X2", description="d", status="active")
    assert any(e[0] == "workspace.updated" for e in events)


# ─────────────────────────────────────────────────────────
# archive_workspace
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_archive_workspace_calls_update_and_emits(mock_db, monkeypatch) -> None:
    mock_db({"select": [{"id": 1, "name": "X", "status": "archived"}]})
    events: list[tuple] = []

    async def fake_emit(event_type: str, **kw):
        events.append((event_type, kw))
        return 1

    monkeypatch.setattr("services.memory_service.emit_event", fake_emit)
    await ws.archive_workspace(1, actor_user_id="alice")
    assert any(e[0] == "workspace.archived" for e in events)


# ─────────────────────────────────────────────────────────
# add_member
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_member_with_known_role(mock_db) -> None:
    mock_db({"select": [{
        "id": 1, "workspace_id": 1, "user_id": "u", "role": "contributor",
        "custom_permissions": "{}", "invited_by": None, "created_at": "now",
    }]})
    result = await ws.add_member(1, "u", role="contributor", invited_by="boss")
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_add_member_unknown_role_raises_value_error(mock_db) -> None:
    mock_db({})
    with pytest.raises(ValueError):
        await ws.add_member(1, "u", role="superhacker_role")


@pytest.mark.asyncio
async def test_add_member_invalid_custom_permissions_raises(mock_db) -> None:
    mock_db({})
    with pytest.raises(ValueError):
        await ws.add_member(
            1, "u", role="contributor",
            custom_permissions={"unknown_key": True},
        )


# ─────────────────────────────────────────────────────────
# update_member_role: self-strip / owner protect
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_update_member_role_owner_protected(mock_db) -> None:
    """最後の owner を降格しようとすると OwnerProtectedError"""
    mock_db({"select": [{"id": 1, "user_id": "alice", "role": "owner",
                          "custom_permissions": "{}"}]})

    # ws._count_role が 1 を返すように mock — ただし関数全体を直接 mock
    async def fake_count(*a, **kw):
        return 1

    import services.workspace_service as mod
    original_count = mod._count_role
    mod._count_role = fake_count
    try:
        with pytest.raises(ws.OwnerProtectedError):
            await ws.update_member_role(
                1, "alice", role="viewer", actor_user_id="bob",
            )
    finally:
        mod._count_role = original_count


@pytest.mark.asyncio
async def test_update_member_role_unknown_custom_perm_raises(mock_db) -> None:
    mock_db({"select": [{"id": 1, "user_id": "u", "role": "contributor",
                          "custom_permissions": "{}"}]})
    with pytest.raises(ValueError):
        await ws.update_member_role(
            1, "u",
            custom_permissions={"fake_perm_key": True},
        )


# ─────────────────────────────────────────────────────────
# transfer_ownership (T-004-05)
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_transfer_ownership_happy_path(mock_db, monkeypatch) -> None:
    """current = owner, new = contributor → 成功"""
    async def fake_get(workspace_id, user_id):
        if user_id == "alice":
            return {"user_id": "alice", "role": "owner"}
        if user_id == "bob":
            return {"user_id": "bob", "role": "contributor"}
        return None

    monkeypatch.setattr("services.workspace_service.get_member", fake_get)
    mock_db({})
    result = await ws.transfer_ownership(
        1, current_owner_id="alice", new_owner_id="bob",
    )
    assert result["ok"] is True
    assert result["from_user_id"] == "alice"
    assert result["to_user_id"] == "bob"


# ─────────────────────────────────────────────────────────
# get_member
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_member_existing(mock_db) -> None:
    mock_db({"select": [{"id": 1, "user_id": "u", "role": "viewer",
                          "custom_permissions": "{}"}]})
    result = await ws.get_member(1, "u")
    assert result is not None


@pytest.mark.asyncio
async def test_get_member_missing(mock_db) -> None:
    mock_db({"select": []})
    result = await ws.get_member(1, "no_such")
    assert result is None
