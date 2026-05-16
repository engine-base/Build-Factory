"""T-V3-B-11 / F-007: workspace-scoped task ops 4 endpoint テスト.

POST /api/workspaces/{id}/tasks/bulk-play
POST /api/workspaces/{id}/tasks/bulk-archive
GET  /api/workspaces/{id}/tasks/export.csv
GET  /api/workspaces/{id}/tasks/dag

AC マッピング (features.json#F-007 ears_ac_seed + 派生):
  AC-F1  EVENT-DRIVEN : bulk-play は dependency 順に session を起動
  AC-F2  UNWANTED     : max_parallel 超過分は queued count として返す
  AC-F3  EVENT-DRIVEN : bulk-play は 2xx + session_ids 配列を返す
  AC-F4  UNWANTED     : bulk-play actor_user_id 不在 → 401
  AC-F5  UNWANTED     : bulk-play body schema 違反 → 422
  AC-F6  UNWANTED     : bulk-play 10/min/workspace 超 → 429
  AC-F7  EVENT-DRIVEN : bulk-archive は archived_count を返す
  AC-F8  UNWANTED     : bulk-archive actor_user_id 不在 → 401
  AC-F9  UNWANTED     : bulk-archive body schema 違反 → 422
  AC-F10 EVENT-DRIVEN : export.csv は text/csv body を返す
  AC-F11 UNWANTED     : export.csv actor_user_id 不在 → 401
  AC-F12 EVENT-DRIVEN : dag は {nodes, edges} を返す
  AC-F13 UNWANTED     : dag actor_user_id 不在 → 401

DB 接続は service 層 monkeypatch でモック化 (実 DB 不要).
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from services import task_workspace_service as tws
from services.task_workspace_service import (
    Forbidden,
    RateLimited,
    Unauthorized,
    ValidationFailed,
    WorkspaceNotFound,
    _rl_reset,
    _sprint_to_wave,
    _topo_sort,
    _validate_task_ids,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _rate_limit_reset() -> None:
    """各 test 前に rate limit bucket をリセット."""
    _rl_reset()


# ══════════════════════════════════════════════════════════════════════════
# AC-F1 / AC-F3 : bulk-play happy path
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_play_happy_path_returns_session_ids(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id, max_parallel=5):
        assert workspace_id == 7
        assert task_ids == [11, 12]
        assert actor_user_id == "alice"
        return {"session_ids": ["play-uuid-1", "play-uuid-2"], "queued": 0}

    monkeypatch.setattr(tws, "bulk_play", fake)
    r = client.post(
        "/api/workspaces/7/tasks/bulk-play",
        json={"task_ids": [11, 12], "actor_user_id": "alice"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_ids"] == ["play-uuid-1", "play-uuid-2"]
    assert body["queued"] == 0


# ══════════════════════════════════════════════════════════════════════════
# AC-F2 : max_parallel 超過 → queued count 返却 (200)
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_play_max_parallel_overflow_queues_rest(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id, max_parallel=5):
        # 8 task / max_parallel=3 → 起動 3, queued 5
        return {"session_ids": ["s1", "s2", "s3"], "queued": 5}

    monkeypatch.setattr(tws, "bulk_play", fake)
    r = client.post(
        "/api/workspaces/7/tasks/bulk-play",
        json={"task_ids": [1, 2, 3, 4, 5, 6, 7, 8],
              "actor_user_id": "alice", "max_parallel": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["session_ids"]) == 3
    assert body["queued"] == 5


# ══════════════════════════════════════════════════════════════════════════
# AC-F4 : bulk-play 未認証 → 401
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_play_missing_actor_returns_401(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id, max_parallel=5):
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "bulk_play", fake)
    r = client.post(
        "/api/workspaces/7/tasks/bulk-play",
        json={"task_ids": [1]},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tasks.unauthorized"


# ══════════════════════════════════════════════════════════════════════════
# AC-F5 : bulk-play body 不正 → 422 (field-level error map)
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_play_empty_task_ids_returns_422(client) -> None:
    r = client.post(
        "/api/workspaces/7/tasks/bulk-play",
        json={"task_ids": [], "actor_user_id": "alice"},
    )
    assert r.status_code == 422
    # FastAPI pydantic error format: detail is a list of field errors
    body = r.json()
    assert "detail" in body


def test_bulk_play_missing_task_ids_returns_422(client) -> None:
    r = client.post(
        "/api/workspaces/7/tasks/bulk-play",
        json={"actor_user_id": "alice"},
    )
    assert r.status_code == 422


def test_bulk_play_invalid_workspace_id_returns_422(client) -> None:
    r = client.post(
        "/api/workspaces/0/tasks/bulk-play",
        json={"task_ids": [1], "actor_user_id": "alice"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "tasks.invalid_workspace_id"


# ══════════════════════════════════════════════════════════════════════════
# AC-F6 : bulk-play rate limit (10/min/workspace) → 429
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_play_rate_limited_returns_429(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id, max_parallel=5):
        raise RateLimited("bulk_play rate limit exceeded: 10/60s on workspace 7")

    monkeypatch.setattr(tws, "bulk_play", fake)
    r = client.post(
        "/api/workspaces/7/tasks/bulk-play",
        json={"task_ids": [1], "actor_user_id": "alice"},
    )
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "tasks.rate_limited"


# ══════════════════════════════════════════════════════════════════════════
# AC-F7 : bulk-archive happy path
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_archive_happy_path(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id):
        assert workspace_id == 7
        assert task_ids == [11, 12, 13]
        return {"archived_count": 3}

    monkeypatch.setattr(tws, "bulk_archive", fake)
    r = client.post(
        "/api/workspaces/7/tasks/bulk-archive",
        json={"task_ids": [11, 12, 13], "actor_user_id": "alice"},
    )
    assert r.status_code == 200
    assert r.json()["archived_count"] == 3


# ══════════════════════════════════════════════════════════════════════════
# AC-F8 : bulk-archive 未認証 → 401
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_archive_missing_actor_returns_401(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id):
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "bulk_archive", fake)
    r = client.post(
        "/api/workspaces/7/tasks/bulk-archive",
        json={"task_ids": [1]},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tasks.unauthorized"


# ══════════════════════════════════════════════════════════════════════════
# AC-F9 : bulk-archive body 不正 → 422
# ══════════════════════════════════════════════════════════════════════════


def test_bulk_archive_empty_task_ids_returns_422(client) -> None:
    r = client.post(
        "/api/workspaces/7/tasks/bulk-archive",
        json={"task_ids": [], "actor_user_id": "alice"},
    )
    assert r.status_code == 422


def test_bulk_archive_workspace_not_found_returns_404(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id):
        raise WorkspaceNotFound(f"workspace {workspace_id} not found")

    monkeypatch.setattr(tws, "bulk_archive", fake)
    r = client.post(
        "/api/workspaces/99999/tasks/bulk-archive",
        json={"task_ids": [1], "actor_user_id": "alice"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "tasks.workspace_not_found"


def test_bulk_archive_forbidden_returns_403(client, monkeypatch) -> None:
    async def fake(workspace_id, task_ids, *, actor_user_id):
        raise Forbidden("role 'contributor' not in ['owner', 'ws_admin']")

    monkeypatch.setattr(tws, "bulk_archive", fake)
    r = client.post(
        "/api/workspaces/7/tasks/bulk-archive",
        json={"task_ids": [1], "actor_user_id": "bob"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "tasks.forbidden"


# ══════════════════════════════════════════════════════════════════════════
# AC-F10 : export.csv happy path
# ══════════════════════════════════════════════════════════════════════════


def test_export_csv_returns_text_csv(client, monkeypatch) -> None:
    async def fake(workspace_id, *, actor_user_id):
        return (
            "task_id,title,status,label,sprint,assigned_to,"
            "estimated_hours,actual_hours\n"
            "T-001,Setup,done,NEW,S0,alice,2.0,1.5\n"
        )

    monkeypatch.setattr(tws, "export_csv", fake)
    r = client.get("/api/workspaces/7/tasks/export.csv?actor_user_id=alice")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "task_id,title,status" in r.text
    assert "T-001,Setup,done" in r.text


# ══════════════════════════════════════════════════════════════════════════
# AC-F11 : export.csv 未認証 → 401
# ══════════════════════════════════════════════════════════════════════════


def test_export_csv_missing_actor_returns_401(client, monkeypatch) -> None:
    async def fake(workspace_id, *, actor_user_id):
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "export_csv", fake)
    r = client.get("/api/workspaces/7/tasks/export.csv")
    assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# AC-F12 : dag happy path
# ══════════════════════════════════════════════════════════════════════════


def test_dag_returns_nodes_and_edges(client, monkeypatch) -> None:
    async def fake(workspace_id, *, actor_user_id):
        return {
            "nodes": [
                {"id": "1", "title": "A", "status": "todo", "wave": 0},
                {"id": "2", "title": "B", "status": "todo", "wave": 1},
            ],
            "edges": [
                {"from_task_id": "1", "to_task_id": "2", "type": "blocks"},
            ],
        }

    monkeypatch.setattr(tws, "get_dag", fake)
    r = client.get("/api/workspaces/7/tasks/dag?actor_user_id=alice")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 2
    assert body["nodes"][0]["id"] == "1"
    assert len(body["edges"]) == 1
    assert body["edges"][0]["type"] == "blocks"


# ══════════════════════════════════════════════════════════════════════════
# AC-F13 : dag 未認証 → 401
# ══════════════════════════════════════════════════════════════════════════


def test_dag_missing_actor_returns_401(client, monkeypatch) -> None:
    async def fake(workspace_id, *, actor_user_id):
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "get_dag", fake)
    r = client.get("/api/workspaces/7/tasks/dag")
    assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# service-layer unit tests (pure helpers, DB 不要)
# ══════════════════════════════════════════════════════════════════════════


def test_validate_task_ids_rejects_non_list() -> None:
    with pytest.raises(ValidationFailed, match="must be a list"):
        _validate_task_ids("nope")  # type: ignore[arg-type]


def test_validate_task_ids_rejects_empty() -> None:
    with pytest.raises(ValidationFailed, match="non-empty"):
        _validate_task_ids([])


def test_validate_task_ids_rejects_non_int() -> None:
    with pytest.raises(ValidationFailed, match="must be int"):
        _validate_task_ids([1, "two", 3])  # type: ignore[list-item]


def test_validate_task_ids_rejects_bool() -> None:
    # bool は int の subclass だが、業務上 task_id とは別物 → 弾く
    with pytest.raises(ValidationFailed, match="must be int"):
        _validate_task_ids([1, True])  # type: ignore[list-item]


def test_validate_task_ids_rejects_negative() -> None:
    with pytest.raises(ValidationFailed, match="must be > 0"):
        _validate_task_ids([1, -3])


def test_validate_task_ids_dedupes_preserving_order() -> None:
    assert _validate_task_ids([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_topo_sort_orders_by_dependency() -> None:
    # 1 depends on 2 (edge: 2 → 1), 2 depends on 3 (edge: 3 → 2)
    # 期待: [3, 2, 1]
    order = _topo_sort([1, 2, 3], [(2, 1), (3, 2)])
    assert order.index(3) < order.index(2) < order.index(1)


def test_topo_sort_handles_no_edges() -> None:
    order = _topo_sort([1, 2, 3], [])
    assert sorted(order) == [1, 2, 3]


def test_topo_sort_handles_cycle_by_trailing_residue() -> None:
    # 1 → 2 → 1 (cycle) — 全 node が cycle 内. residue として末尾に積む.
    order = _topo_sort([1, 2], [(1, 2), (2, 1)])
    assert sorted(order) == [1, 2]


def test_topo_sort_ignores_self_edge_and_external_nodes() -> None:
    order = _topo_sort([1, 2], [(1, 1), (99, 1), (1, 2)])
    assert order == [1, 2]


def test_sprint_to_wave_parses_s_prefix() -> None:
    assert _sprint_to_wave("S0") == 0
    assert _sprint_to_wave("S3") == 3
    assert _sprint_to_wave("s12") == 12


def test_sprint_to_wave_parses_plain_int() -> None:
    assert _sprint_to_wave("4") == 4


def test_sprint_to_wave_returns_none_for_invalid() -> None:
    assert _sprint_to_wave(None) is None
    assert _sprint_to_wave("") is None
    assert _sprint_to_wave("foo") is None
    assert _sprint_to_wave("Sx") is None


# ══════════════════════════════════════════════════════════════════════════
# rate limiter unit test (token bucket)
# ══════════════════════════════════════════════════════════════════════════


def test_rate_limiter_allows_up_to_limit() -> None:
    _rl_reset()
    # 10 までは pass
    for _ in range(10):
        tws._rl_check(42, limit=10, window=60)


def test_rate_limiter_blocks_over_limit() -> None:
    _rl_reset()
    for _ in range(10):
        tws._rl_check(42, limit=10, window=60)
    with pytest.raises(RateLimited):
        tws._rl_check(42, limit=10, window=60)


def test_rate_limiter_isolated_per_workspace() -> None:
    _rl_reset()
    for _ in range(10):
        tws._rl_check(1, limit=10, window=60)
    # workspace 2 はまだ余裕あり
    tws._rl_check(2, limit=10, window=60)


# ══════════════════════════════════════════════════════════════════════════
# verify_workspace_access: Unauthorized
# ══════════════════════════════════════════════════════════════════════════


def test_verify_workspace_access_requires_user_id() -> None:
    with pytest.raises(Unauthorized):
        asyncio.run(tws.verify_workspace_access(1, None))
    with pytest.raises(Unauthorized):
        asyncio.run(tws.verify_workspace_access(1, "   "))


# ══════════════════════════════════════════════════════════════════════════
# bulk_play / bulk_archive / export_csv / get_dag: service-level test via mock DB
# ══════════════════════════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, rows: Optional[list[dict]] = None, rowcount: int = 0) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount

    async def fetchone(self) -> Any:
        return self._rows.pop(0) if self._rows else None

    async def fetchall(self) -> list[dict]:
        rows = list(self._rows)
        self._rows.clear()
        return rows


class _FakeConn:
    Row = dict

    def __init__(
        self,
        ws_exists: bool = True,
        is_member: bool = True,
        role: str = "owner",
        bf_tasks_rows: Optional[list[dict]] = None,
        bf_deps_rows: Optional[list[dict]] = None,
        archive_rowcount: int = 0,
    ) -> None:
        self._ws_exists = ws_exists
        self._is_member = is_member
        self._role = role
        self._bf_tasks_rows = bf_tasks_rows or []
        self._bf_deps_rows = bf_deps_rows or []
        self._archive_rowcount = archive_rowcount
        self.row_factory = None
        self.insert_calls: list[tuple] = []

    async def execute_fetchall(self, sql: str, *args: Any) -> list[dict]:
        s = sql.lower()
        if "from workspaces" in s and "where id" in s:
            return [{"id": args[0][0] if args else 1}] if self._ws_exists else []
        if "from workspace_members" in s:
            return [{"role": self._role}] if self._is_member else []
        if "from bf_tasks t" in s and "where p.workspace_id" in s:
            return list(self._bf_tasks_rows)
        if "from bf_task_dependencies" in s:
            return list(self._bf_deps_rows)
        return []

    async def execute(self, sql: str, *args: Any) -> _FakeCursor:
        s = sql.lower()
        if "insert into sessions" in s:
            self.insert_calls.append(args[0] if args else ())
            return _FakeCursor()
        if "update bf_tasks" in s:
            return _FakeCursor(rowcount=self._archive_rowcount)
        return _FakeCursor()

    async def commit(self) -> None:
        pass

    async def __aenter__(self) -> "_FakeConn":
        return self

    async def __aexit__(self, *a: Any) -> None:
        pass


class _FakeAiosqlite:
    Row = dict

    def __init__(self, **kw: Any) -> None:
        self._kw = kw
        self.last_conn: Optional[_FakeConn] = None

    def connect(self, _path: Any) -> _FakeConn:
        conn = _FakeConn(**self._kw)
        self.last_conn = conn
        return conn


@pytest.fixture
def mock_db(monkeypatch):
    """`tws.aiosqlite` を fake に差し替える helper."""
    def _apply(**kwargs):
        fake = _FakeAiosqlite(**kwargs)
        monkeypatch.setattr(tws, "aiosqlite", fake)
        return fake
    return _apply


def test_service_verify_access_workspace_not_found(mock_db) -> None:
    mock_db(ws_exists=False)
    with pytest.raises(WorkspaceNotFound):
        asyncio.run(tws.verify_workspace_access(7, "alice"))


def test_service_verify_access_non_member_forbidden(mock_db) -> None:
    mock_db(ws_exists=True, is_member=False)
    with pytest.raises(Forbidden):
        asyncio.run(tws.verify_workspace_access(7, "alice"))


def test_service_verify_access_returns_role(mock_db) -> None:
    mock_db(ws_exists=True, is_member=True, role="ws_admin")
    role = asyncio.run(tws.verify_workspace_access(7, "alice"))
    assert role == "ws_admin"


def test_service_bulk_archive_archives_rows(mock_db) -> None:
    mock_db(ws_exists=True, is_member=True, role="owner", archive_rowcount=2)
    result = asyncio.run(tws.bulk_archive(
        7, [1, 2], actor_user_id="alice",
    ))
    assert result == {"archived_count": 2}


def test_service_bulk_archive_requires_admin(mock_db) -> None:
    mock_db(ws_exists=True, is_member=True, role="contributor", archive_rowcount=0)
    with pytest.raises(Forbidden):
        asyncio.run(tws.bulk_archive(
            7, [1, 2], actor_user_id="alice",
        ))


def test_service_export_csv_includes_header(mock_db) -> None:
    mock_db(ws_exists=True, is_member=True,
            bf_tasks_rows=[
                {"task_id": "T-001", "title": "A", "status": "todo",
                 "label": "NEW", "sprint": "S0", "assigned_to": "alice",
                 "estimated_hours": 2.0, "actual_hours": None},
            ])
    csv_text = asyncio.run(tws.export_csv(7, actor_user_id="alice"))
    assert csv_text.startswith("task_id,title,status")
    assert "T-001,A,todo,NEW,S0,alice,2.0," in csv_text


def test_service_get_dag_returns_nodes_edges(mock_db) -> None:
    mock_db(
        ws_exists=True, is_member=True,
        bf_tasks_rows=[
            {"id": 1, "title": "A", "status": "todo", "sprint": "S0"},
            {"id": 2, "title": "B", "status": "todo", "sprint": "S1"},
        ],
        bf_deps_rows=[
            {"task_id": 2, "depends_on_task_id": 1, "dep_type": "blocks"},
        ],
    )
    result = asyncio.run(tws.get_dag(7, actor_user_id="alice"))
    assert len(result["nodes"]) == 2
    assert result["nodes"][0]["wave"] == 0
    assert result["nodes"][1]["wave"] == 1
    assert result["edges"] == [
        {"from_task_id": "1", "to_task_id": "2", "type": "blocks"},
    ]


def test_service_bulk_play_max_parallel_queues_overflow(mock_db) -> None:
    # 5 task / max_parallel=2 → 起動 2 + queued 3
    mock_db(
        ws_exists=True, is_member=True, role="owner",
        bf_tasks_rows=[
            {"id": tid, "title": f"T{tid}", "status": "todo"}
            for tid in (1, 2, 3, 4, 5)
        ],
        bf_deps_rows=[],
    )
    _rl_reset()
    result = asyncio.run(tws.bulk_play(
        7, [1, 2, 3, 4, 5], actor_user_id="alice", max_parallel=2,
    ))
    assert len(result["session_ids"]) == 2
    assert result["queued"] == 3
    for sid in result["session_ids"]:
        assert sid.startswith("play-")


def test_service_bulk_play_orders_by_dependency(mock_db) -> None:
    # task 3 depends on 1 depends on 2 → 起動順は 2, 1, 3
    mock_db(
        ws_exists=True, is_member=True, role="owner",
        bf_tasks_rows=[
            {"id": 1, "title": "A", "status": "todo"},
            {"id": 2, "title": "B", "status": "todo"},
            {"id": 3, "title": "C", "status": "todo"},
        ],
        bf_deps_rows=[
            {"task_id": 1, "depends_on_task_id": 2},
            {"task_id": 3, "depends_on_task_id": 1},
        ],
    )
    _rl_reset()
    fake_aio = tws.aiosqlite  # type: ignore[attr-defined]
    result = asyncio.run(tws.bulk_play(
        7, [1, 2, 3], actor_user_id="alice", max_parallel=10,
    ))
    assert result["queued"] == 0
    # INSERT 順 = topo order. last_conn.insert_calls[i] の bf_task_id を見る.
    inserted_ids = [c[2] for c in fake_aio.last_conn.insert_calls]  # type: ignore[union-attr]
    assert inserted_ids == [2, 1, 3]


def test_service_bulk_play_skips_non_workspace_tasks(mock_db) -> None:
    # request: [1, 99] but only id=1 is in workspace
    mock_db(
        ws_exists=True, is_member=True, role="owner",
        bf_tasks_rows=[{"id": 1, "title": "A", "status": "todo"}],
        bf_deps_rows=[],
    )
    _rl_reset()
    result = asyncio.run(tws.bulk_play(
        7, [1, 99], actor_user_id="alice",
    ))
    assert len(result["session_ids"]) == 1


def test_service_bulk_play_empty_valid_returns_empty(mock_db) -> None:
    # task_ids が全部 workspace 外 → session_ids 空
    mock_db(
        ws_exists=True, is_member=True, role="owner",
        bf_tasks_rows=[],
        bf_deps_rows=[],
    )
    _rl_reset()
    result = asyncio.run(tws.bulk_play(
        7, [777, 888], actor_user_id="alice",
    ))
    assert result == {"session_ids": [], "queued": 0}


def test_service_bulk_play_rate_limit_after_10_calls(mock_db) -> None:
    mock_db(
        ws_exists=True, is_member=True, role="owner",
        bf_tasks_rows=[{"id": 1, "title": "A", "status": "todo"}],
        bf_deps_rows=[],
    )
    _rl_reset()
    for _ in range(10):
        asyncio.run(tws.bulk_play(7, [1], actor_user_id="alice"))
    with pytest.raises(RateLimited):
        asyncio.run(tws.bulk_play(7, [1], actor_user_id="alice"))
