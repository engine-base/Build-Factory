"""T-V3-B-11: workspace-scoped task ops (bulk-play / bulk-archive / export.csv / dag).

F-007 多 view タスク管理 のうち、bulk operation と DAG / CSV export を担当する.

公開 API:
  bulk_play(workspace_id, task_ids, *, actor_user_id, max_parallel=...) -> dict
    └─ dependency 順に session を spawn. max_parallel 超過分は queued でカウント.
  bulk_archive(workspace_id, task_ids, *, actor_user_id) -> dict
    └─ workspace 配下の task を soft-archive (status='cancelled').
  export_csv(workspace_id, *, actor_user_id) -> str
    └─ workspace 配下 task を CSV (text) で返す.
  get_dag(workspace_id, *, actor_user_id) -> dict
    └─ {"nodes": [TaskNode], "edges": [DAGEdge]} を返す.
  verify_workspace_access(workspace_id, user_id) -> str (role)
    └─ workspace 存在 + membership を検証. Not found → WorkspaceNotFound, non-member → Forbidden.

AC マッピング (F-007 ears_ac_seed / 派生):
  AC-F1 EVENT-DRIVEN  : bulk_play は depends_on の topological sort 順に session を起動.
  AC-F2 UNWANTED      : 起動数が max_parallel 超 → 残りを queued count として返す (status 200).
  AC-F3/F7/F10/F12    : 各 endpoint は 2xx + features.json#F-007 contract に従う.
  AC-F4/F8/F11/F13    : actor_user_id 未指定 → Unauthorized.
  AC-F5/F9            : task_ids 不正 → ValidationError (caller が 422).
  AC-F6               : 10/min/workspace の rate limit (in-memory token bucket).

接続先:
  - bf_tasks (E-014 Task) workspace_id は bf_projects 経由
  - bf_task_dependencies (E-015 TaskDependency)
  - sessions (E-024 Session): bulk_play で INSERT
  - workspace_members: actor が member であることを検証
"""
from __future__ import annotations

import csv
import io
import time
import uuid
from collections import defaultdict, deque
from typing import Optional, Sequence

from db import async_db as aiosqlite
from db.queries import DB_PATH


# ──────────────────────────────────────────────────────────────────────────
# Exceptions (router でそれぞれ 4xx に map)
# ──────────────────────────────────────────────────────────────────────────


class Unauthorized(Exception):
    """missing or invalid auth token (actor_user_id 未指定)."""


class Forbidden(Exception):
    """workspace_member ではない."""


class WorkspaceNotFound(Exception):
    """workspaces.id が存在しない."""


class ValidationFailed(Exception):
    """request body / query が schema 違反."""


class RateLimited(Exception):
    """10/min/workspace 超過."""


# ──────────────────────────────────────────────────────────────────────────
# Rate limiter (in-memory token bucket per workspace_id)
#
# F-007 AC-F6: POST /api/workspaces/{id}/tasks/bulk-play は 10/min/workspace.
# 単 process 用. 横スケール時は redis に置換予定.
# ──────────────────────────────────────────────────────────────────────────


_RL_WINDOW_SEC = 60
_RL_BULK_PLAY_LIMIT = 10
_rl_bucket: dict[int, deque[float]] = defaultdict(deque)


def _rl_check(workspace_id: int, *, limit: int = _RL_BULK_PLAY_LIMIT,
              window: int = _RL_WINDOW_SEC) -> None:
    """token bucket: window 秒以内に limit 回まで許可."""
    now = time.monotonic()
    bucket = _rl_bucket[workspace_id]
    while bucket and (now - bucket[0]) > window:
        bucket.popleft()
    if len(bucket) >= limit:
        raise RateLimited(
            f"bulk_play rate limit exceeded: {limit}/{window}s on workspace {workspace_id}"
        )
    bucket.append(now)


def _rl_reset(workspace_id: Optional[int] = None) -> None:
    """test 用: 全 or 特定 workspace の bucket をクリア."""
    if workspace_id is None:
        _rl_bucket.clear()
    else:
        _rl_bucket.pop(workspace_id, None)


# ──────────────────────────────────────────────────────────────────────────
# Auth helper
# ──────────────────────────────────────────────────────────────────────────


