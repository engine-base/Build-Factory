"""T-009-01: bf_task_dependencies CRUD service.

T-001-04 で作成された bf_task_dependencies (task DAG の edges) への CRUD.
cycle 検出は T-001-09 の DB trigger (bf_prevent_task_dep_cycle) に任せる.

公開 API:
  list_dependencies_by_task(task_id) -> list[dict]
  list_dependencies_by_project(project_id) -> list[dict]
  create_dependency(task_id, depends_on_task_id, dep_type='blocks') -> dict
  delete_dependency(dep_id) -> bool
  get_dependency(dep_id) -> dict | None

AC マッピング:
  AC-1 UBIQUITOUS: 4 CRUD 関数 + dep_type enum
  AC-2 EVENT:     2 秒以内 + ValueError → caller 4xx 化
  AC-4 UNWANTED:  self-loop / cycle / unknown task / dep_type invalid → ValueError
"""
from __future__ import annotations

from typing import Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH


VALID_DEP_TYPES = ("blocks", "related", "informs")


class InvalidDepInput(ValueError):
    """task_id == depends_on_task_id / dep_type enum 外."""


class DepCycleDetected(ValueError):
    """cycle 形成 (T-001-09 trigger 経由)."""


class DepNotFound(ValueError):
    """指定 dep_id が DB に存在しない."""


def _row(r) -> dict:
    return dict(r) if r else {}


def _validate_dep_type(dep_type: str) -> None:
    if dep_type not in VALID_DEP_TYPES:
        raise InvalidDepInput(
            f"dep_type must be one of {VALID_DEP_TYPES}, got {dep_type!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# Read
# ──────────────────────────────────────────────────────────────────────────


async def list_dependencies_by_task(task_id: int) -> list[dict]:
    """task の dependency edges (outgoing) を返す."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT * FROM bf_task_dependencies
                WHERE task_id = ?
                ORDER BY id ASC""",
            (task_id,),
        )
    return [_row(r) for r in rows]


async def list_dependencies_by_project(project_id: int) -> list[dict]:
    """project 内の全 dep を返す (DAG 全体描画用)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT d.*
                 FROM bf_task_dependencies d
                 JOIN bf_tasks t ON t.id = d.task_id
                WHERE t.project_id = ?
                ORDER BY d.id ASC""",
            (project_id,),
        )
    return [_row(r) for r in rows]


async def get_dependency(dep_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bf_task_dependencies WHERE id = ?", (dep_id,),
        )
        row = await cur.fetchone()
    return _row(row) if row else None


# ──────────────────────────────────────────────────────────────────────────
# Write
# ──────────────────────────────────────────────────────────────────────────


async def create_dependency(
    *,
    task_id: int,
    depends_on_task_id: int,
    dep_type: str = "blocks",
) -> dict:
    """新規 dep を INSERT.

    Raises:
      InvalidDepInput: dep_type enum 外 / self-loop
      DepCycleDetected: cycle 形成 (DB trigger 経由)
      InvalidDepInput: duplicate (uq_bf_dep)
    """
    _validate_dep_type(dep_type)
    if task_id == depends_on_task_id:
        raise InvalidDepInput(
            f"task cannot depend on itself (task_id={task_id})"
        )

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """INSERT INTO bf_task_dependencies
                    (task_id, depends_on_task_id, dep_type)
                    VALUES (?, ?, ?) RETURNING id""",
                (task_id, depends_on_task_id, dep_type),
            )
            row = await cur.fetchone()
            dep_id = dict(row)["id"] if row else None
            await db.commit()
    except Exception as e:
        msg = str(e).lower()
        if "cycle_detected" in msg or "check_violation" in msg:
            raise DepCycleDetected(
                f"cycle would form: task_id={task_id} → depends_on={depends_on_task_id}"
            ) from e
        if "unique" in msg or "uq_bf_dep" in msg or "duplicate" in msg:
            raise InvalidDepInput(
                f"dependency already exists: task_id={task_id} → depends_on={depends_on_task_id}"
            ) from e
        raise

    if dep_id is None:
        raise DepNotFound("INSERT returned no id")
    return await get_dependency(dep_id) or {}


