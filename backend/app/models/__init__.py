"""backend.app.models — v3 entity model declarations.

T-V3-D-12 (skill_executions / phase_gates / user_knowledge_namespaces) と
T-V3-D-13 (components / screen_components) で同時に作成された package。

Build-Factory uses raw SQL via psycopg (no SQLAlchemy ORM Base — see
``backend/db/async_db.py``). The tickets' work_package_boundary lists
``backend/app/models/`` for model declarations, but the rest of the
repository uses Pydantic schemas under ``backend/schemas/`` as the
serialization / contract layer. To honour the spirit of the tickets
("new tables get formal model definitions") and the
work_package_boundary, this package ships:

  * T-V3-D-12: Pydantic ``BaseModel`` classes (skill_execution / phase_gate /
    user_knowledge_namespace) that mirror the column set of the 3 new
    tables created by
    ``supabase/migrations/20260516190000_critical_new_entities.sql``.
  * T-V3-D-13: pyright-strict module-level constants (component /
    screen_component) for the 2 new tables created by
    ``supabase/migrations/20260516200000_components_screen_components.sql``,
    each exposing ``TABLE_NAME`` / ``REQUIRED_COLUMNS`` / ``Row`` (TypedDict).

Deviation (documented in T-V3-D-12 / T-V3-D-13 audit MDs):
  - SQLAlchemy ``DeclarativeBase`` is **not** introduced. Adding one would
    diverge from the project-wide raw-SQL pattern and would be a much
    larger refactor than these drift tickets scope.
"""
from __future__ import annotations

# T-V3-D-13: component / screen_component modules
from . import component, screen_component

# T-V3-D-12: Pydantic models for critical NEW entities
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
    # T-V3-D-13
    "component",
    "screen_component",
    # T-V3-D-12
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
