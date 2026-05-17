"""backend.app.models.component — v3 entity E-023 Component.

Spec : ``docs/functional-breakdown/2026-05-16_v3/entities.json#E-023``
Impl : ``supabase/migrations/20260516200000_components_screen_components.sql``
            (table ``components``)
Owner: T-V3-D-13 (Group D / Wave 4 / 2026-05-17)

The Build-Factory backend executes raw SQL through ``backend.db.async_db``
(psycopg async) — there is no SQLAlchemy declarative mapper.  This module
therefore exposes constant declarations + a row TypedDict so that integration
tests can drift-check the spec and impl in a strict-typed way.

Acceptance-criteria anchors (T-V3-D-13):

    - ``AC-F2`` EVENT-DRIVEN — ``REQUIRED_COLUMNS`` includes the
      ``(workspace_id, name, version)`` triple; the spec UNIQUE constraint is
      declared in the migration.
    - ``AC-F4`` UNWANTED — ``REPLACED_BY_E058 = None`` for E-023 (this entity
      is *not* deprecated; only E-022 Screen is merged into E-058 BFMock per
      ADR-017).
"""
from __future__ import annotations

from typing import Final, TypedDict

#: ENTITY id (v3 entities.json)
ENTITY_ID: Final[str] = "E-023"

#: Spec table_name and impl table_name (must match; see lint check #17)
TABLE_NAME: Final[str] = "components"

#: Spec ↔ impl required column list.  Drift-check target.
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "workspace_id",
    "name",
    "version",
    "type",
    "description",
    "mock_artifact_id",
    "metadata",
    "created_at",
    "updated_at",
    "deleted_at",
)

#: AC-F2: uniqueness key declared as ``UNIQUE (workspace_id, name, version)``.
UNIQUE_KEY: Final[tuple[str, ...]] = ("workspace_id", "name", "version")

#: type enum CHECK constraint values (kept in sync with migration).
TYPE_ENUM_VALUES: Final[tuple[str, ...]] = (
    "button",
    "input",
    "select",
    "card",
    "modal",
    "table",
    "nav",
    "sidebar",
    "header",
    "footer",
    "form",
    "badge",
    "tooltip",
    "tabs",
    "accordion",
    "toast",
    "avatar",
    "chart",
    "editor",
    "unknown",
)

#: Required RLS policies (canonical names).
RLS_POLICY_NAMES: Final[tuple[str, ...]] = (
    "components_service_role_all",
    "components_workspace_member_select",
)

#: E-023 is not replaced/merged.  ADR-017 only deprecates E-022 Screen.
REPLACED_BY_E058: Final[bool] = False


class Row(TypedDict, total=False):
    """Row materialization shape for the ``components`` table.

    Fields marked optional (``total=False``) tolerate ``SELECT`` projections
    that omit some columns (e.g. when joining with ``screen_components``).
    """

    id: int
    workspace_id: int
    name: str
    version: str
    type: str
    description: str | None
    mock_artifact_id: int | None
    metadata: dict[str, object]
    created_at: str
    updated_at: str
    deleted_at: str | None


__all__ = [
    "ENTITY_ID",
    "TABLE_NAME",
    "REQUIRED_COLUMNS",
    "UNIQUE_KEY",
    "TYPE_ENUM_VALUES",
    "RLS_POLICY_NAMES",
    "REPLACED_BY_E058",
    "Row",
]
