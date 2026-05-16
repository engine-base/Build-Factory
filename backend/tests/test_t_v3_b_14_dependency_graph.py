"""T-V3-B-14 / F-009: Dependency graph backend (edges + impact-analysis).

3 endpoints under workspace-scope:
  GET  /api/workspaces/{id}/dependencies
  POST /api/workspaces/{id}/dependencies
  POST /api/workspaces/{id}/dependencies/impact-analysis

AC mapping (verbatim from tickets-group-b-backend.json T-V3-B-14):

  AC-F1  EVENT-DRIVEN: POST valid edge -> 200 (persist)
  AC-F2  UNWANTED:     POST would create cycle -> 409 + cycle path
  AC-F3  EVENT-DRIVEN: POST impact-analysis -> downstream affected within blast_radius
  AC-F4  EVENT-DRIVEN: GET authorized -> 2xx with dependencies[]
  AC-F5  UNWANTED:     GET no auth -> 401
  AC-F6  UNWANTED:     GET invalid body -> 422
  AC-F7  EVENT-DRIVEN: POST authorized -> 2xx with dependency_id
  AC-F8  UNWANTED:     POST no auth -> 401
  AC-F9  UNWANTED:     POST invalid body -> 422
  AC-F10 EVENT-DRIVEN: POST impact-analysis authorized -> 2xx with affected_tasks
  AC-F11 UNWANTED:     POST impact-analysis no auth -> 401
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services import task_dependency_service as tds
from services.task_dependency_service import (
    DepCycleDetected,
    InvalidDepInput,
    TaskNotInWorkspaceError,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_member(monkeypatch):
    """workspace member check を常に True にする helper."""
    async def _ok(wid, uid):
        return True
    monkeypatch.setattr(tds, "_user_is_workspace_member", _ok)


@pytest.fixture
def auth_non_member(monkeypatch):
    async def _ng(wid, uid):
        return False
    monkeypatch.setattr(tds, "_user_is_workspace_member", _ng)


# ──────────────────────────────────────────────────────────────────────────
# AC-F4 / AC-F5 / AC-F6: GET /api/workspaces/{id}/dependencies
# ──────────────────────────────────────────────────────────────────────────


def test_get_workspace_dependencies_authorized_returns_200(client, monkeypatch, auth_member):
    """AC-F4: authorized caller -> 200 with dependencies[]."""
    async def fake_list(wid):
        return [
            {"id": 1, "task_id": 10, "depends_on_task_id": 20, "dep_type": "blocks"},
            {"id": 2, "task_id": 20, "depends_on_task_id": 30, "dep_type": "blocks"},
        ]
    monkeypatch.setattr(tds, "list_dependencies_by_workspace", fake_list)

    r = client.get("/api/workspaces/1/dependencies?user_id=u1")
    assert r.status_code == 200
    body = r.json()
    assert body["workspace_id"] == 1
    assert body["count"] == 2
    assert len(body["dependencies"]) == 2
    assert body["dependencies"][0]["task_id"] == 10


def test_get_workspace_dependencies_no_auth_returns_401(client, monkeypatch):
    """AC-F5: no user_id (auth token absent) -> 401."""
    r = client.get("/api/workspaces/1/dependencies")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "deps.unauthorized"


def test_get_workspace_dependencies_non_member_returns_403(client, monkeypatch, auth_non_member):
    """member でない user -> 403."""
    r = client.get("/api/workspaces/1/dependencies?user_id=stranger")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "deps.forbidden"


def test_get_workspace_dependencies_invalid_workspace_id_returns_422(client):
    """AC-F6: workspace_id invalid (<=0) -> 422."""
    r = client.get("/api/workspaces/0/dependencies?user_id=u1")
    assert r.status_code == 422
    # 422 either from FastAPI validation (path param) or service-level invalid
    body = r.json()
    assert "detail" in body


# ──────────────────────────────────────────────────────────────────────────
# AC-F1 / AC-F2 / AC-F7 / AC-F8 / AC-F9: POST /api/workspaces/{id}/dependencies
# ──────────────────────────────────────────────────────────────────────────


def test_post_workspace_dependency_happy(client, monkeypatch, auth_member):
    """AC-F1 / AC-F7: valid edge persists and returns 200 with dependency_id."""
    async def fake_create(**kw):
        # service returns the row dict with id
        return {
            "id": 42,
            "task_id": kw["from_task_id"],
            "depends_on_task_id": kw["to_task_id"],
            "dep_type": kw.get("dep_type", "blocks"),
        }
    monkeypatch.setattr(tds, "create_dependency_workspace_scoped", fake_create)

    r = client.post(
        "/api/workspaces/1/dependencies?user_id=u1",
        json={"from_task_id": 10, "to_task_id": 20},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dependency_id"] == 42
    assert body["from_task_id"] == 10
    assert body["to_task_id"] == 20
    assert body["workspace_id"] == 1


def test_post_workspace_dependency_cycle_returns_409(client, monkeypatch, auth_member):
    """AC-F2: cycle would form -> 409 + cycle path."""
    async def fake_create(**kw):
        raise DepCycleDetected(
            "cycle would form: task_id=10 → depends_on=20 (cycle path: 10 → 20 → 10)"
        )
    monkeypatch.setattr(tds, "create_dependency_workspace_scoped", fake_create)

    r = client.post(
        "/api/workspaces/1/dependencies?user_id=u1",
        json={"from_task_id": 10, "to_task_id": 20},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "deps.cycle_detected"
    assert "cycle" in detail["message"].lower()


def test_post_workspace_dependency_self_loop_returns_422(client, monkeypatch, auth_member):
    """self-loop (from == to) -> 422."""
    async def fake_create(**kw):
        raise InvalidDepInput("task cannot depend on itself (task_id=10)")
    monkeypatch.setattr(tds, "create_dependency_workspace_scoped", fake_create)

    r = client.post(
        "/api/workspaces/1/dependencies?user_id=u1",
        json={"from_task_id": 10, "to_task_id": 10},
    )
    assert r.status_code == 422
    # FastAPI validation OR our service-level 422
    body = r.json()
    assert "detail" in body


def test_post_workspace_dependency_duplicate_returns_409(client, monkeypatch, auth_member):
    async def fake_create(**kw):
        raise InvalidDepInput("dependency already exists: task_id=10 → depends_on=20")
    monkeypatch.setattr(tds, "create_dependency_workspace_scoped", fake_create)

    r = client.post(
        "/api/workspaces/1/dependencies?user_id=u1",
        json={"from_task_id": 10, "to_task_id": 20},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "deps.duplicate"


def test_post_workspace_dependency_task_not_in_workspace_returns_404(client, monkeypatch, auth_member):
    async def fake_create(**kw):
        raise TaskNotInWorkspaceError("tasks not found in workspace 1: [999]")
    monkeypatch.setattr(tds, "create_dependency_workspace_scoped", fake_create)

    r = client.post(
        "/api/workspaces/1/dependencies?user_id=u1",
        json={"from_task_id": 999, "to_task_id": 20},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "deps.task_not_found"


def test_post_workspace_dependency_no_auth_returns_401(client):
    """AC-F8: no user_id -> 401."""
    r = client.post(
        "/api/workspaces/1/dependencies",
        json={"from_task_id": 10, "to_task_id": 20},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "deps.unauthorized"


def test_post_workspace_dependency_invalid_body_returns_422(client, auth_member):
    """AC-F9: invalid body (missing field) -> 422 field-level error map."""
    r = client.post(
        "/api/workspaces/1/dependencies?user_id=u1",
        json={"from_task_id": 10},  # missing to_task_id
    )
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    # FastAPI returns list[ValidationError] under detail
    assert isinstance(body["detail"], list)
    # field-level error pointing to to_task_id
    field_paths = [tuple(e.get("loc", [])) for e in body["detail"]]
    assert any("to_task_id" in p for p in field_paths)


def test_post_workspace_dependency_negative_task_id_returns_422(client, auth_member):
    """AC-F9: gt=0 validation -> 422."""
    r = client.post(
        "/api/workspaces/1/dependencies?user_id=u1",
        json={"from_task_id": -1, "to_task_id": 20},
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# AC-F3 / AC-F10 / AC-F11: POST .../impact-analysis
# ──────────────────────────────────────────────────────────────────────────


def test_post_impact_analysis_happy(client, monkeypatch, auth_member):
    """AC-F3 / AC-F10: returns affected_tasks within blast_radius."""
    async def fake_impact(**kw):
        return {
            "task_id": kw["task_id"],
            "affected_tasks": [{"task_id": 11}, {"task_id": 12}, {"task_id": 13}],
            "blast_radius": 3,
            "blast_radius_cap": kw.get("blast_radius_cap", 100),
            "truncated": False,
        }
    monkeypatch.setattr(tds, "compute_workspace_impact", fake_impact)

    r = client.post(
        "/api/workspaces/1/dependencies/impact-analysis?user_id=u1",
        json={"task_id": 10},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == 10
    assert body["blast_radius"] == 3
    assert len(body["affected_tasks"]) == 3
    assert body["affected_tasks"][0]["task_id"] == 11
    assert body["truncated"] is False


def test_post_impact_analysis_blast_radius_cap(client, monkeypatch, auth_member):
    """blast_radius cap enforced + truncated flag."""
    async def fake_impact(**kw):
        cap = kw.get("blast_radius_cap", 100)
        return {
            "task_id": kw["task_id"],
            "affected_tasks": [{"task_id": i} for i in range(100, 100 + cap)],
            "blast_radius": cap,
            "blast_radius_cap": cap,
            "truncated": True,
        }
    monkeypatch.setattr(tds, "compute_workspace_impact", fake_impact)

    r = client.post(
        "/api/workspaces/1/dependencies/impact-analysis?user_id=u1",
        json={"task_id": 10, "blast_radius_cap": 50},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["blast_radius"] == 50
    assert body["truncated"] is True


def test_post_impact_analysis_no_auth_returns_401(client):
    """AC-F11: no user_id -> 401."""
    r = client.post(
        "/api/workspaces/1/dependencies/impact-analysis",
        json={"task_id": 10},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "deps.unauthorized"


def test_post_impact_analysis_non_member_returns_403(client, auth_non_member):
    r = client.post(
        "/api/workspaces/1/dependencies/impact-analysis?user_id=stranger",
        json={"task_id": 10},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "deps.forbidden"


def test_post_impact_analysis_task_not_in_workspace_returns_404(client, monkeypatch, auth_member):
    async def fake_impact(**kw):
        raise TaskNotInWorkspaceError(
            f"task {kw['task_id']} not found in workspace {kw['workspace_id']}"
        )
    monkeypatch.setattr(tds, "compute_workspace_impact", fake_impact)

    r = client.post(
        "/api/workspaces/1/dependencies/impact-analysis?user_id=u1",
        json={"task_id": 999},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "deps.task_not_found"


def test_post_impact_analysis_invalid_body_returns_422(client, auth_member):
    """missing required task_id -> 422."""
    r = client.post(
        "/api/workspaces/1/dependencies/impact-analysis?user_id=u1",
        json={},
    )
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    assert isinstance(body["detail"], list)


def test_post_impact_analysis_blast_radius_cap_validation(client, auth_member):
    """blast_radius_cap out-of-range -> 422."""
    r = client.post(
        "/api/workspaces/1/dependencies/impact-analysis?user_id=u1",
        json={"task_id": 10, "blast_radius_cap": 5000},
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# Service-level pure unit tests (compute_workspace_impact BFS)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_compute_impact_bfs_walks_dependents(monkeypatch):
    """Forward BFS: starting from task 1, traverse depends_on chain.

    Graph (X depends_on Y, recorded as task_id=X, depends_on_task_id=Y):
      task 2 -> task 1 (2 depends on 1)
      task 3 -> task 2 (3 depends on 2)
      task 4 -> task 1 (4 depends on 1)
    From task 1: affected = {2, 3, 4}.
    """
    # Mock _tasks_belong_to_workspace -> always belong
    async def fake_belong(wid, ids):
        return True, []
    monkeypatch.setattr(tds, "_tasks_belong_to_workspace", fake_belong)

    # Mock outgoing dependents
    graph: dict[int, list[int]] = {
        1: [2, 4],
        2: [3],
        3: [],
        4: [],
    }
    async def fake_outgoing(parent_id):
        return list(graph.get(parent_id, []))
    monkeypatch.setattr(tds, "_list_outgoing_dependents", fake_outgoing)

    result = await tds.compute_workspace_impact(
        workspace_id=1, task_id=1, blast_radius_cap=100,
    )
    assert result["task_id"] == 1
    affected_ids = {t["task_id"] for t in result["affected_tasks"]}
    assert affected_ids == {2, 3, 4}
    assert result["blast_radius"] == 3
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_service_compute_impact_blast_radius_cap_truncates(monkeypatch):
    """cap 到達で truncated=True."""
    async def fake_belong(wid, ids):
        return True, []
    monkeypatch.setattr(tds, "_tasks_belong_to_workspace", fake_belong)

    # large fan-out
    async def fake_outgoing(parent_id):
        if parent_id == 1:
            return list(range(100, 200))  # 100 children
        return []
    monkeypatch.setattr(tds, "_list_outgoing_dependents", fake_outgoing)

    result = await tds.compute_workspace_impact(
        workspace_id=1, task_id=1, blast_radius_cap=10,
    )
    assert result["blast_radius"] == 10
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_service_compute_impact_task_not_in_workspace_raises(monkeypatch):
    async def fake_belong(wid, ids):
        return False, ids
    monkeypatch.setattr(tds, "_tasks_belong_to_workspace", fake_belong)

    with pytest.raises(TaskNotInWorkspaceError):
        await tds.compute_workspace_impact(
            workspace_id=1, task_id=999, blast_radius_cap=10,
        )


@pytest.mark.asyncio
async def test_service_create_dependency_workspace_scoped_self_loop(monkeypatch):
    async def fake_belong(wid, ids):
        return True, []
    monkeypatch.setattr(tds, "_tasks_belong_to_workspace", fake_belong)

    with pytest.raises(InvalidDepInput) as exc:
        await tds.create_dependency_workspace_scoped(
            workspace_id=1, from_task_id=10, to_task_id=10,
        )
    assert "itself" in str(exc.value)


@pytest.mark.asyncio
async def test_service_create_dependency_workspace_scoped_task_not_in_ws(monkeypatch):
    async def fake_belong(wid, ids):
        return False, [10]
    monkeypatch.setattr(tds, "_tasks_belong_to_workspace", fake_belong)

    with pytest.raises(TaskNotInWorkspaceError):
        await tds.create_dependency_workspace_scoped(
            workspace_id=1, from_task_id=10, to_task_id=20,
        )


@pytest.mark.asyncio
async def test_service_create_dependency_workspace_scoped_invalid_dep_type(monkeypatch):
    async def fake_belong(wid, ids):
        return True, []
    monkeypatch.setattr(tds, "_tasks_belong_to_workspace", fake_belong)

    with pytest.raises(InvalidDepInput):
        await tds.create_dependency_workspace_scoped(
            workspace_id=1, from_task_id=10, to_task_id=20, dep_type="bogus",
        )