async def delete_dependency(dep_id: int) -> bool:
    """dep を hard-delete. 存在しないなら False."""
    existing = await get_dependency(dep_id)
    if existing is None:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM bf_task_dependencies WHERE id = ?", (dep_id,),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-14 / F-009: workspace-scoped dependency graph + impact-analysis
# ──────────────────────────────────────────────────────────────────────────
#
# F-009 API contract (api-design/2026-05-16_v3/openapi.yaml):
#   GET  /api/workspaces/{id}/dependencies                -> { dependencies: [] }
#   POST /api/workspaces/{id}/dependencies                -> { dependency_id }
#   POST /api/workspaces/{id}/dependencies/impact-analysis -> { affected_tasks, blast_radius }
#
# Direction semantics (F-009 / E-017 TaskDependency):
#   - body field `from_task_id` = depending task (DB column: task_id)
#   - body field `to_task_id`   = depended-on task (DB column: depends_on_task_id)
#   - "from depends on to"
#
# Impact-analysis direction:
#   when task Y changes, "affected_tasks" = all tasks that transitively depend on Y.
#   In DB: walk edges where depends_on_task_id = current_id (forward to dependents).
#
# blast_radius cap: F-009 policy = 100 (truncate beyond).


class TaskNotInWorkspaceError(ValueError):
    """from_task_id / to_task_id が指定 workspace に属していない."""


async def _tasks_belong_to_workspace(
    workspace_id: int, task_ids: list[int],
) -> tuple[bool, list[int]]:
    """指定 task_ids 全件が workspace 配下 (projects.workspace_id 経由) か検証.

    Returns: (all_belong, missing_ids)
    """
    if not task_ids:
        return True, []
    placeholders = ",".join(["?"] * len(task_ids))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # bf_tasks (Postgres only) と tasks (sqlite legacy) の両方に対応.
        # まず bf_tasks スキーマを試し, fallback で tasks/projects 経由を試す.
        try:
            rows = await db.execute_fetchall(
                f"""SELECT t.id FROM bf_tasks t
                     JOIN bf_projects p ON p.id = t.project_id
                    WHERE p.workspace_id = ? AND t.id IN ({placeholders})""",
                (workspace_id, *task_ids),
            )
        except Exception:
            rows = []
        if rows:
            found = {int(r["id"]) for r in rows}
            missing = [t for t in task_ids if t not in found]
            return (len(missing) == 0), missing
        # fallback: sqlite legacy tasks/projects
        try:
            rows = await db.execute_fetchall(
                f"""SELECT t.id FROM tasks t
                     JOIN projects p ON p.id = t.project_id
                    WHERE p.workspace_id = ? AND t.id IN ({placeholders})""",
                (workspace_id, *task_ids),
            )
        except Exception:
            rows = []
        found = {int(r["id"]) for r in rows}
        missing = [t for t in task_ids if t not in found]
        return (len(missing) == 0), missing


