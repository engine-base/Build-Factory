"""T-009-01: bf_task_dependencies CRUD API.

  GET    /api/tasks/{task_id}/dependencies          list by task
  GET    /api/projects/{pid}/dependencies            list by project (DAG view)
  GET    /api/dependencies/{dep_id}                  get single
  POST   /api/tasks/{task_id}/dependencies          create
  DELETE /api/dependencies/{dep_id}                  delete

Error contract:
  4xx: {detail: {code, message}}
    invalid_dep_type / self_loop / cycle_detected / dep_duplicate / dep_not_found
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import task_dependency_service as tds
from services.task_dependency_service import (
    InvalidDepInput, DepCycleDetected, DepNotFound,
)


router = APIRouter(tags=["task-dependencies"])


class DependencyCreate(BaseModel):
    depends_on_task_id: int
    dep_type: str = "blocks"


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
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