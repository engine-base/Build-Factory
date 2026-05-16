#!/usr/bin/env python3
"""
v3 Phase 1 distributed-dev branch-package.json generator.

Generates 100 branch-package.json files (1 file per task) plus _index.json
under .claude/branches/, sourcing the task taxonomy embedded in this script.

Why this script exists
======================
Phase 1 tickets-group-*.json files are not yet committed; this script encodes
the agreed-on 100-task taxonomy (Group B backend / Group C UI / Group D drift)
so that the orchestrator has a single source of truth for branch metadata.
When the per-group tickets.json files land, regenerate by re-running this
script (idempotent overwrite).

Schema reference: skills/distributed-dev/references/profiles/build-factory.md
                  skills/distributed-dev/references/v3-core.md

Usage:
    python3 scripts/_generate_branch_packages.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / ".claude" / "branches"
DOC_DIR = ROOT / "docs" / "distributed-dev" / "2026-05-16_v3_phase1"
AUDIT_DIR_REL = "docs/audit/2026-05-16_v3"

PHASE_TICKETS = {
    "B": "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json",
    "C1": "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part1.json",
    "C2": "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part2.json",
    "D":  "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json",
}

FEATURES_PATH = "docs/functional-breakdown/2026-05-16_v3/features.json"
ENTITIES_PATH = "docs/functional-breakdown/2026-05-16_v3/entities.json"
SCREENS_PATH  = "docs/functional-breakdown/2026-05-16_v3/screens.json"

# ---------------------------------------------------------------------------
# Group B: 30 backend tasks (Wave assignment per v3-core backend-first)
# Wave plan:
#   W1 (21 backend tasks) — independent foundation-near backends
#   W2 (8 backend tasks)  — depend on W1 outputs
#   W3 (1 backend task)   — final integration backend (depends W2)
# ---------------------------------------------------------------------------
GROUP_B: list[dict[str, Any]] = [
    # W1: 21 tasks
    {"n": 1,  "title": "Auth backend: email/pwd + MFA + OAuth endpoints (F-001)",  "feature": "F-001", "estimate": 4, "wave": "W1"},
    {"n": 2,  "title": "Account/workspace/members service layer (F-004)",          "feature": "F-004", "estimate": 4, "wave": "W1"},
    {"n": 3,  "title": "Hearing pipeline service (F-005)",                          "feature": "F-005", "estimate": 4, "wave": "W1"},
    {"n": 4,  "title": "Mock auto-generation pipeline backend (F-005b)",            "feature": "F-005b","estimate": 4, "wave": "W1"},
    {"n": 5,  "title": "Functional/task decomposition + EARS AC service (F-006)",  "feature": "F-006", "estimate": 4, "wave": "W1"},
    {"n": 6,  "title": "Project/phase management backend (F-008)",                  "feature": "F-008", "estimate": 4, "wave": "W1"},
    {"n": 7,  "title": "Dependency graph + impact propagation service (F-009)",    "feature": "F-009", "estimate": 4, "wave": "W1"},
    {"n": 8,  "title": "Claude Code session spawner + swarm manager (F-010)",      "feature": "F-010", "estimate": 5, "wave": "W1"},
    {"n": 9,  "title": "Red-line list + auto-stop guardrail backend (F-012)",      "feature": "F-012", "estimate": 3, "wave": "W1"},
    {"n": 10, "title": "GitHub integration backend (PR + HTML diff) (F-013)",      "feature": "F-013", "estimate": 4, "wave": "W1"},
    {"n": 11, "title": "Obsidian one-way export adapter (F-016)",                   "feature": "F-016", "estimate": 3, "wave": "W1"},
    {"n": 12, "title": "Langfuse self-host integration (F-017)",                    "feature": "F-017", "estimate": 3, "wave": "W1"},
    {"n": 13, "title": "Audit log + notifications + backup service (F-018)",       "feature": "F-018", "estimate": 4, "wave": "W1"},
    {"n": 14, "title": "Existing bootstrap allocator backend (F-019)",              "feature": "F-019", "estimate": 3, "wave": "W1"},
    {"n": 15, "title": "LLM provider abstraction (LiteLLM router) (F-020)",        "feature": "F-020", "estimate": 4, "wave": "W1"},
    {"n": 16, "title": "Role custom_permissions + monitor role backend (F-021)",   "feature": "F-021", "estimate": 4, "wave": "W1"},
    {"n": 17, "title": "AI 3-tier personnel + namespace clone backend (F-022)",    "feature": "F-022", "estimate": 4, "wave": "W1"},
    {"n": 18, "title": "Constitution (project invariants) backend (F-026)",        "feature": "F-026", "estimate": 3, "wave": "W1"},
    {"n": 19, "title": "Email delivery service backend (F-028)",                    "feature": "F-028", "estimate": 3, "wave": "W1"},
    {"n": 20, "title": "API token management + extras backend (F-030)",            "feature": "F-030", "estimate": 3, "wave": "W1"},
    {"n": 21, "title": "Export pipeline (spec PDF / delivery report) backend (F-031)", "feature": "F-031", "estimate": 4, "wave": "W1"},
    # W2: 8 tasks (depend on W1 outputs)
    {"n": 22, "title": "MCP server (data flow) backend (F-010a)",                  "feature": "F-010a","estimate": 4, "wave": "W2", "deps_n": [8]},
    {"n": 23, "title": "Leader AI plan/gen/eval loop backend (F-011)",             "feature": "F-011", "estimate": 4, "wave": "W2", "deps_n": [8, 17]},
    {"n": 24, "title": "Slack notification (one-way) backend (F-014)",             "feature": "F-014", "estimate": 3, "wave": "W2", "deps_n": [13]},
    {"n": 25, "title": "HTML report generator (7 kinds) backend (F-015)",          "feature": "F-015", "estimate": 4, "wave": "W2", "deps_n": [21]},
    {"n": 26, "title": "Skill management (existing 96 skills archive) (F-002)",    "feature": "F-002", "estimate": 3, "wave": "W2", "deps_n": [17]},
    {"n": 27, "title": "AI BMAD + Agent Teams hybrid integration backend (F-003)", "feature": "F-003", "estimate": 5, "wave": "W2", "deps_n": [15, 17]},
    {"n": 28, "title": "Onboarding flow backend (F-027)",                           "feature": "F-027", "estimate": 3, "wave": "W2", "deps_n": [2]},
    {"n": 29, "title": "Global search (Cmd+K) backend (F-024)",                    "feature": "F-024", "estimate": 3, "wave": "W2", "deps_n": [2, 6]},
    # W3: 1 task (depends on W2)
    {"n": 30, "title": "Multi-view task management backend (F-007)",               "feature": "F-007", "estimate": 4, "wave": "W3", "deps_n": [5, 7, 30]},
]

# ---------------------------------------------------------------------------
# Group C: 55 UI tasks split into 2 waves (Wave 4 part1 = 25, Wave 5 part2 = 30).
# UI tasks reference a backend task in depends_on (Wave-internal backend-first).
# ---------------------------------------------------------------------------
GROUP_C_PART1: list[dict[str, Any]] = [
    # 25 UI tasks (W4), aligned to high-priority screens
    {"n": 1,  "title": "S-001 login screen UI (F-001)",                "screen": "S-001", "feature": "F-001", "estimate": 3, "be": 1},
    {"n": 2,  "title": "S-002 signup screen UI (F-001)",               "screen": "S-002", "feature": "F-001", "estimate": 3, "be": 1},
    {"n": 3,  "title": "S-003 password reset UI (F-001)",              "screen": "S-003", "feature": "F-001", "estimate": 2, "be": 1},
    {"n": 4,  "title": "S-004 MFA setup UI (F-001)",                   "screen": "S-004", "feature": "F-001", "estimate": 3, "be": 1},
    {"n": 5,  "title": "S-005 OAuth callback UI (F-001)",              "screen": "S-005", "feature": "F-001", "estimate": 2, "be": 1},
    {"n": 6,  "title": "S-006 10-project overview UI (F-004)",         "screen": "S-006", "feature": "F-004", "estimate": 4, "be": 2},
    {"n": 7,  "title": "S-007 account settings UI (F-023)",            "screen": "S-007", "feature": "F-023", "estimate": 3, "be": 2},
    {"n": 8,  "title": "S-008 member management UI (F-004)",           "screen": "S-008", "feature": "F-004", "estimate": 3, "be": 2},
    {"n": 9,  "title": "S-009 profile settings UI (F-023)",            "screen": "S-009", "feature": "F-023", "estimate": 3, "be": 2},
    {"n": 10, "title": "S-010 notifications inbox UI (F-018)",         "screen": "S-010", "feature": "F-018", "estimate": 3, "be": 13},
    {"n": 11, "title": "S-011 global search Cmd+K UI (F-024)",         "screen": "S-011", "feature": "F-024", "estimate": 3, "be": 29},
    {"n": 12, "title": "S-012 project dashboard UI (F-008)",           "screen": "S-012", "feature": "F-008", "estimate": 4, "be": 6},
    {"n": 13, "title": "S-013 project settings UI (F-008)",            "screen": "S-013", "feature": "F-008", "estimate": 3, "be": 6},
    {"n": 14, "title": "S-014 project members UI (F-004)",             "screen": "S-014", "feature": "F-004", "estimate": 3, "be": 2},
    {"n": 15, "title": "S-015 member invitation UI (F-004)",           "screen": "S-015", "feature": "F-004", "estimate": 3, "be": 2},
    {"n": 16, "title": "S-016 phase management UI (F-008)",            "screen": "S-016", "feature": "F-008", "estimate": 3, "be": 6},
    {"n": 17, "title": "S-017 dependency graph UI (F-009)",            "screen": "S-017", "feature": "F-009", "estimate": 4, "be": 7},
    {"n": 18, "title": "S-018 Constitution editor UI (F-026)",         "screen": "S-018", "feature": "F-026", "estimate": 3, "be": 18},
    {"n": 19, "title": "S-019 red-line settings UI (F-012)",           "screen": "S-019", "feature": "F-012", "estimate": 3, "be": 9},
    {"n": 20, "title": "S-020 hearing session UI (F-005)",             "screen": "S-020", "feature": "F-005", "estimate": 4, "be": 3},
    {"n": 21, "title": "S-021 spec HTML viewer UI (F-005)",            "screen": "S-021", "feature": "F-005", "estimate": 3, "be": 3},
    {"n": 22, "title": "S-022 functional breakdown UI (F-006)",        "screen": "S-022", "feature": "F-006", "estimate": 3, "be": 5},
    {"n": 23, "title": "S-023 mock editor UI (F-005b)",                "screen": "S-023", "feature": "F-005b","estimate": 4, "be": 4},
    {"n": 24, "title": "S-024 task list view UI (F-007)",              "screen": "S-024", "feature": "F-007", "estimate": 3, "be": 30},
    {"n": 25, "title": "S-025 Kanban accordion UI (F-007)",            "screen": "S-025", "feature": "F-007", "estimate": 4, "be": 30},
]

GROUP_C_PART2: list[dict[str, Any]] = [
    # 30 UI tasks (W5)
    {"n": 26, "title": "S-026 task DAG view UI (F-007)",               "screen": "S-026", "feature": "F-007", "estimate": 3, "be": 30},
    {"n": 27, "title": "S-027 acceptance-criteria editor UI (F-025)",  "screen": "S-027", "feature": "F-025", "estimate": 3, "be": 5},
    {"n": 28, "title": "S-028 swarm console UI (F-010)",               "screen": "S-028", "feature": "F-010", "estimate": 4, "be": 8},
    {"n": 29, "title": "S-029 session timeline UI (F-010)",            "screen": "S-029", "feature": "F-010", "estimate": 3, "be": 8},
    {"n": 30, "title": "S-030 cost dashboard UI (F-017)",              "screen": "S-030", "feature": "F-017", "estimate": 3, "be": 12},
    {"n": 31, "title": "S-031 Langfuse trace viewer UI (F-017)",       "screen": "S-031", "feature": "F-017", "estimate": 3, "be": 12},
    {"n": 32, "title": "S-032 audit log viewer UI (F-018)",            "screen": "S-032", "feature": "F-018", "estimate": 3, "be": 13},
    {"n": 33, "title": "S-033 backup/restore UI (F-018)",              "screen": "S-033", "feature": "F-018", "estimate": 3, "be": 13},
    {"n": 34, "title": "S-034 GitHub PR review UI (F-013)",            "screen": "S-034", "feature": "F-013", "estimate": 4, "be": 10},
    {"n": 35, "title": "S-035 HTML diff annotation UI (F-013)",        "screen": "S-035", "feature": "F-013", "estimate": 3, "be": 10},
    {"n": 36, "title": "S-036 Slack settings UI (F-014)",              "screen": "S-036", "feature": "F-014", "estimate": 2, "be": 24},
    {"n": 37, "title": "S-037 Obsidian export settings UI (F-016)",    "screen": "S-037", "feature": "F-016", "estimate": 2, "be": 11},
    {"n": 38, "title": "S-038 MCP server config UI (F-010a)",          "screen": "S-038", "feature": "F-010a","estimate": 3, "be": 22},
    {"n": 39, "title": "S-039 LLM provider switch UI (F-020)",         "screen": "S-039", "feature": "F-020", "estimate": 3, "be": 15},
    {"n": 40, "title": "S-040 role permissions UI (F-021)",            "screen": "S-040", "feature": "F-021", "estimate": 3, "be": 16},
    {"n": 41, "title": "S-041 AI personnel directory UI (F-022)",      "screen": "S-041", "feature": "F-022", "estimate": 3, "be": 17},
    {"n": 42, "title": "S-042 AI clone opt-in UI (F-022)",             "screen": "S-042", "feature": "F-022", "estimate": 3, "be": 17},
    {"n": 43, "title": "S-043 leader AI walkthrough UI (F-011)",       "screen": "S-043", "feature": "F-011", "estimate": 4, "be": 23},
    {"n": 44, "title": "S-044 onboarding welcome UI (F-027)",          "screen": "S-044", "feature": "F-027", "estimate": 2, "be": 28},
    {"n": 45, "title": "S-045 onboarding setup wizard UI (F-027)",     "screen": "S-045", "feature": "F-027", "estimate": 3, "be": 28},
    {"n": 46, "title": "S-046 AI introduction tour UI (F-027)",        "screen": "S-046", "feature": "F-027", "estimate": 3, "be": 28},
    {"n": 47, "title": "S-047 email template editor UI (F-028)",       "screen": "S-047", "feature": "F-028", "estimate": 3, "be": 19},
    {"n": 48, "title": "S-048 design system catalog UI (F-029)",       "screen": "S-048", "feature": "F-029", "estimate": 3, "be": None},
    {"n": 49, "title": "S-049 API token management UI (F-030)",        "screen": "S-049", "feature": "F-030", "estimate": 3, "be": 20},
    {"n": 50, "title": "S-050 export pipeline UI (F-031)",             "screen": "S-050", "feature": "F-031", "estimate": 3, "be": 21},
    {"n": 51, "title": "S-051 HTML report gallery UI (F-015)",         "screen": "S-051", "feature": "F-015", "estimate": 3, "be": 25},
    {"n": 52, "title": "S-052 confirm-delete dialog (F-032)",          "screen": "S-052", "feature": "F-032", "estimate": 2, "be": None},
    {"n": 53, "title": "S-053 unsaved-changes dialog (F-032)",         "screen": "S-053", "feature": "F-032", "estimate": 2, "be": None},
    {"n": 54, "title": "S-054 MFA challenge dialog (F-032)",           "screen": "S-054", "feature": "F-032", "estimate": 2, "be": 1},
    {"n": 55, "title": "S-055 system pages (404/500/403/maintenance) (F-033)", "screen": "S-055", "feature": "F-033", "estimate": 2, "be": None},
]

# ---------------------------------------------------------------------------
# Group D: 15 drift fix tasks (W6 — post-UI polish on entity / api / screen drifts)
# ---------------------------------------------------------------------------
GROUP_D: list[dict[str, Any]] = [
    {"n": 1,  "title": "Entity drift fix: account & workspace columns", "estimate": 2, "category": "entity-drift"},
    {"n": 2,  "title": "Entity drift fix: project & phase columns",     "estimate": 2, "category": "entity-drift"},
    {"n": 3,  "title": "Entity drift fix: task & dependency relations", "estimate": 2, "category": "entity-drift"},
    {"n": 4,  "title": "Entity drift fix: session & swarm tables",      "estimate": 2, "category": "entity-drift"},
    {"n": 5,  "title": "Entity drift fix: audit_log & notification",    "estimate": 2, "category": "entity-drift"},
    {"n": 6,  "title": "API drift fix: auth endpoints (F-001)",         "estimate": 2, "category": "api-drift"},
    {"n": 7,  "title": "API drift fix: project / phase endpoints",      "estimate": 2, "category": "api-drift"},
    {"n": 8,  "title": "API drift fix: task / DAG endpoints",           "estimate": 2, "category": "api-drift"},
    {"n": 9,  "title": "API drift fix: session / swarm endpoints",      "estimate": 2, "category": "api-drift"},
    {"n": 10, "title": "API drift fix: report / export endpoints",      "estimate": 2, "category": "api-drift"},
    {"n": 11, "title": "Screen drift fix: auth screens (S-001..005)",   "estimate": 2, "category": "screen-drift"},
    {"n": 12, "title": "Screen drift fix: workspace screens",           "estimate": 2, "category": "screen-drift"},
    {"n": 13, "title": "Screen drift fix: task / Kanban / DAG screens", "estimate": 2, "category": "screen-drift"},
    {"n": 14, "title": "Screen drift fix: AI / swarm screens",          "estimate": 2, "category": "screen-drift"},
    {"n": 15, "title": "Screen drift fix: ops / settings screens",      "estimate": 2, "category": "screen-drift"},
]

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
CI_GATES = ["lint-mock", "AC-validator", "RLS-coverage", "audit-md",
            "pytest-cov-70", "pyright", "tsc", "mock-impl-diff"]


def backend_boundary(feature_id: str, n: int) -> dict[str, list[str]]:
    """Build a Group B boundary keyed on FastAPI modular monolith path layout."""
    slug = feature_id.lower().replace("-", "_")
    return {
        "editable": [
            f"backend/app/routers/{slug}.py",
            f"backend/app/services/{slug}.py",
            f"backend/app/schemas/{slug}.py",
            f"backend/tests/routers/test_{slug}.py",
            f"backend/tests/services/test_{slug}.py",
        ],
        "shared_no_concurrent_edit": [
            "backend/app/main.py",
            "backend/app/router.py",
        ],
        "readonly": [
            "docs/functional-breakdown/2026-05-16_v3/",
            "docs/api-design/",
            "supabase/migrations/",
        ],
        "forbidden": [
            "frontend/",
            "scripts/",
            ".github/workflows/",
        ],
    }


def ui_boundary(screen_id: str, feature_id: str) -> dict[str, list[str]]:
    s = screen_id.lower()
    fslug = feature_id.lower().replace("-", "_")
    return {
        "editable": [
            f"frontend/app/{s}/page.tsx",
            f"frontend/app/{s}/layout.tsx",
            f"frontend/components/{fslug}/",
            f"frontend/__tests__/{s}.test.tsx",
        ],
        "shared_no_concurrent_edit": [
            "frontend/app/layout.tsx",
            "frontend/lib/api-client.ts",
        ],
        "readonly": [
            "docs/mocks/2026-05-09_v1/",
            "docs/functional-breakdown/2026-05-16_v3/",
            "backend/app/routers/",
        ],
        "forbidden": [
            "backend/",
            "scripts/",
            ".github/workflows/",
        ],
    }


def drift_boundary(category: str, n: int) -> dict[str, list[str]]:
    if category == "entity-drift":
        return {
            "editable": [
                f"supabase/migrations/2026_05_16_drift_{n:02d}.sql",
                "docs/functional-breakdown/2026-05-16_v3/entities.json",
                "backend/app/models/",
            ],
            "shared_no_concurrent_edit": ["docs/functional-breakdown/2026-05-16_v3/entities.json"],
            "readonly": ["docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md"],
            "forbidden": ["frontend/", ".github/workflows/"],
        }
    if category == "api-drift":
        return {
            "editable": [
                "docs/api-design/2026-05-16_v3/openapi.yaml",
                "backend/app/routers/",
                "backend/app/schemas/",
            ],
            "shared_no_concurrent_edit": ["docs/api-design/2026-05-16_v3/openapi.yaml"],
            "readonly": ["docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md"],
            "forbidden": ["frontend/", ".github/workflows/"],
        }
    return {  # screen-drift
        "editable": [
            "docs/functional-breakdown/2026-05-16_v3/screens.json",
            "docs/mocks/2026-05-09_v1/",
            "frontend/app/",
        ],
        "shared_no_concurrent_edit": ["docs/functional-breakdown/2026-05-16_v3/screens.json"],
        "readonly": ["docs/functional-breakdown/2026-05-16_v3/screen-drift-summary.md"],
        "forbidden": ["backend/", ".github/workflows/"],
    }


def make_package(task_id: str, title: str, branch: str, phase: str, wave: str,
                 group: str, layer: str, estimate: int,
                 boundary: dict[str, list[str]],
                 depends_on: list[str],
                 spec_links: list[str],
                 required_reads: list[str]) -> dict[str, Any]:
    return {
        "version": "v3",
        "task_id": task_id,
        "title": title,
        "branch": branch,
        "phase": phase,
        "wave": wave,
        "group": group,
        "deliverable_layer": layer,
        "estimate_hours": estimate,
        "session_meta": {
            "subagent_type": "general-purpose",
            "isolation": "worktree",
            "model_preference": "sonnet",
            "spec_links": spec_links,
            "required_reads": required_reads,
        },
        "work_package_boundary": boundary,
        "depends_on": depends_on,
        "audit_md_path": f"{AUDIT_DIR_REL}/{task_id}.md",
        "ci_gates": CI_GATES,
        "final_state": "pending",
        "failure_count": 0,
    }


def build_group_b() -> list[dict[str, Any]]:
    out = []
    for t in GROUP_B:
        task_id = f"T-V3-B-{t['n']:02d}"
        deps = [f"T-V3-B-{d:02d}" for d in t.get("deps_n", [])]
        boundary = backend_boundary(t["feature"], t["n"])
        spec_links = [
            f"{PHASE_TICKETS['B']}#{task_id}",
            f"{AUDIT_DIR_REL}/{task_id}.md",
            f"{FEATURES_PATH}#{t['feature']}",
        ]
        required_reads = [PHASE_TICKETS["B"], f"{AUDIT_DIR_REL}/{task_id}.md",
                          FEATURES_PATH, ENTITIES_PATH]
        out.append(make_package(
            task_id=task_id, title=t["title"], branch=f"claude/{task_id}",
            phase="Phase 1A", wave=t["wave"], group="B",
            layer="backend", estimate=t["estimate"], boundary=boundary,
            depends_on=deps, spec_links=spec_links, required_reads=required_reads,
        ))
    return out


def build_group_c() -> list[dict[str, Any]]:
    out = []
    for part, items, wave, ticket_key, phase in [
        ("part1", GROUP_C_PART1, "W4", "C1", "Phase 1B"),
        ("part2", GROUP_C_PART2, "W5", "C2", "Phase 1B"),
    ]:
        for t in items:
            task_id = f"T-V3-C-{t['n']:02d}"
            be_n = t.get("be")
            deps = [f"T-V3-B-{be_n:02d}"] if be_n else []
            boundary = ui_boundary(t["screen"], t["feature"])
            spec_links = [
                f"{PHASE_TICKETS[ticket_key]}#{task_id}",
                f"{AUDIT_DIR_REL}/{task_id}.md",
                f"{FEATURES_PATH}#{t['feature']}",
                f"{SCREENS_PATH}#{t['screen']}",
            ]
            required_reads = [PHASE_TICKETS[ticket_key],
                              f"{AUDIT_DIR_REL}/{task_id}.md",
                              FEATURES_PATH, SCREENS_PATH]
            out.append(make_package(
                task_id=task_id, title=t["title"], branch=f"claude/{task_id}",
                phase=phase, wave=wave, group="C",
                layer="ui", estimate=t["estimate"], boundary=boundary,
                depends_on=deps, spec_links=spec_links, required_reads=required_reads,
            ))
    return out


def build_group_d() -> list[dict[str, Any]]:
    out = []
    for t in GROUP_D:
        task_id = f"T-V3-D-{t['n']:02d}"
        boundary = drift_boundary(t["category"], t["n"])
        spec_links = [
            f"{PHASE_TICKETS['D']}#{task_id}",
            f"{AUDIT_DIR_REL}/{task_id}.md",
            f"docs/functional-breakdown/2026-05-16_v3/{t['category']}-summary.md",
        ]
        required_reads = [PHASE_TICKETS["D"], f"{AUDIT_DIR_REL}/{task_id}.md",
                          FEATURES_PATH, ENTITIES_PATH, SCREENS_PATH]
        out.append(make_package(
            task_id=task_id, title=t["title"], branch=f"claude/{task_id}",
            phase="Phase 1C", wave="W6", group="D",
            layer="polish", estimate=t["estimate"], boundary=boundary,
            depends_on=[], spec_links=spec_links, required_reads=required_reads,
        ))
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    packages = build_group_b() + build_group_c() + build_group_d()
    assert len(packages) == 100, f"Expected 100 tasks, got {len(packages)}"

    # Write per-task files
    for p in packages:
        path = OUT_DIR / f"{p['task_id']}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(p, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    # Aggregate index
    by_wave: dict[str, int] = {}
    by_group: dict[str, int] = {}
    for p in packages:
        by_wave[p["wave"]] = by_wave.get(p["wave"], 0) + 1
        by_group[p["group"]] = by_group.get(p["group"], 0) + 1

    index = {
        "version": "v3",
        "generated_at": "2026-05-16",
        "generator": "scripts/_generate_branch_packages.py",
        "total_tasks": len(packages),
        "by_wave": dict(sorted(by_wave.items())),
        "by_group": dict(sorted(by_group.items())),
        "tasks": [p["task_id"] for p in packages],
    }
    with (OUT_DIR / "_index.json").open("w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"Wrote {len(packages)} branch-package.json files + _index.json")
    print(f"  by_wave:  {index['by_wave']}")
    print(f"  by_group: {index['by_group']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
