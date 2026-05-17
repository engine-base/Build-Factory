"""backend.app — v3 entity model containers (added in T-V3-D-12/D-13).

This package hosts thin, pyright-strict typed declarations for entities that
were formalized during Phase 1 末尾 drift fix Wave 4 (Group D).  The Build-
Factory backend executes raw SQL via ``backend.db.async_db`` (psycopg async)
and does **not** rely on a SQLAlchemy declarative mapper for runtime queries;
the modules under ``backend.app.models`` therefore expose:

    - ``TABLE_NAME`` constants (single source of truth for the impl table)
    - ``REQUIRED_COLUMNS`` tuples (spec ↔ impl drift guard)
    - ``Row`` ``TypedDict`` shapes for row materialization
    - ``__all__`` for explicit symbol export

These declarations are imported by integration tests
(``backend/tests/integration/test_components_screen_components.py`` etc.) to
verify drift between the spec (``docs/functional-breakdown/2026-05-16_v3/
entities.json``) and the impl migration
(``supabase/migrations/20260516200000_components_screen_components.sql``).
"""
from __future__ import annotations

__all__ = ["models"]
