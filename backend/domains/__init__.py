"""T-001-01b: backend modular monolith — 13 bounded-context domain registry.

各 domain は `backend/domains/<name>/__init__.py` を public barrel として使う.
domain 外からは barrel 経由でのみ access 可能 (bypass は lint で検出).

13 domains:
  auth, workspace, project, task, memory, llm, skill, knowledge,
  artifact, review, observability, billing, integration
"""
from __future__ import annotations

# 13 bounded-context domain names (AC-1)
DOMAIN_NAMES: tuple[str, ...] = (
    "auth",
    "workspace",
    "project",
    "task",
    "memory",
    "llm",
    "skill",
    "knowledge",
    "artifact",
    "review",
    "observability",
    "billing",
    "integration",
)

assert len(DOMAIN_NAMES) == 13, "T-001-01b AC-1: exactly 13 domains required"
