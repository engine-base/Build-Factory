"""T-V3-D-12 / E-009 SkillExecution Pydantic model.

Mirrors the column set of ``skill_executions`` in
``supabase/migrations/20260516190000_critical_new_entities.sql``.

Spec source: ``docs/functional-breakdown/2026-05-16_v3/entities.json``
entity ``E-009`` ``fields[]``.

AC reference (T-V3-D-12):
  AC-F2 EVENT-DRIVEN: When a skill is executed via /api/skills/{id}/test,
  the system shall record a row in skill_executions with workspace_id +
  skill_id + ai_employee_id + cost + tokens + status + langfuse_trace_id.

This Pydantic model serves as the typed contract for future
``/api/skills/{id}/test`` POST handlers and reporting queries.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

#: status enum mirrors CHECK constraint in
#: ``20260516190000_critical_new_entities.sql`` skill_executions.
SkillExecutionStatus = Literal["success", "failed", "cancelled"]


class SkillExecutionCreate(BaseModel):
    """Insert payload for a new skill_executions row.

    ``id``/``created_at``/``updated_at`` are server-assigned (BIGSERIAL +
    NOW() defaults). All other columns map 1:1 to the DB column.
    """

    skill_id: int = Field(..., description="FK -> skill_definitions.id")
    workspace_id: int = Field(..., description="FK -> workspaces.id")
    ai_employee_id: int | None = Field(
        default=None, description="FK -> ai_employees.id (nullable per E-009)"
    )
    user_id: str | None = Field(
        default=None,
        description="text user id (Supabase auth.uid()::text; nullable for "
        "service-role-initiated runs)",
        max_length=255,
    )
    session_id: int | None = Field(
        default=None, description="FK -> sessions.id (nullable per E-009)"
    )
    input: dict[str, Any] = Field(
        default_factory=dict, description="JSONB input payload (default empty obj)"
    )
    output: dict[str, Any] = Field(
        default_factory=dict, description="JSONB output payload (default empty obj)"
    )
    cost: Decimal = Field(
        default=Decimal("0"),
        description="NUMERIC(12,6) cost (USD or token-equivalent)",
    )
    tokens: int = Field(default=0, description="total tokens consumed")
    status: SkillExecutionStatus = Field(
        default="success", description="execution outcome"
    )
    langfuse_trace_id: str | None = Field(
        default=None,
        description="upstream langfuse trace id for observability",
        max_length=255,
    )


class SkillExecution(SkillExecutionCreate):
    """Full row representation including server-assigned columns."""

    id: int = Field(..., description="BIGSERIAL primary key")
    created_at: datetime = Field(..., description="server NOW() at insert")
    updated_at: datetime = Field(..., description="server NOW() at last update")

    model_config = {
        "from_attributes": True,  # support psycopg dict_row -> model conversion
    }
