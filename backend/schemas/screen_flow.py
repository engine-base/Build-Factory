"""T-V3-B-09 / F-005b: Pydantic schemas for screen-flow graph.

OpenAPI 仕様 (docs/api-design/2026-05-16_v3/openapi.yaml) との contract に
1:1 対応する response model 群.

スコープ entities: E-011 Screen.
"""
from __future__ import annotations

from pydantic import BaseModel


class ScreenFlowNode(BaseModel):
    """Node of the screen-flow graph (one screen)."""

    screen_id: str
    name: str = ""
    kind: str = "screen"


class ScreenFlowEdge(BaseModel):
    """Edge of the screen-flow graph (S → S transition)."""

    from_screen_id: str
    to_screen_id: str
    trigger: str = ""


class ScreenFlowResponse(BaseModel):
    """GET /api/workspaces/{id}/screen-flow response."""

    nodes: list[ScreenFlowNode]
    edges: list[ScreenFlowEdge]
