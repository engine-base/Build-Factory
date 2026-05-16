#!/usr/bin/env python3
"""tickets.json の必須メタデータを検証し、不足を一覧化する。

各タスクが備えるべきメタ:
- id, title, sprint, feature, layer, label : 必須 (既存)
- acceptance_criteria : EARS 5 形式の AC を最低 3 件
- mock_link : 関連モック (S-XXX のパス) — UI タスクのみ
- spec_link : 関連仕様書 (M-X / requirements-v1.md の anchor)
- existing_files : REUSE / REFACTOR / ARCHIVE の場合は対象ファイル
- entities : 関連 DB テーブル

CI / 実装着手前に必ず実行する。

v3 拡張 (T-FOUNDATION-05): --check-file <path> で任意 tickets.json を検証する.
v3 schema (acceptance_criteria が dict / 3-tier structural/functional/regression) も
受け付ける. v3 では sprint/feature/layer は無いが代わりに wave/phase/deliverable_layer
を要求する.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS_PATH = ROOT / "docs/task-decomposition/2026-05-09_v1/tickets.json"


def validate_ticket(t: dict) -> list[str]:
    issues: list[str] = []
    label = t.get("label", "")

    # 必須フィールド (既存)
    # sprint は 0 (Sprint 0) も valid なので、None or キー欠落のみを「missing」と判定する
    for f in ["id", "title", "sprint", "feature", "layer", "label"]:
        if t.get(f) is None or (f != "sprint" and not t.get(f)):
            issues.append(f"missing {f}")

    # 必須フィールド (今回追加)
    if "acceptance_criteria" not in t or not t["acceptance_criteria"]:
        issues.append("missing acceptance_criteria (EARS)")
    else:
        ac = t["acceptance_criteria"]
        if not isinstance(ac, list):
            issues.append("acceptance_criteria is not a list")
        elif len(ac) < 3:
            issues.append(f"acceptance_criteria has only {len(ac)} items (min 3)")
        else:
            # EARS 形式の簡易チェック
            unwanted_count = sum(
                1 for a in ac
                if isinstance(a, dict) and a.get("type", "").upper() == "UNWANTED"
            )
            if unwanted_count == 0:
                issues.append("no UNWANTED-form AC (異常系の網羅漏れ)")

    if "spec_link" not in t:
        issues.append("missing spec_link")

    # UI タスクには mock_link 必須
    feature = t.get("feature", "")
    if any(ui_marker in feature for ui_marker in ["F-005", "F-006", "F-007", "F-008", "F-010", "F-011", "F-012", "F-013", "F-024"]):
        if "mock_link" not in t:
            issues.append("missing mock_link (UI タスク)")

    # REUSE/REFACTOR/ARCHIVE には existing_files 必須
    if label in ("REUSE", "REFACTOR", "ARCHIVE"):
        if "existing_files" not in t:
            issues.append(f"missing existing_files ({label})")

    return issues


# ----------------------------------------------------------------
# v3 schema validator (--check-file <path> 専用)
# ----------------------------------------------------------------

_V3_REQUIRED_FIELDS = (
    "id",
    "title",
    "category",
    "label",
    "phase",
    "wave",
    "group",
    "deliverable_layer",
    "files_changed",
    "work_package_boundary",
    "acceptance_criteria",
    "audit_md_path",
    "branch",
)


def _validate_v3_ticket(t: dict) -> list[str]:
    """v3 (3-tier AC) schema 検証. validate_ticket とは別系統."""
    issues: list[str] = []

    for f in _V3_REQUIRED_FIELDS:
        if f not in t:
            issues.append(f"missing {f}")
            continue
        # None 許容: feature_id / legacy_task_id 等は task によって None
        if t[f] is None and f not in ("id", "title"):
            continue
        if f in ("files_changed",) and not isinstance(t[f], list):
            issues.append(f"{f} must be a list")

    # acceptance_criteria は 3-tier dict
    ac = t.get("acceptance_criteria")
    if not isinstance(ac, dict):
        issues.append("acceptance_criteria must be a dict {structural, functional, regression}")
    else:
        for tier in ("structural", "functional", "regression"):
            if tier not in ac:
                issues.append(f"acceptance_criteria.{tier} missing")
            elif not isinstance(ac[tier], list):
                issues.append(f"acceptance_criteria.{tier} must be a list")
        # functional は最低 1 件必要 (3-tier core)
        if isinstance(ac.get("functional"), list) and len(ac["functional"]) == 0:
            issues.append("acceptance_criteria.functional is empty (min 1 EARS AC)")
        # regression も最低 1 件 (CI gate)
        if isinstance(ac.get("regression"), list) and len(ac["regression"]) == 0:
            issues.append("acceptance_criteria.regression is empty (min 1 gate)")

    # work_package_boundary は 4 key dict
    wpb = t.get("work_package_boundary")
    if isinstance(wpb, dict):
        for k in ("editable", "shared_no_concurrent_edit", "readonly", "forbidden"):
            if k not in wpb:
                issues.append(f"work_package_boundary.{k} missing")
            elif not isinstance(wpb[k], list):
                issues.append(f"work_package_boundary.{k} must be a list")
    else:
        issues.append("work_package_boundary must be a dict")

    return issues


def _check_file(path: Path) -> int:
    """任意 tickets.json を v3 schema で検証 (drift-tickets-W<N>.json 等も対象)."""
    if not path.exists():
        print(f"NG: file not found: {path}", file=sys.stderr)
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"NG: invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict) or "tasks" not in data:
        print("NG: top-level must be an object with 'tasks' array", file=sys.stderr)
        return 1
    tasks = data["tasks"]
    if not isinstance(tasks, list):
        print("NG: 'tasks' must be a list", file=sys.stderr)
        return 1

    total_issues = 0
    print("=" * 60)
    print(f"v3 tickets.json validation: {path}")
    print("=" * 60)
    print(f"Total tasks: {len(tasks)}")
    for t in tasks:
        issues = _validate_v3_ticket(t)
        if issues:
            total_issues += 1
            tid = t.get("id", "?")
            print(f"  {tid}: {', '.join(issues)}")
    if total_issues > 0:
        print(f"NG: {total_issues}/{len(tasks)} tasks have issues.")
        return 1
    print("OK: all tasks pass v3 schema validation.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="validate-tickets — tickets.json メタ + EARS AC を検証",
    )
    parser.add_argument(
        "--check-file",
        type=Path,
        default=None,
        help="v3 tickets.json (drift-tickets 等) を schema 検証する (legacy 経路 bypass)",
    )
    args = parser.parse_args()

    if args.check_file is not None:
        return _check_file(args.check_file)

    data = json.loads(TICKETS_PATH.read_text())
    tickets = data.get("tickets", [])
    critical = data.get("critical_path", [])

    total_issues = 0
    by_label: dict[str, int] = {}
    critical_issues: list[tuple[str, list[str]]] = []
    sample_issues: list[tuple[str, list[str]]] = []

    for t in tickets:
        issues = validate_ticket(t)
        if issues:
            total_issues += 1
            label = t.get("label", "?")
            by_label[label] = by_label.get(label, 0) + 1
            tid = t.get("id", "?")
            if tid in critical:
                critical_issues.append((tid, issues))
            elif len(sample_issues) < 5:
                sample_issues.append((tid, issues))

    print("=" * 60)
    print("tickets.json validation report")
    print("=" * 60)
    print(f"Total tickets       : {len(tickets)}")
    print(f"Tickets with issues : {total_issues}")
    print(f"Compliant tickets   : {len(tickets) - total_issues}")
    print()
    print("Issue count by label:")
    for label, count in sorted(by_label.items()):
        print(f"  {label:10s} : {count}")
    print()

    if critical_issues:
        print("CRITICAL PATH issues (要即対応):")
        for tid, issues in critical_issues:
            print(f"  {tid}:")
            for i in issues:
                print(f"    - {i}")
        print()

    if sample_issues:
        print("Sample non-critical issues (5 件まで表示):")
        for tid, issues in sample_issues:
            print(f"  {tid}: {', '.join(issues)}")

    if total_issues > 0:
        print()
        print(f"NG: {total_issues}/{len(tickets)} tickets need updates.")
        print("実装着手前に最低限クリティカルパスのタスクを補完すること。")
        return 1
    print("OK: all tickets pass validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
