#!/usr/bin/env python3
"""generate-drift-tickets — lint 違反 (drift) を自動で fix task に変換する.

T-FOUNDATION-05 (Group A-2 / Foundation phase) の実体.
integration v3-core の主軸 3 (drift fix → drift fix queue 流し込み) を担う:
  W<source> 完了集計の lint 違反 JSON を読み、各 violation を 1 件の
  T-DRIFT-W<source>-<seq> task に変換し、W<target> の drift fix queue
  (BF profile: Group D) に投入できる drift-tickets-W<source>.json を出力する.

入力 lint-output schema (T-FOUNDATION-02 出力互換):
  {
    "drift_count": int,
    "drifts": [
      {
        "rule_id": str,         # optional (省略時は "mock-impl-diff" にフォールバック)
        "screen_id": str,
        "field": str,
        "mock_value": Any,
        "impl_value": Any,
        "severity": "error" | "warning",
        "kind": str,            # optional
        "error": str            # optional (severity=error 時の補足)
      },
      ...
    ]
  }
top-level が list でも受け付ける ([entry, entry, ...] の形)。

出力 schema (v3 tickets.json の tasks[] と byte-identical compatible):
  {
    "version": "v3",
    "project": "<profile project name>",
    "source_wave": "W<source>",
    "target_wave": "W<target>",
    "generated_at": "YYYY-MM-DD",
    "tasks": [
      { id, title, category, label, ..., acceptance_criteria: {3-tier} }, ...
    ]
  }

Usage:
  python3 scripts/generate-drift-tickets.py \
    --lint-output drift.json \
    --source-wave W1 --target-wave W2 \
    --output docs/task-decomposition/2026-05-16_v3/drift-tickets-W1.json

  python3 scripts/generate-drift-tickets.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDIT_DATE = "2026-05-16"

# ----------------------------------------------------------------
# rule_id → deliverable_layer / impl_file_template mapping
# ----------------------------------------------------------------
# v3-core (skills/integration/references/v3-core.md) + BF profile に基づく.
# 未知 rule_id は warning + skip (AC: UNWANTED 未知 rule_id).
_RULE_MAPPING: dict[str, dict[str, str]] = {
    "mock-impl-diff": {
        "deliverable_layer": "ui",
        "impl_file_template": "frontend/src/screens/{screen_id}.tsx",
    },
    "screens-API": {
        "deliverable_layer": "backend",
        "impl_file_template": "backend/app/routers/{screen_id}.py",
    },
    "entity-table-naming": {
        "deliverable_layer": "backend",
        "impl_file_template": "backend/app/models/{screen_id}.py",
    },
}

# BF profile default group / spec_link
_DEFAULT_GROUP_BF = "D"
_DEFAULT_GROUP_GENERIC = "drift_fix_queue"
_DEFAULT_SPEC_LINKS = [
    "skills/integration/references/v3-core.md#主軸-3-drift-fix--drift-fix-queue-流し込み",
]

# Tier 3 標準 regression gate (BF profile preset)
_TIER3_REGRESSION_BF = [
    "bash scripts/lint-mock.sh PASS",
    "python3 scripts/validate-tickets.py PASS",
    "python3 scripts/lint-mock-impl-diff.py --strict PASS",
    "bash scripts/pre-commit-check.sh PASS",
    "pyright --strict 0 errors (backend) / tsc --noEmit 0 errors (frontend)",
    "bash scripts/audit-md-check.sh <task_id> PASS",
]
# generic (profile 不在時) — BF 固有 script を仮 placeholder で抽象化
_TIER3_REGRESSION_GENERIC = [
    "lint_runner PASS",
    "ac_validator PASS",
    "mock_impl_diff --strict PASS",
    "pre-commit check PASS",
    "static type check PASS",
    "audit_md_check PASS",
]


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ----------------------------------------------------------------
# Schema validation (lint-output)
# ----------------------------------------------------------------


_REQUIRED_FIELDS = ("screen_id", "field", "mock_value", "impl_value", "severity")


def _validate_lint_output(data: Any) -> list[dict[str, Any]]:
    """lint-output JSON を検証して entries (list) を返す.

    Raises:
        ValueError: schema 不正時.
    """
    raw_entries: object
    if isinstance(data, list):
        raw_entries = list(data)  # type: ignore[arg-type]
    elif isinstance(data, dict):
        d: dict[str, Any] = data  # type: ignore[assignment]
        if "drifts" in d:
            raw_entries = d["drifts"]
        elif "violations" in d:  # 別名サポート
            raw_entries = d["violations"]
        else:
            raise ValueError(
                "invalid lint output schema: object must have 'drifts' or 'violations' key"
            )
    else:
        raise ValueError("invalid lint output schema: must be array or object")

    if not isinstance(raw_entries, list):
        raise ValueError("invalid lint output schema: 'drifts' must be an array")

    entries: list[dict[str, Any]] = []
    for idx, e in enumerate(raw_entries):  # type: ignore[arg-type]
        if not isinstance(e, dict):
            raise ValueError(
                f"invalid lint output schema: entry [{idx}] is not an object"
            )
        e_typed: dict[str, Any] = e  # type: ignore[assignment]
        missing = [f for f in _REQUIRED_FIELDS if f not in e_typed]
        if missing:
            raise ValueError(
                f"invalid lint output schema: entry [{idx}] missing fields: "
                f"{', '.join(missing)}"
            )
        entries.append(e_typed)

    return entries


# ----------------------------------------------------------------
# Profile loading (minimal: read mapping table from BF profile MD or use defaults)
# ----------------------------------------------------------------


def _load_profile(profile_path: Path | None) -> dict[str, Any]:
    """profile から group / spec_link / tier3 regression を取得.

    profile MD は人間可読のため正規 parse はせず、検出キーワードで識別する.
    profile 不在 / parse 不能 -> generic defaults.
    """
    if profile_path is None or not profile_path.exists():
        return {
            "project": "generic",
            "group": _DEFAULT_GROUP_GENERIC,
            "tier3_regression": _TIER3_REGRESSION_GENERIC,
            "spec_links": _DEFAULT_SPEC_LINKS,
            "audit_dir": "docs/audit/{date}_v3",
            "branch_prefix": "claude/",
        }

    # BF profile detection
    text = profile_path.read_text(encoding="utf-8", errors="replace")
    # spec_links に絶対 path が混入しないよう、REPO_ROOT 配下なら relative に正規化
    try:
        rel = profile_path.resolve().relative_to(REPO_ROOT)
        profile_rel = str(rel)
    except ValueError:
        profile_rel = profile_path.name
    if "Build-Factory" in text and "Group D" in text:
        return {
            "project": "Build-Factory",
            "group": _DEFAULT_GROUP_BF,
            "tier3_regression": _TIER3_REGRESSION_BF,
            "spec_links": _DEFAULT_SPEC_LINKS + [profile_rel],
            "audit_dir": "docs/audit/{date}_v3",
            "branch_prefix": "claude/",
        }
    return {
        "project": "generic",
        "group": _DEFAULT_GROUP_GENERIC,
        "tier3_regression": _TIER3_REGRESSION_GENERIC,
        "spec_links": _DEFAULT_SPEC_LINKS,
        "audit_dir": "docs/audit/{date}_v3",
        "branch_prefix": "claude/",
    }


# ----------------------------------------------------------------
# drift task building (per violation)
# ----------------------------------------------------------------


def _infer_rule_id(entry: dict[str, Any]) -> str:
    """rule_id が無ければ T-02 既定の 'mock-impl-diff' を仮定."""
    rid = entry.get("rule_id")
    if isinstance(rid, str) and rid:
        return rid
    return "mock-impl-diff"


def _build_impl_file(rule_id: str, screen_id: str) -> str:
    tmpl = _RULE_MAPPING.get(rule_id, {}).get(
        "impl_file_template", "<unknown>/{screen_id}"
    )
    return tmpl.format(screen_id=screen_id)


def _build_task(
    *,
    seq: int,
    source_wave: str,
    target_wave: str,
    entry: dict[str, Any],
    rule_id: str,
    profile: dict[str, Any],
    date: str,
) -> dict[str, Any]:
    """1 violation -> 1 drift task object."""
    layer = _RULE_MAPPING[rule_id]["deliverable_layer"]
    screen_id = entry["screen_id"]
    field = entry["field"]
    mock_value = entry["mock_value"]
    impl_value = entry["impl_value"]
    severity = entry["severity"]
    kind = entry.get("kind", "value_mismatch")

    task_id = f"T-DRIFT-{source_wave}-{seq:03d}"
    title = f"Fix drift: {field} for {screen_id}"
    impl_file = _build_impl_file(rule_id, screen_id)
    audit_md_path = profile["audit_dir"].format(date=date) + f"/{task_id}.md"
    branch = f"{profile['branch_prefix']}{task_id}"

    # Tier 1 (structural) — 元 violation を逐語的に保存
    structural = [
        (
            f"STATE-DRIVEN: While the violation persists, the system shall expose "
            f"a drift entry matching the source: "
            f"rule_id={rule_id}, screen_id={screen_id}, field={field}, "
            f"mock_value={json.dumps(mock_value, ensure_ascii=False)}, "
            f"impl_value={json.dumps(impl_value, ensure_ascii=False)}, "
            f"severity={severity}, kind={kind}"
        )
    ]

    # Tier 2 (functional) — EARS UBIQUITOUS の整合化要求 + UNWANTED 異常系
    mock_repr = json.dumps(mock_value, ensure_ascii=False)
    functional = [
        (
            f"UBIQUITOUS: The system shall align {field} between mock({screen_id}) "
            f"and impl({impl_file}) to value: {mock_repr}"
        ),
        (
            f"EVENT-DRIVEN: When the impl file is updated, "
            f"the rule_id={rule_id} lint check shall report 0 violations "
            f"for this (screen_id, field) pair."
        ),
        (
            f"UNWANTED: If the alignment regresses, "
            f"the CI gate shall fail with rule_id={rule_id} drift re-detected."
        ),
    ]

    # Tier 3 (regression) — profile の標準 gate を逐語コピー
    regression = list(profile["tier3_regression"])

    return {
        "id": task_id,
        "title": title,
        "category": "infra",
        "label": "FIX",
        "feature_id": None,
        "screen_ids": [screen_id],
        "entity_ids": [],
        "legacy_task_id": None,
        "phase": "Foundation",
        "wave": target_wave,
        "wave_priority": "Second",
        "group": profile["group"],
        "deliverable_layer": layer,
        "estimate_hours": 1,
        "estimate_sessions": 1,
        "depends_on": [],
        "files_changed": [impl_file],
        "work_package_boundary": {
            "editable": [impl_file],
            "shared_no_concurrent_edit": [],
            "readonly": [],
            "forbidden": [],
        },
        "acceptance_criteria": {
            "structural": structural,
            "functional": functional,
            "regression": regression,
        },
        "access_policies_required": [],
        "spec_links": profile["spec_links"],
        "audit_md_path": audit_md_path,
        "branch": branch,
        "drift_source": {
            "source_wave": source_wave,
            "rule_id": rule_id,
            "screen_id": screen_id,
            "field": field,
            "mock_value": mock_value,
            "impl_value": impl_value,
            "severity": severity,
            "kind": kind,
        },
        "risk_flags": ["drift_fix"],
    }


# ----------------------------------------------------------------
# Main generation
# ----------------------------------------------------------------


def generate(
    *,
    lint_output: dict[str, Any] | list[Any],
    source_wave: str,
    target_wave: str,
    profile: dict[str, Any],
    date: str,
    warn_stream: Any = sys.stderr,
) -> dict[str, Any]:
    """drift-tickets.json 全体 (dict) を組み立てて返す."""
    entries = _validate_lint_output(lint_output)
    tasks: list[dict[str, Any]] = []
    seq = 1

    for entry in entries:
        rule_id = _infer_rule_id(entry)
        if rule_id not in _RULE_MAPPING:
            print(
                f"warning: unknown rule_id '{rule_id}' for screen_id="
                f"{entry.get('screen_id', '?')} field={entry.get('field', '?')} "
                "— skipped",
                file=warn_stream,
            )
            continue
        task = _build_task(
            seq=seq,
            source_wave=source_wave,
            target_wave=target_wave,
            entry=entry,
            rule_id=rule_id,
            profile=profile,
            date=date,
        )
        tasks.append(task)
        seq += 1

    return {
        "version": "v3",
        "project": profile["project"],
        "source_wave": source_wave,
        "target_wave": target_wave,
        "generated_at": date,
        "summary": {
            "total_tasks": len(tasks),
            "by_deliverable_layer": _count_by_layer(tasks),
            "by_rule_id": _count_by_rule(tasks),
        },
        "tasks": tasks,
    }


def _count_by_layer(tasks: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in tasks:
        layer = t["deliverable_layer"]
        out[layer] = out.get(layer, 0) + 1
    return out


def _count_by_rule(tasks: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in tasks:
        rid = t["drift_source"]["rule_id"]
        out[rid] = out.get(rid, 0) + 1
    return out


# ----------------------------------------------------------------
# Output JSON dumping (deterministic / byte-identical golden test)
# ----------------------------------------------------------------


def _dump_json(data: dict[str, Any]) -> str:
    """deterministic dumps: indent=2 + sort_keys=False (insertion order) + LF + 末尾 LF."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# ----------------------------------------------------------------
