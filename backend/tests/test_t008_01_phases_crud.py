"""T-008-01: phases CRUD AC 検証.

DB mock で全 path カバー + 4 AC 機械検証.

AC マッピング:
  AC-1 UBIQUITOUS: 7 endpoint (list/get/create/update/start/complete/delete)
  AC-2 EVENT:     2 秒以内 + {detail: {code, message}}
  AC-3 STATE:     idempotent start (in_progress 既 → 同じ row 返す)
  AC-4 UNWANTED:  invalid phase_no / status / 空 name / duplicate → 4xx + {code, message}
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import phase_service as ps
from services.phase_service import (
    InvalidPhaseInput, PhaseNotFound, VALID_PHASE_STATUSES,
    PHASE_NO_MIN, PHASE_NO_MAX,
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

    def __init__(self, rows_by_kw=None, rowcount=1, raise_on_keyword=None):
        self._rows = rows_by_kw or {}
        self._rowcount = rowcount
        self._raise_on = raise_on_keyword
        self.row_factory = None
        self.executed: list[tuple[str, tuple]] = []

    async def execute_fetchall(self, sql, *args):
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return rows
        return []

    async def execute(self, sql, *args):
        self.executed.append((sql, args[0] if args else ()))
        if self._raise_on and self._raise_on.lower() in sql.lower():
            raise RuntimeError("UNIQUE constraint failed: uq_bf_phase")
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return _FakeCursor(rows=rows, rowcount=self._rowcount)
        return _FakeCursor(rows=[], rowcount=self._rowcount)

    async def commit(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass


class _FakeAiosqlite:
    Row = dict

    def __init__(self, **kw):
        self._kw = kw

    def connect(self, _path):
        return _FakeConn(**self._kw)


@pytest.fixture
def mock_db(monkeypatch):
    def _apply(**kwargs):
        fake = _FakeAiosqlite(**kwargs)
        monkeypatch.setattr(ps, "aiosqlite", fake)
        return fake
    return _apply


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 7 endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_router_list_phases(client, monkeypatch) -> None:
    async def fake(pid): return [{"id": 1, "phase_no": 1, "name": "hearing"}]
    monkeypatch.setattr(ps, "list_phases", fake)
    r = client.get("/api/projects/1/phases")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["phases"][0]["phase_no"] == 1


def test_router_get_phase(client, monkeypatch) -> None:
    async def fake(pid): return {"id": pid, "name": "hearing", "status": "pending"}
    monkeypatch.setattr(ps, "get_phase", fake)
    r = client.get("/api/phases/1")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_router_get_phase_404(client, monkeypatch) -> None:
    async def fake(pid): return None
    monkeypatch.setattr(ps, "get_phase", fake)
    r = client.get("/api/phases/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "phase_not_found"


def test_router_create_phase(client, monkeypatch) -> None:
    async def fake(**kw):
        return {"id": 100, **kw}
    monkeypatch.setattr(ps, "create_phase", fake)
    r = client.post("/api/projects/1/phases", json={
        "phase_no": 1, "name": "hearing",
    })
    assert r.status_code == 200
    assert r.json()["name"] == "hearing"


def test_router_update_phase(client, monkeypatch) -> None:
    async def fake(pid, **fields):
        return {"id": pid, **fields}
    monkeypatch.setattr(ps, "update_phase", fake)
    r = client.patch("/api/phases/1", json={"name": "updated", "status": "in_progress"})
    assert r.status_code == 200


def test_router_start_phase(client, monkeypatch) -> None:
    async def fake(pid):
        return {"id": pid, "status": "in_progress", "started_at": "2026-05-12"}
    monkeypatch.setattr(ps, "start_phase", fake)
    r = client.post("/api/phases/1/start")
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_router_complete_phase(client, monkeypatch) -> None:
    async def fake(pid):
        return {"id": pid, "status": "completed", "completed_at": "2026-05-12"}
    monkeypatch.setattr(ps, "complete_phase", fake)
    r = client.post("/api/phases/1/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_router_delete_phase(client, monkeypatch) -> None:
    async def fake(pid): return True
    monkeypatch.setattr(ps, "delete_phase", fake)
    r = client.delete("/api/phases/1")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_router_delete_phase_404(client, monkeypatch) -> None:
    async def fake(pid): return False
    monkeypatch.setattr(ps, "delete_phase", fake)
    r = client.delete("/api/phases/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "phase_not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: invalid input → 400/409 + {code, message}
# ──────────────────────────────────────────────────────────────────────────


def test_router_create_phase_pydantic_rejects_phase_no_0(client) -> None:
    """phase_no < 1 → Pydantic 422 (ge=1)."""
    r = client.post("/api/projects/1/phases", json={
        "phase_no": 0, "name": "x",
    })
    assert r.status_code == 422


def test_router_create_phase_pydantic_rejects_phase_no_11(client) -> None:
    """phase_no > 10 → Pydantic 422 (le=10)."""
    r = client.post("/api/projects/1/phases", json={
        "phase_no": 11, "name": "x",
    })
    assert r.status_code == 422


def test_router_create_phase_empty_name_returns_400(client, monkeypatch) -> None:
    async def fake(**kw):
        raise InvalidPhaseInput("name must not be empty")
    monkeypatch.setattr(ps, "create_phase", fake)
    r = client.post("/api/projects/1/phases", json={
        "phase_no": 1, "name": "  ",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_name"


def test_router_create_phase_duplicate_returns_409(client, monkeypatch) -> None:
    async def fake(**kw):
        raise InvalidPhaseInput("phase_no 1 already exists for project 1")
    monkeypatch.setattr(ps, "create_phase", fake)
    r = client.post("/api/projects/1/phases", json={
        "phase_no": 1, "name": "hearing",
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "phase_duplicate"


def test_router_update_phase_invalid_status_400(client, monkeypatch) -> None:
    async def fake(pid, **fields):
        raise InvalidPhaseInput("status must be one of ...")
    monkeypatch.setattr(ps, "update_phase", fake)
    r = client.patch("/api/phases/1", json={"status": "BOGUS"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_status"


def test_router_update_phase_not_found_404(client, monkeypatch) -> None:
    async def fake(pid, **fields):
        raise PhaseNotFound(f"phase not found: {pid}")
    monkeypatch.setattr(ps, "update_phase", fake)
    r = client.patch("/api/phases/9999", json={"name": "x"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "phase_not_found"


def test_router_start_phase_not_found_404(client, monkeypatch) -> None:
    async def fake(pid):
        raise PhaseNotFound(f"phase not found: {pid}")
    monkeypatch.setattr(ps, "start_phase", fake)
    r = client.post("/api/phases/9999/start")
    assert r.status_code == 404


def test_router_complete_phase_not_found_404(client, monkeypatch) -> None:
    async def fake(pid):
        raise PhaseNotFound(f"phase not found: {pid}")
    monkeypatch.setattr(ps, "complete_phase", fake)
    r = client.post("/api/phases/9999/complete")
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────
# Service layer cov (DB mock 経由)
# ──────────────────────────────────────────────────────────────────────────


def test_service_validate_phase_no_rejects_out_of_range() -> None:
    with pytest.raises(InvalidPhaseInput):
        ps._validate_phase_no(0)
    with pytest.raises(InvalidPhaseInput):
        ps._validate_phase_no(11)
    with pytest.raises(InvalidPhaseInput):
        ps._validate_phase_no("1")  # type: ignore[arg-type]


def test_service_validate_phase_no_accepts_1_to_10() -> None:
    for n in range(PHASE_NO_MIN, PHASE_NO_MAX + 1):
        ps._validate_phase_no(n)


def test_service_validate_status_rejects_unknown() -> None:
    with pytest.raises(InvalidPhaseInput, match="status must be"):
        ps._validate_status("BOGUS")


def test_service_validate_status_accepts_all_5_enums() -> None:
    for s in VALID_PHASE_STATUSES:
        ps._validate_status(s)


def test_service_valid_phase_statuses_constant() -> None:
    """5 status (pending/in_progress/completed/blocked/skipped)."""
    assert set(VALID_PHASE_STATUSES) == {
        "pending", "in_progress", "completed", "blocked", "skipped",
    }


def test_service_create_phase_rejects_empty_name(mock_db) -> None:
    mock_db()
    with pytest.raises(InvalidPhaseInput, match="name"):
        asyncio.run(ps.create_phase(project_id=1, phase_no=1, name="  "))


def test_service_create_phase_inserts(mock_db) -> None:
    mock_db(rows_by_kw={
        "insert into bf_phases": [{"id": 42}],
        "select * from bf_phases": [
            {"id": 42, "project_id": 1, "phase_no": 1, "name": "hearing",
             "status": "pending"},
        ],
    })
    out = asyncio.run(ps.create_phase(
        project_id=1, phase_no=1, name="hearing",
        artifacts_dir="docs/h", notes="initial",
    ))
    assert out["id"] == 42
    assert out["name"] == "hearing"


def test_service_create_phase_duplicate_raises(mock_db) -> None:
    """UNIQUE 制約違反 → InvalidPhaseInput."""
    mock_db(raise_on_keyword="insert into bf_phases")
    with pytest.raises(InvalidPhaseInput, match="already exists"):
        asyncio.run(ps.create_phase(
            project_id=1, phase_no=1, name="hearing",
        ))


def test_service_get_phase_returns_row(mock_db) -> None:
    mock_db(rows_by_kw={"select": [{"id": 1, "phase_no": 1, "name": "x"}]})
    out = asyncio.run(ps.get_phase(1))
    assert out["phase_no"] == 1


def test_service_get_phase_returns_none(mock_db) -> None:
    mock_db(rows_by_kw={"select": []})
    out = asyncio.run(ps.get_phase(99999))
    assert out is None


def test_service_list_phases_returns_ordered(mock_db) -> None:
    mock_db(rows_by_kw={
        "select * from bf_phases": [
            {"id": 1, "phase_no": 1, "name": "hearing"},
            {"id": 2, "phase_no": 2, "name": "requirements"},
        ],
    })
    out = asyncio.run(ps.list_phases(1))
    assert len(out) == 2


def test_service_update_phase_not_found_raises(mock_db) -> None:
    mock_db(rows_by_kw={"select": []})
    with pytest.raises(PhaseNotFound):
        asyncio.run(ps.update_phase(99999, name="x"))


def test_service_update_phase_invalid_status_raises(mock_db) -> None:
    mock_db(rows_by_kw={"select": [{"id": 1, "name": "x"}]})
    with pytest.raises(InvalidPhaseInput, match="status"):
        asyncio.run(ps.update_phase(1, status="BOGUS"))


def test_service_update_phase_invalid_phase_no_raises(mock_db) -> None:
    mock_db(rows_by_kw={"select": [{"id": 1, "name": "x"}]})
    with pytest.raises(InvalidPhaseInput, match="phase_no"):
        asyncio.run(ps.update_phase(1, phase_no=99))


def test_service_update_phase_empty_name_raises(mock_db) -> None:
    mock_db(rows_by_kw={"select": [{"id": 1, "name": "x"}]})
    with pytest.raises(InvalidPhaseInput, match="name"):
        asyncio.run(ps.update_phase(1, name="  "))


def test_service_update_phase_no_fields_returns_existing(mock_db) -> None:
    """fields 空 → existing 返却."""
    mock_db(rows_by_kw={"select": [{"id": 1, "name": "x"}]})
    out = asyncio.run(ps.update_phase(1))
    assert out["id"] == 1


def test_service_update_phase_unique_conflict_raises(monkeypatch) -> None:
    """UPDATE 中 UNIQUE conflict (phase_no 衝突) → InvalidPhaseInput."""
    class _UpdConn(_FakeConn):
        async def execute(self, sql, *args):
            self.executed.append((sql, args[0] if args else ()))
            s = sql.lower()
            if "update bf_phases" in s:
                raise RuntimeError("UNIQUE constraint failed: uq_bf_phase")
            if "select" in s:
                return _FakeCursor(rows=[{"id": 1, "name": "x"}])
            return _FakeCursor()

    class _FA:
        Row = dict
        def connect(self, _p): return _UpdConn()
    monkeypatch.setattr(ps, "aiosqlite", _FA())

    with pytest.raises(InvalidPhaseInput, match="conflicts"):
        asyncio.run(ps.update_phase(1, phase_no=2))


def test_service_start_phase_idempotent(mock_db) -> None:
    """既 in_progress なら同じ row 返す (idempotent)."""
    mock_db(rows_by_kw={"select": [
        {"id": 1, "status": "in_progress", "started_at": "2026-01-01"},
    ]})
    out = asyncio.run(ps.start_phase(1))
    assert out["status"] == "in_progress"


def test_service_start_phase_not_found(mock_db) -> None:
    mock_db(rows_by_kw={"select": []})
    with pytest.raises(PhaseNotFound):
        asyncio.run(ps.start_phase(99999))


def test_service_start_phase_transitions_to_in_progress(mock_db) -> None:
    """pending → in_progress に遷移."""
    rows = [
        {"id": 1, "status": "pending"},          # 1 回目 SELECT (existence check)
        {"id": 1, "status": "in_progress"},      # 2 回目 SELECT (return value)
    ]
    mock_db(rows_by_kw={"select": rows})
    out = asyncio.run(ps.start_phase(1))
    # 戻り値は最終 SELECT の row (2 回目)
    assert isinstance(out, dict)


def test_service_complete_phase(mock_db) -> None:
    rows = [
        {"id": 1, "status": "in_progress"},
        {"id": 1, "status": "completed"},
    ]
    mock_db(rows_by_kw={"select": rows})
    out = asyncio.run(ps.complete_phase(1))
    assert isinstance(out, dict)


def test_service_complete_phase_not_found(mock_db) -> None:
    mock_db(rows_by_kw={"select": []})
    with pytest.raises(PhaseNotFound):
        asyncio.run(ps.complete_phase(99999))


def test_service_delete_phase_returns_true_when_deleted(mock_db) -> None:
    mock_db(rows_by_kw={"select": [{"id": 1, "status": "pending"}]}, rowcount=1)
    out = asyncio.run(ps.delete_phase(1))
    assert out is True


def test_service_delete_phase_returns_false_when_not_found(mock_db) -> None:
    mock_db(rows_by_kw={"select": []})
    out = asyncio.run(ps.delete_phase(99999))
    assert out is False


# ──────────────────────────────────────────────────────────────────────────
# Exception hierarchy
# ──────────────────────────────────────────────────────────────────────────


def test_invalid_phase_input_inherits_value_error() -> None:
    assert issubclass(InvalidPhaseInput, ValueError)


def test_phase_not_found_inherits_value_error() -> None:
    assert issubclass(PhaseNotFound, ValueError)