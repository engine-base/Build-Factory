"""T-008-01: phases (bf_phases) CRUD service.

architecture-v1 §4 / T-001-04 で定義された bf_phases テーブルへの CRUD ラッパ.

公開 API:
  list_phases(project_id) -> list[dict]
  get_phase(phase_id) -> dict | None
  create_phase(project_id, phase_no, name, ...) -> dict
  update_phase(phase_id, **fields) -> dict
  delete_phase(phase_id) -> bool   (実態は status='skipped' soft-delete)
  start_phase(phase_id) -> dict    (status='in_progress' + started_at)
  complete_phase(phase_id) -> dict (status='completed' + completed_at)

AC:
  - phase_no は 1-10 (CHECK 制約と整合)
  - status enum: pending / in_progress / completed / blocked / skipped
  - 同 project 内で phase_no 一意 (uq_bf_phase)
"""
from __future__ import annotations

import json
from typing import Optional

from db import async_db as aiosqlite
from db.queries import DB_PATH


VALID_PHASE_STATUSES = ("pending", "in_progress", "completed", "blocked", "skipped")
PHASE_NO_MIN = 1
PHASE_NO_MAX = 10


class InvalidPhaseInput(ValueError):
    """phase_no / status / project_id の入力 invalid."""


class PhaseNotFound(ValueError):
    """指定 phase_id が DB に存在しない."""


def _row(r) -> dict:
    return dict(r) if r else {}


def _validate_phase_no(phase_no: int) -> None:
    if not isinstance(phase_no, int) or phase_no < PHASE_NO_MIN or phase_no > PHASE_NO_MAX:
        raise InvalidPhaseInput(
            f"phase_no must be {PHASE_NO_MIN}-{PHASE_NO_MAX}, got {phase_no!r}"
        )


def _validate_status(status: str) -> None:
    if status not in VALID_PHASE_STATUSES:
        raise InvalidPhaseInput(
            f"status must be one of {VALID_PHASE_STATUSES}, got {status!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────


async def list_phases(project_id: int) -> list[dict]:
    """project の全 phase を phase_no 順で返す."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM bf_phases WHERE project_id = ? ORDER BY phase_no ASC",
            (project_id,),
        )
    return [_row(r) for r in rows]


async def get_phase(phase_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bf_phases WHERE id = ?", (phase_id,))
        row = await cur.fetchone()
    return _row(row) if row else None


async def create_phase(
    *,
    project_id: int,
    phase_no: int,
    name: str,
    artifacts_dir: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """新規 phase を作成. phase_no が duplicate なら ValueError."""
    _validate_phase_no(phase_no)
    if not name or not name.strip():
        raise InvalidPhaseInput("name must not be empty")
    name = name.strip()

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """INSERT INTO bf_phases (project_id, phase_no, name, artifacts_dir, notes)
                   VALUES (?, ?, ?, ?, ?) RETURNING id""",
                (project_id, phase_no, name, artifacts_dir, notes),
            )
            row = await cur.fetchone()
            phase_id = dict(row)["id"] if row else None
            await db.commit()
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "uq_bf_phase" in msg or "duplicate" in msg:
            raise InvalidPhaseInput(
                f"phase_no {phase_no} already exists for project {project_id}"
            ) from e
        raise
    if phase_id is None:
        raise PhaseNotFound("INSERT returned no id")
    return await get_phase(phase_id) or {}


async def update_phase(phase_id: int, **fields) -> dict:
    """phase の更新. unknown phase_id → PhaseNotFound. invalid → InvalidPhaseInput."""
    existing = await get_phase(phase_id)
    if existing is None:
        raise PhaseNotFound(f"phase not found: {phase_id}")

    if "phase_no" in fields:
        _validate_phase_no(fields["phase_no"])
    if "status" in fields:
        _validate_status(fields["status"])
    if "name" in fields and not (fields["name"] or "").strip():
        raise InvalidPhaseInput("name must not be empty")

    cols, vals = [], []
    for k in ("phase_no", "name", "status", "artifacts_dir", "notes"):
        if k in fields:
            cols.append(f"{k} = ?")
            vals.append(fields[k])
    if not cols:
        return existing
    cols.append("updated_at = datetime('now','localtime')")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE bf_phases SET {', '.join(cols)} WHERE id = ?",
                [*vals, phase_id],
            )
            await db.commit()
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "uq_bf_phase" in msg:
            raise InvalidPhaseInput(
                f"phase_no {fields.get('phase_no')} conflicts with existing"
            ) from e
        raise
    return await get_phase(phase_id) or {}


async def start_phase(phase_id: int) -> dict:
    """phase を in_progress に + started_at を NOW でセット."""
    existing = await get_phase(phase_id)
    if existing is None:
        raise PhaseNotFound(f"phase not found: {phase_id}")
    if existing.get("status") == "in_progress":
        return existing  # idempotent
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE bf_phases
                  SET status = 'in_progress',
                      started_at = COALESCE(started_at, datetime('now','localtime')),
                      updated_at = datetime('now','localtime')
                WHERE id = ?""",
            (phase_id,),
        )
        await db.commit()
    return await get_phase(phase_id) or {}