# Self-test
# ----------------------------------------------------------------


def _run_self_test() -> int:
    fixtures_dir = (
        Path(__file__).resolve().parent / "tests" / "fixtures" / "drift-tickets"
    )
    lint_input_path = fixtures_dir / "lint-output-3-violations.json"
    expected_path = fixtures_dir / "expected-tickets.json"

    if not lint_input_path.exists():
        print(f"[self-test] FAIL: fixture not found: {lint_input_path}")
        return 1
    if not expected_path.exists():
        print(f"[self-test] FAIL: expected golden not found: {expected_path}")
        return 1

    lint_data = json.loads(lint_input_path.read_text(encoding="utf-8"))
    profile_path = (
        REPO_ROOT
        / "skills"
        / "integration"
        / "references"
        / "profiles"
        / "build-factory.md"
    )
    profile = _load_profile(profile_path)

    # 固定日付で再現性を担保
    result = generate(
        lint_output=lint_data,
        source_wave="W1",
        target_wave="W2",
        profile=profile,
        date=DEFAULT_AUDIT_DATE,
    )
    actual = _dump_json(result)
    expected = expected_path.read_text(encoding="utf-8")

    if actual != expected:
        print("[self-test] FAIL: output != expected golden")
        # diff 行頭を表示 (最大 20 行)
        a_lines = actual.splitlines()
        e_lines = expected.splitlines()
        n = max(len(a_lines), len(e_lines))
        shown = 0
        for i in range(n):
            a = a_lines[i] if i < len(a_lines) else "<missing>"
            e = e_lines[i] if i < len(e_lines) else "<missing>"
            if a != e:
                print(f"  line {i + 1}:")
                print(f"    expected: {e}")
                print(f"    actual:   {a}")
                shown += 1
                if shown >= 20:
                    print("  ... (truncated)")
                    break
        return 1

    print(f"[self-test] PASS: 3-violation fixture -> {len(result['tasks'])} drift tasks")
    print("[self-test] PASS: output byte-identical to expected-tickets.json")
    return 0