async def verify_workspace_access(
    workspace_id: int,
    user_id: Optional[str],
) -> str:
    """workspace 存在 + user が member であることを検証して role を返す.

    Raises:
      Unauthorized: user_id が None / 空文字
      WorkspaceNotFound: workspaces.id 不在
      Forbidden: user が workspace_members に無い
    """
    if not user_id or not user_id.strip():
        raise Unauthorized("actor_user_id is required")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        ws_rows = await db.execute_fetchall(
            "SELECT id FROM workspaces WHERE id=?", (workspace_id,),
        )
        if not ws_rows:
            raise WorkspaceNotFound(f"workspace {workspace_id} not found")

        mem_rows = await db.execute_fetchall(
            "SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=? LIMIT 1",
            (workspace_id, user_id.strip()),
        )
        if not mem_rows:
            raise Forbidden(
                f"user {user_id} is not a member of workspace {workspace_id}"
            )
    return dict(mem_rows[0])["role"]


_WRITE_ROLES = {"owner", "ws_admin", "contributor"}


def _require_role(role: str, allowed: set[str]) -> None:
    if role not in allowed:
        raise Forbidden(f"role {role!r} not in {sorted(allowed)}")


# ──────────────────────────────────────────────────────────────────────────
# Validation helpers (caller / pydantic で前段検証する想定; 二重防御)
# ──────────────────────────────────────────────────────────────────────────


def _validate_task_ids(task_ids: Sequence[int]) -> list[int]:
    if not isinstance(task_ids, (list, tuple)):
        raise ValidationFailed("task_ids must be a list")
    if not task_ids:
        raise ValidationFailed("task_ids must be non-empty")
    out: list[int] = []
    for v in task_ids:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValidationFailed(f"task_id must be int, got {type(v).__name__}")
        if v <= 0:
            raise ValidationFailed(f"task_id must be > 0, got {v}")
        out.append(v)
    # de-dup (順序保持)
    seen: set[int] = set()
    dedup: list[int] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            dedup.append(v)
    return dedup


# ──────────────────────────────────────────────────────────────────────────
# bulk_play: dependency 順に session を起動
#
# bf_tasks.project_id → bf_projects.workspace_id でフィルタ.
# topological sort: 依存元 (depends_on_task_id) を先に並べる.
# max_parallel 超過分は queued count に積む.
# ──────────────────────────────────────────────────────────────────────────


async def bulk_play(
    workspace_id: int,
    task_ids: Sequence[int],
    *,
    actor_user_id: Optional[str],
    max_parallel: int = 5,
) -> dict:
    """選択 task を dependency 順に play. max_parallel 超過は queued.

    Returns: {"session_ids": [uuid str], "queued": int}
    """
    role = await verify_workspace_access(workspace_id, actor_user_id)
    _require_role(role, _WRITE_ROLES)
    _rl_check(workspace_id)

    ids = _validate_task_ids(task_ids)

    # workspace 配下 task のみ抽出
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(ids))
        task_rows = await db.execute_fetchall(
            f"""SELECT t.id, t.title, t.status
                  FROM bf_tasks t
                  JOIN bf_projects p ON p.id = t.project_id
                 WHERE p.workspace_id = ? AND t.id IN ({placeholders})""",
            (workspace_id, *ids),
        )
        valid_ids = {dict(r)["id"] for r in task_rows}
        if not valid_ids:
            return {"session_ids": [], "queued": 0}

        dep_rows = await db.execute_fetchall(
            f"""SELECT task_id, depends_on_task_id FROM bf_task_dependencies
                 WHERE task_id IN ({placeholders}) OR depends_on_task_id IN ({placeholders})""",
            (*ids, *ids),
        )

    ordered_ids = _topo_sort(list(valid_ids),
                             [(dict(r)["depends_on_task_id"], dict(r)["task_id"])
                              for r in dep_rows])

    # 起動: max_parallel まで session INSERT, 残りは queued count
    session_ids: list[str] = []
    queued = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for idx, tid in enumerate(ordered_ids):
            if idx >= max_parallel:
                queued += 1
                continue
            sdk_sid = f"play-{uuid.uuid4()}"
            await db.execute(
                """INSERT INTO sessions
                    (sdk_session_id, workspace_id, bf_task_id, prompt,
                     status, created_by)
                   VALUES (?, ?, ?, ?, 'running', ?)""",
                (sdk_sid, workspace_id, tid,
                 f"bulk_play task_id={tid}", actor_user_id),
            )
            session_ids.append(sdk_sid)
        await db.commit()

    return {"session_ids": session_ids, "queued": queued}