async def complete_phase(phase_id: int) -> dict:
    """phase を completed + completed_at セット."""
    existing = await get_phase(phase_id)
    if existing is None:
        raise PhaseNotFound(f"phase not found: {phase_id}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE bf_phases
                  SET status = 'completed',
                      completed_at = datetime('now','localtime'),
                      updated_at = datetime('now','localtime')
                WHERE id = ?""",
            (phase_id,),
        )
        await db.commit()
    return await get_phase(phase_id) or {}


async def delete_phase(phase_id: int) -> bool:
    """phase を soft-delete (status='skipped'). 既存 dependency を壊さない."""
    existing = await get_phase(phase_id)
    if existing is None:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """UPDATE bf_phases
                  SET status = 'skipped',
                      updated_at = datetime('now','localtime')
                WHERE id = ?""",
            (phase_id,),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-13 / F-008: workspace-scoped phase helpers
#
# F-008 spec (docs/functional-breakdown/2026-05-16_v3/features.json) uses
# workspace-scoped URLs (/api/workspaces/{id}/phases) but the impl table
# bf_phases keys phases via project_id. These helpers transparently resolve
# a workspace -> its primary bf_project and operate on phases scoped to it.
#
# policies: max_phases_per_workspace = 10 (F-008 policies)
# ──────────────────────────────────────────────────────────────────────────


MAX_PHASES_PER_WORKSPACE = 10


class WorkspaceProjectResolutionError(RuntimeError):
    """workspace に紐付く bf_project が解決できない."""


async def resolve_project_id_for_workspace(workspace_id: int) -> int:
    """workspace に紐付く primary bf_project の id を返す.

    bf_project が存在しなければ自動作成する (auto-bootstrap).
    workspace 自体が存在しなければ WorkspaceProjectResolutionError.
    """
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise WorkspaceProjectResolutionError(
            f"workspace_id must be int > 0, got {workspace_id!r}"
        )
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM bf_projects WHERE workspace_id = ? ORDER BY id ASC LIMIT 1",
            (workspace_id,),
        )
        row = await cur.fetchone()
        if row:
            return int(dict(row)["id"])
        # auto-bootstrap: workspace 名から bf_project を作成
        ws_cur = await db.execute(
            "SELECT name FROM workspaces WHERE id = ?", (workspace_id,),
        )
        ws_row = await ws_cur.fetchone()
        if not ws_row:
            raise WorkspaceProjectResolutionError(
                f"workspace not found: {workspace_id}"
            )
        ws_name = dict(ws_row)["name"]
        slug = f"ws-{workspace_id}"
        ins = await db.execute(
            """INSERT INTO bf_projects (workspace_id, name, slug, status)
               VALUES (?, ?, ?, 'planning') RETURNING id""",
            (workspace_id, ws_name, slug),
        )
        ins_row = await ins.fetchone()
        await db.commit()
        if not ins_row:
            raise WorkspaceProjectResolutionError(
                f"failed to create bf_project for workspace {workspace_id}"
            )
        return int(dict(ins_row)["id"])


async def list_phases_for_workspace(workspace_id: int) -> list[dict]:
    """workspace に紐付く phases を phase_no 順で返す.

    bf_project が無い場合は空配列を返す (auto-bootstrap は行わない).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM bf_projects WHERE workspace_id = ? ORDER BY id ASC LIMIT 1",
            (workspace_id,),
        )
        proj_row = await cur.fetchone()
        if not proj_row:
            return []
        project_id = int(dict(proj_row)["id"])
        rows = await db.execute_fetchall(
            "SELECT * FROM bf_phases WHERE project_id = ? ORDER BY phase_no ASC",
            (project_id,),
        )
    return [_row(r) for r in rows]


