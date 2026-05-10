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
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS_PATH = ROOT / "docs/task-decomposition/2026-05-09_v1/tickets.json"


def validate_ticket(t: dict) -> list[str]:
    issues: list[str] = []
    tid = t.get("id", "?")
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


def main() -> int:
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
    print(f"tickets.json validation report")
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
