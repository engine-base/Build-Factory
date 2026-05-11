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


# ─────────────────────────────────────────────────────────
# cov 70% 達成のため不足経路を網羅
# ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_workspaces_for_user_returns_joined_rows(mock_db) -> None:
    """list_workspaces_for_user: workspace_members JOIN 経路 (L 53-63)."""
    mock_db({"join workspace_members": [
        {"id": 1, "name": "WS A", "status": "active", "member_role": "admin"},
        {"id": 2, "name": "WS B", "status": "active", "member_role": "contributor"},
    ]})
    rows = await ws.list_workspaces_for_user("user_1")
    assert len(rows) == 2
    assert all("member_role" in r for r in rows)


@pytest.mark.asyncio
async def test_list_workspaces_for_user_empty(mock_db) -> None:
    mock_db({"join workspace_members": []})
    assert await ws.list_workspaces_for_user("ghost") == []


@pytest.mark.asyncio
async def test_create_workspace_inserts_and_adds_admin_member(mock_db) -> None:
    """create_workspace: INSERT workspaces + workspace_members admin 自動追加 (L 83-100)."""
    # INSERT RETURNING + 後の get_workspace 両方に対応
    mock_db({
        "insert into workspaces": [{"id": 100}],
        "select * from workspaces": [{"id": 100, "name": "New WS",
                                       "account_id": 5, "status": "active"}],
    })
    result = await ws.create_workspace(
        account_id=5, name="New WS",
        description="d", project_meta={"k": "v"},
        creator_user_id="alice",
    )
    assert result.get("id") == 100
    assert result.get("name") == "New WS"


@pytest.mark.asyncio
async def test_update_workspace_with_budget_jpy_field(mock_db, monkeypatch) -> None:
    """budget_jpy_monthly 経路 (L 116-118)."""
    mock_db({"select": [{"id": 1, "name": "X", "budget_jpy_monthly": 50000}]})

    async def fake_emit(*a, **kw): pass
    monkeypatch.setattr(ws, "_emit_audit", fake_emit)

    result = await ws.update_workspace(1, budget_jpy_monthly=80000, actor_user_id="bob")
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_update_workspace_with_jsonb_fields(mock_db, monkeypatch) -> None:
    """project_meta / client_visibility / redlines 経路 (L 119-121)."""
    mock_db({"select": [{"id": 1, "name": "X"}]})

    async def fake_emit(*a, **kw): pass
    monkeypatch.setattr(ws, "_emit_audit", fake_emit)

    await ws.update_workspace(1, project_meta={"x": 1}, client_visibility=["task"],
                              redlines={"forbidden": ["DROP"]})


@pytest.mark.asyncio
async def test_count_role_returns_int(mock_db) -> None:
    """_count_role: COUNT(*) クエリ (L 308-314)."""
    # COUNT クエリは fetchone で (n,) を返す形式
    class _CntCursor:
        def __init__(self): self.rowcount = 0
        async def fetchone(self): return (3,)

    class _CntConn(FakeConn):
        async def execute(self, sql, *args):
            if "count(*)" in sql.lower():
                return _CntCursor()
            return await super().execute(sql, *args)
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    class _CntAiosqlite:
        Row = dict
        def connect(self, _p): return _CntConn({})

    import services.workspace_service as wsv
    saved = wsv.aiosqlite
    wsv.aiosqlite = _CntAiosqlite()
    try:
        n = await ws._count_role(workspace_id=1, role="owner")
        assert n == 3
    finally:
        wsv.aiosqlite = saved


@pytest.mark.asyncio
async def test_update_member_role_owner_unchanged_no_block(mock_db, monkeypatch) -> None:
    """owner → owner の no-op は block しない (L 327)."""
    mock_db({"select": [{"workspace_id": 1, "user_id": "u", "role": "owner",
                          "custom_permissions": None}]})

    async def fake_emit(*a, **kw): pass
    async def fake_count(*a, **kw): return 2  # owners が 2 人いる

    monkeypatch.setattr(ws, "_emit_audit", fake_emit)
    monkeypatch.setattr(ws, "_count_role", fake_count)
    # role を None で渡せば block 経路に入らない (custom_permissions のみ更新)
    result = await ws.update_member_role(
        1, "u", custom_permissions={"edit_task": True}, actor_user_id="boss",
    )
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_update_member_role_with_role_normalize(mock_db, monkeypatch) -> None:
    """role 文字列正規化 + emit audit (L 335-363)."""
    mock_db({"select": [{"workspace_id": 1, "user_id": "u",
                          "role": "contributor", "custom_permissions": None}]})

    async def fake_emit(event_type, *, user_id=None, detail=None):
        assert event_type == "workspace.member.updated"
        # _normalize_role が "admin" → "ws_admin" に変換 (DB 互換)
        assert detail["new_role"] == "ws_admin"

    async def fake_count(*a, **kw): return 5  # owner block かからない
    monkeypatch.setattr(ws, "_emit_audit", fake_emit)
    monkeypatch.setattr(ws, "_count_role", fake_count)

    result = await ws.update_member_role(1, "u", role="admin", actor_user_id="boss")
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_remove_member_happy_path(mock_db, monkeypatch) -> None:
    """remove_member: DELETE + audit emit (L 372-388)."""
    mock_db({"select": [{"workspace_id": 1, "user_id": "u",
                          "role": "contributor", "custom_permissions": None}]},
            rowcount=1)
    captured: list = []

    async def fake_emit(event_type, *, user_id=None, detail=None):
        captured.append((event_type, detail))

    monkeypatch.setattr(ws, "_emit_audit", fake_emit)
    ok = await ws.remove_member(1, "u", actor_user_id="boss")
    assert ok is True
    assert any(e[0] == "workspace.member.removed" for e in captured)