async def count_phases_for_workspace(workspace_id: int) -> int:
    """workspace に紐付く非 skipped phase 数を返す (max_phases_per_workspace チェック用)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM bf_projects WHERE workspace_id = ? ORDER BY id ASC LIMIT 1",
            (workspace_id,),
        )
        row = await cur.fetchone()
        if not row:
            return 0
        project_id = int(dict(row)["id"])
        c2 = await db.execute(
            "SELECT COUNT(*) AS n FROM bf_phases "
            "WHERE project_id = ? AND status != 'skipped'",
            (project_id,),
        )
        crow = await c2.fetchone()
        return int(dict(crow)["n"]) if crow else 0


async def create_phase_for_workspace(
    *,
    workspace_id: int,
    name: str,
    gate_conditions: Optional[list[str]] = None,
) -> dict:
    """F-008 POST /api/workspaces/{id}/phases.

    auto-bootstrap で bf_project を解決し、次の phase_no を割り当てる.
    max_phases_per_workspace=10 を超える場合は InvalidPhaseInput(max_phases_reached).
    """
    if not isinstance(name, str) or not name.strip():
        raise InvalidPhaseInput("name must not be empty")
    name = name.strip()
    if len(name) > 200:
        raise InvalidPhaseInput("name must be <= 200 chars")

    existing = await count_phases_for_workspace(workspace_id)
    if existing >= MAX_PHASES_PER_WORKSPACE:
        raise InvalidPhaseInput(
            f"max_phases_reached: workspace {workspace_id} already has "
            f"{existing} phases (limit={MAX_PHASES_PER_WORKSPACE})"
        )

    project_id = await resolve_project_id_for_workspace(workspace_id)

    # 次の phase_no = (現在の最大 phase_no) + 1, range 1..10
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT COALESCE(MAX(phase_no), 0) AS mx FROM bf_phases WHERE project_id = ?",
            (project_id,),
        )
        row = await cur.fetchone()
        next_no = (int(dict(row)["mx"]) if row else 0) + 1
    if next_no > PHASE_NO_MAX:
        raise InvalidPhaseInput(
            f"max_phases_reached: next phase_no={next_no} exceeds {PHASE_NO_MAX}"
        )

    # gate_conditions は notes に JSON で永続化 (F-008 spec で別 column 未定義)
    notes_payload: Optional[str] = None
    if gate_conditions is not None:
        if not isinstance(gate_conditions, list) or any(
            not isinstance(c, str) for c in gate_conditions
        ):
            raise InvalidPhaseInput("gate_conditions must be a list of strings")
        notes_payload = json.dumps(
            {"gate_conditions": list(gate_conditions)}, ensure_ascii=False,
        )

    return await create_phase(
        project_id=project_id,
        phase_no=next_no,
        name=name,
        notes=notes_payload,
    )


def _extract_gate_conditions(phase: dict) -> list[str]:
    """phase.notes に格納された JSON から gate_conditions を取り出す."""
    notes = phase.get("notes") if isinstance(phase, dict) else None
    if not notes:
        return []
    try:
        data = json.loads(notes)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        gc = data.get("gate_conditions")
        if isinstance(gc, list):
            return [str(x) for x in gc]
    return []


async def get_phase_for_workspace(workspace_id: int, phase_id: int) -> Optional[dict]:
    """phase_id が workspace に紐付くか検証してから返す.

    workspace 外の phase_id は None (router で 404 に変換).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT p.* FROM bf_phases p
                 JOIN bf_projects pr ON pr.id = p.project_id
                WHERE p.id = ? AND pr.workspace_id = ?""",
            (phase_id, workspace_id),
        )
        row = await cur.fetchone()
    return _row(row) if row else None


async def evaluate_gate_and_unlock_next(
    *,
    workspace_id: int,
    phase_id: int,
    force: bool = False,
) -> dict:
    """F-008 POST /api/workspaces/{id}/phases/{phase_id}/gate.

    Returns:
        {"unlocked_phase_id": <next phase id or None>,
         "evaluated_at": <isoformat timestamp>,
         "passed": True}
    Raises:
        PhaseNotFound: phase_id が workspace に紐付かない
        InvalidPhaseInput(code="gate_conditions_not_met", failing=...) :
            未達 (force=False のとき)
    """
    from datetime import datetime as _dt

    phase = await get_phase_for_workspace(workspace_id, phase_id)
    if not phase:
        raise PhaseNotFound(
            f"phase not found in workspace {workspace_id}: {phase_id}"
        )

    failing: list[str] = []
    if not force:
        # gate 条件: (a) phase.status が 'completed' であること (b) gate_conditions
        # 全件は MVP では「completion 済」とみなす. すべての文字列条件は
        # phase.notes に保存されている前提で、現状は status のみで判定する.
        if phase.get("status") != "completed":
            failing.append(
                f"phase_not_completed: current status={phase.get('status')!r}"
            )
        # gate_conditions のテキスト評価 (MVP: 空でない場合 status='completed' でのみ満了)
        gc = _extract_gate_conditions(phase)
        if gc and phase.get("status") != "completed":
            for c in gc:
                failing.append(f"condition_not_met: {c}")

    if failing:
        err = InvalidPhaseInput(
            f"gate_conditions_not_met: {failing}"
        )
        # 失敗条件を attribute で渡す (router が 409 detail に詰める)
        err.failing_conditions = failing  # type: ignore[attr-defined]
        raise err

    # 次の phase を探して unlock (status を pending -> in_progress)
    project_id = int(phase["project_id"])
    next_phase: Optional[dict] = None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bf_phases WHERE project_id = ? AND phase_no > ? "
            "AND status != 'skipped' ORDER BY phase_no ASC LIMIT 1",
            (project_id, int(phase["phase_no"])),
        )
        nrow = await cur.fetchone()
        if nrow:
            next_phase = _row(nrow)

    unlocked_id: Optional[int] = None
    if next_phase is not None and next_phase.get("status") in (
        "pending", "blocked",
    ):
        unlocked = await start_phase(int(next_phase["id"]))
        unlocked_id = int(unlocked["id"]) if unlocked else None
    elif next_phase is not None:
        unlocked_id = int(next_phase["id"])  # 既に進行中 → idempotent

    return {
        "unlocked_phase_id": unlocked_id,
        "evaluated_at": _dt.utcnow().isoformat() + "Z",
        "passed": True,
    }