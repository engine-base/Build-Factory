"""backend.app.models — v3 entity model declarations.

Each module exposes:

    - ``TABLE_NAME``: ``str``         single source of truth for the impl table
    - ``REQUIRED_COLUMNS``: ``tuple`` spec ↔ impl drift guard
    - ``Row``: ``TypedDict``           row materialization shape
    - ``__all__``: explicit exports
"""
from __future__ import annotations

from . import component, screen_component

__all__ = ["component", "screen_component"]
