"""T-V3-B-12 / F-007: tasks single play + workspace play-all テスト.

POST /api/tasks/{id}/play
POST /api/workspaces/{id}/tasks/play-all
POST /api/workspaces/{id}/play-all

AC マッピング (tickets-group-b-backend.json#T-V3-B-12):
  AC-F1 UNWANTED      : POST /api/tasks/{id}/play depends_on 未充足 → 409
  AC-F2 EVENT-DRIVEN  : POST /api/tasks/{id}/play 正常系 → 2xx + session_id
  AC-F3 UNWANTED      : POST /api/tasks/{id}/play no auth → 401
  AC-F4 UNWANTED      : POST /api/tasks/{id}/play body validation → 422
  AC-F5 UNWANTED      : POST /api/tasks/{id}/play 30/min/user 超 → 429
  AC-F6 EVENT-DRIVEN  : POST /api/workspaces/{id}/tasks/play-all 正常系 → 2xx + queued
  AC-F7 UNWANTED      : POST /api/workspaces/{id}/tasks/play-all no auth → 401
  AC-F8 EVENT-DRIVEN  : POST /api/workspaces/{id}/play-all 正常系 → 2xx + queued
  AC-F9 UNWANTED      : POST /api/workspaces/{id}/play-all no auth → 401

Service (task_workspace_service) は monkeypatch でモック化.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from services import task_workspace_service as tws
from services.task_workspace_service import (
    DependencyConflict,
    Forbidden,
    RateLimited,
    TaskNotFound,
    Unauthorized,
    ValidationFailed,
    _partition_playable,
    _rl_check_user,
    _rl_reset,
    _rl_reset_user,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ.setdefault("DEV_BYPASS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _rl_reset_all() -> None:
    """各 test 前に rate limit bucket を全 reset."""
    _rl_reset()
    _rl_reset_user()


# ══════════════════════════════════════════════════════════════════════════
# AC-F2: POST /api/tasks/{id}/play happy path → 201 + session_id
# ══════════════════════════════════════════════════════════════════════════


def test_play_task_happy_path_returns_session_id(client, monkeypatch) -> None:
    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        assert task_id == 42
        assert actor_user_id == "alice"
        return {"session_id": "play-uuid-aaa"}

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post(
        "/api/tasks/42/play",
        json={"actor_user_id": "alice"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["session_id"] == "play-uuid-aaa"


def test_play_task_uses_jwt_sub_when_body_missing_actor(client, monkeypatch) -> None:
    """DEV_BYPASS + body 未指定でも sub から actor が解決される."""
    captured: dict = {}

    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        captured["actor"] = actor_user_id
        return {"session_id": "play-jwt"}

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post("/api/tasks/3/play")
    assert r.status_code == 201
    # DEV_BYPASS=1 で DEV_USER の sub が actor になる
    assert captured["actor"] is not None


# ══════════════════════════════════════════════════════════════════════════
# AC-F1: depends_on 未充足 → 409
# ══════════════════════════════════════════════════════════════════════════


def test_play_task_unsatisfied_dependencies_returns_409(client, monkeypatch) -> None:
    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        raise DependencyConflict(
            f"task {task_id} has unsatisfied dependencies: [99]"
        )

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post("/api/tasks/42/play", json={"actor_user_id": "alice"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "tasks.dependencies_not_satisfied"


# ══════════════════════════════════════════════════════════════════════════
# AC-F3: actor 不在 → 401
# ══════════════════════════════════════════════════════════════════════════


def test_play_task_missing_actor_returns_401(client, monkeypatch) -> None:
    # DEV_BYPASS を一時 off にし、actor を取れない状況を再現
    monkeypatch.setenv("DEV_BYPASS", "0")
    from importlib import reload
    import services.auth_middleware as am
    reload(am)

    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post("/api/tasks/42/play", json={})
    # Bearer が無いと auth dependency 側で 401
    assert r.status_code == 401


def test_play_task_service_unauthorized_returns_401(client, monkeypatch) -> None:
    """service が Unauthorized を raise したケース."""
    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post("/api/tasks/42/play", json={"actor_user_id": "  "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tasks.unauthorized"


# ══════════════════════════════════════════════════════════════════════════
# AC-F4: body / path 不正 → 422
# ══════════════════════════════════════════════════════════════════════════


def test_play_task_zero_id_returns_422(client) -> None:
    r = client.post("/api/tasks/0/play", json={"actor_user_id": "alice"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_play_task_negative_id_returns_422(client) -> None:
    # FastAPI path-int parsing で -1 は通る (int) → router 内 guard
    r = client.post("/api/tasks/-1/play", json={"actor_user_id": "alice"})
    # FastAPI が path int を許容するので 422 (router guard) になる想定
    assert r.status_code == 422


def test_play_task_non_int_id_returns_422(client) -> None:
    r = client.post("/api/tasks/abc/play", json={"actor_user_id": "alice"})
    # FastAPI 自身が 422 を返す
    assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# AC-F5: rate limit (30/min/user) → 429
# ══════════════════════════════════════════════════════════════════════════


def test_play_task_rate_limited_returns_429(client, monkeypatch) -> None:
    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        raise RateLimited("play rate limit exceeded: 30/60s for user alice")

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post("/api/tasks/42/play", json={"actor_user_id": "alice"})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "tasks.rate_limited"


def test_play_task_not_found_returns_404(client, monkeypatch) -> None:
    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        raise TaskNotFound(f"task {task_id} not found")

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post("/api/tasks/99999/play", json={"actor_user_id": "alice"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "tasks.task_not_found"


def test_play_task_forbidden_returns_403(client, monkeypatch) -> None:
    async def fake(task_id: int, *, actor_user_id: Optional[str]) -> dict:
        raise Forbidden(f"user {actor_user_id!r} is not a member")

    monkeypatch.setattr(tws, "play_task", fake)
    r = client.post("/api/tasks/42/play", json={"actor_user_id": "bob"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "tasks.forbidden"


# ══════════════════════════════════════════════════════════════════════════
# AC-F6: POST /api/workspaces/{id}/tasks/play-all happy path
# ══════════════════════════════════════════════════════════════════════════


def test_play_all_workspace_tasks_happy_path(client, monkeypatch) -> None:
    async def fake(workspace_id: int, *, actor_user_id: Optional[str],
                   filter: Optional[str] = None,
                   max_parallel: int = 5) -> dict:
        assert workspace_id == 7
        assert actor_user_id == "alice"
        return {"queued": 3, "skipped": 1}

    monkeypatch.setattr(tws, "play_all_in_workspace_tasks", fake)
    r = client.post(
        "/api/workspaces/7/tasks/play-all",
        json={"actor_user_id": "alice"},
    )
    assert r.status_code == 200
    assert r.json() == {"queued": 3, "skipped": 1}


# ══════════════════════════════════════════════════════════════════════════
# AC-F7: tasks/play-all actor 不在 → 401
# ══════════════════════════════════════════════════════════════════════════


def test_play_all_workspace_tasks_missing_actor_returns_401(
    client, monkeypatch,
) -> None:
    async def fake(workspace_id: int, *, actor_user_id: Optional[str],
                   filter: Optional[str] = None,
                   max_parallel: int = 5) -> dict:
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "play_all_in_workspace_tasks", fake)
    r = client.post("/api/workspaces/7/tasks/play-all", json={})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tasks.unauthorized"


def test_play_all_workspace_tasks_forbidden_returns_403(
    client, monkeypatch,
) -> None:
    async def fake(workspace_id: int, *, actor_user_id: Optional[str],
                   filter: Optional[str] = None,
                   max_parallel: int = 5) -> dict:
        raise Forbidden("role 'contributor' not in ['owner', 'ws_admin']")

    monkeypatch.setattr(tws, "play_all_in_workspace_tasks", fake)
    r = client.post(
        "/api/workspaces/7/tasks/play-all",
        json={"actor_user_id": "bob"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "tasks.forbidden"


def test_play_all_workspace_tasks_invalid_workspace_returns_422(client) -> None:
    r = client.post(
        "/api/workspaces/0/tasks/play-all",
        json={"actor_user_id": "alice"},
    )
    assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# AC-F8: POST /api/workspaces/{id}/play-all happy path
# ══════════════════════════════════════════════════════════════════════════


def test_play_all_workspace_happy_path(client, monkeypatch) -> None:
    async def fake(workspace_id: int, *, actor_user_id: Optional[str],
                   max_parallel: int = 5) -> dict:
        assert workspace_id == 7
        assert actor_user_id == "alice"
        return {"queued": 4}

    monkeypatch.setattr(tws, "play_all_workspace", fake)
    r = client.post(
        "/api/workspaces/7/play-all",
        json={"actor_user_id": "alice"},
    )
    assert r.status_code == 200
    assert r.json() == {"queued": 4}


# ══════════════════════════════════════════════════════════════════════════
# AC-F9: workspaces/{id}/play-all actor 不在 → 401
# ══════════════════════════════════════════════════════════════════════════


def test_play_all_workspace_missing_actor_returns_401(client, monkeypatch) -> None:
    async def fake(workspace_id: int, *, actor_user_id: Optional[str],
                   max_parallel: int = 5) -> dict:
        raise Unauthorized("actor_user_id is required")

    monkeypatch.setattr(tws, "play_all_workspace", fake)
    r = client.post("/api/workspaces/7/play-all", json={})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tasks.unauthorized"


def test_play_all_workspace_invalid_workspace_returns_422(client) -> None:
    r = client.post(
        "/api/workspaces/0/play-all",
        json={"actor_user_id": "alice"},
    )
    assert r.status_code == 422


def test_play_all_workspace_max_parallel_reached_returns_409(
    client, monkeypatch,
) -> None:
    from services.task_workspace_service import MaxParallelReached

    async def fake(workspace_id: int, *, actor_user_id: Optional[str],
                   max_parallel: int = 5) -> dict:
        raise MaxParallelReached(
            f"workspace {workspace_id} reached max_parallel"
        )

    monkeypatch.setattr(tws, "play_all_workspace", fake)
    r = client.post(
        "/api/workspaces/7/play-all",
        json={"actor_user_id": "alice"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "tasks.max_parallel_reached"


# ══════════════════════════════════════════════════════════════════════════
# Service-layer pure helpers (DB 不要)
# ══════════════════════════════════════════════════════════════════════════


def test_partition_playable_skips_completed() -> None:
    rows = [
        {"id": 1, "status": "todo"},
        {"id": 2, "status": "completed"},
        {"id": 3, "status": "in_progress"},
        {"id": 4, "status": "cancelled"},
        {"id": 5, "status": None},  # legacy 行を許容
    ]
    playable, skipped = _partition_playable(rows, [])
    assert playable == [1, 5]
    assert skipped == 3


def test_partition_playable_skips_unmet_dependency() -> None:
    rows = [{"id": 1, "status": "todo"}, {"id": 2, "status": "todo"}]
    deps = [
        # task 1 depends on 99 (status todo) → unmet
        {"task_id": 1, "depends_on_task_id": 99, "dep_status": "todo"},
        # task 2 depends on 88 (status completed) → met
        {"task_id": 2, "depends_on_task_id": 88, "dep_status": "completed"},
    ]
    playable, skipped = _partition_playable(rows, deps)
    assert playable == [2]
    assert skipped == 1


def test_partition_playable_treats_done_as_satisfied() -> None:
    rows = [{"id": 1, "status": "todo"}]
    deps = [
        {"task_id": 1, "depends_on_task_id": 5, "dep_status": "done"},
    ]
    playable, skipped = _partition_playable(rows, deps)
    assert playable == [1]
    assert skipped == 0


def test_partition_playable_empty_input() -> None:
    assert _partition_playable([], []) == ([], 0)


# ══════════════════════════════════════════════════════════════════════════
# user-scoped rate limiter (token bucket)
# ══════════════════════════════════════════════════════════════════════════


def test_rl_check_user_allows_up_to_30() -> None:
    _rl_reset_user()
    for _ in range(30):
        _rl_check_user("alice")


def test_rl_check_user_blocks_after_30() -> None:
    _rl_reset_user()
    for _ in range(30):
        _rl_check_user("alice")
    with pytest.raises(RateLimited):
        _rl_check_user("alice")


def test_rl_check_user_isolated_per_user() -> None:
    _rl_reset_user()
    for _ in range(30):
        _rl_check_user("alice")
    # bob はまだ余裕
    _rl_check_user("bob")


# ══════════════════════════════════════════════════════════════════════════
# service-level: play_task (mock DB)
# ══════════════════════════════════════════════════════════════════════════


class _FakeCursor:
    def __init__(self, rows: Optional[list[dict]] = None,
                 rowcount: int = 0) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount

    async def fetchone(self) -> Any:
        return self._rows.pop(0) if self._rows else None

    async def fetchall(self) -> list[dict]:
        rows = list(self._rows)
        self._rows.clear()
        return rows


class _FakePlayConn:
    """play_task 用 DB stub."""
    Row = dict

    def __init__(
        self,
        task_row: Optional[dict] = None,
        is_member: bool = True,
        dep_rows: Optional[list[dict]] = None,
    ) -> None:
        self._task_row = task_row
        self._is_member = is_member
        self._dep_rows = dep_rows or []
        self.row_factory = None
        self.insert_calls: list[tuple] = []

    async def execute_fetchall(self, sql: str, *args: Any) -> list[dict]:
        s = sql.lower()
        if "from bf_tasks t" in s and "join bf_projects p" in s and "where t.id" in s:
            return [self._task_row] if self._task_row else []
        if "from workspace_members" in s:
            return [{"role": "owner"}] if self._is_member else []
        if "from bf_task_dependencies" in s:
            return list(self._dep_rows)
        return []

    async def execute(self, sql: str, *args: Any) -> _FakeCursor:
        s = sql.lower()
        if "insert into sessions" in s:
            self.insert_calls.append(args[0] if args else ())
        return _FakeCursor()

    async def commit(self) -> None:
        pass

    async def __aenter__(self) -> "_FakePlayConn":
        return self

    async def __aexit__(self, *a: Any) -> None:
        pass


class _FakeAiosqlite:
    Row = dict

    def __init__(self, **kw: Any) -> None:
        self._kw = kw
        self.last_conn: Optional[_FakePlayConn] = None

    def connect(self, _path: Any) -> _FakePlayConn:
        conn = _FakePlayConn(**self._kw)
        self.last_conn = conn
        return conn


@pytest.fixture
def play_mock_db(monkeypatch):
    def _apply(**kwargs):
        fake = _FakeAiosqlite(**kwargs)
        monkeypatch.setattr(tws, "aiosqlite", fake)
        return fake
    return _apply


def test_service_play_task_requires_actor(play_mock_db) -> None:
    play_mock_db()
    with pytest.raises(Unauthorized):
        asyncio.run(tws.play_task(1, actor_user_id=None))
    with pytest.raises(Unauthorized):
        asyncio.run(tws.play_task(1, actor_user_id="  "))


def test_service_play_task_rejects_invalid_id(play_mock_db) -> None:
    play_mock_db()
    with pytest.raises(ValidationFailed):
        asyncio.run(tws.play_task(0, actor_user_id="alice"))
    with pytest.raises(ValidationFailed):
        asyncio.run(tws.play_task(-3, actor_user_id="alice"))


def test_service_play_task_task_not_found(play_mock_db) -> None:
    play_mock_db(task_row=None)
    with pytest.raises(TaskNotFound):
        asyncio.run(tws.play_task(999, actor_user_id="alice"))


def test_service_play_task_non_member_forbidden(play_mock_db) -> None:
    play_mock_db(
        task_row={"id": 1, "title": "A", "status": "todo", "workspace_id": 7},
        is_member=False,
    )
    with pytest.raises(Forbidden):
        asyncio.run(tws.play_task(1, actor_user_id="bob"))


def test_service_play_task_unmet_deps_raises(play_mock_db) -> None:
    play_mock_db(
        task_row={"id": 1, "title": "A", "status": "todo", "workspace_id": 7},
        is_member=True,
        dep_rows=[
            {"depends_on_task_id": 5, "status": "todo"},
        ],
    )
    _rl_reset_user()
    with pytest.raises(DependencyConflict):
        asyncio.run(tws.play_task(1, actor_user_id="alice"))


def test_service_play_task_satisfied_deps_spawns_session(play_mock_db) -> None:
    fake = play_mock_db(
        task_row={"id": 1, "title": "A", "status": "todo", "workspace_id": 7},
        is_member=True,
        dep_rows=[
            {"depends_on_task_id": 5, "status": "completed"},
        ],
    )
    _rl_reset_user()
    result = asyncio.run(tws.play_task(1, actor_user_id="alice"))
    assert result["session_id"].startswith("play-")
    # session INSERT が走っている
    assert fake.last_conn is not None
    assert len(fake.last_conn.insert_calls) == 1


def test_service_play_task_no_deps_spawns_session(play_mock_db) -> None:
    fake = play_mock_db(
        task_row={"id": 7, "title": "B", "status": "todo", "workspace_id": 3},
        is_member=True,
        dep_rows=[],
    )
    _rl_reset_user()
    result = asyncio.run(tws.play_task(7, actor_user_id="carol"))
    assert "session_id" in result
    assert fake.last_conn is not None
    assert len(fake.last_conn.insert_calls) == 1


def test_service_play_task_rate_limited_after_30(play_mock_db) -> None:
    play_mock_db(
        task_row={"id": 1, "title": "A", "status": "todo", "workspace_id": 7},
        is_member=True,
        dep_rows=[],
    )
    _rl_reset_user()
    for _ in range(30):
        asyncio.run(tws.play_task(1, actor_user_id="alice"))
    with pytest.raises(RateLimited):
        asyncio.run(tws.play_task(1, actor_user_id="alice"))
