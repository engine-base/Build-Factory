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