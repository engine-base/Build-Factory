"""T-V3-B-27 / F-024: Account dashboard schemas.

EARS AC seed (T-V3-B-27 functional Tier):
  - EVENT-DRIVEN: GET /api/accounts/{id}/dashboard aggregates KPI across all
                  workspaces the caller belongs to within the account.

The account dashboard view is consumed by S-006 (account_dashboard) and shows a
per-workspace summary plus aggregate KPI across the account. Members only see
workspaces they belong to (workspace_members filter).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WorkspaceSummary(BaseModel):
    """One workspace card on the account dashboard."""

    id: int
    name: str
    status: Optional[str] = None
    role: Optional[str] = Field(None, description="caller's role within this workspace")
    progress: float = Field(0.0, ge=0.0, le=1.0)
    completed_tasks: int = 0
    running_sessions: int = 0
    monthly_cost_jpy: float = 0.0
    pending_approvals: int = 0


class AccountKPIAggregate(BaseModel):
    """KPI roll-up across all workspaces the caller can see in the account."""

    workspace_count: int = Field(0, description="Workspaces the caller belongs to")
    total_progress: float = Field(0.0, ge=0.0, le=1.0)
    completed_tasks: int = 0
    running_sessions: int = 0
    monthly_cost_jpy: float = 0.0
    pending_approvals: int = 0


class AccountDashboardResponse(BaseModel):
    """``GET /api/accounts/{id}/dashboard`` 2xx response."""

    account_id: int
    workspaces: list[WorkspaceSummary]
    kpi: AccountKPIAggregate
    computed_at: float = Field(..., description="unix timestamp of aggregation")
    duration_ms: int = Field(0, description="aggregation time in ms (perf debug)")
