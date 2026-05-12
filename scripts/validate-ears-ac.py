#!/usr/bin/env python3
"""T-025-01: EARS AC を JSON Schema で機械的に validate する.

既存 scripts/validate-tickets.py は heuristic check のみ. 本 script は
backend/schemas/ears_ac_schema.json の JSON Schema (draft-07) を使い、
type / text / pattern の構造的整合性を厳格 verify.

## Usage

  python3 scripts/validate-ears-ac.py                  # 全 tickets
  python3 scripts/validate-ears-ac.py --task-id T-001  # 単一タスク
  python3 scripts/validate-ears-ac.py --verbose        # 各 AC の結果出力
  python3 scripts/validate-ears-ac.py --strict         # warning も error 扱い

## Exit codes

  0 : 全 AC が schema valid
  1 : 1 件以上 invalid
  2 : argument error / schema 自体が invalid

## AC マッピング (T-025-01)

  AC-1 UBIQUITOUS    : JSON Schema (ears_ac_schema.json) で全タスク AC を validate.
  AC-2 EVENT-DRIVEN  : --task-id で単一 / --verbose で詳細 / --strict で warning 昇格.
  AC-3 STATE-DRIVEN  : read-only (tickets.json を mutate しない) / 既存 scripts と
                       並列 (validate-tickets.py 不変).
  AC-4 UNWANTED      : invalid schema 自身 → exit 2 / unknown --task-id → exit 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft7Validator, SchemaError
except ImportError:  # pragma: no cover
    print(
        "ERROR: jsonschema not installed. Run: pip install jsonschema>=4.0",
        file=sys.stderr,
    )
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "backend" / "schemas" / "ears_ac_schema.json"
TICKETS_PATH = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ──────────────────────────────────────────────────────────────────────
# Loaders
# ──────────────────────────────────────────────────────────────────────


def load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema not found: {SCHEMA_PATH}")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_tickets() -> dict:
    if not TICKETS_PATH.exists():
        raise FileNotFoundError(f"tickets not found: {TICKETS_PATH}")
    with open(TICKETS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────────────────────────────


def validate_ticket_ac(
    ticket: dict, validator: Draft7Validator,
) -> list[dict]:
    """Validate a single ticket's AC list. Returns list of issues."""
    tid = ticket.get("id", "?")
    issues: list[dict] = []
    ac_list = ticket.get("acceptance_criteria") or []
    if not isinstance(ac_list, list):
        issues.append({
            "task_id": tid, "ac_index": -1,
            "error": "acceptance_criteria is not a list",
        })
        return issues
    for i, ac in enumerate(ac_list):
        for err in validator.iter_errors(ac):
            issues.append({
                "task_id": tid,
                "ac_index": i,
                "ac_type": ac.get("type") if isinstance(ac, dict) else None,
                "error": err.message,
                "path": list(err.path),
            })
    return issues


def validate_all(
    tickets: dict,
    schema: dict,
    *,
    task_id_filter: str | None = None,
) -> tuple[int, int, list[dict]]:
    """Validate all tickets (or single task).

    Returns:
        (total_tickets_checked, total_ac_checked, issues_list)
    """
    validator = Draft7Validator(schema)
    total_tickets = 0
    total_ac = 0
    issues: list[dict] = []

    ticket_list = tickets.get("tickets") or []
    if task_id_filter:
        ticket_list = [t for t in ticket_list if t.get("id") == task_id_filter]
        if not ticket_list:
            issues.append({
                "task_id": task_id_filter, "ac_index": -1,
                "error": f"task_id not found: {task_id_filter}",
            })
            return (0, 0, issues)

    for t in ticket_list:
        total_tickets += 1
        ac_list = t.get("acceptance_criteria") or []
        total_ac += len(ac_list) if isinstance(ac_list, list) else 0
        issues.extend(validate_ticket_ac(t, validator))

    return (total_tickets, total_ac, issues)


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="T-025-01: EARS AC を JSON Schema で機械的検証.",
    )
    parser.add_argument("--task-id", type=str, default=None,
                        help="single task id (e.g., T-M27-02)")
    parser.add_argument("--verbose", action="store_true",
                        help="emit each AC validation result")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as errors (reserved for future)")
    parser.add_argument("--schema-only", action="store_true",
                        help="only validate the JSON Schema itself")
    args = parser.parse_args(argv)

    try:
        schema = load_schema()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot load schema: {e}", file=sys.stderr)
        return 2

    # schema 自身の validity (Draft 7) check
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as e:
        print(f"ERROR: schema is invalid: {e.message}", file=sys.stderr)
        return 2

    if args.schema_only:
        print("OK: schema is valid Draft-07")
        return 0

    try:
        tickets = load_tickets()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot load tickets: {e}", file=sys.stderr)
        return 2

    total_tickets, total_ac, issues = validate_all(
        tickets, schema, task_id_filter=args.task_id,
    )

    print("=" * 60)
    print("EARS AC validation (JSON Schema)")
    print("=" * 60)
    print(f"Schema      : {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    print(f"Tickets     : {TICKETS_PATH.relative_to(REPO_ROOT)}")
    if args.task_id:
        print(f"Filter      : task_id={args.task_id}")
    print(f"Checked     : {total_tickets} tickets / {total_ac} AC")
    print(f"Issues      : {len(issues)}")
    print()

    if args.verbose and issues:
        print("Issues detail:")
        for iss in issues:
            print(
                f"  - {iss['task_id']} AC[{iss.get('ac_index', '?')}] "
                f"({iss.get('ac_type', '?')}): {iss['error']}"
            )
        print()

    if issues:
        print(f"FAIL: {len(issues)} EARS AC violations detected")
        if not args.verbose:
            print("(use --verbose for per-AC detail)")
        return 1

    print("OK: all AC pass EARS JSON Schema validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
