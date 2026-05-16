"""T-V3-B-09 / F-005b: Pydantic schemas for Components catalog + usage.

OpenAPI 仕様 (docs/api-design/2026-05-16_v3/openapi.yaml) との contract に
1:1 対応する response model 群.

スコープ entities: E-012 Component / E-013 ScreenComponent.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ComponentItem(BaseModel):
    """Component (E-012)."""

    id: str = Field(..., description="component logical id (e.g. button-primary)")
    workspace_id: int = Field(..., ge=1)
    name: str = ""
    type: str = ""
    description: str = ""


class ComponentListResponse(BaseModel):
    """GET /api/workspaces/{id}/components response."""

    components: list[ComponentItem]


class ComponentUsageItem(BaseModel):
    """ComponentUsage (E-013) — where this component is used."""

    screen_id: str
    screen_name: str = ""
    instance_count: int = Field(..., ge=0)


class ComponentUsageResponse(BaseModel):
    """GET /api/workspaces/{id}/components/{component_id}/usage response."""

    usages: list[ComponentUsageItem]
