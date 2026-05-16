"""T-V3-B-28 / F-026: Constitution **service** layer tests.

router test (test_constitution.py) は services を monkeypatch しているため,
service 本体のロジックは本テストで網羅する.

戦略: aiosqlite (postgres) を本物の接続なしで動かすため, db.async_db.connect
を fake-connection に差し替える. SQL を逐次 in-memory dict に反映する
最小限の fake (workspaces / bf_constitutions / bf_constitution_revisions
3 テーブル分).
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest


# ──────────────────────────────────────────────────────────────────────────
# Fake DB (in-memory)
# ──────────────────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rows=None, lastrowid=None):
        self._rows = list(rows or [])
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)


class _FakeDB:
    """超軽量 fake (本サービスが発行する 7 種の SQL だけ理解する)."""

    def __init__(self, store):
        self.store = store
        self.row_factory = None

    async def execute(self, sql: str, params=()):
        sql_norm = " ".join(sql.split())
        params = tuple(params) if params else ()

        # CREATE TABLE no-op
        if sql_norm.startswith("CREATE TABLE"):
            return _FakeCursor(rows=[])

        # sqlite_master テーブル存在チェック (_table_exists)
        if "sqlite_master" in sql_norm:
            table_name = params[0] if params else ""
            return _FakeCursor(
                rows=[{"name": table_name}] if table_name in self.store["tables"] else []
            )

        # workspaces 存在チェック
        if "FROM workspaces WHERE id = ?" in sql_norm or "from workspaces where id = ?" in sql_norm.lower():
            wid = params[0]
            return _FakeCursor(
                rows=[{"1": 1}] if wid in self.store["workspaces"] else []
            )

        # 現 active 取得 (GET)
        if "SELECT version, principles, is_current FROM bf_constitutions" in sql_norm:
            wid = params[0]
            rows = sorted(
                [r for r in self.store["bf_constitutions"]
                 if r["workspace_id"] == wid and r["is_current"] == 1],
                key=lambda r: -r["version"],
            )
            return _FakeCursor(rows=rows)

        # max(version) 採番
        if "SELECT COALESCE(MAX(version)" in sql_norm:
            wid = params[0]
            mx = max(
                (r["version"] for r in self.store["bf_constitutions"]
                 if r["workspace_id"] == wid),
                default=0,
            )
            return _FakeCursor(rows=[{"mx": mx}])

        # version 取得 (approve target)
        if "SELECT id, is_current FROM bf_constitutions" in sql_norm:
            wid, v = params
            for r in self.store["bf_constitutions"]:
                if r["workspace_id"] == wid and r["version"] == v:
                    return _FakeCursor(rows=[r])
            return _FakeCursor(rows=[])

        # INSERT bf_constitutions
        if sql_norm.startswith("INSERT INTO bf_constitutions"):
            wid, version, principles, author = params
            new_id = len(self.store["bf_constitutions"]) + 1
            self.store["bf_constitutions"].append({
                "id": new_id, "workspace_id": wid, "version": version,
                "principles": principles, "is_current": 0,
                "authored_by": author, "approved_by": None, "approved_at": None,
            })
            return _FakeCursor(rows=[], lastrowid=new_id)

        # INSERT bf_constitution_revisions
        if sql_norm.startswith("INSERT INTO bf_constitution_revisions"):
            cid, diff, rationale, revised_by = params
            self.store["bf_constitution_revisions"].append({
                "id": len(self.store["bf_constitution_revisions"]) + 1,
                "constitution_id": cid, "diff": diff, "rationale": rationale,
                "revised_by": revised_by,
            })
            return _FakeCursor(rows=[], lastrowid=len(self.store["bf_constitution_revisions"]))

        # UPDATE deactivate
        if "UPDATE bf_constitutions SET is_current = 0" in sql_norm:
            wid = params[0]
            for r in self.store["bf_constitutions"]:
                if r["workspace_id"] == wid:
                    r["is_current"] = 0
            return _FakeCursor(rows=[])

        # UPDATE activate
        if "UPDATE bf_constitutions SET is_current = 1" in sql_norm:
            approver, approved_at, rid = params
            for r in self.store["bf_constitutions"]:
                if r["id"] == rid:
                    r["is_current"] = 1
                    r["approved_by"] = approver
                    r["approved_at"] = approved_at
            return _FakeCursor(rows=[])

        raise AssertionError(f"unexpected SQL in fake: {sql_norm!r}")

    async def commit(self):
        pass


@pytest.fixture
def fake_db(monkeypatch):
    """services.constitution_service が呼ぶ aiosqlite.connect を fake に差し替える."""
    store = {
        "workspaces": {1, 2},
        "bf_constitutions": [],
        "bf_constitution_revisions": [],
        "tables": {"workspaces", "bf_constitutions", "bf_constitution_revisions"},
    }

    @asynccontextmanager
    async def fake_connect(_path=None, **kw):
        yield _FakeDB(store)

    from services import constitution_service as cs
    monkeypatch.setattr(cs.aiosqlite, "connect", fake_connect)
    # Row 属性は不要 (FakeCursor.fetchone は dict を返す)
    monkeypatch.setattr(cs.aiosqlite, "Row", dict, raising=False)
    return store


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_constitution_returns_none_when_empty(fake_db):
    from services import constitution_service as cs
    assert await cs.get_constitution(1) is None


@pytest.mark.asyncio
async def test_get_constitution_workspace_not_found(fake_db):
    from services import constitution_service as cs
    with pytest.raises(cs.WorkspaceNotFoundError):
        await cs.get_constitution(99999)


@pytest.mark.asyncio
async def test_create_version_assigns_increasing_version_numbers(fake_db):
    """AC-F1: create はバージョン採番するが active 化はしない."""
    from services import constitution_service as cs

    r1 = await cs.create_version(
        workspace_id=1, content_md="# v1", message="initial", author="masato",
    )
    assert r1["version_number"] == 1
    assert r1["version_id"]  # uuid 文字列

    r2 = await cs.create_version(
        workspace_id=1, content_md="# v2", message="second", author="masato",
    )
    assert r2["version_number"] == 2

    # AC-F1: active 化されていない → get_constitution は None
    assert await cs.get_constitution(1) is None


@pytest.mark.asyncio
async def test_create_version_rejects_too_large(fake_db):
    """AC-F3: 10 KB 超で ContentTooLargeError."""
    from services import constitution_service as cs
    too_big = "x" * (10 * 1024 + 1)
    with pytest.raises(cs.ContentTooLargeError):
        await cs.create_version(
            workspace_id=1, content_md=too_big, message="m", author="a",
        )


@pytest.mark.asyncio
async def test_create_version_rejects_empty(fake_db):
    from services import constitution_service as cs
    with pytest.raises(cs.ContentTooLargeError):
        await cs.create_version(
            workspace_id=1, content_md="   ", message="m", author="a",
        )


@pytest.mark.asyncio
async def test_create_version_workspace_not_found(fake_db):
    from services import constitution_service as cs
    with pytest.raises(cs.WorkspaceNotFoundError):
        await cs.create_version(
            workspace_id=99999, content_md="# ok", message="m", author="a",
        )


@pytest.mark.asyncio
async def test_approve_version_activates_and_returns_contract(fake_db):
    """AC-F2 / AC-F10: approve で is_current=1 + get で参照可能になる."""
    from services import constitution_service as cs

    r = await cs.create_version(
        workspace_id=1, content_md="# v1 body", message="m1", author="masato",
    )
    assert r["version_number"] == 1

    approved = await cs.approve_version(
        workspace_id=1, version=1, approver="masato",
    )
    assert approved["active_version"] == 1
    assert "T" in approved["approved_at"]  # ISO 形式

    got = await cs.get_constitution(1)
    assert got is not None
    assert got["version"] == 1
    assert got["is_active"] is True
    assert got["content_md"] == "# v1 body"


@pytest.mark.asyncio
async def test_approve_version_deactivates_previous_active(fake_db):
    """AC-F2: 新 version approve で旧 active を deactivate (atomic)."""
    from services import constitution_service as cs

    await cs.create_version(workspace_id=1, content_md="# v1", message="m1", author="a")
    await cs.create_version(workspace_id=1, content_md="# v2", message="m2", author="a")
    await cs.approve_version(workspace_id=1, version=1, approver="a")
    assert (await cs.get_constitution(1))["version"] == 1

    await cs.approve_version(workspace_id=1, version=2, approver="a")
    got = await cs.get_constitution(1)
    assert got["version"] == 2
    assert got["content_md"] == "# v2"


@pytest.mark.asyncio
async def test_approve_version_already_active(fake_db):
    """409: 既に active な version を再 approve すると AlreadyActiveError."""
    from services import constitution_service as cs

    await cs.create_version(workspace_id=1, content_md="# v1", message="m1", author="a")
    await cs.approve_version(workspace_id=1, version=1, approver="a")

    with pytest.raises(cs.AlreadyActiveError):
        await cs.approve_version(workspace_id=1, version=1, approver="a")


@pytest.mark.asyncio
async def test_approve_version_not_found(fake_db):
    from services import constitution_service as cs
    with pytest.raises(cs.VersionNotFoundError):
        await cs.approve_version(workspace_id=1, version=999, approver="a")


@pytest.mark.asyncio
async def test_approve_version_workspace_not_found(fake_db):
    from services import constitution_service as cs
    with pytest.raises(cs.WorkspaceNotFoundError):
        await cs.approve_version(workspace_id=99999, version=1, approver="a")


@pytest.mark.asyncio
async def test_versions_are_isolated_per_workspace(fake_db):
    """workspace_id ごとに version 採番は独立."""
    from services import constitution_service as cs

    a = await cs.create_version(workspace_id=1, content_md="# A", message="ma", author="u")
    b = await cs.create_version(workspace_id=2, content_md="# B", message="mb", author="u")
    assert a["version_number"] == 1
    assert b["version_number"] == 1


@pytest.mark.asyncio
async def test_principles_to_content_md_section_fallback(fake_db):
    """legacy principles (section_* keys) からも content_md を取れる."""
    from services import constitution_service as cs

    # 直接 fake store に legacy 形式の行を投入
    legacy = {
        "section_2_values": ["シンプル", "速く"],
        "section_4_red_lines": ["DROP TABLE 禁止"],
    }
    fake_db["bf_constitutions"].append({
        "id": 1, "workspace_id": 1, "version": 1,
        "principles": json.dumps(legacy, ensure_ascii=False),
        "is_current": 1, "authored_by": "legacy",
        "approved_by": None, "approved_at": None,
    })

    got = await cs.get_constitution(1)
    assert got is not None
    assert got["version"] == 1
    assert got["is_active"] is True
    # legacy section_* の少なくとも 1 件は文字列に含まれる
    assert "section_2_values" in got["content_md"] or "section_4_red_lines" in got["content_md"]