# ----------------------------------------------------------------
# CLI
# ----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "generate-drift-tickets — lint 違反 JSON から drift fix task 群を生成する"
        )
    )
    parser.add_argument("--lint-output", type=Path, help="T-02 出力 JSON path")
    parser.add_argument("--source-wave", type=str, help="drift が検出された wave (例: W1)")
    parser.add_argument("--target-wave", type=str, help="drift fix を実行する wave (例: W2)")
    parser.add_argument("--output", type=Path, help="drift-tickets-W<source>.json 出力先")
    parser.add_argument(
        "--profile",
        type=Path,
        default=REPO_ROOT
        / "skills"
        / "integration"
        / "references"
        / "profiles"
        / "build-factory.md",
        help="profile MD (BF profile を default に group / tier3 regression / audit_dir 等を解決)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="generated_at に埋め込む日付 (YYYY-MM-DD, default: 今日)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="3 violation fixture で expected-tickets.json と byte-identical 一致を検証",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    # CLI 引数チェック (self-test 以外は全部必須)
    missing = [
        n
        for n, v in [
            ("--lint-output", args.lint_output),
            ("--source-wave", args.source_wave),
            ("--target-wave", args.target_wave),
            ("--output", args.output),
        ]
        if v is None
    ]
    if missing:
        print(
            f"error: missing required argument(s): {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2

    if not args.lint_output.exists():
        print(
            f"error: --lint-output does not exist: {args.lint_output}", file=sys.stderr
        )
        return 2

    try:
        lint_data = json.loads(args.lint_output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"invalid lint output schema: {exc}", file=sys.stderr)
        return 1

    profile = _load_profile(args.profile)
    date = args.date or _now_date()

    try:
        result = generate(
            lint_output=lint_data,
            source_wave=args.source_wave,
            target_wave=args.target_wave,
            profile=profile,
            date=date,
        )
    except ValueError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    output_text = _dump_json(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_text, encoding="utf-8")
    print(
        f"generated {len(result['tasks'])} drift task(s) -> {args.output} "
        f"(violations={result['summary']['total_tasks']})"
    )

    # violation 0 件は AC 上 exit 0 (空 tasks 配列で正常終了)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