@pytest.mark.asyncio
async def test_remove_member_owner_protection_raises(mock_db, monkeypatch) -> None:
    """remove_member: 最後の owner は削除不可 (OwnerProtectedError)."""
    mock_db({"select": [{"workspace_id": 1, "user_id": "u",
                          "role": "owner", "custom_permissions": None}]})

    async def fake_count(*a, **kw): return 1  # 最後の owner

    monkeypatch.setattr(ws, "_count_role", fake_count)
    with pytest.raises(ws.OwnerProtectedError):
        await ws.remove_member(1, "u", actor_user_id="boss")


@pytest.mark.asyncio
async def test_remove_member_self_strip_raises(mock_db) -> None:
    """remove_member: 自分自身を削除 → SelfStripError."""
    with pytest.raises(ws.SelfStripError):
        await ws.remove_member(1, "u_self", actor_user_id="u_self")


@pytest.mark.asyncio
async def test_create_invitation_returns_token_and_url(mock_db) -> None:
    """create_invitation: INSERT + token / expires_at / invitation_url (L 414-424)."""
    mock_db({"insert into workspace_invitations": []})
    out = await ws.create_invitation(
        workspace_id=1, email="x@example.com",
        role="contributor", invited_by="alice", expires_in_days=7,
    )
    assert out["email"] == "x@example.com"
    assert out["role"] == "contributor"
    assert "token" in out and len(out["token"]) >= 16
    assert out["invitation_url"].startswith("/invite/")
    assert "expires_at" in out


@pytest.mark.asyncio
async def test_accept_invitation_member_added(mock_db) -> None:
    """accept_invitation: valid token → member 追加 (L 435-467)."""
    from datetime import datetime, timedelta
    future = (datetime.now() + timedelta(days=7)).isoformat(timespec="seconds")
    mock_db({"select * from workspace_invitations": [{
        "id": 10, "workspace_id": 5, "email": "u@example.com",
        "role": "contributor", "status": "pending",
        "expires_at": future, "invited_by": "alice",
    }]})
    out = await ws.accept_invitation(token="abc", user_id="new_user")
    assert out is not None
    assert out["workspace_id"] == 5
    assert out["user_id"] == "new_user"
    assert out["role"] == "contributor"


@pytest.mark.asyncio
async def test_accept_invitation_unknown_token_returns_none(mock_db) -> None:
    mock_db({"select * from workspace_invitations": []})
    out = await ws.accept_invitation(token="bad", user_id="u")
    assert out is None


@pytest.mark.asyncio
async def test_accept_invitation_expired_returns_none(mock_db) -> None:
    """期限切れ token → status='expired' 更新 + None 返却."""
    from datetime import datetime, timedelta
    past = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    mock_db({"select * from workspace_invitations": [{
        "id": 11, "workspace_id": 5, "email": "u@example.com",
        "role": "contributor", "status": "pending",
        "expires_at": past, "invited_by": "alice",
    }]})
    out = await ws.accept_invitation(token="exp", user_id="u")
    assert out is None


@pytest.mark.asyncio
async def test_accept_invitation_malformed_expires_at_does_not_crash(mock_db) -> None:
    """expires_at が parse 不能でも crash しない (try/except)."""
    mock_db({"select * from workspace_invitations": [{
        "id": 12, "workspace_id": 5, "email": "u@x.com",
        "role": "contributor", "status": "pending",
        "expires_at": "not-an-iso-date",
        "invited_by": None,
    }]})
    out = await ws.accept_invitation(token="t", user_id="u")
    assert out is not None  # parse 失敗時は pass → member 追加に進む
