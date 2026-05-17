"""T-V3-D-12 / E-013 PhaseGate Pydantic model.

Mirrors the column set of ``phase_gates`` in
``supabase/migrations/20260516190000_critical_new_entities.sql``.

Spec source: ``docs/functional-breakdown/2026-05-16_v3/entities.json``
entity ``E-013`` ``fields[]``.

AC reference (T-V3-D-12):
  AC-F3 EVENT-DRIVEN: When a phase gate is checked and passes, the system
  shall record passed_at + passed_by in phase_gates.

``workspace_id`` is non-normalized (denormalized) from ``bf_phases ->
bf_projects -> workspace`` to enable direct RLS evaluation via
``bf_can_access_workspace(workspace_id)``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

#: condition_type enum mirrors CHECK constraint
#: (task_completion / review_approval / manual).
PhaseGateConditionType = Literal["task_completion", "review_approval", "manual"]

#: status enum mirrors CHECK constraint (pending / passed / failed).
PhaseGateStatus = Literal["pending", "passed", "failed"]


class PhaseGateCreate(BaseModel):
    """Insert payload for a new phase_gates row."""

    phase_id: int = Field(..., description="FK -> bf_phases.id")
    workspace_id: int = Field(
        ...,
        description="FK -> workspaces.id (denormalized from phase->project->workspace)",
    )
    name: str = Field(..., description="human-readable gate name", max_length=255)
    condition_type: PhaseGateConditionType = Field(
        ..., description="gate condition type"
    )
    user_id: str | None = Field(
        default=None,
        description="text user id who created the gate (optional)",
        max_length=255,
    )
    criteria: dict[str, Any] = Field(
        default_factory=dict, description="JSONB gate criteria (default empty obj)"
    )
    status: PhaseGateStatus = Field(default="pending", description="gate status")
    passed_at: datetime | None = Field(
        default=None, description="set when status transitions to 'passed'"
    )
    passed_by: str | None = Field(
        default=None,
        description="text user id who marked gate as passed",
        max_length=255,
    )


class PhaseGate(PhaseGateCreate):
    """Full row representation including server-assigned columns."""

    id: int = Field(..., description="BIGSERIAL primary key")
    created_at: datetime = Field(..., description="server NOW() at insert")
    updated_at: datetime = Field(..., description="server NOW() at last update")

    model_config = {"from_attributes": True}
