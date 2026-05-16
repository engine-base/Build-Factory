#!/usr/bin/env python3
"""Group C Part 2 generator — 8 category × 28 mock + S-027 3 分割 = 30 task.

Inputs:
  docs/functional-breakdown/2026-05-16_v3/screens.json
  docs/functional-breakdown/2026-05-16_v3/features.json

Outputs:
  docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part2.json
"""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCREENS = json.loads((ROOT / "docs/functional-breakdown/2026-05-16_v3/screens.json").read_text())["items"]
FEATURES = json.loads((ROOT / "docs/functional-breakdown/2026-05-16_v3/features.json").read_text())["items"]
FMAP = {f["id"]: f for f in FEATURES}

TARGET_CATS = ["moat", "onboarding", "ops", "review", "spec", "system", "task", "workspace"]
AUDIT_DIR_REL = "docs/audit/2026-05-16_v3"

# Part1 covers ~ T-V3-C-01..36 (36 mock). Part2 starts T-V3-C-37 to avoid collision.
START_ID = 37


def feature_drift_seed(fid: str) -> str | None:
    f = FMAP.get(fid)
    if not f:
        return None
    notes = f.get("legacy_drift_notes")
    if isinstance(notes, dict):
        return notes.get("task_id_seed")
    return None


def backend_deps_for(feature_ids: list[str]) -> list[str]:
    """Group B backend task ID stubs for given features.

    Convention: Group B-1 (backend) parallel session generates T-V3-B-<feature_short>.
    We emit dependency references that the cross-group integrator can resolve.
    """
    deps: list[str] = []
    for fid in feature_ids:
        if fid == "F-system":
            continue
        # numeric suffix for B-N convention
        num = fid.split("-")[-1] if "-" in fid else fid
        deps.append(f"T-V3-B-{num}")
    return sorted(set(deps))


def ears_seed_for(feature_ids: list[str], limit: int = 2) -> list[str]:
    out: list[str] = []
    for fid in feature_ids:
        f = FMAP.get(fid) or {}
        for ac in (f.get("ears_ac_seed") or [])[:limit]:
            out.append(ac)
    return out


def screen_files(screen_id: str, screen_name: str) -> dict:
    """Path conventions for vertical slice frontend Next.js App Router."""
    sid = screen_id.lower()
    sn = screen_name.replace("_", "-")
    return {
        "page": f"frontend/app/{sid}-{sn}/page.tsx",
        "page_test": f"frontend/app/{sid}-{sn}/page.test.tsx",
        "hook": f"frontend/lib/hooks/use-{sn}.ts",
        "client_api": f"frontend/lib/api/{sn}.ts",
        "story": f"frontend/stories/{sid}-{sn}.stories.tsx",
    }


def structural_ac(scr: dict) -> list[str]:
    h1 = scr.get("h1_text", "")
    kpis = scr.get("kpi_labels") or []
    sections = scr.get("section_h2_texts") or []
    out: list[str] = [
        f'STATE-DRIVEN: While the {scr["screen_name"]} page is rendered, the system shall display an h1 element with the exact text "{h1}" (matching {scr["mock_path"]} h1).',
    ]
    if kpis:
        kpi_list = " / ".join(kpis)
        out.append(
            f"STATE-DRIVEN: While the page hero is rendered, the system shall display KPI components whose labels equal the set {{{kpi_list}}} (matching mock kpi_labels)."
        )
    if sections:
        sec_list = " / ".join(sections)
        out.append(
            f"STATE-DRIVEN: While the page is rendered, the system shall display section h2 headings whose set equals {{{sec_list}}} (matching mock section_h2_texts)."
        )
    out.append(
        f"UBIQUITOUS: The system shall use Lucide icons exclusively (no emoji) for icon-glyph elements on this page (design-tokens.md §8)."
    )
    return out


