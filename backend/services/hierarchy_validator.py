"""T-022-02: 階層循環参照 (cycle) 防止 validator.

supabase migration 20260512300000_cycle_prevention_triggers.sql で DB layer に
trigger は既設置 (bf_task_dependencies + ai_hierarchies 2 graph). 本サービスは
application 層で同じ判定を事前に行い、 cycle 検出時に {detail: {code, message}}
で 4xx を返すことで DB round-trip と RAISE EXCEPTION の cost を回避する.

graph model:
  - 有向エッジ集合 edges = [(from_node, to_node), ...]
  - 新 edge (a, b) を加えるとき、 既存 graph に b → ... → a の path があれば
    cycle 形成 → reject

公開 API:
  - detect_cycle_on_add(edges, new_from, new_to) -> Optional[list[int]]
      cycle path を返す (a → ... → b → a の順)、 cycle が無ければ None
  - validate_edge_addition(edges, new_from, new_to) -> None
      cycle 形成時に HierarchyError を raise
  - find_all_cycles(edges) -> list[list[int]]
      既存 graph 内の全 cycle を検出 (debug / integrity 用)
  - topological_order(edges, nodes) -> list[int]
      cycle が無ければ topological 順を返す、 あれば HierarchyError

設計:
  - node は int (DB の BIGSERIAL id 想定); 既存 trigger と一致
  - edges は list[tuple[int, int]] (重複 OK; set 化は呼び側責任)
  - 自己ループ (a, a) は cycle として reject
  - 入力は immutable に扱い、 永続化はしない (4xx 返却のみ)
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class HierarchyError(RuntimeError):
    pass


MAX_NODES = 100_000
MAX_EDGES = 1_000_000
MAX_DEPTH = 10_000


def _validate_node(node, *, field_name: str) -> int:
    if not isinstance(node, int) or isinstance(node, bool) or node <= 0:
        raise HierarchyError(f"{field_name} must be a positive int")
    return node


def _validate_edges(edges: Iterable) -> list[tuple[int, int]]:
    if not isinstance(edges, (list, tuple)):
        raise HierarchyError("edges must be a list")
    out: list[tuple[int, int]] = []
    for i, e in enumerate(edges):
        if not isinstance(e, (list, tuple)) or len(e) != 2:
            raise HierarchyError(f"edges[{i}] must be (from, to) pair")
        a = _validate_node(e[0], field_name=f"edges[{i}].from")
        b = _validate_node(e[1], field_name=f"edges[{i}].to")
        out.append((a, b))
    if len(out) > MAX_EDGES:
        raise HierarchyError(f"edges must be <= {MAX_EDGES}")
    return out


def _build_adjacency(edges: list[tuple[int, int]]) -> dict[int, list[int]]:
    adj: dict[int, list[int]] = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
    return adj


def _bfs_path(
    adj: dict[int, list[int]], start: int, target: int,
) -> Optional[list[int]]:
    """start → target への最短 path. なければ None."""
    if start == target:
        return [start]
    visited: dict[int, int] = {start: -1}  # node -> parent
    q: deque[int] = deque([start])
    steps = 0
    while q:
        steps += 1
        if steps > MAX_DEPTH:
            raise HierarchyError(f"BFS exceeded MAX_DEPTH={MAX_DEPTH}")
        n = q.popleft()
        for nx in adj.get(n, ()):
            if nx in visited:
                continue
            visited[nx] = n
            if nx == target:
                # reconstruct path
                path = [target]
                cur = n
                while cur != -1:
                    path.append(cur)
                    cur = visited.get(cur, -1)
                path.reverse()
                return path
            q.append(nx)
    return None


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def detect_cycle_on_add(
    edges: Iterable,
    new_from: int,
    new_to: int,
) -> Optional[list[int]]:
    """新 edge (new_from → new_to) を加えると cycle が形成されるか判定.

    Returns:
        cycle path (new_from → ... → new_to → new_from の順) or None.
        path の長さは 2 以上 (self-loop 含む).
    """
    new_from = _validate_node(new_from, field_name="new_from")
    new_to = _validate_node(new_to, field_name="new_to")
    e_list = _validate_edges(edges)
    if new_from == new_to:
        return [new_from, new_to]  # self-loop
    adj = _build_adjacency(e_list)
    # new_to から new_from へ既存 path があれば cycle 形成
    back_path = _bfs_path(adj, new_to, new_from)
    if back_path is None:
        return None
    # 完成する cycle: new_from → new_to → ... → new_from
    return [new_from] + back_path


def validate_edge_addition(
    edges: Iterable,
    new_from: int,
    new_to: int,
) -> None:
    cycle = detect_cycle_on_add(edges, new_from, new_to)
    if cycle is not None:
        path_str = " → ".join(str(n) for n in cycle)
        raise HierarchyError(
            f"cycle_detected: adding ({new_from}→{new_to}) forms cycle: {path_str}"
        )


def find_all_cycles(edges: Iterable) -> list[list[int]]:
    """既存 graph 内に存在する全 cycle を DFS で列挙.

    各 cycle は最初に到達した node から再到達した node までの path.
    self-loop も 1 cycle として返す.
    """
    e_list = _validate_edges(edges)
    adj = _build_adjacency(e_list)
    cycles: list[list[int]] = []
    visited: set[int] = set()
    on_stack: set[int] = set()
    parent: dict[int, int] = {}

    def _dfs(node: int) -> None:
        if len(on_stack) > MAX_DEPTH:
            raise HierarchyError(f"DFS exceeded MAX_DEPTH={MAX_DEPTH}")
        visited.add(node)
        on_stack.add(node)
        for nx in adj.get(node, ()):
            if nx == node:
                cycles.append([node, node])
                continue
            if nx in on_stack:
                # cycle: from nx back through parent chain to nx
                cycle_path = [nx, node]
                cur = node
                while parent.get(cur) is not None and parent[cur] != nx:
                    cur = parent[cur]
                    cycle_path.append(cur)
                cycle_path.append(nx)
                cycle_path.reverse()
                cycles.append(cycle_path)
                continue
            if nx in visited:
                continue
            parent[nx] = node
            _dfs(nx)
        on_stack.discard(node)

    nodes = set()
    for a, b in e_list:
        nodes.add(a)
        nodes.add(b)
    if len(nodes) > MAX_NODES:
        raise HierarchyError(f"node count must be <= {MAX_NODES}")
    for n in sorted(nodes):
        if n not in visited:
            parent[n] = None  # type: ignore
            _dfs(n)
    return cycles


def topological_order(
    edges: Iterable,
    nodes: Optional[Iterable[int]] = None,
) -> list[int]:
    """Kahn's algorithm. cycle があれば HierarchyError."""
    e_list = _validate_edges(edges)
    adj = _build_adjacency(e_list)
    in_degree: dict[int, int] = defaultdict(int)
    all_nodes: set[int] = set()
    for a, b in e_list:
        all_nodes.add(a)
        all_nodes.add(b)
        in_degree[b] += 1
        in_degree.setdefault(a, 0)
    if nodes is not None:
        for n in nodes:
            n = _validate_node(n, field_name="nodes[*]")
            all_nodes.add(n)
            in_degree.setdefault(n, 0)
    if len(all_nodes) > MAX_NODES:
        raise HierarchyError(f"node count must be <= {MAX_NODES}")
    q: deque[int] = deque(sorted(n for n in all_nodes if in_degree[n] == 0))
    order: list[int] = []
    while q:
        n = q.popleft()
        order.append(n)
        # deterministic: 子も sorted で
        for nx in sorted(adj.get(n, ())):
            in_degree[nx] -= 1
            if in_degree[nx] == 0:
                q.append(nx)
    if len(order) < len(all_nodes):
        remaining = sorted(all_nodes - set(order))
        raise HierarchyError(
            f"cycle_detected: cannot topo-sort; "
            f"remaining nodes in cycle: {remaining[:10]}..."
        )
    return order
