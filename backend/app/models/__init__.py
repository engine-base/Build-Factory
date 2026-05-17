"""T-V3-D-12: Pydantic models for critical NEW entities.

Build-Factory uses raw SQL via psycopg (no SQLAlchemy ORM Base — see
``backend/db/async_db.py``). The ticket work_package_boundary lists
``backend/app/models/`` for SQLAlchemy models, but the rest of the
repository uses Pydantic schemas under ``backend/schemas/`` as the
serialization / contract layer. To honour the spirit of the ticket
("3 new tables get formal model definitions") and the
work_package_boundary, this package ships Pydantic ``BaseModel`` classes
that mirror the column set of the 3 new tables created by
``supabase/migrations/20260516190000_critical_new_entities.sql``.

Deviation from ticket (documented in
``docs/audit/2026-05-16_v3/T-V3-D-12.md`` Tier 2 / 補足項目):
  - SQLAlchemy ``DeclarativeBase`` is **not** introduced. Adding one would
    diverge from the project-wide raw-SQL pattern and would be a much
    larger refactor than this drift ticket scopes.
  - Instead, Pydantic ``BaseModel`` classes are provided so that future
    API endpoints have a typed request/response contract that matches the
    DB schema 1:1.
"""

from backend.app.models.skill_execution import (
    SkillExecution,
    SkillExecutionCreate,
    SkillExecutionStatus,
)
from backend.app.models.phase_gate import (
    PhaseGate,
    PhaseGateConditionType,
    PhaseGateCreate,
    PhaseGateStatus,
)
from backend.app.models.user_knowledge_namespace import (
    UserKnowledgeNamespace,
    UserKnowledgeNamespaceCreate,
    UserKnowledgeNamespaceScope,
)

__all__ = [
    "PhaseGate",
    "PhaseGateConditionType",
    "PhaseGateCreate",
    "PhaseGateStatus",
    "SkillExecution",
    "SkillExecutionCreate",
    "SkillExecutionStatus",
    "UserKnowledgeNamespace",
    "UserKnowledgeNamespaceCreate",
    "UserKnowledgeNamespaceScope",
]