def functional_ac(scr: dict, feature_ids: list[str]) -> list[str]:
    out: list[str] = []
    apis = scr.get("related_apis") or []
    if apis:
        # Use first API as primary load event
        api0 = apis[0]
        method, _, path = api0.partition(" ")
        out.append(
            f"EVENT-DRIVEN: When the page mounts for an authenticated workspace member, the system shall call {api0} and render its 2xx body into the page; on 4xx the system shall render an inline error toast and an empty state."
        )
    # Access policy / unauthorized
    roles = scr.get("access_roles") or []
    if "public" not in roles:
        out.append(
            f"UNWANTED: If an unauthenticated visitor navigates to this page, the system shall redirect to /login (S-001) and shall not render any workspace-scoped data."
        )
    # Pull EARS seeds (max 2) for feature linkage
    for ac in ears_seed_for(feature_ids, limit=1):
        out.append(ac)
    if len(out) < 3:
        out.append(
            f"STATE-DRIVEN: While data is being fetched, the system shall render a skeleton loader with role=\"status\" aria-live=\"polite\"; once data arrives the skeleton shall be replaced atomically."
        )
    if not any(a.startswith("UNWANTED") for a in out):
        out.append(
            "UNWANTED: If the API returns 403 (RBAC denial), the system shall display a 403 page (S-046) instead of partial data."
        )
    return out


def regression_ac(screen_id: str) -> list[str]:
    return [
        f"The system shall pass `pnpm test --filter={screen_id.lower()}` with coverage >= 70%.",
        f"The system shall pass `tsc --noEmit` with 0 errors.",
        f"The system shall pass `pnpm run lint` (ESLint + design-token lint) with 0 violations.",
        f"The system shall pass `bash scripts/lint-mock.sh` 12/12 OK (no emoji / no AGPL / no ARCHIVE residue).",
        f"The system shall pass `bash scripts/lint-mock-impl-diff.sh {screen_id}` (Tier 1 structural diff = 0).",
        f"The system shall pass `python3 scripts/validate-tickets.py --check-file docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part2.json` for this task id.",
        f"The system shall pass `bash scripts/audit-md-check.sh {{task_id}}` (audit MD pre-flight green).",
    ]


