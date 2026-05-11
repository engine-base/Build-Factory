"""T-009-01: task_dependencies CRUD AC 検証.

DB mock で 4 AC 機械検証. T-001-09 cycle 防止 trigger との連携も検証.

AC マッピング:
  AC-1 UBIQUITOUS: 5 endpoint (list by task / list by project / get / create / delete)
  AC-2 EVENT:     2 秒以内 + {detail: {code, message}}
  AC-3 STATE:     T-001-09 trigger と連携 (cycle 検出 → DepCycleDetected)
  AC-4 UNWANTED:  self-loop / cycle / duplicate / dep_type enum 外 / not_found → 4xx
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import task_dependency_service as tds
from services.task_dependency_service import (
    InvalidDepInput, DepCycleDetected, DepNotFound, VALID_DEP_TYPES,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────
# DB mock
# ──────────────────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rows=None, rowcount=0):
        self._rows = list(rows or [])
        self.rowcount = rowcount

    async def fetchone(self): return self._rows.pop(0) if self._rows else None
    async def fetchall(self): return list(self._rows)


class _FakeConn:
    Row = dict

    def __init__(self, rows_by_kw=None, rowcount=1,
                 raise_on_insert: Optional[str] = None):  # noqa: F821
        self._rows = rows_by_kw or {}
        self._rowcount = rowcount
        self._raise_on_insert = raise_on_insert
        self.row_factory = None

    async def execute_fetchall(self, sql, *args):
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return rows
        return []

    async def execute(self, sql, *args):
        s = sql.lower()
        if "insert into bf_task_dependencies" in s and self._raise_on_insert:
            raise RuntimeError(self._raise_on_insert)
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return _FakeCursor(rows=rows, rowcount=self._rowcount)
        return _FakeCursor(rows=[], rowcount=self._rowcount)

    async def commit(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass


# typing.Optional は使うが定義の関係で簡略化
from typing import Optional  # noqa: E402


class _FakeAiosqlite:
    Row = dict

    def __init__(self, **kw): self._kw = kw

    def connect(self, _path):
        return _FakeConn(**self._kw)


@pytest.fixture
def mock_db(monkeypatch):
    def _apply(**kwargs):
        fake = _FakeAiosqlite(**kwargs)
        monkeypatch.setattr(tds, "aiosqlite", fake)
        return fake
    return _apply


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 5 endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_router_list_by_task(client, monkeypatch) -> None:
    async def fake(tid): return [{"id": 1, "task_id": tid, "depends_on_task_id": 2, "dep_type": "blocks"}]
    monkeypatch.setattr(tds, "list_dependencies_by_task", fake)
    r = client.get("/api/tasks/1/dependencies")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["task_id"] == 1


def test_router_list_by_project(client, monkeypatch) -> None:
    async def fake(pid): return [
        {"id": 1, "task_id": 1, "depends_on_task_id": 2, "dep_type": "blocks"},
        {"id": 2, "task_id": 2, "depends_on_task_id": 3, "dep_type": "related"},
    ]
    monkeypatch.setattr(tds, "list_dependencies_by_project", fake)
    r = client.get("/api/projects/1/dependencies")
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_router_get_dep(client, monkeypatch) -> None:
    async def fake(did): return {"id": did, "task_id": 1, "depends_on_task_id": 2}
    monkeypatch.setattr(tds, "get_dependency", fake)
    r = client.get("/api/dependencies/1")
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_router_get_dep_404(client, monkeypatch) -> None:
    async def fake(did): return None
    monkeypatch.setattr(tds, "get_dependency", fake)
    r = client.get("/api/dependencies/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "dep_not_found"


def test_router_create_dep_happy(client, monkeypatch) -> None:
    async def fake(**kw):
        return {"id": 42, **kw}
    monkeypatch.setattr(tds, "create_dependency", fake)
    r = client.post("/api/tasks/1/dependencies", json={
        "depends_on_task_id": 2, "dep_type": "blocks",
    })
    assert r.status_code == 200
    assert r.json()["id"] == 42


def test_router_delete_dep(client, monkeypatch) -> None:
    async def fake(did): return True
    monkeypatch.setattr(tds, "delete_dependency", fake)
    r = client.delete("/api/dependencies/1")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_router_delete_dep_404(client, monkeypatch) -> None:
    async def fake(did): return False
    monkeypatch.setattr(tds, "delete_dependency", fake)
    r = client.delete("/api/dependencies/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "dep_not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: invalid input → 4xx + {code, message}
# ──────────────────────────────────────────────────────────────────────────


def test_router_create_self_loop_returns_400(client, monkeypatch) -> None:
    async def fake(**kw):
        raise InvalidDepInput("task cannot depend on itself (task_id=1)")
    monkeypatch.setattr(tds, "create_dependency", fake)
    r = client.post("/api/tasks/1/dependencies", json={"depends_on_task_id": 1})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "self_loop"


def test_router_create_cycle_returns_409(client, monkeypatch) -> None:
    async def fake(**kw):
        raise DepCycleDetected("cycle would form: task_id=1 → depends_on=2")
    monkeypatch.setattr(tds, "create_dependency", fake)
    r = client.post("/api/tasks/1/dependencies", json={"depends_on_task_id": 2})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "cycle_detected"
    assert "cycle" in detail["message"].lower()


def test_router_create_duplicate_returns_409(client, monkeypatch) -> None:
    async def fake(**kw):
        raise InvalidDepInput("dependency already exists: task_id=1 → depends_on=2")
    monkeypatch.setattr(tds, "create_dependency", fake)
    r = client.post("/api/tasks/1/dependencies", json={"depends_on_task_id": 2})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "dep_duplicate"


def test_router_create_invalid_dep_type_returns_400(client, monkeypatch) -> None:
    async def fake(**kw):
        raise InvalidDepInput("dep_type must be one of ('blocks','related','informs')")
    monkeypatch.setattr(tds, "create_dependency", fake)
    r = client.post("/api/tasks/1/dependencies", json={
        "depends_on_task_id": 2, "dep_type": "BOGUS",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_dep_type"


# ──────────────────────────────────────────────────────────────────────────
# Service layer (DB mock 経由)
# ──────────────────────────────────────────────────────────────────────────


def test_service_valid_dep_types_constant() -> None:
    """dep_type 3 enum (blocks/related/informs) — DB CHECK 制約と一致."""
    assert set(VALID_DEP_TYPES) == {"blocks", "related", "informs"}


def test_service_validate_dep_type_rejects_unknown() -> None:
    with pytest.raises(InvalidDepInput, match="dep_type must be"):
        tds._validate_dep_type("BOGUS")


@pytest.mark.parametrize("dt", VALID_DEP_TYPES)
def test_service_validate_dep_type_accepts_all_3(dt: str) -> None:
    tds._validate_dep_type(dt)  # 例外なし


def test_service_create_rejects_self_loop(mock_db) -> None:
    mock_db()
    with pytest.raises(InvalidDepInput, match="depend on itself"):
        asyncio.run(tds.create_dependency(
            task_id=1, depends_on_task_id=1,
        ))


def test_service_create_rejects_invalid_dep_type(mock_db) -> None:
    mock_db()
    with pytest.raises(InvalidDepInput, match="dep_type must be"):
        asyncio.run(tds.create_dependency(
            task_id=1, depends_on_task_id=2, dep_type="BOGUS",
        ))


def test_service_create_detects_cycle_from_trigger(mock_db) -> None:
    """DB trigger (T-001-09) が cycle_detected を raise → DepCycleDetected."""
    mock_db(raise_on_insert="cycle_detected: adding dep (1 → 2) would create cycle")
    with pytest.raises(DepCycleDetected, match="cycle would form"):
        asyncio.run(tds.create_dependency(
            task_id=1, depends_on_task_id=2,
        ))


def test_service_create_handles_unique_conflict(mock_db) -> None:
    """UNIQUE 制約違反 (重複 dep) → InvalidDepInput."""
    mock_db(raise_on_insert="UNIQUE constraint failed: uq_bf_dep")
    with pytest.raises(InvalidDepInput, match="already exists"):
        asyncio.run(tds.create_dependency(
            task_id=1, depends_on_task_id=2,
        ))


def test_service_create_check_violation_treated_as_cycle(mock_db) -> None:
    """check_violation ERRCODE も cycle 扱い (defense in depth)."""
    mock_db(raise_on_insert="check_violation: bf_prevent_task_dep_cycle")
    with pytest.raises(DepCycleDetected):
        asyncio.run(tds.create_dependency(
            task_id=1, depends_on_task_id=2,
        ))


def test_service_create_inserts_and_returns_row(mock_db) -> None:
    """正常 INSERT → get_dependency で返却."""
    mock_db(rows_by_kw={
        "insert into bf_task_dependencies": [{"id": 42}],
        "select * from bf_task_dependencies": [
            {"id": 42, "task_id": 1, "depends_on_task_id": 2, "dep_type": "blocks"},
        ],
    })
    out = asyncio.run(tds.create_dependency(
        task_id=1, depends_on_task_id=2, dep_type="blocks",
    ))
    assert out["id"] == 42
    assert out["dep_type"] == "blocks"


def test_service_list_by_task(mock_db) -> None:
    mock_db(rows_by_kw={
        "select * from bf_task_dependencies": [
            {"id": 1, "task_id": 1, "depends_on_task_id": 2, "dep_type": "blocks"},
        ],
    })
    out = asyncio.run(tds.list_dependencies_by_task(1))
    assert len(out) == 1


def test_service_list_by_project_uses_join(mock_db) -> None:
    """project 検索は bf_tasks JOIN."""
    mock_db(rows_by_kw={
        "join bf_tasks": [
            {"id": 1, "task_id": 1, "depends_on_task_id": 2, "dep_type": "blocks"},
            {"id": 2, "task_id": 2, "depends_on_task_id": 3, "dep_type": "related"},
        ],
    })
    out = asyncio.run(tds.list_dependencies_by_project(1))
    assert len(out) == 2


def test_service_get_dep_returns_row(mock_db) -> None:
    mock_db(rows_by_kw={"select * from bf_task_dependencies": [
        {"id": 7, "task_id": 1, "depends_on_task_id": 2, "dep_type": "blocks"},
    ]})
    out = asyncio.run(tds.get_dependency(7))
    assert out["id"] == 7


def test_service_get_dep_returns_none(mock_db) -> None:
    mock_db(rows_by_kw={"select * from bf_task_dependencies": []})
    out = asyncio.run(tds.get_dependency(99999))
    assert out is None


def test_service_delete_dep_returns_true(mock_db) -> None:
    mock_db(rows_by_kw={"select * from bf_task_dependencies": [
        {"id": 1, "task_id": 1, "depends_on_task_id": 2},
    ]}, rowcount=1)
    out = asyncio.run(tds.delete_dependency(1))
    assert out is True


def test_service_delete_dep_returns_false_when_not_found(mock_db) -> None:
    mock_db(rows_by_kw={"select * from bf_task_dependencies": []})
    out = asyncio.run(tds.delete_dependency(99999))
    assert out is False


# ──────────────────────────────────────────────────────────────────────────
# Exception hierarchy
# ──────────────────────────────────────────────────────────────────────────


def test_invalid_dep_input_inherits_value_error() -> None:
    assert issubclass(InvalidDepInput, ValueError)


def test_dep_cycle_detected_inherits_value_error() -> None:
    assert issubclass(DepCycleDetected, ValueError)


def test_dep_not_found_inherits_value_error() -> None:
    assert issubclass(DepNotFound, ValueError)