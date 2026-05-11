"""T-003-03 / F-003: AI 社員 (persona) 継承 guideline endpoint.

Endpoint:
  GET /api/personas/{employee_id}/guideline?workspace_id=N&actor_user_id=...

T-003-03 AC:
  AC-1 UBIQUITOUS    : parent → child 継承を解決する endpoint 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内に success or {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit (CLAUDE.md §5.3, RLS は DB 側 schema で担保)
  AC-4 UNWANTED      : invalid input / 不明 employee / 循環 hierarchy は 4xx +
                       {detail:{code,message}} かつ persistent state mutate しない
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from services.guideline_inheritance import (
    CycleDetectedError,
    EmployeeNotFoundError,
    GuidelineInheritanceError,
    PersonaSnapshot,
    resolve_guideline,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/personas", tags=["personas"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("personas-guideline audit emit failed: %s -- %s", event_type, e)


# ──────────────────────────────────────────────────────────────────────────
# Default DB-backed loaders (SQLite互換 async_db 経由)
# tests では module 内 _default_hierarchy_loader / _default_persona_loader を差し替える
# ──────────────────────────────────────────────────────────────────────────


async def _default_hierarchy_loader(employee_id: int) -> Optional[int]:
    """child_id=employee_id の parent_id を返す (見つからなければ None = root)."""
    try:
        from db import async_db as aiosqlite
        DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT parent_id FROM ai_hierarchies "
                "WHERE child_id=? AND relation_type IN ('reports_to','mentors') "
                "ORDER BY id ASC LIMIT 1",
                (employee_id,),
            )
            if not rows:
                return None
            return dict(rows[0]).get("parent_id")
    except Exception:
        return None


async def _default_persona_loader(employee_id: int) -> Optional[PersonaSnapshot]:
    """ai_employees + ai_personas を join してスナップショットを作る."""
    try:
        from db import async_db as aiosqlite
        DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT e.id AS employee_id, e.employee_key, "
                "       p.persona_key, p.persona_name, p.personality, "
                "       p.tone_style, p.specialty "
                "FROM ai_employees e LEFT JOIN ai_personas p ON p.id = e.persona_id "
                "WHERE e.id=? AND e.is_active=TRUE",
                (employee_id,),
            )
            if not rows:
                return None
            r = dict(rows[0])
            return PersonaSnapshot(
                employee_id=r["employee_id"],
                employee_key=r.get("employee_key") or f"emp-{employee_id}",
                persona_key=r.get("persona_key"),
                persona_name=r.get("persona_name"),
                personality=r.get("personality"),
                tone_style=r.get("tone_style"),
                specialty=r.get("specialty"),
                guideline_text=_build_guideline_text(r),
            )
    except Exception:
        return None


def _build_guideline_text(row: dict) -> str:
    """ai_personas の各 column から guideline 本文を組み立てる."""
    parts = []
    if row.get("personality"):
        parts.append(f"性格: {row['personality']}")
    if row.get("tone_style"):
        parts.append(f"口調: {row['tone_style']}")
    if row.get("specialty"):
        parts.append(f"専門: {row['specialty']}")
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2: endpoint
# ──────────────────────────────────────────────────────────────────────────


@router.get("/{employee_id}/guideline")
async def get_inherited_guideline(
    employee_id: int,
    workspace_id: Optional[int] = Query(None),
    actor_user_id: Optional[str] = Query(None),
    max_depth: int = Query(10, ge=1, le=20),
) -> dict[str, Any]:
    """employee_id の継承 guideline を返す."""
    # AC-4: input validation
    if employee_id <= 0:
        raise _error("personas.invalid_employee_id", "employee_id must be > 0")
    if workspace_id is not None and workspace_id <= 0:
        raise _error("personas.invalid_workspace_id", "workspace_id must be > 0 when provided")
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error("personas.unauthorized", "actor_user_id must not be empty when provided",
                     status_code=401)
    if max_depth <= 0 or max_depth > 20:
        raise _error("personas.invalid_max_depth", "max_depth must be 1..20")

    try:
        result = await resolve_guideline(
            employee_id,
            hierarchy_loader=_default_hierarchy_loader,
            persona_loader=_default_persona_loader,
            max_depth=max_depth,
        )
    except EmployeeNotFoundError as e:
        raise _error("personas.employee_not_found", str(e), status_code=404)
    except CycleDetectedError as e:
        raise _error("personas.cycle_detected", str(e), status_code=409)
    except GuidelineInheritanceError as e:
        raise _error("personas.resolve_failed", str(e), status_code=400)

    await _audit(
        "personas.guideline.resolved",
        user_id=actor_user_id,
        detail={
            "employee_id": employee_id,
            "workspace_id": workspace_id,
            "chain_depth": result["chain_depth"],
        },
    )
    return result
