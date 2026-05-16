#!/usr/bin/env python3
"""
ears-test-mapping.json generator (v3 / Phase 1).

For each task in the 4 input ticket files, walk its 3-tier AC list and
produce a typed test-mapping entry:

  structural  -> mock-impl-diff lint  (UI gate / Gate #8)
  functional  -> unit + contract test (Backend gate / Gate #5)
                  + access-control matrix test (Backend gate / Gate #3)
  regression  -> CI gate auto-pass (Gate #1-#8)

EARS form auto-detection:
  - EVENT-DRIVEN   -> happy-path test
  - UNWANTED       -> negative test
  - STATE-DRIVEN   -> parametrize test
  - UBIQUITOUS     -> property / invariant test
  - OPTIONAL       -> conditional test

Output target:
  docs/test-verification/2026-05-16_v3_phase1/ears-test-mapping.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
TICKET_FILES = [
    "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json",
    "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part1.json",
    "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part2.json",
    "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json",
]
OUTPUT = ROOT / "docs/test-verification/2026-05-16_v3_phase1/ears-test-mapping.json"

EARS_PATTERNS = [
    ("UBIQUITOUS", re.compile(r"^\s*UBIQUITOUS\s*:", re.IGNORECASE)),
    ("EVENT-DRIVEN", re.compile(r"^\s*EVENT-DRIVEN\s*:", re.IGNORECASE)),
    ("STATE-DRIVEN", re.compile(r"^\s*STATE-DRIVEN\s*:", re.IGNORECASE)),
    ("OPTIONAL", re.compile(r"^\s*OPTIONAL\s*:", re.IGNORECASE)),
    ("UNWANTED", re.compile(r"^\s*UNWANTED\s*:", re.IGNORECASE)),
]

# Implicit EARS detection fallbacks (regression rules use plain "The system shall ...")
IMPL_EARS = [
    ("UNWANTED", re.compile(r"^\s*If\b", re.IGNORECASE)),
    ("EVENT-DRIVEN", re.compile(r"^\s*When\b", re.IGNORECASE)),
    ("STATE-DRIVEN", re.compile(r"^\s*While\b", re.IGNORECASE)),
    ("OPTIONAL", re.compile(r"^\s*Where\b", re.IGNORECASE)),
    ("UBIQUITOUS", re.compile(r"^\s*The (system|migration) shall\b", re.IGNORECASE)),
]


def detect_ears_form(text: str) -> str:
    for form, pat in EARS_PATTERNS:
        if pat.match(text):
            return form
    for form, pat in IMPL_EARS:
        if pat.match(text):
            return form
    return "UBIQUITOUS"


# Extract endpoint paths e.g. "POST /api/auth/login"
ENDPOINT_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/[^\s\.,;\)]+)")
# rate-limit short phrase capture (e.g., "(5/min/ip)")
RATE_LIMIT_RE = re.compile(r"\((\d+)/(min|hour|day)/([a-z_]+)\)")
# status code capture (return 200/401/422/etc.)
STATUS_RE = re.compile(r"\b(2\d{2}|4\d{2}|5\d{2})\b")


def shorten(text: str, limit: int = 64) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    if len(s) > limit:
        s = s[: limit - 3] + "..."
    return s


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:48]


def classify_test_layer(tier: str, ears_form: str, ac_text: str, task: dict) -> dict[str, Any]:
    """Return test_layer / test_type / tool / gate / test_path / test_function info."""
    task_id = task["id"]
    category = task.get("category", "")
    is_backend = category in {"backend", "db"} or task_id.startswith("T-V3-B") or task_id.startswith("T-V3-D")
    is_frontend = category == "frontend" or task_id.startswith("T-V3-C")

    # Common test-id slug
    ac_slug = slug(shorten(ac_text, 48))

    # default mapping
    test_layer = "functional"
    test_type = "unit"
    tool = "pytest"
    gate = "gate-5-pytest-cov"
    test_path = "backend/tests/"
    test_function = f"test_{slug(task_id)}_{ac_slug}"

    if tier == "structural":
        test_layer = "structural"
        test_type = "mock-impl-diff"
        tool = "scripts/lint-mock-impl-diff.py"
        gate = "gate-8-mock-impl-diff"
        # Most structural ACs apply to UI screens
        screen_ids = task.get("screen_ids") or []
        screen_token = screen_ids[0].split()[0] if screen_ids else "screen"
        test_path = f"frontend/tests/screens/{screen_token}-drift.spec.tsx"
        test_function = f"drift_{slug(screen_token)}_{ac_slug}"
        return {
            "test_layer": test_layer,
            "test_type": test_type,
            "tool": tool,
            "gate": gate,
            "test_path": test_path,
            "test_function": test_function,
        }

    if tier == "regression":
        test_layer = "regression"
        # Try to detect which gate the regression rule actually runs.
        t = ac_text.lower()
        if "lint-mock-impl-diff" in t or "mock-impl diff" in t or "drift" in t:
            gate, tool, test_type = "gate-8-mock-impl-diff", "scripts/lint-mock-impl-diff.py", "drift-lint"
            test_path = "scripts/lint-mock-impl-diff.py"
        elif "lint-mock" in t or "scripts/lint-mock.sh" in t:
            gate, tool, test_type = "gate-1-lint-mock", "scripts/lint-mock.sh", "static-lint"
            test_path = "scripts/lint-mock.sh"
        elif "validate-tickets" in t or "validate-ears-ac" in t or "ac validator" in t or "3-tier ac" in t:
            gate, tool, test_type = "gate-2-ac-validator", "scripts/validate-tickets.py", "schema-lint"
            test_path = "scripts/validate-tickets.py"
        elif "audit-md-check" in t or "validate-audit-md" in t or "audit md" in t:
            gate, tool, test_type = "gate-4-audit-md", "scripts/audit-md-check.sh", "audit-md"
            test_path = "scripts/audit-md-check.sh"
        elif "verify-rls-coverage" in t or "rls coverage" in t:
            gate, tool, test_type = "gate-3-rls-coverage", "scripts/verify-rls-coverage.py", "rls-matrix"
            test_path = "scripts/verify-rls-coverage.py"
        elif "pytest" in t or "coverage" in t or "cov-fail-under" in t:
            gate, tool, test_type = "gate-5-pytest-cov", "pytest", "coverage"
            test_path = "backend/tests/"
        elif "pyright" in t:
            gate, tool, test_type = "gate-6-pyright", "pyright --strict", "type-check"
            test_path = "backend/"
        elif "tsc" in t or "--noemit" in t:
            gate, tool, test_type = "gate-7-tsc-strict", "tsc --noEmit", "type-check"
            test_path = "frontend/"
        elif "vitest" in t:
            gate, tool, test_type = "gate-5-pytest-cov", "vitest", "frontend-unit"
            test_path = "frontend/tests/"
        elif "ruff" in t or "pnpm run lint" in t:
            gate, tool, test_type = "gate-1-lint-mock", "ruff/pnpm", "static-lint"
            test_path = "."
        else:
            gate, tool, test_type = "gate-1-lint-mock", "ci-v3", "regression-check"
            test_path = "."
        test_function = f"gate_{slug(gate)}_{slug(task_id)}_{ac_slug}"
        return {
            "test_layer": test_layer,
            "test_type": test_type,
            "tool": tool,
            "gate": gate,
            "test_path": test_path,
            "test_function": test_function,
        }

    # functional tier
    t = ac_text.lower()
    # Detect access-control / role mention
    access_keywords = ("rls", "role", "owner", "admin", "member", "guest", "policy", "access_polic")
    is_access = any(k in t for k in access_keywords) or " unauthorized" in t or "401" in t or "403" in t

    if is_access:
        test_layer = "functional.access_control"
        test_type = "parametrize"
        tool = "pytest"
        gate = "gate-3-rls-coverage"
        entity_token = "entity"
        if task.get("entity_ids"):
            entity_token = task["entity_ids"][0].split()[0]  # E-002
        test_path = f"backend/tests/rls/test_{slug(entity_token)}_matrix.py"
        test_function = f"test_rls_{slug(entity_token)}_{ac_slug}"
    else:
        # functional.api
        endpoint_match = ENDPOINT_RE.search(ac_text)
        if endpoint_match:
            method = endpoint_match.group(1).lower()
            path = endpoint_match.group(2)
            ep_slug = slug(f"{method}_{path}")
            if is_frontend:
                test_layer = "functional.api"
                test_type = "vitest+contract" if ears_form in ("EVENT-DRIVEN", "UNWANTED") else "vitest"
                tool = "vitest"
                gate = "gate-5-pytest-cov"
                screen_ids = task.get("screen_ids") or ["screen"]
                stoken = screen_ids[0].split()[0]
                test_path = f"frontend/tests/screens/{stoken}.spec.tsx"
                test_function = f"test_{slug(stoken)}_{ep_slug}_{ac_slug}"
            else:
                test_layer = "functional.api"
                test_type = (
                    "unit+contract"
                    if ears_form in ("EVENT-DRIVEN", "UNWANTED")
                    else "parametrize"
                    if ears_form == "STATE-DRIVEN"
                    else "property"
                    if ears_form == "UBIQUITOUS"
                    else "conditional"
                )
                tool = "pytest+schemathesis"
                gate = "gate-5-pytest-cov"
                # Try to map task router file
                router_token = task.get("feature_id") or "feature"
                # Try to extract router file from files_changed
                for f in task.get("files_changed", []):
                    m = re.search(r"backend/tests/[\w/]+/test_(\w+)\.py", f)
                    if m:
                        test_path = f"backend/tests/routers/test_{m.group(1)}.py"
                        break
                    m2 = re.search(r"backend/app/routers/(\w+)\.py", f)
                    if m2:
                        test_path = f"backend/tests/routers/test_{m2.group(1)}.py"
                        break
                else:
                    test_path = f"backend/tests/routers/test_{slug(router_token)}.py"
                test_function = f"test_{ep_slug}_{ac_slug}"
        else:
            # No endpoint matched: structural-ish state assertion or generic API behavior
            if is_frontend:
                test_layer = "functional.ui"
                test_type = "vitest"
                tool = "vitest"
                gate = "gate-5-pytest-cov"
                screen_ids = task.get("screen_ids") or ["screen"]
                stoken = screen_ids[0].split()[0]
                test_path = f"frontend/tests/screens/{stoken}.spec.tsx"
                test_function = f"test_{slug(stoken)}_{ac_slug}"
            elif task.get("category") == "db":
                test_layer = "functional.migration"
                test_type = "migration-test"
                tool = "pytest+alembic"
                gate = "gate-5-pytest-cov"
                test_path = "backend/tests/migrations/"
                test_function = f"test_migration_{slug(task_id)}_{ac_slug}"
            else:
                test_layer = "functional.api"
                test_type = "unit"
                tool = "pytest"
                gate = "gate-5-pytest-cov"
                test_path = "backend/tests/"
                test_function = f"test_{slug(task_id)}_{ac_slug}"

    return {
        "test_layer": test_layer,
        "test_type": test_type,
        "tool": tool,
        "gate": gate,
        "test_path": test_path,
        "test_function": test_function,
    }


def build_mapping_for_task(task: dict) -> list[dict]:
    """Walk 3-tier AC and emit a flat list of test-mapping entries for the task."""
    results: list[dict] = []
    task_id = task["id"]
    ac = task.get("acceptance_criteria") or {}

    # Counters for stable test IDs per tier-letter
    counters = {"S": 0, "F": 0, "R": 0}

    for tier_letter, tier_key in (("S", "structural"), ("F", "functional"), ("R", "regression")):
        for ac_text in ac.get(tier_key, []) or []:
            counters[tier_letter] += 1
            ac_id = f"AC-{tier_letter}{counters[tier_letter]}"
            test_id = f"{task_id}-{tier_letter}{counters[tier_letter]}"
            ears_form = detect_ears_form(ac_text)
            cls = classify_test_layer(tier_key, ears_form, ac_text, task)
            entry = {
                "task_id": task_id,
                "ac_id": ac_id,
                "ac_tier": tier_key,
                "ears_form": ears_form,
                "ears_text": ac_text,
                "test_id": test_id,
                **cls,
            }
            # Endpoint capture (for backend traceability)
            ep = ENDPOINT_RE.search(ac_text)
            if ep:
                entry["endpoint"] = f"{ep.group(1)} {ep.group(2)}"
            results.append(entry)
    return results


def main() -> None:
    all_tasks: list[dict] = []
    summary_per_file: list[dict] = []
    for f in TICKET_FILES:
        path = ROOT / f
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        tasks = data.get("tasks", [])
        all_tasks.extend(tasks)
        summary_per_file.append({"file": f, "task_count": len(tasks)})

    mappings: list[dict] = []
    task_summaries: list[dict] = []
    gate_counts: dict[str, int] = {}
    tier_counts = {"structural": 0, "functional": 0, "regression": 0}
    ears_counts: dict[str, int] = {}

    for task in all_tasks:
        entries = build_mapping_for_task(task)
        # Group mappings under per-task wrapper for human readability AND keep flat list.
        ac_to_test = [
            {
                "ac_id": e["ac_id"],
                "ac_tier": e["ac_tier"],
                "ears_form": e["ears_form"],
                "ears_text": e["ears_text"],
                "test_id": e["test_id"],
                "test_layer": e["test_layer"],
                "test_type": e["test_type"],
                "tool": e["tool"],
                "gate": e["gate"],
                "test_path": e["test_path"],
                "test_function": e["test_function"],
                **({"endpoint": e["endpoint"]} if "endpoint" in e else {}),
            }
            for e in entries
        ]
        task_summaries.append(
            {
                "task_id": task["id"],
                "title": task.get("title", ""),
                "feature_id": task.get("feature_id"),
                "screen_ids": task.get("screen_ids", []),
                "entity_ids": task.get("entity_ids", []),
                "phase": task.get("phase"),
                "wave": task.get("wave"),
                "group": task.get("group"),
                "category": task.get("category"),
                "ac_to_test": ac_to_test,
            }
        )
        for e in entries:
            mappings.append(e)
            tier_counts[e["ac_tier"]] += 1
            gate_counts[e["gate"]] = gate_counts.get(e["gate"], 0) + 1
            ears_counts[e["ears_form"]] = ears_counts.get(e["ears_form"], 0) + 1

    out = {
        "version": "v3",
        "skill": "test-verification",
        "project": "Build-Factory",
        "phase": "Phase 1",
        "profile": "skills/test-verification/references/profiles/build-factory.md",
        "created_at": "2026-05-16",
        "inputs": summary_per_file,
        "summary": {
            "total_tasks": len(all_tasks),
            "total_test_ids": len(mappings),
            "by_tier": tier_counts,
            "by_gate": gate_counts,
            "by_ears_form": ears_counts,
        },
        "tasks": task_summaries,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"Wrote {OUTPUT}")
    print(f"  total_tasks={len(all_tasks)}  total_test_ids={len(mappings)}")
    print(f"  by_tier={tier_counts}")
    print(f"  by_gate={gate_counts}")
    print(f"  by_ears_form={ears_counts}")


if __name__ == "__main__":
    main()
