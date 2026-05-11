"""T-010c-02: タスク親子昇格 (依存グラフ尊重) サービス.

依存関係 (child blocks parent) で、child の priority が parent より高い場合、
親の priority を child の max まで昇格させる. ブロッカー解消を優先するための仕組み.

サイクル検出: T-006-03 の impact_analyzer と同様の方針で DFS により検出.

Priority 順序: urgent > high > medium > low
公開 API:
  - elevate_priorities(tasks, dependencies) -> ElevationReport
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class PriorityElevationError(RuntimeError):
    pass


class CycleDetectedError(PriorityElevationError):
    pass


PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "urgent": 3}
VALID_PRIORITIES = tuple(PRIORITY_ORDER.keys())
ORDER_TO_PRIORITY = {v: k for k, v in PRIORITY_ORDER.items()}


@dataclass
class PriorityElevation:
    task_id: int
    from_priority: str
    to_priority: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "from_priority": self.from_priority,
            "to_priority": self.to_priority,
            "reason": self.reason,
        }


@dataclass
class ElevationReport:
    total_tasks: int
    elevated: list[PriorityElevation] = field(default_factory=list)
    unchanged: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_tasks": self.total_tasks,
            "elevated_count": len(self.elevated),
            "unchanged_count": self.unchanged,
            "elevated": [e.to_dict() for e in self.elevated],
            "warnings": self.warnings,
        }


def _norm_priority(p: Optional[str]) -> str:
    if not p or not isinstance(p, str):
        return "medium"
    p_l = p.strip().lower()
    if p_l not in PRIORITY_ORDER:
        return "medium"
    return p_l


def _validate_inputs(tasks, dependencies) -> None:
    if not isinstance(tasks, list):
        raise PriorityElevationError("tasks must be a list")
    if not isinstance(dependencies, list):
        raise PriorityElevationError("dependencies must be a list")
    if len(tasks) > 5000:
        raise PriorityElevationError("tasks must be <= 5000")
    if len(dependencies) > 20000:
        raise PriorityElevationError("dependencies must be <= 20000")


def _build_graph(
    tasks: list[dict], dependencies: list[dict],
) -> tuple[dict[int, dict], dict[int, set[int]]]:
    """task_id → task dict, task_id → child task_id set を返す."""
    task_map: dict[int, dict] = {}
    for t in tasks:
        if not isinstance(t, dict):
            continue
        tid = t.get("id") or t.get("task_id")
        if not isinstance(tid, int) or tid <= 0:
            continue
        task_map[tid] = {
            "id": tid,
            "priority": _norm_priority(t.get("priority")),
        }

    # children[parent_id] = set of child_id
    children: dict[int, set[int]] = defaultdict(set)
    for d in dependencies:
        if not isinstance(d, dict):
            continue
        parent = d.get("from_task_id") or d.get("parent_id")
        child = d.get("to_task_id") or d.get("child_id")
        if not isinstance(parent, int) or not isinstance(child, int):
            continue
        if parent <= 0 or child <= 0 or parent == child:
            continue
        if parent in task_map and child in task_map:
            children[parent].add(child)

    return task_map, children


def _detect_cycle(children: dict[int, set[int]], roots: Iterable[int]) -> Optional[list[int]]:
    """DFS で cycle 検出. 見つかれば cycle path を返す."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = defaultdict(lambda: WHITE)

    def dfs(start: int) -> Optional[list[int]]:
        stack: list[tuple[int, list[int]]] = [(start, [start])]
        local_visited: dict[int, int] = {}
        while stack:
            u, path = stack[-1]
            if local_visited.get(u) == GRAY:
                # cycle detection done; pop
                stack.pop()
                local_visited[u] = BLACK
                color[u] = BLACK
                continue
            local_visited[u] = GRAY
            color[u] = GRAY
            for v in children.get(u, ()):
                if local_visited.get(v) == GRAY:
                    # cycle
                    if v in path:
                        idx = path.index(v)
                        return path[idx:] + [v]
                    return path + [v]
                if color.get(v, WHITE) == WHITE:
                    stack.append((v, path + [v]))
                    break
            else:
                stack.pop()
                local_visited[u] = BLACK
                color[u] = BLACK
        return None

    for r in roots:
        if color[r] == WHITE:
            cycle = dfs(r)
            if cycle:
                return cycle
    return None


def elevate_priorities(
    tasks: list[dict],
    dependencies: list[dict],
) -> ElevationReport:
    """親子昇格を計算する.

    Rule: 各 parent の priority は、その全 children の priority の max を下回らない.
    依存グラフを bottom-up に走査して priority を伝播させる.
    """
    _validate_inputs(tasks, dependencies)
    task_map, children = _build_graph(tasks, dependencies)
    if not task_map:
        return ElevationReport(total_tasks=0)

    # cycle 検出
    all_ids = list(task_map.keys())
    cycle = _detect_cycle(children, all_ids)
    if cycle:
        raise CycleDetectedError(
            f"cycle detected in dependency graph: {' -> '.join(str(x) for x in cycle)}"
        )

    # topological sort (parents 後に処理: bottom-up)
    in_degree: dict[int, int] = defaultdict(int)
    for parent, kids in children.items():
        for k in kids:
            in_degree[parent] += 0  # parent count tracked separately
    # parent_in_children: child → set of parents
    parents_of: dict[int, set[int]] = defaultdict(set)
    for parent, kids in children.items():
        for k in kids:
            parents_of[k].add(parent)
    # Process: child first (topological), then parent picks up max child priority.
    # 子 (in-degree of parents_of) = 0 から開始する逆 topo sort.
    # 簡易実装: iterative bottom-up (固定点まで反復).
    elevated: list[PriorityElevation] = []
    elevated_set: set[int] = set()
    MAX_ITER = 20
    for _ in range(MAX_ITER):
        changed = False
        for parent_id, kids in children.items():
            if not kids:
                continue
            parent = task_map[parent_id]
            child_max_order = max(
                PRIORITY_ORDER[task_map[k]["priority"]] for k in kids
            )
            parent_order = PRIORITY_ORDER[parent["priority"]]
            if child_max_order > parent_order:
                to = ORDER_TO_PRIORITY[child_max_order]
                if parent_id not in elevated_set:
                    elevated.append(PriorityElevation(
                        task_id=parent_id,
                        from_priority=parent["priority"],
                        to_priority=to,
                        reason=f"child has priority {to}",
                    ))
                    elevated_set.add(parent_id)
                else:
                    # 既に elevated 済 → 上書き
                    for e in elevated:
                        if e.task_id == parent_id:
                            e.from_priority = e.from_priority  # original 保持
                            e.to_priority = to
                            break
                parent["priority"] = to
                changed = True
        if not changed:
            break

    return ElevationReport(
        total_tasks=len(task_map),
        elevated=elevated,
        unchanged=len(task_map) - len(elevated_set),
    )
