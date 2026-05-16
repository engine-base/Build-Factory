"""T-V3-B-27 / F-024: Global search schemas.

EARS AC seed (T-V3-B-27 functional Tier):
  - EVENT-DRIVEN: GET /api/search returns hits ranked by FTS + vector similarity.
  - UNWANTED   : q > 500 chars or empty -> 422.
  - UNWANTED   : > 60 req/min/user -> 429.

This module declares the Pydantic schemas used by ``backend/routers/search.py``.
We keep response shapes aligned with openapi.yaml#/api/search (SearchHit + total +
categories). The schemas are intentionally permissive on the input side so the
router can produce structured field-level error maps (422) when invariants fail.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# F-024 contract: tasks | artifacts | knowledge | audit
SearchCategory = Literal["tasks", "artifacts", "knowledge", "audit"]


class SearchHit(BaseModel):
    """Single ranked search hit returned from ``GET /api/search``.

    The ``score`` field is the combined FTS + vector similarity score in [0, 1].
    Higher is better. ``category`` matches the OpenAPI categories enum and lets
    the frontend group results in the Cmd+K modal.
    """

    id: str = Field(..., description="Stable id of the underlying row")
    category: SearchCategory = Field(..., description="tasks|artifacts|knowledge|audit")
    title: str = Field(..., description="Display title (label) of the hit")
    snippet: Optional[str] = Field(None, description="Short context snippet")
    score: float = Field(..., ge=0.0, le=1.0, description="Combined FTS + vector score")
    workspace_id: Optional[int] = Field(
        None, description="Workspace owning the hit (for RLS filtering)",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """``GET /api/search`` 2xx response — must include hits/total/categories."""

    hits: list[SearchHit]
    total: int
    categories: dict[str, int] = Field(
        default_factory=dict,
        description="Counts per category (tasks/artifacts/knowledge/audit)",
    )
    query: str = Field(..., description="Normalized query echoed back")
    rate_limit_remaining: Optional[int] = Field(
        None, description="Remaining requests in current minute window (debug)",
    )