def build_task(seq: int, scr: dict, *, sub_id: str | None = None,
               override_title: str | None = None,
               override_structural: list[str] | None = None,
               override_functional: list[str] | None = None,
               override_files: list[str] | None = None,
               override_editable: list[str] | None = None,
               override_estimate: float | None = None,
               extra_depends: list[str] | None = None) -> dict:
    task_id = f"T-V3-C-{seq:02d}"
    if sub_id:
        task_id = f"T-V3-C-{seq:02d}-{sub_id}"
    feature_ids = scr["meta_tags"].get("bf-feature-id") or []
    if isinstance(feature_ids, str):
        feature_ids = [feature_ids]
    files = screen_files(scr["id"], scr["screen_name"])
    if override_files:
        files_list = override_files
    else:
        files_list = [
            f"{files['page']} (new)",
            f"{files['page_test']} (new)",
            f"{files['hook']} (new)",
            f"{files['client_api']} (new)",
        ]
    editable = override_editable or [p.split(" ")[0] for p in files_list]

    structural = override_structural if override_structural is not None else structural_ac(scr)
    functional = override_functional if override_functional is not None else functional_ac(scr, feature_ids)
    regression = regression_ac(scr["id"])
    # Substitute {task_id} in regression
    regression = [r.replace("{task_id}", task_id) for r in regression]

    base_title = override_title or f"{scr['id']} {scr['name']} — Vertical Slice UI (Next.js page + API client + hook + test)"
    label = "REFACTOR" if scr["legacy_drift_notes"].get("impl_status") == "exists" else "NEW"

    deps = backend_deps_for(feature_ids)
    if extra_depends:
        deps.extend(extra_depends)
    deps = sorted(set(deps))

    audit_md_path = f"{AUDIT_DIR_REL}/{task_id}.md"

    return {
        "id": task_id,
        "title": base_title,
        "category": "frontend",
        "label": label,
        "feature_id": feature_ids[0] if feature_ids else None,
        "screen_ids": [scr["id"]],
        "entity_ids": scr.get("related_entities") or [],
        "legacy_task_id": scr["legacy_drift_notes"].get("task_id_seed"),
        "phase": "Phase 1",
        "wave": "1",
        "wave_priority": "First",
        "group": "C",
        "deliverable_layer": "ui",
        "estimate_hours": override_estimate if override_estimate is not None else 4.0,
        "estimate_sessions": 1,
        "depends_on": deps,
        "files_changed": files_list,
        "work_package_boundary": {
            "editable": editable,
            "shared_no_concurrent_edit": [
                "frontend/app/layout.tsx",
                "frontend/lib/api/client.ts",
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
        "access_policies_required": [],
        "spec_links": [
            scr["mock_path"],
            f"docs/functional-breakdown/2026-05-16_v3/screens.json#{scr['id']}",
        ] + [f"docs/functional-breakdown/2026-05-16_v3/features.json#{fid}" for fid in feature_ids],
        "audit_md_path": audit_md_path,
        "branch": f"claude/{task_id}",
        "risk_flags": [],
    }


def build_kanban_split(seq_start: int, scr: dict) -> list[dict]:
    """S-027 Kanban — split into 3 sub-tasks (core / drag-drop / filter)."""
    base_seq = seq_start

    files_core = [
        "frontend/app/s-027-task-kanban/page.tsx (new)",
        "frontend/app/s-027-task-kanban/page.test.tsx (new)",
        "frontend/lib/hooks/use-kanban-board.ts (new)",
        "frontend/lib/api/kanban.ts (new)",
        "frontend/components/kanban/AccordionBoard.tsx (new)",
        "frontend/components/kanban/Column.tsx (new)",
    ]
    files_dnd = [
        "frontend/components/kanban/DraggableCard.tsx (new)",
        "frontend/components/kanban/DropZone.tsx (new)",
        "frontend/lib/hooks/use-task-dnd.ts (new)",
        "frontend/lib/api/kanban-move.ts (new)",
        "frontend/app/s-027-task-kanban/page.tsx (modify)",
    ]
    files_filter = [
        "frontend/components/kanban/FilterBar.tsx (new)",
        "frontend/components/kanban/FeatureToggle.tsx (new)",
        "frontend/lib/hooks/use-kanban-filter.ts (new)",
        "frontend/app/s-027-task-kanban/page.tsx (modify)",
    ]

    core_struct = [
        'STATE-DRIVEN: While the kanban page is rendered, the system shall display an h1 element with the exact text "タスク Kanban" (matching docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html h1).',
        "UBIQUITOUS: The system shall render kanban as a feature-grouped accordion (each feature_id = one accordion section containing 4 columns: Todo / In Progress / Review / Done), NOT a flat 6-column board (Hermes-flat layout is forbidden per CLAUDE.md §5.5).",
        "UBIQUITOUS: The system shall expand only in-progress feature accordions by default; completed (all Done) and not-started (all Todo) features shall be collapsed by default.",
        "UBIQUITOUS: The system shall use Lucide icons exclusively (no emoji) for icon-glyph elements (design-tokens.md §8).",
    ]
    core_func = [
        "EVENT-DRIVEN: When the page mounts for an authenticated workspace member, the system shall call GET /api/workspaces/{id}/tasks?group_by=feature and render tasks grouped by feature_id with accordion-friendly metadata.",
        "UNWANTED: If an unauthenticated visitor navigates to this page, the system shall redirect to /login (S-001) and shall not render any task data.",
        'STATE-DRIVEN: While data is being fetched, the system shall render a skeleton accordion with role="status" aria-live="polite".',
        "UNWANTED: If the API returns 403, the system shall display a 403 page (S-046) instead of partial data.",
    ]

    dnd_struct = [
        "STATE-DRIVEN: While a task card is being dragged, the system shall apply a `data-dragging=true` attribute and show a drop-shadow visual treatment matching design-tokens.md §6 elevation/2.",
        "UBIQUITOUS: The system shall render valid drop zones (same feature, different column) with a dashed eb-500 border ring during a drag operation.",
    ]
    dnd_func = [
        "EVENT-DRIVEN: When a user drops a task card on a valid column DropZone of the SAME feature, the system shall call PATCH /api/tasks/{task_id} with the new status and optimistically update the UI within 100ms; on 4xx the system shall revert the optimistic move and show an error toast.",
        "UNWANTED: If a user attempts to drop a task on a column belonging to a DIFFERENT feature accordion, the system shall reject the drop, revert the card position, and not call any API.",
        "UNWANTED: If POST /api/tasks/{id}/play is called for a task with unsatisfied dependencies, the system shall surface the 409 error inline and not advance the card status.",
        "OPTIONAL: Where the user holds shift while dropping, the system shall open a confirmation dialog before applying the status change.",
    ]

    filter_struct = [
        "UBIQUITOUS: The system shall render a sticky FilterBar above the accordion containing: feature multi-select / status multi-select / assignee multi-select / text search input.",
        "STATE-DRIVEN: While at least one filter is active, the system shall display an active-filter badge count and a 'Clear filters' button.",
    ]
    filter_func = [
        "EVENT-DRIVEN: When a user changes any filter input, the system shall debounce 250ms and then re-call GET /api/workspaces/{id}/tasks?group_by=feature with the corresponding query parameters; the URL search params shall mirror the active filter state.",
        "STATE-DRIVEN: While a filter narrows results to zero, the system shall display an empty state per accordion section with a 'Reset filters' CTA.",
        "UNWANTED: If text search input exceeds 200 characters, the system shall truncate to 200 and not call the API beyond that length.",
    ]

    backend_deps = backend_deps_for(["F-007"])

    base_kwargs = dict(
        scr=scr,
        override_files=None,
    )

    core = build_task(
        base_seq, scr,
        sub_id="1",
        override_title="S-027 タスク Kanban — core (accordion layout + columns + data fetch)",
        override_structural=core_struct,
        override_functional=core_func,
        override_files=files_core,
        override_editable=[p.split(" ")[0] for p in files_core],
        override_estimate=6.0,
        extra_depends=backend_deps,
    )
    dnd = build_task(
        base_seq, scr,
        sub_id="2",
        override_title="S-027 タスク Kanban — drag & drop (within-feature card move + optimistic update)",
        override_structural=dnd_struct,
        override_functional=dnd_func,
        override_files=files_dnd,
        override_editable=[p.split(" ")[0] for p in files_dnd if p.endswith("(new)")],
        override_estimate=5.0,
        extra_depends=[core["id"]] + backend_deps,
    )
    flt = build_task(
        base_seq, scr,
        sub_id="3",
        override_title="S-027 タスク Kanban — filter & search (feature / status / assignee / text)",
        override_structural=filter_struct,
        override_functional=filter_func,
        override_files=files_filter,
        override_editable=[p.split(" ")[0] for p in files_filter if p.endswith("(new)")],
        override_estimate=3.0,
        extra_depends=[core["id"]] + backend_deps,
    )
    # boundary readonly for the sub-tasks should ref the same mock
    return [core, dnd, flt]


def main() -> None:
    tasks: list[dict] = []
    seq = START_ID

    # Aggregate target screens in deterministic order
    by_cat: dict[str, list[dict]] = {c: [] for c in TARGET_CATS}
    for s in SCREENS:
        if s["category"] in by_cat:
            by_cat[s["category"]].append(s)
    for c in by_cat:
        by_cat[c].sort(key=lambda s: s["id"])

    for cat in TARGET_CATS:
        for scr in by_cat[cat]:
            if scr["id"] == "S-027":
                tasks.extend(build_kanban_split(seq, scr))
                seq += 1
            else:
                tasks.append(build_task(seq, scr))
                seq += 1

    out = {
        "version": "v3",
        "project": "Build-Factory",
        "profile": "build-factory",
        "phase_target": "Phase 1",
        "group": "C (UI / Vertical Slice) — Part 2",
        "categories": TARGET_CATS,
        "created_at": "2026-05-16",
        "summary": {
            "mock_count": 28,
            "task_count": len(tasks),
            "s027_split": 3,
            "id_range": f"{tasks[0]['id']}..{tasks[-1]['id']}",
        },
        "tasks": tasks,
    }
    out_path = ROOT / "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part2.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path} — {len(tasks)} tasks")


if __name__ == "__main__":
    main()
