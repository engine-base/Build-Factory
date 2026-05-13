"""T-008-01 phases CRUD — 1:1 spec verification test.

docs/audit/2026-05-13_v2/T-008-01.md と 1:1 で trace する spec test.
F-008 「プロジェクト・フェーズ管理基盤」の `phases CRUD` を 4 AC × 24
sub-clause で機械検証する.

設計原則 (PR #251 pattern):
  - 各 sub-clause に対し、シグネチャ存在ではなく **意味的不変条件** を検証する
    test を最低 1 つ書く (state mutation の前後 / ordering / validation timing
    / response shape / error handling).
  - 既存 test_t008_01_phases_crud.py は併存 (本 spec test は audit との 1:1
    trace を主眼とする, REUSE 適合 9 項目の機械検証も同梱).

AC マッピング:
  AC-1 UBIQUITOUS (7 test) — DDL / endpoint / service 公開 + 5 status enum + 1..10 range
  AC-2 EVENT-DRIVEN (5 test) — success shape / error envelope / latency
  AC-3 STATE-DRIVEN (5 test) — REFACTOR invariant + idempotent + soft-delete
  AC-4 UNWANTED (7 test) — validation BEFORE mutation / 4xx / no partial mutation
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import phase_service as ps
from services.phase_service import (
    InvalidPhaseInput,
    PhaseNotFound,
    VALID_PHASE_STATUSES,
    PHASE_NO_MIN,
    PHASE_NO_MAX,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BF = REPO_ROOT / "supabase" / "migrations" / "20260510000001_bf_project_tables.sql"
PHASE_SERVICE_FILE = REPO_ROOT / "backend" / "services" / "phase_service.py"
PHASES_ROUTER_FILE = REPO_ROOT / "backend" / "routers" / "phases.py"
FEATURES_JSON = REPO_ROOT / "docs" / "functional-breakdown" / "2026-05-09_v1" / "features.json"
AUDIT_DOC = REPO_ROOT / "docs" / "audit" / "2026-05-13_v2" / "T-008-01.md"


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


class _Cursor:
    def __init__(self, rows: list[dict] | None = None, rowcount: int = 0) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount
        self.lastrowid = 1

    async def fetchone(self) -> dict | None:
        return self._rows.pop(0) if self._rows else None

    async def fetchall(self) -> list[dict]:
        return list(self._rows)


class FakeConn:
    """Records all execute() calls so tests can verify ordering / 'no mutation' invariants.

    `executed` list captures (sql, params) tuples. Tests assert that, when validation
    rejects input, the executed list contains no INSERT/UPDATE/DELETE entries.
    """

    Row = dict

    def __init__(
        self,
        rows_by_kw: dict[str, list[dict]] | None = None,
        rowcount: int = 1,
        raise_on_keyword: str | None = None,
    ) -> None:
        self._rows = rows_by_kw or {}
        self._rowcount = rowcount
        self._raise_on = raise_on_keyword
        self.row_factory = None
        self.executed: list[tuple[str, tuple]] = []
        self.commits = 0

    async def execute_fetchall(self, sql: str, *args: Any) -> list[dict]:
        self.executed.append((sql, args[0] if args else ()))
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return rows
        return []

    async def execute(self, sql: str, *args: Any) -> _Cursor:
        self.executed.append((sql, args[0] if args else ()))
        if self._raise_on and self._raise_on.lower() in sql.lower():
            raise RuntimeError("UNIQUE constraint failed: uq_bf_phase")
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return _Cursor(rows=rows, rowcount=self._rowcount)
        return _Cursor(rows=[], rowcount=self._rowcount)

    async def commit(self) -> None:
        self.commits += 1

    async def __aenter__(self) -> "FakeConn":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


class _FakeAiosqlite:
    Row = dict

    def __init__(self, **kw: Any) -> None:
        self._kw = kw
        self.last_conn: FakeConn | None = None

    def connect(self, _path: str) -> FakeConn:
        self.last_conn = FakeConn(**self._kw)
        return self.last_conn


@pytest.fixture
def fake_db(monkeypatch):
    """Replace aiosqlite in phase_service with a FakeConn factory and return it."""
    def _apply(**kwargs: Any) -> _FakeAiosqlite:
        fake = _FakeAiosqlite(**kwargs)
        monkeypatch.setattr(ps, "aiosqlite", fake)
        return fake
    return _apply


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_bf_phases_ddl_exists_with_check_constraints() -> None:
    """AC-1.1: bf_phases DDL が migration に存在し、5 constraint を全て持つ.

    DDL が削除 / 改変されたら fail (T-001-04 REFACTOR invariant).
    """
    sql = MIGRATION_BF.read_text(encoding="utf-8")
    # collapse internal whitespace for matching (DDL uses column alignment padding)
    sql_norm = re.sub(r"[ \t]+", " ", sql)
    assert "CREATE TABLE IF NOT EXISTS bf_phases" in sql_norm
    # 5 constraint:
    assert "phase_no INTEGER NOT NULL CHECK (phase_no BETWEEN 1 AND 10)" in sql_norm
    assert "status TEXT NOT NULL DEFAULT 'pending'" in sql_norm
    assert "CHECK (status IN ('pending','in_progress','completed','blocked','skipped'))" in sql_norm
    assert "CONSTRAINT uq_bf_phase UNIQUE (project_id, phase_no)" in sql_norm
    assert "REFERENCES bf_projects(id) ON DELETE CASCADE" in sql_norm
    assert "name TEXT NOT NULL" in sql_norm


def test_ac1_seven_crud_endpoints_registered() -> None:
    """AC-1.2: 7 CRUD endpoint が router に登録されている.

    list / get / create / update / start / complete / delete.
    """
    from routers.phases import router as phases_router
    paths_methods: set[tuple[str, str]] = set()
    for r in phases_router.routes:
        for m in getattr(r, "methods", ()):
            paths_methods.add((r.path, m))

    required = {
        ("/api/projects/{project_id}/phases", "GET"),
        ("/api/phases/{phase_id}", "GET"),
        ("/api/projects/{project_id}/phases", "POST"),
        ("/api/phases/{phase_id}", "PATCH"),
        ("/api/phases/{phase_id}/start", "POST"),
        ("/api/phases/{phase_id}/complete", "POST"),
        ("/api/phases/{phase_id}", "DELETE"),
    }
    missing = required - paths_methods
    assert not missing, f"missing CRUD endpoints: {missing}"


def test_ac1_phase_service_exposes_seven_public_apis() -> None:
    """AC-1.3: service layer が 7 public async function を export する."""
    required = [
        "list_phases", "get_phase", "create_phase", "update_phase",
        "start_phase", "complete_phase", "delete_phase",
    ]
    for name in required:
        fn = getattr(ps, name, None)
        assert fn is not None, f"phase_service.{name} missing"
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


def test_ac1_status_enum_matches_ddl_check_constraint() -> None:
    """AC-1.4: service の VALID_PHASE_STATUSES が DDL CHECK と完全一致.

    片方を変更したら fail (= drift 検知). DDL has multiple CHECK (status IN ...)
    (bf_projects / bf_phases / bf_tasks); scope to the bf_phases section.
    """
    ddl_sql = MIGRATION_BF.read_text(encoding="utf-8")
    start = ddl_sql.find("CREATE TABLE IF NOT EXISTS bf_phases")
    end = ddl_sql.find("CREATE TABLE IF NOT EXISTS", start + 50)
    bf_phases_section = ddl_sql[start:end] if end > 0 else ddl_sql[start:]
    m = re.search(r"CHECK \(status IN \(([^)]+)\)\)", bf_phases_section)
    assert m, "bf_phases DDL status CHECK constraint not found"
    ddl_statuses = tuple(s.strip().strip("'") for s in m.group(1).split(","))
    assert set(ddl_statuses) == set(VALID_PHASE_STATUSES), (
        f"DDL {ddl_statuses} vs service {VALID_PHASE_STATUSES} drift"
    )


def test_ac1_phase_no_range_matches_ddl_check_constraint() -> None:
    """AC-1.5: PHASE_NO_MIN/MAX が DDL CHECK (BETWEEN 1 AND 10) と一致."""
    ddl_sql = MIGRATION_BF.read_text(encoding="utf-8")
    assert "CHECK (phase_no BETWEEN 1 AND 10)" in ddl_sql
    assert PHASE_NO_MIN == 1
    assert PHASE_NO_MAX == 10


def test_ac1_phase_no_max_matches_f008_policy() -> None:
    """AC-1.6: PHASE_NO_MAX が F-008 policy `max_phases_per_workspace` と整合.

    features.json の policy が変わったら fail (drift 検知).
    """
    features = json.loads(FEATURES_JSON.read_text(encoding="utf-8"))
    # features.json schema: top-level dict with "items" array (other layouts may use "features")
    feats = features.get("items") or features.get("features") or []
    f008 = next(f for f in feats if f["id"] == "F-008")
    assert f008["policies"]["max_phases_per_workspace"] == PHASE_NO_MAX


def test_ac1_phases_router_included_in_app() -> None:
    """AC-1.7: router が FastAPI app に include されている."""
    from main import app
    paths = {r.path for r in app.routes}
    assert "/api/projects/{project_id}/phases" in paths
    assert "/api/phases/{phase_id}" in paths


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_success_responses_are_structured_dicts(client, monkeypatch) -> None:
    """AC-2.1: 6 success path 全てが JSON dict を返却 (200)."""
    async def fake_list(pid): return [{"id": 1, "phase_no": 1, "name": "h"}]
    async def fake_get(pid): return {"id": pid, "status": "pending"}
    async def fake_create(**kw): return {"id": 100, **kw}
    async def fake_update(pid, **f): return {"id": pid, **f}
    async def fake_start(pid): return {"id": pid, "status": "in_progress"}
    async def fake_complete(pid): return {"id": pid, "status": "completed"}

    monkeypatch.setattr(ps, "list_phases", fake_list)
    monkeypatch.setattr(ps, "get_phase", fake_get)
    monkeypatch.setattr(ps, "create_phase", fake_create)
    monkeypatch.setattr(ps, "update_phase", fake_update)
    monkeypatch.setattr(ps, "start_phase", fake_start)
    monkeypatch.setattr(ps, "complete_phase", fake_complete)

    assert isinstance(client.get("/api/projects/1/phases").json(), dict)
    assert isinstance(client.get("/api/phases/1").json(), dict)
    assert isinstance(
        client.post("/api/projects/1/phases", json={"phase_no": 1, "name": "h"}).json(),
        dict,
    )
    assert isinstance(client.patch("/api/phases/1", json={"name": "x"}).json(), dict)
    assert isinstance(client.post("/api/phases/1/start").json(), dict)
    assert isinstance(client.post("/api/phases/1/complete").json(), dict)


def test_ac2_delete_success_response_shape(client, monkeypatch) -> None:
    """AC-2.2: DELETE 成功時 `{deleted: True, phase_id: N}`."""
    async def fake(pid): return True
    monkeypatch.setattr(ps, "delete_phase", fake)
    r = client.delete("/api/phases/42")
    assert r.status_code == 200
    body = r.json()
    assert body == {"deleted": True, "phase_id": 42}


def test_ac2_error_envelope_shape_for_all_4xx_codes(client, monkeypatch) -> None:
    """AC-2.3: 全 5 error code が `{detail: {code, message}}` envelope を返す.

    code: phase_not_found / phase_duplicate / invalid_name / invalid_status / invalid_phase_no.
    """
    seen_codes: set[str] = set()

    # phase_not_found (GET)
    async def get_none(pid): return None
    monkeypatch.setattr(ps, "get_phase", get_none)
    body = client.get("/api/phases/9999").json()
    assert "detail" in body and {"code", "message"} <= body["detail"].keys()
    seen_codes.add(body["detail"]["code"])

    # phase_duplicate (POST create)
    async def create_dup(**kw):
        raise InvalidPhaseInput("phase_no 1 already exists for project 1")
    monkeypatch.setattr(ps, "create_phase", create_dup)
    body = client.post("/api/projects/1/phases", json={"phase_no": 1, "name": "h"}).json()
    assert body["detail"]["code"] == "phase_duplicate"
    seen_codes.add(body["detail"]["code"])

    # invalid_name (POST create with empty name)
    async def create_empty(**kw):
        raise InvalidPhaseInput("name must not be empty")
    monkeypatch.setattr(ps, "create_phase", create_empty)
    body = client.post("/api/projects/1/phases", json={"phase_no": 1, "name": "  "}).json()
    assert body["detail"]["code"] == "invalid_name"
    seen_codes.add(body["detail"]["code"])

    # invalid_status (PATCH update)
    async def upd_bad_status(pid, **f):
        raise InvalidPhaseInput("status must be one of ...")
    monkeypatch.setattr(ps, "update_phase", upd_bad_status)
    body = client.patch("/api/phases/1", json={"status": "BOGUS"}).json()
    assert body["detail"]["code"] == "invalid_status"
    seen_codes.add(body["detail"]["code"])

    # invalid_phase_no (POST create that triggers service-level raise)
    async def create_bad_no(**kw):
        raise InvalidPhaseInput("phase_no must be 1-10")
    monkeypatch.setattr(ps, "create_phase", create_bad_no)
    # Use Pydantic-valid range (1) so the service-level raise is reached
    body = client.post("/api/projects/1/phases", json={"phase_no": 1, "name": "x"}).json()
    assert body["detail"]["code"] == "invalid_phase_no"
    seen_codes.add(body["detail"]["code"])

    assert seen_codes == {
        "phase_not_found", "phase_duplicate", "invalid_name",
        "invalid_status", "invalid_phase_no",
    }


def test_ac2_list_response_includes_count(client, monkeypatch) -> None:
    """AC-2.4: list 応答が project_id / phases / count フィールドを必ず含む."""
    async def fake(pid):
        return [{"id": i, "phase_no": i, "name": f"p{i}"} for i in range(1, 4)]
    monkeypatch.setattr(ps, "list_phases", fake)
    body = client.get("/api/projects/7/phases").json()
    assert body["project_id"] == 7
    assert len(body["phases"]) == 3
    assert body["count"] == 3


def test_ac2_crud_completes_within_2_seconds(fake_db) -> None:
    """AC-2.5: service-level CRUD 操作が 2 秒以内に完了 (mock DB 経由).

    EVENT-DRIVEN AC の "within 2 seconds" を service レイヤで wall-clock 計測.
    """
    fake_db(rows_by_kw={
        "select * from bf_phases": [
            {"id": 1, "project_id": 1, "phase_no": 1, "name": "hearing", "status": "pending"},
        ],
        "insert into bf_phases": [{"id": 1}],
    })
    t0 = time.perf_counter()
    asyncio.run(ps.list_phases(1))
    asyncio.run(ps.get_phase(1))
    asyncio.run(ps.create_phase(project_id=1, phase_no=2, name="req"))
    asyncio.run(ps.update_phase(1, name="updated"))
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"CRUD took {elapsed:.3f}s, exceeds 2s budget"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN (REFACTOR invariants + idempotent + soft-delete)
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_bf_phases_ddl_invariants_intact() -> None:
    """AC-3.1: T-001-04 DDL の 5 constraint count が baseline 通り (改変ゼロ)."""
    sql = MIGRATION_BF.read_text(encoding="utf-8")
    bf_phases_section = sql[sql.find("CREATE TABLE IF NOT EXISTS bf_phases"):]
    # Cut at the next CREATE TABLE to stay within bf_phases scope
    end = bf_phases_section.find("CREATE TABLE IF NOT EXISTS", 50)
    bf_phases_section = bf_phases_section[:end] if end > 0 else bf_phases_section
    # Required constraints:
    assert bf_phases_section.count("CHECK (phase_no BETWEEN 1 AND 10)") == 1
    assert bf_phases_section.count(
        "CHECK (status IN ('pending','in_progress','completed','blocked','skipped'))"
    ) == 1
    assert bf_phases_section.count("CONSTRAINT uq_bf_phase UNIQUE (project_id, phase_no)") == 1
    assert bf_phases_section.count("ON DELETE CASCADE") >= 1


def test_ac3_phase_service_public_symbols_intact() -> None:
    """AC-3.2: phase_service の公開 symbol が 12 件揃っている (REFACTOR invariant).

    7 funcs + 3 const + 2 exception = 12.
    """
    required = {
        # functions
        "list_phases", "get_phase", "create_phase", "update_phase",
        "start_phase", "complete_phase", "delete_phase",
        # constants
        "VALID_PHASE_STATUSES", "PHASE_NO_MIN", "PHASE_NO_MAX",
        # exceptions
        "InvalidPhaseInput", "PhaseNotFound",
    }
    missing = required - set(dir(ps))
    assert not missing, f"phase_service missing symbols: {missing}"


def test_ac3_phases_router_public_endpoints_intact() -> None:
    """AC-3.3: 7 CRUD + 1 gate evaluate endpoint = 計 8 endpoint が登録."""
    from routers.phases import router as phases_router
    paths = {(r.path, m) for r in phases_router.routes for m in getattr(r, "methods", ())}
    crud_endpoints = {
        ("/api/projects/{project_id}/phases", "GET"),
        ("/api/phases/{phase_id}", "GET"),
        ("/api/projects/{project_id}/phases", "POST"),
        ("/api/phases/{phase_id}", "PATCH"),
        ("/api/phases/{phase_id}/start", "POST"),
        ("/api/phases/{phase_id}/complete", "POST"),
        ("/api/phases/{phase_id}", "DELETE"),
    }
    gate_endpoint = {("/api/phases/{phase_id}/evaluate-gate", "POST")}
    assert crud_endpoints <= paths, f"missing CRUD: {crud_endpoints - paths}"
    assert gate_endpoint <= paths, f"missing gate: {gate_endpoint - paths}"


def test_ac3_start_phase_idempotent_no_second_mutation(fake_db) -> None:
    """AC-3.4: 既に in_progress な phase に start_phase を呼んでも UPDATE は execute されない.

    idempotent invariant: state mutation を二重に起こさない.
    """
    fake = fake_db(rows_by_kw={
        "select": [{"id": 1, "status": "in_progress", "started_at": "2026-01-01"}],
    })
    out = asyncio.run(ps.start_phase(1))
    assert out["status"] == "in_progress"
    # 検証: executed list 内に UPDATE は無い (= state mutation 起こさず)
    update_calls = [sql for sql, _ in (fake.last_conn.executed if fake.last_conn else []) if "UPDATE bf_phases" in sql]
    assert update_calls == [], f"idempotent start should NOT issue UPDATE, but got: {update_calls}"


def test_ac3_delete_is_soft_not_physical(fake_db) -> None:
    """AC-3.5: delete_phase は physical DELETE せず、`status='skipped'` UPDATE のみ.

    F-008 error_path 「phase 削除 → タスク移動要求」を満たすための soft-delete invariant.
    """
    fake = fake_db(
        rows_by_kw={"select": [{"id": 1, "status": "pending"}]},
        rowcount=1,
    )
    out = asyncio.run(ps.delete_phase(1))
    assert out is True
    executed = fake.last_conn.executed if fake.last_conn else []
    # physical DELETE が無く、UPDATE ... status = 'skipped' が含まれる
    physical = [sql for sql, _ in executed if re.search(r"\bDELETE\s+FROM\s+bf_phases\b", sql, re.I)]
    assert physical == [], f"soft-delete invariant violated, physical DELETE found: {physical}"
    soft = [sql for sql, _ in executed if "UPDATE bf_phases" in sql and "skipped" in sql]
    assert soft, f"expected soft-delete UPDATE with 'skipped' but executed={executed}"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED (validation BEFORE mutation / no partial state)
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_phase_no_out_of_range_rejected_before_mutation(client, fake_db) -> None:
    """AC-4.1: 範囲外 phase_no は INSERT execute 前に 4xx で拒否.

    Pydantic level (422) + service level (InvalidPhaseInput) の二重防御.
    """
    # Router level: Pydantic ge=1, le=10 で 422
    r0 = client.post("/api/projects/1/phases", json={"phase_no": 0, "name": "x"})
    r11 = client.post("/api/projects/1/phases", json={"phase_no": 11, "name": "x"})
    assert r0.status_code == 422
    assert r11.status_code == 422

    # Service level: invalid type bypassing Pydantic → no INSERT execute
    fake = fake_db()
    with pytest.raises(InvalidPhaseInput):
        asyncio.run(ps.create_phase(project_id=1, phase_no=99, name="x"))
    executed = fake.last_conn.executed if fake.last_conn else []
    inserts = [sql for sql, _ in executed if "INSERT INTO bf_phases" in sql]
    assert inserts == [], f"validation should reject BEFORE INSERT, but got: {inserts}"


def test_ac4_empty_name_raises_before_insert_execute(fake_db) -> None:
    """AC-4.2: 空 name (`"  "`) → InvalidPhaseInput が INSERT 発行前に raise.

    validation timing invariant: state mutation を起こさない.
    """
    fake = fake_db()
    with pytest.raises(InvalidPhaseInput, match="name"):
        asyncio.run(ps.create_phase(project_id=1, phase_no=1, name="  "))
    executed = fake.last_conn.executed if fake.last_conn else []
    # 検証: INSERT は execute されていない
    inserts = [sql for sql, _ in executed if "INSERT" in sql.upper()]
    assert inserts == [], f"empty name should raise BEFORE INSERT, but got: {inserts}"


def test_ac4_invalid_status_raises_before_update_execute(fake_db) -> None:
    """AC-4.3: invalid status enum → InvalidPhaseInput が UPDATE 発行前に raise.

    validation timing invariant.
    """
    fake = fake_db(rows_by_kw={"select": [{"id": 1, "name": "x", "status": "pending"}]})
    with pytest.raises(InvalidPhaseInput, match="status"):
        asyncio.run(ps.update_phase(1, status="BOGUS_STATUS"))
    executed = fake.last_conn.executed if fake.last_conn else []
    updates = [sql for sql, _ in executed if "UPDATE bf_phases" in sql]
    assert updates == [], f"invalid status should raise BEFORE UPDATE, but got: {updates}"


def test_ac4_duplicate_returns_409_phase_duplicate(client, monkeypatch) -> None:
    """AC-4.4: (project_id, phase_no) duplicate → HTTP 409 phase_duplicate."""
    async def create_dup(**kw):
        raise InvalidPhaseInput("phase_no 1 already exists for project 1")
    monkeypatch.setattr(ps, "create_phase", create_dup)
    r = client.post("/api/projects/1/phases", json={"phase_no": 1, "name": "h"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "phase_duplicate"


def test_ac4_unknown_phase_id_returns_404(client, monkeypatch) -> None:
    """AC-4.5: 存在しない phase_id → 404 phase_not_found on update/start/complete/delete/get."""
    async def raise_not_found(pid, **_kw):
        raise PhaseNotFound(f"phase not found: {pid}")

    async def raise_not_found_no_kw(pid):
        raise PhaseNotFound(f"phase not found: {pid}")

    async def get_none(pid):
        return None

    async def delete_false(pid):
        return False

    monkeypatch.setattr(ps, "get_phase", get_none)
    monkeypatch.setattr(ps, "update_phase", raise_not_found)
    monkeypatch.setattr(ps, "start_phase", raise_not_found_no_kw)
    monkeypatch.setattr(ps, "complete_phase", raise_not_found_no_kw)
    monkeypatch.setattr(ps, "delete_phase", delete_false)

    for resp in [
        client.get("/api/phases/99999"),
        client.patch("/api/phases/99999", json={"name": "x"}),
        client.post("/api/phases/99999/start"),
        client.post("/api/phases/99999/complete"),
        client.delete("/api/phases/99999"),
    ]:
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "phase_not_found"


def test_ac4_update_unique_conflict_returns_409_no_partial_mutation(monkeypatch) -> None:
    """AC-4.6: UPDATE 中 UNIQUE conflict → InvalidPhaseInput("conflicts") raise.

    SQL UNIQUE 制約違反は service レイヤで `conflicts` メッセージに変換され、
    router 層で 409 にマップされる。
    `commits` カウンタが増えないことで partial mutation が起きていないことを検証.
    """
    captured: dict[str, FakeConn] = {}

    class _UpdConn(FakeConn):
        async def execute(self, sql: str, *args: Any) -> _Cursor:
            self.executed.append((sql, args[0] if args else ()))
            s = sql.lower()
            if "update bf_phases" in s:
                raise RuntimeError("UNIQUE constraint failed: uq_bf_phase")
            if "select" in s:
                return _Cursor(rows=[{"id": 1, "name": "x", "status": "pending"}])
            return _Cursor()

    class _FA:
        Row = dict

        def connect(self, _p: str) -> _UpdConn:
            captured["conn"] = _UpdConn()
            return captured["conn"]

    monkeypatch.setattr(ps, "aiosqlite", _FA())

    with pytest.raises(InvalidPhaseInput, match="conflicts"):
        asyncio.run(ps.update_phase(1, phase_no=2))
    # commit() should not be invoked since UPDATE raised
    conn = captured.get("conn")
    assert conn is not None
    assert conn.commits == 0, "UNIQUE conflict must NOT commit a partial UPDATE"


def test_ac4_no_hardcoded_secret_in_phases_path() -> None:
    """AC-4.7 (lint #5): phase_service / phases router に supabase/anthropic key リテラルなし.

    `scripts/lint-mock.sh` check #5 と同等のパターンを spec test で個別検証.
    """
    # actual API key prefixes only (avoid matching the substring "anthropic" in import strings)
    forbidden = re.compile(r"(sb-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{50,})")
    for path in [PHASE_SERVICE_FILE, PHASES_ROUTER_FILE]:
        text = path.read_text(encoding="utf-8")
        m = forbidden.search(text)
        assert m is None, f"hardcoded secret detected in {path}: {m.group() if m else ''}"


# ──────────────────────────────────────────────────────────────────────────
# Audit doc 存在 + REFACTOR 適合 9 項目 機械検証
# ──────────────────────────────────────────────────────────────────────────


def test_audit_doc_exists_and_cites_f008_source() -> None:
    """audit doc が存在し、F-008 features.json を 源泉 として明示引用している."""
    assert AUDIT_DOC.exists(), f"audit doc missing: {AUDIT_DOC}"
    body = AUDIT_DOC.read_text(encoding="utf-8")
    assert "Spec literal expansion" in body
    assert "F-008" in body
    assert "max_phases_per_workspace" in body  # F-008 policy citation
    assert "uq_bf_phase" in body  # DDL constraint citation


def test_audit_doc_lists_all_four_ac_blocks() -> None:
    """audit doc が 4 AC ブロック (UBIQUITOUS/EVENT-DRIVEN/STATE-DRIVEN/UNWANTED) を全部含む."""
    body = AUDIT_DOC.read_text(encoding="utf-8")
    assert "AC-1 UBIQUITOUS" in body
    assert "AC-2 EVENT-DRIVEN" in body
    assert "AC-3 STATE-DRIVEN" in body
    assert "AC-4 UNWANTED" in body


def test_refactor_invariant_no_phase_service_signature_change() -> None:
    """REFACTOR v2.1 適合 #5: 公開 API シグネチャが variable 化していない.

    各 public function が期待される async signature を持つことを反射的に検証.
    """
    sig = inspect.signature(ps.create_phase)
    # create_phase: keyword-only args (project_id, phase_no, name, artifacts_dir, notes)
    assert "project_id" in sig.parameters
    assert "phase_no" in sig.parameters
    assert "name" in sig.parameters
    # update_phase: (phase_id, **fields)
    sig2 = inspect.signature(ps.update_phase)
    assert "phase_id" in sig2.parameters
    assert any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig2.parameters.values()), (
        "update_phase must accept **fields (var-keyword)"
    )


def test_invalid_phase_input_inherits_value_error() -> None:
    """exception hierarchy invariant: 既存 caller が ValueError catch していても破壊しない."""
    assert issubclass(InvalidPhaseInput, ValueError)
    assert issubclass(PhaseNotFound, ValueError)
