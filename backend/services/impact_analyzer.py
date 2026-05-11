"""T-006-03: impact-analysis (downstream task discovery).

タスク 1 件が変更された時、依存グラフを通じて影響を受ける全 downstream task を列挙する.
T-009-01 (task_dependencies CRUD) で構築した依存グラフを forward BFS で辿る.

公開 API:
  - compute_impact(task_id, *, deps_loader, max_depth=20) -> ImpactReport
  - ImpactReport(.task_id, .total, .downstream)

deps_loader 注入式で DB 非依存テスト可能.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class ImpactAnalyzerError(RuntimeError):
    pass


class CycleDetectedError(ImpactAnalyzerError):
    pass


@dataclass
class ImpactedTask:
    task_id: int
    depth: int
    dep_type: str = "reports_to"  # 経由した dependency type


@dataclass
class ImpactReport:
    task_id: int
    total: int
    max_depth: int
    downstream: list[ImpactedTask] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "total": self.total,
            "max_depth": self.max_depth,
            "downstream": [
                {"task_id": t.task_id, "depth": t.depth, "dep_type": t.dep_type}
                for t in self.downstream
            ],
            "warnings": self.warnings,
        }


# 注入用 loader: task_id -> list of dependent task dicts
# 各 dep dict: {"to_task_id": int, "dep_type": str}
DependencyLoader = Callable[[int], Awaitable[list[dict]]]


async def compute_impact(
    task_id: int,
    *,
    deps_loader: DependencyLoader,
    max_depth: int = 20,
) -> ImpactReport:
    """task_id から forward BFS で全 downstream task を列挙する.

    deps_loader(parent_id) は dependency dict list を返す (子タスク = to_task_id).
    cycle が発生したら CycleDetectedError.
    max_depth 到達で truncate (warning に記録).
    """
    if task_id is None or task_id <= 0:
        raise ImpactAnalyzerError(f"task_id must be > 0, got {task_id}")
    if max_depth <= 0 or max_depth > 100:
        raise ImpactAnalyzerError("max_depth must be 1..100")

    visited: set[int] = {task_id}
    downstream: list[ImpactedTask] = []
    warnings: list[str] = []

    # BFS queue: (current_task_id, current_depth)
    queue: deque[tuple[int, int]] = deque([(task_id, 0)])
    max_depth_observed = 0

    while queue:
        parent_id, depth = queue.popleft()
        if depth >= max_depth:
            warnings.append(f"max_depth_reached_at_task_{parent_id}")
            continue

        try:
            deps = await deps_loader(parent_id)
        except Exception as e:
            warnings.append(f"loader_failed_for_{parent_id}:{e}")
            continue
        if not isinstance(deps, list):
            warnings.append(f"loader_invalid_response_for_{parent_id}")
            continue

        for dep in deps:
            if not isinstance(dep, dict):
                continue
            child_id = dep.get("to_task_id") or dep.get("child_id")
            if not isinstance(child_id, int) or child_id <= 0:
                continue
            if child_id == task_id:
                # 起点 task に戻った = cycle
                raise CycleDetectedError(
                    f"cycle detected: task {parent_id} → {child_id} (= start)"
                )
            if child_id in visited:
                # 既出 (別経路で訪問済) — skip
                continue
            visited.add(child_id)
            dep_type = dep.get("dep_type") or "reports_to"
            new_depth = depth + 1
            max_depth_observed = max(max_depth_observed, new_depth)
            downstream.append(ImpactedTask(
                task_id=child_id,
                depth=new_depth,
                dep_type=dep_type,
            ))
            queue.append((child_id, new_depth))

    return ImpactReport(
        task_id=task_id,
        total=len(downstream),
        max_depth=max_depth_observed,
        downstream=downstream,
        warnings=warnings,
    )