def _topo_sort(node_ids: list[int],
               edges: list[tuple[int, int]]) -> list[int]:
    """Kahn topo sort. edges = [(from_dep, to_task)]; from_dep を先に並べる.
    node_ids に含まれない端は無視. cycle / 残余は末尾に積む.
    """
    node_set = set(node_ids)
    indeg: dict[int, int] = {n: 0 for n in node_ids}
    adj: dict[int, list[int]] = {n: [] for n in node_ids}
    for src, dst in edges:
        if src in node_set and dst in node_set and src != dst:
            adj[src].append(dst)
            indeg[dst] += 1

    queue = deque([n for n in node_ids if indeg[n] == 0])
    out: list[int] = []
    while queue:
        n = queue.popleft()
        out.append(n)
        for nxt in adj[n]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)

    # cycle 残余は末尾
    for n in node_ids:
        if n not in out:
            out.append(n)
    return out


# ──────────────────────────────────────────────────────────────────────────
# bulk_archive: 選択 task を cancelled (= archive 相当) に
# ──────────────────────────────────────────────────────────────────────────


async def bulk_archive(
    workspace_id: int,
    task_ids: Sequence[int],
    *,
    actor_user_id: Optional[str],
) -> dict:
    """workspace_admin 以上が選択 task を archive (status='cancelled')."""
    role = await verify_workspace_access(workspace_id, actor_user_id)
    _require_role(role, {"owner", "ws_admin"})
    ids = _validate_task_ids(task_ids)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(ids))
        cur = await db.execute(
            f"""UPDATE bf_tasks SET status='cancelled', updated_at=CURRENT_TIMESTAMP
                  WHERE id IN ({placeholders})
                    AND project_id IN (SELECT id FROM bf_projects WHERE workspace_id=?)""",
            (*ids, workspace_id),
        )
        await db.commit()
        archived = cur.rowcount or 0

    return {"archived_count": archived}


# ──────────────────────────────────────────────────────────────────────────
# export.csv: workspace 配下 task を CSV (text)
# ──────────────────────────────────────────────────────────────────────────


CSV_HEADER = ("task_id", "title", "status", "label", "sprint", "assigned_to",
              "estimated_hours", "actual_hours")


async def export_csv(
    workspace_id: int,
    *,
    actor_user_id: Optional[str],
) -> str:
    """workspace 配下 bf_tasks を CSV text として返す (RFC 4180 + utf-8)."""
    await verify_workspace_access(workspace_id, actor_user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT t.task_id, t.title, t.status, t.label, t.sprint,
                      t.assigned_to, t.estimated_hours, t.actual_hours
                 FROM bf_tasks t
                 JOIN bf_projects p ON p.id = t.project_id
                WHERE p.workspace_id = ?
                ORDER BY t.id ASC""",
            (workspace_id,),
        )

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for r in rows:
        d = dict(r)
        writer.writerow([d.get(k) if d.get(k) is not None else "" for k in CSV_HEADER])
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────
# get_dag: workspace の task と dep を node/edge で返す
# ──────────────────────────────────────────────────────────────────────────


async def get_dag(
    workspace_id: int,
    *,
    actor_user_id: Optional[str],
) -> dict:
    """workspace 配下の task / dep を DAG 形式で返す.

    Returns: {"nodes": [{id, title, status, wave?}],
              "edges": [{from_task_id, to_task_id, type}]}
    """
    await verify_workspace_access(workspace_id, actor_user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        task_rows = await db.execute_fetchall(
            """SELECT t.id, t.title, t.status, t.sprint
                 FROM bf_tasks t
                 JOIN bf_projects p ON p.id = t.project_id
                WHERE p.workspace_id = ?
                ORDER BY t.id ASC""",
            (workspace_id,),
        )
        task_ids = [dict(r)["id"] for r in task_rows]
        if task_ids:
            placeholders = ",".join("?" * len(task_ids))
            dep_rows = await db.execute_fetchall(
                f"""SELECT task_id, depends_on_task_id, dep_type
                      FROM bf_task_dependencies
                     WHERE task_id IN ({placeholders})""",
                tuple(task_ids),
            )
        else:
            dep_rows = []

    nodes = [
        {
            "id": str(d["id"]),
            "title": d["title"],
            "status": d["status"],
            "wave": _sprint_to_wave(d.get("sprint")),
        }
        for d in (dict(r) for r in task_rows)
    ]
    edges = [
        {
            "from_task_id": str(d["depends_on_task_id"]),
            "to_task_id": str(d["task_id"]),
            "type": d["dep_type"] or "blocks",
        }
        for d in (dict(r) for r in dep_rows)
    ]
    return {"nodes": nodes, "edges": edges}


def _sprint_to_wave(sprint: Optional[str]) -> Optional[int]:
    """'S0' / 'S1' 等 → int. 不正値は None."""
    if not sprint or not isinstance(sprint, str):
        return None
    s = sprint.strip().upper()
    if s.startswith("S") and s[1:].isdigit():
        return int(s[1:])
    if s.isdigit():
        return int(s)
    return None
