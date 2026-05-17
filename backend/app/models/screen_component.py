"""backend.app.models.screen_component — v3 entity E-024 ScreenComponent.

Spec : ``docs/functional-breakdown/2026-05-16_v3/entities.json#E-024``
Impl : ``supabase/migrations/20260516200000_components_screen_components.sql``
            (table ``screen_components``)
Owner: T-V3-D-13 (Group D / Wave 4 / 2026-05-17)

ADR-017 (E-022 Screen → E-058 BFMock merge):

    ``screen_components.screen_id`` is declared ``BIGINT NOT NULL`` and
    references ``bf_mocks(id)`` (not a separate ``screens`` table).  The v1
    spec Screen entity (E-022) has been merged into E-058 BFMock; this module
    pins the FK target so that drift-check tests can verify the migration
    references the correct table.

Acceptance-criteria anchors (T-V3-D-13):

    - ``AC-F3`` EVENT-DRIVEN — ``FK_TARGETS`` enumerates the two FK targets
      (``bf_mocks`` for ``screen_id``, ``components`` for ``component_id``).
    - ``AC-F1`` UBIQUITOUS — the join table existence is verified via
      ``TABLE_NAME``.
"""
from __future__ import annotations

from typing import Final, TypedDict

#: ENTITY id (v3 entities.json)
ENTITY_ID: Final[str] = "E-024"

#: Spec table_name and impl table_name (must match; see lint check #17)
TABLE_NAME: Final[str] = "screen_components"

#: Spec ↔ impl required column list.  Drift-check target.
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "workspace_id",
    "screen_id",
    "component_id",
    "slot",
    "position",
    "layout",
    "created_at",
    "updated_at",
)

#: FK targets per AC-F3.  ``screen_id`` is intentionally a FK to ``bf_mocks``
#: per ADR-017 (E-022 Screen entity is merged into E-058 BFMock).
FK_TARGETS: Final[dict[str, str]] = {
    "screen_id": "bf_mocks",
    "component_id": "components",
}

#: AC-F3 implicit uniqueness — same component cannot appear twice in the
#: same screen-slot.  ``slot`` may be NULL but PostgreSQL UNIQUE treats two
#: NULLs as distinct, so multiple "default slot" pairs are allowed; explicit
#: deduplication is the application layer's responsibility.
UNIQUE_KEY: Final[tuple[str, ...]] = ("screen_id", "component_id", "slot")

#: Required RLS policies (canonical names).
RLS_POLICY_NAMES: Final[tuple[str, ...]] = (
    "screen_components_service_role_all",
    "screen_components_workspace_member_select",
)


class Row(TypedDict, total=False):
    """Row materialization shape for the ``screen_components`` table."""

    id: int
    workspace_id: int
    screen_id: int  # FK → bf_mocks(id) per ADR-017
    component_id: int  # FK → components(id)
    slot: str | None
    position: int
    layout: dict[str, object]
    created_at: str
    updated_at: str


__all__ = [
    "ENTITY_ID",
    "TABLE_NAME",
    "REQUIRED_COLUMNS",
    "FK_TARGETS",
    "UNIQUE_KEY",
    "RLS_POLICY_NAMES",
    "Row",
]
