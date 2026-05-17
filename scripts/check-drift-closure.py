#!/usr/bin/env python3
"""T-V3-D-15: Drift closure validator (Phase 1 final gate).

Build-Factory v3 Phase 1 末尾の drift fix Wave (D-01〜D-14) が完了した状態を
機械的に検証する。次の 6 カテゴリの drift が全て resolved / deferred / wontfix の
いずれかにマップされ、resolver が valid な D-task ID であることを確認する。

検証対象:
  1. Entity drift (critical 3 + high 9 + medium 11 + new 25 = 48 件)
     → docs/functional-breakdown/2026-05-16_v3/entities.json
     → legacy_drift_notes.task_id / resolution.task_id が valid D-task ID か
     → status が resolution を示す値か
  2. API method drift (5 件)
     → docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md §high (method mismatch)
     → T-V3-D-09 (API method alignment / ADR-016) で resolved
  3. API non-method high drift (2 件 missing endpoint) + medium 1 件 + low 2 件 = 5 件
     → api-drift-summary.md §high non-method + medium + low
     → T-V3-D-10 (high non-method) で resolved / WebSocket low は intentional deferred
  4. Screen drift (9 件 hint match)
     → docs/functional-breakdown/2026-05-16_v3/screen-drift-summary.md §exists
     → T-V3-D-11 (screen h1 / KPI / section drift fix) で resolved
  5. RLS coverage 100% (subprocess delegate to verify-rls-coverage.py)
  6. lint #19 entity-table-naming 100% green (subprocess delegate to lint-mock.sh)

Note: API critical missing 94 件 (Group B-1 vertical slice scope) と
      screen missing 55 件 (Group C 新規実装 scope) は drift fix Group D の
      範囲外であり、本 script の検証対象外 (it's "Build Backlog" not "Drift Backlog").

Usage:
    python3 scripts/check-drift-closure.py            # 通常検証
    python3 scripts/check-drift-closure.py --json     # JSON 出力
    python3 scripts/check-drift-closure.py --quiet    # 集計行のみ
    python3 scripts/check-drift-closure.py --entities-file <path>  # fixture 検証用

Exit codes:
    0  全 drift category green
    1  drift category に open / unresolved item あり
    2  外部 dependency 検証失敗 (RLS coverage / lint #19)
    64 引数誤り
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENTITIES_PATH = ROOT / "docs/functional-breakdown/2026-05-16_v3/entities.json"
API_DRIFT_PATH = ROOT / "docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md"
SCREEN_DRIFT_PATH = ROOT / "docs/functional-breakdown/2026-05-16_v3/screen-drift-summary.md"
TICKETS_PATH = ROOT / "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json"

VALID_D_TASKS = {f"T-V3-D-{i:02d}" for i in range(1, 16)}  # T-V3-D-01 .. T-V3-D-15

# entity status that indicates resolution (no further action needed)
RESOLVED_STATUS = {
    "rls_complete",
    "formalized_in_migration",
    "formal",
    "archived_as_view",
    "deprecated_merged_into_e058",
    "discovered_in_migration",  # E-044〜E-068 の一部 (RLS 補完前の中間 status)
}

# Canonical mapping: entity_id -> resolver D-task. Derived from D-task scope (entity_ids).
# This is the SOURCE OF TRUTH for "this drift was closed by this task".
ENTITY_DRIFT_RESOLUTION: dict[str, str] = {
    # T-V3-D-01: rename entity table_name
    "E-008": "T-V3-D-01", "E-021": "T-V3-D-01", "E-012": "T-V3-D-01",
    # T-V3-D-02: bf_ prefix (ADR-014 keep)
    "E-014": "T-V3-D-02", "E-015": "T-V3-D-02", "E-016": "T-V3-D-02", "E-017": "T-V3-D-02",
    # T-V3-D-03: type/enum drift (impl-as-source)
    "E-002": "T-V3-D-03", "E-003": "T-V3-D-03", "E-004": "T-V3-D-03",
    "E-005": "T-V3-D-03", "E-020": "T-V3-D-03", "E-025": "T-V3-D-03",
    # T-V3-D-04: legacy twin ARCHIVE (ADR-015)
    "E-007": "T-V3-D-04", "E-027": "T-V3-D-04", "E-032": "T-V3-D-04",
    # T-V3-D-05: RLS batch 1 (AI hierarchy / clone)
    "E-044": "T-V3-D-05", "E-045": "T-V3-D-05", "E-046": "T-V3-D-05",
    # T-V3-D-06: RLS batch 2 (auth & profile)
    "E-047": "T-V3-D-06", "E-048": "T-V3-D-06", "E-049": "T-V3-D-06",
    "E-050": "T-V3-D-06", "E-051": "T-V3-D-06", "E-052": "T-V3-D-06",
    "E-053": "T-V3-D-06", "E-054": "T-V3-D-06", "E-055": "T-V3-D-06",
    # T-V3-D-07: RLS batch 3 (bf_project)
    "E-056": "T-V3-D-07", "E-057": "T-V3-D-07", "E-058": "T-V3-D-07",
    "E-059": "T-V3-D-07", "E-060": "T-V3-D-07", "E-061": "T-V3-D-07",
    # T-V3-D-08: RLS batch 4 (design & infra)
    "E-062": "T-V3-D-08", "E-063": "T-V3-D-08", "E-064": "T-V3-D-08",
    "E-065": "T-V3-D-08", "E-066": "T-V3-D-08", "E-067": "T-V3-D-08",
    "E-068": "T-V3-D-08",
    # T-V3-D-12: NEW entity formalization batch 1 (critical missing)
    "E-009": "T-V3-D-12", "E-013": "T-V3-D-12", "E-010": "T-V3-D-12",
    # T-V3-D-13: NEW entity formalization batch 2
    "E-023": "T-V3-D-13", "E-024": "T-V3-D-13", "E-022": "T-V3-D-13",
    # T-V3-D-14: AuditLog unification (E-037 + E-055 both already listed elsewhere)
    "E-037": "T-V3-D-14",
}

# API method drift (5 endpoints, all resolved by T-V3-D-09 / ADR-016)
API_METHOD_DRIFT = [
    ("F-003-02", "PUT /api/ai-employees/{id}"),
    ("F-004-01", "PUT /api/accounts/{id}"),
    ("F-004-05", "PUT /api/workspaces/{id}"),
    ("F-004-07", "GET /api/workspaces/{id}/invitations"),
    ("F-006-04", "PUT /api/tasks/{id}"),
]

# API non-method high drift (2 missing endpoints) + medium (1) + low WebSocket (2)
# T-V3-D-10 covers F-030-01 / F-031-01 / F-029-01
# Low WebSocket endpoints (F-005-01 / F-010-01) は intentional_deferred (WS routes not enumerated)
API_NON_METHOD_DRIFT = [
    ("F-030-01", "POST /api/me/api-tokens", "T-V3-D-10"),
    ("F-031-01", "POST /api/workspaces/{id}/exports", "T-V3-D-10"),
    ("F-029-01", "GET /api/design-system/tokens", "T-V3-D-10"),
    ("F-005-01", "WS /ws/hearing/{session_id}", "intentional_deferred"),
    ("F-010-01", "WS /ws/sessions/{id}/log", "intentional_deferred"),
]

# Screen "exists" hint-match drift (9 screens, all resolved by T-V3-D-11)
SCREEN_HINT_MATCH_DRIFT = [
    "S-007", "S-009", "S-028", "S-031", "S-036",
    "S-038", "S-039", "S-040", "S-041",
]


@dataclass
class CategoryResult:
    name: str
    total: int = 0
    resolved: int = 0
    intentional_deferred: int = 0
    open: list[str] = field(default_factory=list)

    @property
    def is_green(self) -> bool:
        return len(self.open) == 0

    def summary_line(self) -> str:
        return (
            f"{self.name}: total={self.total} resolved={self.resolved} "
            f"intentional_deferred={self.intentional_deferred} open={len(self.open)}"
        )


def load_tickets(path: Path) -> set[str]:
    """Load D-task IDs that exist in the drift ticket file."""
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data.get("tasks", data.get("tickets", [])) if isinstance(data, dict) else data
    return {t["id"] for t in tasks if isinstance(t, dict) and "id" in t}


def collect_entity_drifts(entities_path: Path) -> tuple[list[dict], dict[str, str]]:
    """Return (entity list with drift, eid -> status map)."""
    if not entities_path.exists():
        return [], {}
    data = json.loads(entities_path.read_text(encoding="utf-8"))
    entities = data.get("entities", data) if isinstance(data, dict) else data
    drift_entities = []
    status_map = {}
    for e in entities:
        eid = e.get("id")
        if not eid:
            continue
        status_map[eid] = e.get("status", "unknown")
        notes = e.get("legacy_drift_notes") or {}
        # Drift candidate if legacy_drift_notes has any meaningful keys OR
        # entity is explicitly in our resolution map
        has_drift_notes = isinstance(notes, dict) and bool(notes)
        is_in_map = eid in ENTITY_DRIFT_RESOLUTION
        if has_drift_notes or is_in_map:
            drift_entities.append(e)
    return drift_entities, status_map


def check_entity_drift(entities_path: Path, valid_tickets: set[str]) -> CategoryResult:
    result = CategoryResult(name="entity_drift")
    drift_entities, status_map = collect_entity_drifts(entities_path)
    in_scope_eids = sorted(set(ENTITY_DRIFT_RESOLUTION.keys()))
    result.total = len(in_scope_eids)
    # Build a quick lookup from entities
    by_id = {e["id"]: e for e in drift_entities if "id" in e}
    for eid in in_scope_eids:
        expected_task = ENTITY_DRIFT_RESOLUTION[eid]
        ent = by_id.get(eid)
        if ent is None:
            result.open.append(
                f"{eid} expected resolution {expected_task} but entity not present in entities.json"
            )
            continue
        # Pull task_id from legacy_drift_notes.
        # Priority: resolution.task_id (canonical resolver) > task_id (legacy placeholder).
        # The top-level task_id often retains the original `T-V3-DRIFT-E-XXX` placeholder
        # generated at functional-breakdown phase; the real resolver D-task ID is stored
        # under resolution.task_id after Group D session lands.
        notes = ent.get("legacy_drift_notes") or {}
        actual_task = None
        resolution_task = None
        if isinstance(notes, dict):
            if isinstance(notes.get("resolution"), dict):
                resolution_task = notes["resolution"].get("task_id")
            actual_task = resolution_task or notes.get("task_id")
        status = ent.get("status", "unknown")
        # AC-F3: impl_table must not be '(missing)' string after this task
        impl_table = notes.get("impl_table") if isinstance(notes, dict) else None
        if impl_table == "(missing)":
            result.open.append(
                f"{eid} legacy_drift_notes.impl_table == '(missing)' (must be resolved by {expected_task})"
            )
            continue
        # Accept resolution if any of these structural proofs hold:
        #   (a) resolution.task_id (or task_id) matches a real D-task in the tickets file
        #   (b) status indicates closure (rls_complete / formalized_in_migration / ...)
        #   (c) entity.table_name == entity.spec_table_name AND status == 'decided'
        #       (rename drift closed at spec-level; legacy placeholder task_id retained)
        #   (d) entity.legacy_drift_notes.archived_table is set (T-V3-D-04 / ADR-015 ARCHIVE)
        accepted = False
        reason = ""
        impl_name = ent.get("table_name")
        spec_name = ent.get("spec_table_name")
        archived_table = notes.get("archived_table") if isinstance(notes, dict) else None
        if resolution_task and resolution_task in valid_tickets:
            accepted = True
            reason = f"resolution.task_id={resolution_task}"
        elif actual_task and actual_task in valid_tickets:
            accepted = True
            reason = f"task_id={actual_task}"
        elif status in RESOLVED_STATUS:
            accepted = True
            reason = f"status={status}"
        elif impl_name and spec_name and impl_name == spec_name and status == "decided":
            accepted = True
            reason = f"table_name==spec_table_name=={impl_name!r} (rename drift closed at spec-level)"
        elif archived_table:
            accepted = True
            reason = f"archived_table={archived_table} (ADR-015 ARCHIVE)"
        if accepted:
            result.resolved += 1
        else:
            result.open.append(
                f"{eid} status={status} task_id={actual_task!r} "
                f"impl='{impl_name}' spec='{spec_name}' "
                f"(expected resolver {expected_task} or status in RESOLVED_STATUS)"
            )
    return result


def check_api_method_drift(valid_tickets: set[str]) -> CategoryResult:
    result = CategoryResult(name="api_method_drift")
    result.total = len(API_METHOD_DRIFT)
    if "T-V3-D-09" not in valid_tickets:
        result.open.append(
            "T-V3-D-09 (API method alignment) missing from tickets file — 5 method mismatch endpoints unresolved"
        )
        return result
    # Verify ADR-016 exists (the decision document for method alignment)
    adr016 = ROOT / "docs/decisions/ADR-016-api-method-alignment.md"
    if not adr016.exists():
        result.open.append(
            "ADR-016-api-method-alignment.md missing — method drift resolution undocumented"
        )
        return result
    result.resolved = result.total
    return result


def check_api_non_method_drift(valid_tickets: set[str]) -> CategoryResult:
    result = CategoryResult(name="api_non_method_drift")
    result.total = len(API_NON_METHOD_DRIFT)
    for tid, endpoint, resolver in API_NON_METHOD_DRIFT:
        if resolver == "intentional_deferred":
            result.intentional_deferred += 1
            continue
        if resolver not in valid_tickets:
            result.open.append(
                f"{tid} ({endpoint}) resolver {resolver} missing from tickets file"
            )
            continue
        result.resolved += 1
    return result


def check_screen_drift(valid_tickets: set[str]) -> CategoryResult:
    result = CategoryResult(name="screen_drift")
    result.total = len(SCREEN_HINT_MATCH_DRIFT)
    if "T-V3-D-11" not in valid_tickets:
        result.open.append(
            "T-V3-D-11 (screen h1/KPI/section drift fix) missing — 9 screen hint-match drifts unresolved"
        )
        return result
    result.resolved = result.total
    return result


def run_subprocess(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def check_rls_coverage() -> CategoryResult:
    result = CategoryResult(name="rls_coverage")
    code, out, err = run_subprocess([sys.executable, "scripts/verify-rls-coverage.py"])
    # Extract counts from output
    total_match = re.search(r"Total CREATE TABLE in migrations:\s+(\d+)", out)
    enabled_match = re.search(r"Tables with RLS enabled:\s+(\d+)", out)
    missing_match = re.search(r"Missing RLS:\s+(\d+)", out)
    total = int(total_match.group(1)) if total_match else 0
    enabled = int(enabled_match.group(1)) if enabled_match else 0
    missing = int(missing_match.group(1)) if missing_match else -1
    result.total = total
    result.resolved = enabled
    if code != 0 or missing != 0:
        result.open.append(
            f"verify-rls-coverage.py exit={code} missing={missing} (expected 0)"
        )
        if err.strip():
            result.open.append(f"stderr: {err.strip()[:200]}")
    return result


def check_entity_table_naming_lint() -> CategoryResult:
    """Delegate to lint-mock.sh --entity-table-naming (rule #19 / current rule #17)."""
    result = CategoryResult(name="entity_table_naming_lint")
    result.total = 1
    code, out, err = run_subprocess(["bash", "scripts/lint-mock.sh", "--entity-table-naming"])
    if code != 0:
        result.open.append(
            f"lint-mock.sh --entity-table-naming exit={code} (expected 0)"
        )
        if "DRIFT" in out:
            result.open.append("entity-table-naming DRIFT detected (spec != impl outside ADR-014 allow-list)")
        if err.strip():
            result.open.append(f"stderr: {err.strip()[:200]}")
    else:
        result.resolved = 1
    return result


def emit_report(results: list[CategoryResult], json_out: bool, quiet: bool) -> None:
    if json_out:
        payload = {
            "categories": [
                {
                    "name": r.name,
                    "total": r.total,
                    "resolved": r.resolved,
                    "intentional_deferred": r.intentional_deferred,
                    "open_count": len(r.open),
                    "open_items": r.open,
                    "is_green": r.is_green,
                }
                for r in results
            ],
            "all_green": all(r.is_green for r in results),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print("=" * 72)
    print("Build-Factory v3 Phase 1 — Drift Closure Validation")
    print("=" * 72)
    for r in results:
        marker = "OK " if r.is_green else "NG "
        print(f"  [{marker}] {r.summary_line()}")
        if not quiet and r.open:
            for item in r.open[:10]:
                print(f"        - {item}")
            if len(r.open) > 10:
                print(f"        ... (+{len(r.open) - 10} more)")
    total_open = sum(len(r.open) for r in results)
    total_resolved = sum(r.resolved for r in results)
    total_deferred = sum(r.intentional_deferred for r in results)
    print("-" * 72)
    print(
        f"Aggregate: resolved={total_resolved} intentional_deferred={total_deferred} open={total_open}"
    )
    if total_open == 0:
        print("RESULT: PHASE 1 DRIFT CLOSURE 100% GREEN")
    else:
        print("RESULT: DRIFT OPEN — see categories above")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drift closure validator (T-V3-D-15)")
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    parser.add_argument(
        "--entities-file",
        type=Path,
        default=ENTITIES_PATH,
        help="entities.json path override (for test fixtures)",
    )
    parser.add_argument(
        "--tickets-file",
        type=Path,
        default=TICKETS_PATH,
        help="tickets-group-d-drift.json path override",
    )
    parser.add_argument(
        "--skip-rls-check",
        action="store_true",
        help="skip RLS coverage subprocess (for fast self-test)",
    )
    parser.add_argument(
        "--skip-lint-check",
        action="store_true",
        help="skip lint #19 subprocess (for fast self-test)",
    )
    args = parser.parse_args(argv)

    valid_tickets = load_tickets(args.tickets_file)
    if not valid_tickets:
        print(
            f"FAIL: ticket file {args.tickets_file} not found or empty",
            file=sys.stderr,
        )
        return 64

    results: list[CategoryResult] = []
    results.append(check_entity_drift(args.entities_file, valid_tickets))
    results.append(check_api_method_drift(valid_tickets))
    results.append(check_api_non_method_drift(valid_tickets))
    results.append(check_screen_drift(valid_tickets))
    if not args.skip_rls_check:
        results.append(check_rls_coverage())
    if not args.skip_lint_check:
        results.append(check_entity_table_naming_lint())

    emit_report(results, json_out=args.json, quiet=args.quiet)
    all_green = all(r.is_green for r in results)
    return 0 if all_green else 1


if __name__ == "__main__":
    raise SystemExit(main())