async def list_dependencies_by_workspace(workspace_id: int) -> list[dict]:
    """workspace 配下 (projects.workspace_id 経由) の全 dependency edges を返す.

    F-009 GET /api/workspaces/{id}/dependencies の service 層.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # bf_* schema 試行 → 失敗時 legacy tasks/projects へ fallback.
        try:
            rows = await db.execute_fetchall(
                """SELECT d.id, d.task_id, d.depends_on_task_id, d.dep_type, d.created_at
                     FROM bf_task_dependencies d
                     JOIN bf_tasks t ON t.id = d.task_id
                     JOIN bf_projects p ON p.id = t.project_id
                    WHERE p.workspace_id = ?
                    ORDER BY d.id ASC""",
                (workspace_id,),
            )
        except Exception:
            rows = []
        if rows:
            return [_row(r) for r in rows]
        try:
            rows = await db.execute_fetchall(
                """SELECT d.id, d.task_id, d.depends_on_task_id, d.dep_type, d.created_at
                     FROM bf_task_dependencies d
                     JOIN tasks t ON t.id = d.task_id
                     JOIN projects p ON p.id = t.project_id
                    WHERE p.workspace_id = ?
                    ORDER BY d.id ASC""",
                (workspace_id,),
            )
        except Exception:
            rows = []
    return [_row(r) for r in rows]


async def create_dependency_workspace_scoped(
    *,
    workspace_id: int,
    from_task_id: int,
    to_task_id: int,
    dep_type: str = "blocks",
) -> dict:
    """F-009 POST /api/workspaces/{id}/dependencies の service 層.

    body.from_task_id → DB.task_id
    body.to_task_id   → DB.depends_on_task_id

    Raises:
      InvalidDepInput: dep_type enum 外 / self-loop / duplicate
      TaskNotInWorkspaceError: from_task_id or to_task_id が workspace 配下でない
      DepCycleDetected: cycle 形成
    """
    _validate_dep_type(dep_type)
    if from_task_id == to_task_id:
        raise InvalidDepInput(
            f"task cannot depend on itself (task_id={from_task_id})"
        )
    if from_task_id <= 0 or to_task_id <= 0:
        raise InvalidDepInput(
            f"task ids must be > 0 (from={from_task_id}, to={to_task_id})"
        )

    ok, missing = await _tasks_belong_to_workspace(
        workspace_id, [from_task_id, to_task_id],
    )
    if not ok:
        raise TaskNotInWorkspaceError(
            f"tasks not found in workspace {workspace_id}: {missing}"
        )

    return await create_dependency(
        task_id=from_task_id,
        depends_on_task_id=to_task_id,
        dep_type=dep_type,
    )


async def _list_outgoing_dependents(parent_task_id: int) -> list[int]:
    """parent_task_id を depends_on_task_id にもつ全 row の task_id を返す.

    impact-analysis 用. 「parent_task_id が変更されたら影響を受ける tasks」.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT task_id FROM bf_task_dependencies
                WHERE depends_on_task_id = ?
                ORDER BY id ASC""",
            (parent_task_id,),
        )
    return [int(r["task_id"]) for r in rows]


async def compute_workspace_impact(
    *,
    workspace_id: int,
    task_id: int,
    blast_radius_cap: int = 100,
) -> dict:
    """F-009 impact-analysis: forward BFS で affected_tasks を列挙.

    blast_radius は visit した affected task の総数 (起点除く).
    cap 到達で truncated=True を返す.
    """
    if task_id <= 0:
        raise InvalidDepInput(f"task_id must be > 0, got {task_id}")
    if blast_radius_cap <= 0 or blast_radius_cap > 1000:
        raise InvalidDepInput("blast_radius_cap must be 1..1000")

    ok, missing = await _tasks_belong_to_workspace(workspace_id, [task_id])
    if not ok:
        raise TaskNotInWorkspaceError(
            f"task {task_id} not found in workspace {workspace_id}"
        )

    from collections import deque
    visited: set[int] = {task_id}
    affected: list[int] = []
    queue: deque[int] = deque([task_id])
    truncated = False

    while queue:
        cur = queue.popleft()
        children = await _list_outgoing_dependents(cur)
        for child in children:
            if child == task_id:
                # cycle (impact-analysis でも cycle は明示 detect)
                continue
            if child in visited:
                continue
            visited.add(child)
            affected.append(child)
            if len(affected) >= blast_radius_cap:
                truncated = True
                queue.clear()
                break
            queue.append(child)

    return {
        "task_id": task_id,
        "affected_tasks": [{"task_id": t} for t in affected],
        "blast_radius": len(affected),
        "blast_radius_cap": blast_radius_cap,
        "truncated": truncated,
    }


async def _user_is_workspace_member(
    workspace_id: int, user_id: str,
) -> bool:
    """workspace_members 経由で user が member か検証."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            rows = await db.execute_fetchall(
                """SELECT 1 FROM workspace_members
                    WHERE workspace_id = ? AND user_id = ? LIMIT 1""",
                (workspace_id, user_id),
            )
        except Exception:
            return False
    return bool(rows)