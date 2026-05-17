#!/usr/bin/env python3
"""Group C-3 generator — Phase 1.0-fix Wave 0 task B.

Decomposes the 55 screen-missing items (from screen-drift-summary.md) into
formal tickets with 3-tier EARS AC. Produces:

  docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c3-screen-missing.json

Inputs:
  - docs/functional-breakdown/2026-05-16_v3/screen-drift-summary.md (the 55 list)
  - docs/functional-breakdown/2026-05-16_v3/screens.json (canonical screen spec)
  - docs/functional-breakdown/2026-05-16_v3/features.json (feature defs)
  - docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json
        (for cross-ref of backend B tickets used in depends_on)

Schema: matches tickets-group-c-ui-part2.json (v3 3-tier AC).
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCREENS = json.loads((ROOT / "docs/functional-breakdown/2026-05-16_v3/screens.json").read_text())["items"]
FEATURES = json.loads((ROOT / "docs/functional-breakdown/2026-05-16_v3/features.json").read_text())["items"]
GROUP_B = json.loads((ROOT / "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json").read_text())["tasks"]

SCRMAP = {s["id"]: s for s in SCREENS}
FMAP = {f["id"]: f for f in FEATURES}

AUDIT_DIR_REL = "docs/audit/2026-05-16_v3"
TICKETS_FILE_REL = "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c3-screen-missing.json"

# Order of 55 missing screens from screen-drift-summary.md.
# (screen_id, route_segment_relative_to_app)
# route_segment is a path under `frontend/src/app/...` ending in `page.tsx`.
# Empty string means top-level page.tsx (S-012 is the workspace dashboard).
MISSING_SCREENS = [
    # account category
    ("S-006", "settings/account-dashboard"),
    ("S-008", "settings/members"),
    ("S-010", "inbox"),
    ("S-011", "search"),
    # ai_management
    ("S-037", "ai-employees/[id]"),
    # auth (5)
    ("S-001", "(auth)/login"),
    ("S-002", "(auth)/signup"),
    ("S-003", "(auth)/password-reset"),
    ("S-004", "(auth)/mfa-setup"),
    ("S-005", "(auth)/oauth-callback"),
    # client (2)
    ("S-042", "client/workspace"),
    ("S-043", "client/comment"),
    # dialog (5) — modal components rendered inside layout, but expose a route for storybook/testing
    ("S-051", "dialogs/confirm-delete"),
    ("S-052", "dialogs/unsaved-changes"),
    ("S-053", "dialogs/mfa-challenge"),
    ("S-054", "dialogs/session-expired"),
    ("S-055", "dialogs/danger-zone"),
    # email (5) — server-rendered email templates exposed at /email/*
    ("S-056", "(email)/signup-verify"),
    ("S-057", "(email)/password-reset"),
    ("S-058", "(email)/invitation"),
    ("S-059", "(email)/task-notification"),
    ("S-060", "(email)/weekly-summary"),
    # export (2)
    ("S-061", "export/spec-pdf"),
    ("S-062", "export/delivery-report"),
    # extras (2)
    ("S-063", "search/results"),
    ("S-064", "settings/api-tokens"),
    # moat (5)
    ("S-016", "workspaces/[id]/phases"),
    ("S-017", "workspaces/[id]/dependency-graph"),
    ("S-018", "constitution"),
    ("S-019", "settings/red-line"),
    ("S-034", "approvals/red-line"),
    # onboarding (3) — already (onboarding) route group exists; canonical slugs
    ("S-048", "(onboarding)/welcome"),
    ("S-049", "(onboarding)/workspace-setup"),
    ("S-050", "(onboarding)/ai-introduction"),
    # review (2)
    ("S-033", "approvals/pr-review/[id]"),
    ("S-035", "approvals/delivery/[id]"),
    # spec (7)
    ("S-020", "workspaces/[id]/hearing"),
    ("S-021", "workspaces/[id]/requirements"),
    ("S-022", "workspaces/[id]/spec"),
    ("S-023", "workspaces/[id]/mocks"),
    ("S-024", "workspaces/[id]/components"),
    ("S-025", "workspaces/[id]/flow-map"),
    ("S-026", "workspaces/[id]/design-editor"),
    # system (4)
    ("S-044", "(system)/not-found"),
    ("S-045", "(system)/server-error"),
    ("S-046", "(system)/forbidden"),
    ("S-047", "(system)/maintenance"),
    # task (4)
    ("S-027", "workspaces/[id]/kanban"),
    ("S-029", "workspaces/[id]/dag"),
    ("S-030", "tasks/[id]"),
    ("S-032", "workspaces/[id]/swarm/[session_id]"),
    # workspace (4)
    ("S-012", "workspaces/[id]"),
    ("S-013", "workspaces/[id]/settings"),
    ("S-014", "workspaces/[id]/members"),
    ("S-015", "workspaces/[id]/invite"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_screen_to_b_map() -> dict[str, list[str]]:
    mp: dict[str, list[str]] = {}
    for t in GROUP_B:
        bid = t["id"]
        for sid_raw in t.get("screen_ids", []):
            sid = sid_raw.split(" ")[0].strip() if " " in sid_raw else sid_raw
            mp.setdefault(sid, []).append(bid)
    return mp


SCREEN_TO_B = build_screen_to_b_map()


def slug_for(screen_id: str, screen_name: str) -> str:
    """A safe slug fragment: lower S-XXX + screen_name with '-'.

    Example: S-016 phase_management -> s-016-phase-management
    """
    return f"{screen_id.lower()}-{screen_name.replace('_', '-')}"


def page_paths(screen_id: str, screen_name: str, route_seg: str) -> dict:
    """Compute file paths for vertical slice (Next.js App Router under src/)."""
    slug = slug_for(screen_id, screen_name)
    # api / hook module name: prefer the bare screen_name with '-'
    mod_name = screen_name.replace("_", "-")
    # Use PascalCase-like for hook (use-<screen_name>.ts is the convention)
    return {
        "page": f"frontend/src/app/{route_seg}/page.tsx",
        "api": f"frontend/src/api/{mod_name}.ts",
        "hook": f"frontend/src/hooks/use-{mod_name}.ts",
        "test": f"frontend/tests/screens/{screen_id}-{screen_name}.spec.tsx",
        "mock_ref": f"docs/mocks/2026-05-15_v3/{screen_id_to_dir(screen_id)}/{screen_id}-{mod_name}.html",
        "slug": slug,
    }


def screen_id_to_dir(screen_id: str) -> str:
    """Map S-XXX to the mock directory it lives in. Source of truth: drift summary."""
    return SCRMAP[screen_id]["mock_path"].split("/")[-2]


def feature_ids_for(screen_id: str) -> list[str]:
    s = SCRMAP[screen_id]
    fids = s.get("meta_tags", {}).get("bf-feature-id") or []
    if isinstance(fids, str):
        fids = [fids]
    # filter out non-F-XXX values (e.g., "F-system" is allowed)
    return [f for f in fids if f and f != "F-system"]


def backend_deps_for(screen_id: str) -> list[str]:
    """All Group B backend tickets that touch this screen."""
    return sorted(set(SCREEN_TO_B.get(screen_id, [])))


def ears_seeds_for(feature_ids: list[str], limit: int = 1) -> list[str]:
    out: list[str] = []
    for fid in feature_ids:
        f = FMAP.get(fid) or {}
        for ac in (f.get("ears_ac_seed") or [])[:limit]:
            out.append(ac)
    return out


# ---------------------------------------------------------------------------
# AC builders (3-tier EARS)
# ---------------------------------------------------------------------------

def structural_ac(scr: dict, route_seg: str) -> list[str]:
    sid = scr["id"]
    name = scr["screen_name"]
    h1 = (scr.get("h1_text") or "").strip()
    sections = scr.get("section_h2_texts") or []
    kpis = scr.get("kpi_labels") or []

    out: list[str] = []
    # 1: data-screen-id
    out.append(
        f'UBIQUITOUS: The system shall expose a `data-screen-id="{sid}"` attribute on the page root element matching the canonical mock {scr["mock_path"]}.'
    )
    # 2: h1 verbatim
    if h1:
        out.append(
            f'STATE-DRIVEN: While the {name} page is rendered, the system shall display an h1 element with the exact text "{h1}" (matching {scr["mock_path"]} h1_text from screens.json#{sid}).'
        )
    else:
        out.append(
            f'STATE-DRIVEN: While the {name} page is rendered, the system shall NOT render an h1 element (matching screens.json#{sid}.h1_text=="" specification).'
        )
    # 3: section h2 verbatim
    if sections:
        sec_list = " / ".join(sections)
        out.append(
            f"STATE-DRIVEN: While the page is rendered, the system shall display section h2 headings whose set equals {{{sec_list}}} (matching screens.json#{sid}.section_h2_texts verbatim)."
        )
    elif kpis:
        kpi_list = " / ".join(kpis)
        out.append(
            f"STATE-DRIVEN: While the page hero is rendered, the system shall display KPI components whose labels equal the set {{{kpi_list}}} (matching mock kpi_labels)."
        )
    else:
        out.append(
            f"UBIQUITOUS: The system shall preserve the section structure of {scr['mock_path']} 1:1 (no extra or missing top-level sections vs the canonical mock)."
        )
    # 4: Lucide icons
    out.append(
        "UBIQUITOUS: The system shall use Lucide icons exclusively (no emoji, no other icon fonts) for icon-glyph elements on this page (design-tokens.md §8)."
    )
    # 5: ENGINE BASE green
    out.append(
        "UBIQUITOUS: The system shall use the ENGINE BASE green palette (`eb-500` = #1a6648) as the primary brand color and shall NOT introduce ad-hoc hex colors that bypass design-tokens.md §1."
    )
    return out


def functional_ac(scr: dict, feature_ids: list[str], route_seg: str) -> list[str]:
    sid = scr["id"]
    apis = [a for a in (scr.get("related_apis") or []) if a and not a.startswith("N/A")]
    roles = scr.get("access_roles") or []

    out: list[str] = []
    if apis:
        api0 = apis[0]
        out.append(
            f"EVENT-DRIVEN: When the page mounts for an authorized member, the system shall call {api0} and render its 2xx body into the page content area (loading -> data swap via TanStack Query)."
        )
        out.append(
            f"EVENT-DRIVEN: When {api0} returns 422 (validation error), the system shall render an inline error toast with the server-provided non-technical message and shall preserve user input."
        )
        out.append(
            f"EVENT-DRIVEN: When {api0} returns 5xx or a network failure occurs, the system shall display a non-technical error toast (Japanese copy) and offer a Retry action."
        )
    else:
        out.append(
            f"STATE-DRIVEN: While the {scr['screen_name']} page is rendered, the system shall render the canonical static layout from the mock without making any backend API call (the screen is static per screens.json#{sid})."
        )

    # 401 / 403
    if "public" in roles:
        out.append(
            "OPTIONAL: Where the visitor is already authenticated, the system shall redirect to the post-login landing (account dashboard or last visited workspace) on mount, and shall not display this public form again."
        )
    else:
        out.append(
            "UNWANTED: If an unauthenticated visitor navigates to this page, the system shall redirect to /login (S-001) and shall NOT render workspace-scoped data."
        )
        out.append(
            "UNWANTED: If the current session lacks the required role for this screen, the system shall route to /forbidden (S-046) and shall NOT call any workspace-scoped API for this page."
        )

    # 404 / not-found
    if "[id]" in route_seg or "[session_id]" in route_seg:
        out.append(
            "UNWANTED: If the workspace / task / session id in the URL does not resolve (404), the system shall render the not-found page (S-044) instead of partial data."
        )

    # 409 (conflict) — heuristic: include for mutation-capable screens
    has_mutation = any(a.split(" ", 1)[0] in {"POST", "PUT", "PATCH", "DELETE"} for a in apis)
    if has_mutation:
        out.append(
            "UNWANTED: If a mutation endpoint returns 409 (state conflict, e.g. stale-write), the system shall surface the conflict reason inline and shall NOT silently overwrite remote state."
        )

    # Skeleton/empty
    out.append(
        'STATE-DRIVEN: While data is being fetched, the system shall render a skeleton loader with `role="status"` and `aria-live="polite"`; once data arrives the skeleton shall be replaced atomically.'
    )
    if apis:
        out.append(
            "STATE-DRIVEN: While the data set is empty (2xx with zero items), the system shall display an empty state copy + primary CTA per design-tokens.md §10 empty-state pattern."
        )

    # Append 1 EARS seed from features for traceability
    for ac in ears_seeds_for(feature_ids, limit=1):
        out.append(ac)

    # Trim to a reasonable 5-8 range while keeping critical entries
    return out[:8]


def regression_ac(task_id: str, screen_id: str) -> list[str]:
    return [
        f"The system shall pass `pnpm vitest run frontend/tests/screens/{screen_id}-{SCRMAP[screen_id]['screen_name']}.spec.tsx` with all cases green and coverage >= 70%.",
        f"The system shall pass `pnpm tsc --noEmit` with 0 errors on touched modules (page / hook / api client / test).",
        f"The system shall pass `bash scripts/lint-mock.sh` 17/17 OK, `bash scripts/audit-md-check.sh {task_id}` green, and `bash scripts/lint-mock-impl-diff.sh {screen_id}` reporting drift_count=0 for this screen.",
    ]


# ---------------------------------------------------------------------------
# Task builder
# ---------------------------------------------------------------------------

# Wave 1 priority screens (~30): onboarding + auth + dashboard / core ops surfaces.
# The remaining ~25 go to Wave 2.
WAVE_1_SCREEN_IDS = {
    # auth (5) — foundational, blocks all logged-in flows
    "S-001", "S-002", "S-003", "S-004", "S-005",
    # onboarding (3)
    "S-048", "S-049", "S-050",
    # workspace + account dashboard core
    "S-012", "S-013", "S-014", "S-015",
    "S-006", "S-008",
    # email surfaces (signup verify / password reset / invitation) — used during onboarding
    "S-056", "S-057", "S-058",
    # system pages — needed early for guarded routes
    "S-044", "S-045", "S-046", "S-047",
    # dialogs core (mfa challenge / session expired) — needed for auth flow
    "S-053", "S-054",
    # global utilities visible from day 1
    "S-010", "S-011",
    # task/kanban + task detail — daily-driver surfaces for Phase 1 dogfooding
    "S-027", "S-030",
    # moat — constitution & red-line settings (required for phase 1 governance)
    "S-018", "S-019",
    # spec — requirements editor and spec viewer (vertical slice driver)
    "S-021", "S-022",
}


def wave_for(screen_id: str) -> str:
    return "W1" if screen_id in WAVE_1_SCREEN_IDS else "W2"


def wave_priority_for(screen_id: str) -> str:
    # First wave priority = onboarding / auth / dashboard
    if screen_id in {"S-001", "S-002", "S-003", "S-004", "S-005",
                     "S-048", "S-049", "S-050",
                     "S-012", "S-044", "S-045", "S-046", "S-047"}:
        return "First"
    if screen_id in WAVE_1_SCREEN_IDS:
        return "Second"
    return "Third"


def estimate_hours_for(screen_id: str) -> float:
    """Static pages: 2h. Listing/detail with API: 3h. Complex (kanban, dag, html editor): 4h."""
    complex_set = {"S-027", "S-029", "S-026", "S-017", "S-023"}
    static_set = {"S-051", "S-052", "S-053", "S-054", "S-055",
                  "S-056", "S-057", "S-058", "S-059", "S-060",
                  "S-044", "S-045", "S-046", "S-047", "S-005"}
    if screen_id in complex_set:
        return 4.0
    if screen_id in static_set:
        return 2.0
    return 3.0


def label_for(screen_id: str) -> str:
    """drift summary marks all 55 as missing (impl_status absent or 'missing'), so NEW."""
    drift = SCRMAP[screen_id].get("legacy_drift_notes") or {}
    if drift.get("impl_status") == "exists":
        return "REFACTOR"
    return "NEW"


def risk_flags_for(screen_id: str) -> list[str]:
    flags: list[str] = ["depends-on-T-V3-C-TEST-01"]  # vitest infra is shared cross-task prereq
    if screen_id == "S-027":
        flags.append("kanban-accordion-shape-mandatory")
    if screen_id in {"S-017", "S-029"}:
        flags.append("react-flow-dag-perf")
    if screen_id == "S-026":
        flags.append("grapesjs-bsd3-only")
    if screen_id in {"S-001", "S-002", "S-003", "S-004", "S-005"}:
        flags.append("auth-flow-prereq-for-other-tasks")
    return flags


def build_task(seq: int, screen_id: str, route_seg: str) -> dict:
    scr = SCRMAP[screen_id]
    feature_ids = feature_ids_for(screen_id)
    paths = page_paths(screen_id, scr["screen_name"], route_seg)

    task_id = f"T-V3-C3-{seq:03d}"
    files_changed = [
        f"{paths['page']} (new)",
        f"{paths['api']} (new or modify)",
        f"{paths['hook']} (new)",
        f"{paths['test']} (new)",
    ]
    editable = [paths["page"], paths["api"], paths["hook"], paths["test"]]

    structural = structural_ac(scr, route_seg)
    functional = functional_ac(scr, feature_ids, route_seg)
    regression = regression_ac(task_id, screen_id)

    deps = backend_deps_for(screen_id)

    # Build spec_links
    spec_links: list[str] = [
        scr["mock_path"],
        f"docs/functional-breakdown/2026-05-16_v3/screens.json#{screen_id}",
    ]
    for fid in feature_ids:
        spec_links.append(f"docs/functional-breakdown/2026-05-16_v3/features.json#{fid}")
    # Add primary OpenAPI ref if API exists
    apis = [a for a in (scr.get("related_apis") or []) if a and not a.startswith("N/A")]
    if apis:
        spec_links.append(f"openapi.yaml#{apis[0]}")

    legacy_drift = scr.get("legacy_drift_notes") or {}
    legacy_task_id = legacy_drift.get("task_id_seed")

    title_base = scr.get("name") or scr.get("screen_name")
    feature_clause = f"/ {feature_ids[0]}" if feature_ids else ""

    return {
        "id": task_id,
        "title": f"{screen_id} {title_base} Vertical Slice {feature_clause}".strip(),
        "category": "ui",
        "label": label_for(screen_id),
        "feature_id": feature_ids[0] if feature_ids else None,
        "screen_ids": [screen_id],
        "entity_ids": scr.get("related_entities") or [],
        "legacy_task_id": legacy_task_id,
        "phase": "Phase 1.0-fix",
        "wave": wave_for(screen_id),
        "wave_priority": wave_priority_for(screen_id),
        "group": "C-3",
        "deliverable_layer": "ui",
        "estimate_hours": estimate_hours_for(screen_id),
        "estimate_sessions": 1,
        "depends_on": deps,
        "files_changed": files_changed,
        "work_package_boundary": {
            "editable": editable,
            "shared_no_concurrent_edit": [
                "frontend/src/app/layout.tsx",
                "frontend/src/api/client.ts",
                "frontend/src/lib/auth.ts",
            ],
            "readonly": [
                scr["mock_path"],
                "docs/functional-breakdown/2026-05-16_v3/screens.json",
                "docs/functional-breakdown/2026-05-16_v3/features.json",
                "docs/mocks/2026-05-15_v3/design-system/DESIGN.md",
            ],
            "forbidden": [
                "data/migrations/",
                "backend/",
            ],
        },
        "acceptance_criteria": {
            "structural": structural,
            "functional": functional,
            "regression": regression,
        },
        "access_policies_required": scr.get("access_roles") or [],
        "spec_links": spec_links,
        "audit_md_path": f"{AUDIT_DIR_REL}/{task_id}.md",
        "branch": f"claude/{task_id}",
        "risk_flags": risk_flags_for(screen_id),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Verify all mocks exist on disk and all screens are in screens.json
    failures: list[str] = []
    for sid, _seg in MISSING_SCREENS:
        if sid not in SCRMAP:
            failures.append(f"{sid}: not in screens.json")
            continue
        mock_path = ROOT / SCRMAP[sid]["mock_path"]
        if not mock_path.exists():
            failures.append(f"{sid}: mock file missing at {mock_path}")
    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 2

    tasks: list[dict] = []
    for i, (sid, seg) in enumerate(MISSING_SCREENS, start=1):
        tasks.append(build_task(i, sid, seg))

    total_hours = sum(t["estimate_hours"] for t in tasks)
    w1_count = sum(1 for t in tasks if t["wave"] == "W1")
    w2_count = sum(1 for t in tasks if t["wave"] == "W2")
    labels: dict[str, int] = {}
    for t in tasks:
        labels[t["label"]] = labels.get(t["label"], 0) + 1

    out = {
        "version": "v3",
        "project": "Build-Factory",
        "profile": "build-factory",
        "phase_target": "Phase 1.0-fix",
        "group": "C-3 (UI / Vertical Slice — Screen-Missing Backfill)",
        "categories": sorted({SCRMAP[sid]["category"] for sid, _ in MISSING_SCREENS}),
        "created_at": "2026-05-17",
        "source": {
            "drift_summary": "docs/functional-breakdown/2026-05-16_v3/screen-drift-summary.md",
            "screens_spec": "docs/functional-breakdown/2026-05-16_v3/screens.json",
            "features_spec": "docs/functional-breakdown/2026-05-16_v3/features.json",
            "backend_ref": "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json",
        },
        "summary": {
            "task_count": len(tasks),
            "wave_W1_count": w1_count,
            "wave_W2_count": w2_count,
            "label_distribution": labels,
            "total_estimate_hours": total_hours,
            "id_range": f"{tasks[0]['id']}..{tasks[-1]['id']}",
        },
        "tasks": tasks,
    }
    out_path = ROOT / TICKETS_FILE_REL
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path} — {len(tasks)} tasks  W1={w1_count} W2={w2_count}  total={total_hours}h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
