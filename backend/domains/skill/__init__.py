"""skill domain — public barrel (T-001-01b AC-2).

責務: skill registry / skill auto-detection.
"""
from __future__ import annotations

from services.skill_manager import (
    list_skills,
    get_skill,
    create_skill,
    sync_filesystem_to_db,
)
from services.skill_detector import (
    detect_skill,
    load_skill_md,
)

__all__ = [
    "list_skills",
    "get_skill",
    "create_skill",
    "sync_filesystem_to_db",
    "detect_skill",
    "load_skill_md",
]
