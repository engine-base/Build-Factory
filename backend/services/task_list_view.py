"""T-007-02: task_list view (table + sort + 一括操作) サービス.

table 表示用の sort / filter / pagination + 一括 update を提供する.
loader 注入式で DB 非依存テスト可能.

公開 API:
  - filter_and_sort(tasks, *, status, assigned_to, sort_by, sort_order) -> list
  - paginate(items, *, page, page_size) -> Pagination
  - bulk_update(task_ids, updates, *, update_fn) -> BulkUpdateResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)


class TaskListViewError(RuntimeError):
    pass


VALID_SORT_BY = (
    "created_at", "updated_at", "due_date", "priority",
    "status", "assigned_to", "title", "id",
)
VALID_SORT_ORDER = ("asc", "desc")
VALID_BULK_FIELDS = ("status", "priority", "assigned_to", "due_date")
VALID_STATUS = ("pending", "in_progress", "review", "completed",
                "blocked_question", "blocked_dependency", "cancelled")
VALID_PRIORITY = ("low", "medium", "high", "urgent")
MAX_BULK_SIZE = 200
MAX_PAGE_SIZE = 500


@dataclass
class Pagination:
    items: list[dict]
    total: int
    page: int
    page_size: int
    total_pages: int

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
        }


@dataclass
class BulkUpdateResult:
    updated: list[int] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "updated": list(self.updated),
            "failed": [dict(f) for f in self.failed],
            "total": self.total,
            "success_count": len(self.updated),
            "failure_count": len(self.failed),
        }


# ──────────────────────────────────────────────────────────────────────────
# filter & sort
# ──────────────────────────────────────────────────────────────────────────


def filter_and_sort(
    tasks: list[dict],
    *,
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    project_id: Optional[int] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list[dict]:
    """task list を filter + sort して返す."""
    if not isinstance(tasks, list):
        raise TaskListViewError("tasks must be a list")
    if sort_by not in VALID_SORT_BY:
        raise TaskListViewError(
            f"sort_by must be one of {VALID_SORT_BY}, got {sort_by!r}"
        )
    if sort_order not in VALID_SORT_ORDER:
        raise TaskListViewError(
            f"sort_order must be one of {VALID_SORT_ORDER}, got {sort_order!r}"
        )
    if status is not None and status not in VALID_STATUS:
        raise TaskListViewError(
            f"status must be one of {VALID_STATUS}, got {status!r}"
        )

    items = tasks
    if status:
        items = [t for t in items if t.get("status") == status]
    if assigned_to is not None:
        items = [t for t in items if t.get("assigned_to") == assigned_to]
    if project_id is not None:
        items = [t for t in items if t.get("project_id") == project_id]

    reverse = sort_order == "desc"

    def sort_key(t: dict) -> Any:
        v = t.get(sort_by)
        if v is None:
            return (1, "")  # nulls last for both asc and desc
        return (0, v)

    return sorted(items, key=sort_key, reverse=reverse)


# ──────────────────────────────────────────────────────────────────────────
# pagination
# ──────────────────────────────────────────────────────────────────────────


def paginate(
    items: list[dict],
    *,
    page: int = 1,
    page_size: int = 50,
) -> Pagination:
    if page <= 0:
        raise TaskListViewError(f"page must be > 0, got {page}")
    if page_size <= 0 or page_size > MAX_PAGE_SIZE:
        raise TaskListViewError(
            f"page_size must be 1..{MAX_PAGE_SIZE}, got {page_size}"
        )
    total = len(items)
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    end = start + page_size
    return Pagination(
        items=items[start:end],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ──────────────────────────────────────────────────────────────────────────
# bulk update
# ──────────────────────────────────────────────────────────────────────────


UpdateFn = Callable[[int, dict], Awaitable[dict]]


def validate_bulk_updates(updates: dict) -> dict:
    """bulk update body を validate (各 field の値域も check)."""
    if not isinstance(updates, dict):
        raise TaskListViewError("updates must be a dict")
    if not updates:
        raise TaskListViewError("updates must not be empty")
    unknown = [k for k in updates if k not in VALID_BULK_FIELDS]
    if unknown:
        raise TaskListViewError(
            f"unknown fields {unknown}; allowed {VALID_BULK_FIELDS}"
        )
    if "status" in updates and updates["status"] not in VALID_STATUS:
        raise TaskListViewError(
            f"status must be one of {VALID_STATUS}, got {updates['status']!r}"
        )
    if "priority" in updates and updates["priority"] not in VALID_PRIORITY:
        raise TaskListViewError(
            f"priority must be one of {VALID_PRIORITY}, got {updates['priority']!r}"
        )
    if "assigned_to" in updates:
        v = updates["assigned_to"]
        if v is not None and (not isinstance(v, int) or v <= 0):
            raise TaskListViewError("assigned_to must be a positive int or null")
    return updates


async def bulk_update(
    task_ids: Iterable[int],
    updates: dict,
    *,
    update_fn: UpdateFn,
) -> BulkUpdateResult:
    """task_ids 全件に updates を適用. 各 update は update_fn(id, updates) で実行."""
    ids = list(task_ids)
    if not ids:
        raise TaskListViewError("task_ids must not be empty")
    if len(ids) > MAX_BULK_SIZE:
        raise TaskListViewError(
            f"task_ids must be <= {MAX_BULK_SIZE} per request"
        )
    for tid in ids:
        if not isinstance(tid, int) or tid <= 0:
            raise TaskListViewError(f"each task_id must be > 0, got {tid!r}")
    if len(set(ids)) != len(ids):
        raise TaskListViewError("task_ids must be unique")

    validate_bulk_updates(updates)

    result = BulkUpdateResult(total=len(ids))
    for tid in ids:
        try:
            await update_fn(tid, dict(updates))
            result.updated.append(tid)
        except Exception as e:
            result.failed.append({
                "task_id": tid,
                "reason": type(e).__name__,
                "message": str(e),
            })
    return result
