"""T-009-01 + T-V3-B-14 / F-009: bf_task_dependencies CRUD + Dependency graph API.

T-009-01 endpoints:
  GET    /api/tasks/{task_id}/dependencies          list by task
  GET    /api/projects/{pid}/dependencies            list by project (DAG view)
  GET    /api/dependencies/{dep_id}                  get single
  POST   /api/tasks/{task_id}/dependencies          create
  DELETE /api/dependencies/{dep_id}                  delete

T-V3-B-14 / F-009 endpoints (workspace-scoped):
  GET    /api/workspaces/{id}/dependencies                 list deps in workspace
  POST   /api/workspaces/{id}/dependencies                 create edge (from, to)
  POST   /api/workspaces/{id}/dependencies/impact-analysis blast_radius computation

Error contract:
  4xx: {detail: {code, message}}
    invalid_dep_type / self_loop / cycle_detected / dep_duplicate / dep_not_found
    deps.unauthorized / deps.forbidden / deps.task_not_found / deps.invalid
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import task_dependency_service as tds
from services.task_dependency_service import (
    InvalidDepInput, DepCycleDetected, TaskNotInWorkspaceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["task-dependencies"])


class DependencyCreate(BaseModel):
    depends_on_task_id: int
    dep_type: str = "blocks"


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-14 / F-009 schema (workspace-scoped)
# ──────────────────────────────────────────────────────────────────────────


class WorkspaceDependencyCreate(BaseModel):
    """F-009 POST body. from_task_id depends on to_task_id."""
    from_task_id: int = Field(..., gt=0, description="depending task id")
    to_task_id: int = Field(..., gt=0, description="depended-on task id")
    dep_type: str = "blocks"


class WorkspaceImpactRequest(BaseModel):
    """F-009 impact-analysis body."""
    task_id: int = Field(..., gt=0)
    blast_radius_cap: int = Field(100, ge=1, le=1000)


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


async def _audit_dep(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("dependency audit emit failed: %s -- %s", event_type, e)


async def _check_workspace_auth(workspace_id: int, user_id: Optional[str]) -> None:
    """F-009 共通 auth check.

      - user_id 未指定 / 空文字 → 401
      - 指定済だが member でない → 403
    """
    if user_id is None or not user_id.strip():
        raise _err("deps.unauthorized", "user_id is required (auth token missing)", 401)
    is_member = await tds._user_is_workspace_member(workspace_id, user_id.strip())
    if not is_member:
        raise _err(
            "deps.forbidden",
            f"user {user_id} is not a member of workspace {workspace_id}",
            403,
        )


@router.get("/api/tasks/{task_id}/dependencies")
async def list_by_task(task_id: int):
    deps = await tds.list_dependencies_by_task(task_id)
    return {"task_id": task_id, "dependencies": deps, "count": len(deps)}


@router.get("/api/projects/{project_id}/dependencies")
async def list_by_project(project_id: int):
    deps = await tds.list_dependencies_by_project(project_id)
    return {"project_id": project_id, "dependencies": deps, "count": len(deps)}


@router.get("/api/dependencies/{dep_id}")
async def get_dep(dep_id: int):
    d = await tds.get_dependency(dep_id)
    if not d:
        raise _err("dep_not_found", f"dependency not found: {dep_id}", 404)
    return d


@router.post("/api/tasks/{task_id}/dependencies")
async def create_dep(task_id: int, body: DependencyCreate):
    try:
        return await tds.create_dependency(
            task_id=task_id,
            depends_on_task_id=body.depends_on_task_id,
            dep_type=body.dep_type,
        )
    except DepCycleDetected as e:
        raise _err("cycle_detected", str(e), 409)
    except InvalidDepInput as e:
        msg = str(e)
        if "itself" in msg:
            raise _err("self_loop", msg)
        if "already exists" in msg:
            raise _err("dep_duplicate", msg, 409)
        raise _err("invalid_dep_type", msg)


@router.delete("/api/dependencies/{dep_id}")
async def delete_dep(dep_id: int):
    ok = await tds.delete_dependency(dep_id)
    if not ok:
        raise _err("dep_not_found", f"dependency not found: {dep_id}", 404)
    return {"deleted": True, "dep_id": dep_id}


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-14 / F-009: workspace-scoped dependency graph + impact-analysis
# ──────────────────────────────────────────────────────────────────────────


@router.get("/api/workspaces/{workspace_id}/dependencies")
async def list_workspace_dependencies(
    workspace_id: int,
    user_id: Optional[str] = Query(None, description="actor user id (auth)"),
):
    """F-009 AC: GET dependencies in workspace.

    EVENT-DRIVEN: When called by authorized caller -> 2xx with {dependencies}.
    UNWANTED: missing auth -> 401 / non-member -> 403 / invalid id -> 422.
    """
    if workspace_id <= 0:
        raise _err("deps.invalid_workspace_id", "workspace_id must be > 0", 422)
    await _check_workspace_auth(workspace_id, user_id)
    deps = await tds.list_dependencies_by_workspace(workspace_id)
    return {
        "workspace_id": workspace_id,
        "dependencies": deps,
        "count": len(deps),
    }


@router.post("/api/workspaces/{workspace_id}/dependencies")
async def create_workspace_dependency(
    workspace_id: int,
    body: WorkspaceDependencyCreate,
    user_id: Optional[str] = Query(None, description="actor user id (auth)"),
):
    """F-009 AC: POST create edge (from_task_id, to_task_id).

    EVENT-DRIVEN: valid edge -> 201 with {dependency_id}.
    UNWANTED: cycle -> 409 / self-loop -> 422 / task not in workspace -> 404 /
              missing auth -> 401 / non-member -> 403.
    """
    if workspace_id <= 0:
        raise _err("deps.invalid_workspace_id", "workspace_id must be > 0", 422)
    await _check_workspace_auth(workspace_id, user_id)

    try:
        result = await tds.create_dependency_workspace_scoped(
            workspace_id=workspace_id,
            from_task_id=body.from_task_id,
            to_task_id=body.to_task_id,
            dep_type=body.dep_type,
        )
    except DepCycleDetected as e:
        raise _err("deps.cycle_detected", str(e), 409)
    except TaskNotInWorkspaceError as e:
        raise _err("deps.task_not_found", str(e), 404)
    except InvalidDepInput as e:
        msg = str(e)
        if "itself" in msg:
            raise _err("deps.self_loop", msg, 422)
        if "already exists" in msg:
            raise _err("deps.duplicate", msg, 409)
        raise _err("deps.invalid", msg, 422)

    dependency_id = result.get("id") if isinstance(result, dict) else None
    await _audit_dep(
        "dependency_added",
        user_id=user_id,
        detail={
            "workspace_id": workspace_id,
            "dependency_id": dependency_id,
            "from_task_id": body.from_task_id,
            "to_task_id": body.to_task_id,
        },
    )
    return {
        "dependency_id": dependency_id,
        "workspace_id": workspace_id,
        "from_task_id": body.from_task_id,
        "to_task_id": body.to_task_id,
        "dep_type": body.dep_type,
    }


@router.post("/api/workspaces/{workspace_id}/dependencies/impact-analysis")
async def workspace_impact_analysis(
    workspace_id: int,
    body: WorkspaceImpactRequest,
    user_id: Optional[str] = Query(None, description="actor user id (auth)"),
):
    """F-009 AC: POST impact-analysis.

    EVENT-DRIVEN: valid task_id -> 2xx with {affected_tasks, blast_radius}.
    UNWANTED: missing auth -> 401 / non-member -> 403 / task not in workspace -> 404.
    """
    if workspace_id <= 0:
        raise _err("deps.invalid_workspace_id", "workspace_id must be > 0", 422)
    await _check_workspace_auth(workspace_id, user_id)

    try:
        result = await tds.compute_workspace_impact(
            workspace_id=workspace_id,
            task_id=body.task_id,
            blast_radius_cap=body.blast_radius_cap,
        )
    except TaskNotInWorkspaceError as e:
        raise _err("deps.task_not_found", str(e), 404)
    except InvalidDepInput as e:
        raise _err("deps.invalid", str(e), 422)

    await _audit_dep(
        "impact_analyzed",
        user_id=user_id,
        detail={
            "workspace_id": workspace_id,
            "task_id": body.task_id,
            "blast_radius": result.get("blast_radius"),
            "truncated": result.get("truncated"),
        },
    )
    return result