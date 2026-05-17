"""T-V3-D-12 / E-010 UserKnowledgeNamespace Pydantic model.

Mirrors the column set of ``user_knowledge_namespaces`` in
``supabase/migrations/20260516190000_critical_new_entities.sql``.

Spec source: ``docs/functional-breakdown/2026-05-16_v3/entities.json``
entity ``E-010`` ``fields[]``.

AC reference (T-V3-D-12):
  AC-F4 EVENT-DRIVEN: When a user knowledge namespace is created, the
  system shall enforce uniqueness on (user_id, namespace_id) and shall
  record scope (private/account/workspace).

Used by Mem0/Obsidian/Constitution namespace isolation (T-AI-MEM-04
provider-adapter) to keep per-user knowledge namespaces separated even
when the same logical namespace_id is shared across providers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

#: scope enum mirrors CHECK constraint (private / account / workspace).
#: Note: T-V3-D-12 extends spec's (private/shared) to
#: (private/account/workspace) for richer namespace isolation semantics —
#: rationale documented in migration header + audit MD.
UserKnowledgeNamespaceScope = Literal["private", "account", "workspace"]


class UserKnowledgeNamespaceCreate(BaseModel):
    """Insert payload for a new user_knowledge_namespaces row."""

    user_id: str = Field(
        ..., description="owner user id (text; auth.uid()::text)", max_length=255
    )
    namespace_id: str = Field(
        ...,
        description="logical namespace id (e.g. mem0/obsidian/constitution key)",
        max_length=255,
    )
    scope: UserKnowledgeNamespaceScope = Field(
        default="private", description="namespace visibility scope"
    )


class UserKnowledgeNamespace(UserKnowledgeNamespaceCreate):
    """Full row representation including server-assigned columns.

    Enforces UNIQUE (user_id, namespace_id) at the DB layer (see
    ``uq_user_knowledge_namespaces_user_namespace`` constraint).
    """

    id: int = Field(..., description="BIGSERIAL primary key")
    created_at: datetime = Field(..., description="server NOW() at insert")
    updated_at: datetime = Field(..., description="server NOW() at last update")

    model_config = {"from_attributes": True}
