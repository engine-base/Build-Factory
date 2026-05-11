#!/usr/bin/env python3
"""T-S0-13b: existing-inventory.json から .md レポートを生成."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
INV_JSON = REPO / "docs/audit/2026-05-10_v1/existing-inventory.json"
INV_MD = REPO / "docs/audit/2026-05-10_v1/existing-inventory.md"


def _resolve_feature(ticket_idx: dict, tid: str) -> str:
    return ticket_idx.get(tid, {}).get("feature", "?")


def main() -> None:
    data = json.loads(INV_JSON.read_text(encoding="utf-8"))
    summary = data["summary"]
    inventory = data["inventory"]
    orphans = data["orphan_tickets"]

    # tickets.json も読む (feature 取得)
    tickets = json.loads(
        (REPO / "docs/task-decomposition/2026-05-09_v1/tickets.json").read_text(encoding="utf-8")
    )["tickets"]
    ticket_idx = {t["id"]: t for t in tickets}

    by_label: dict[str, list[dict]] = defaultdict(list)
    for it in inventory:
        by_label[it["mapping_status"]].append(it)

    lines: list[str] = []
    lines.append("# T-S0-13b: 既存実装インベントリ監査結果 (再生成)")
    lines.append("")
    lines.append(f"- 監査 ID: `{summary['audit_id']}` (supersedes `{summary.get('supersedes', 'N/A')}`)")
    lines.append(f"- 再生成日: {summary['regenerated_at']}")
    scope = summary["scope"]
    lines.append(
        f"- 走査対象: routers={scope['routers_scanned']}, "
        f"services={scope['services_scanned']}, "
        f"integrations={scope.get('integrations_scanned', 0)}, "
        f"sandbox={scope.get('sandbox_scanned', 0)}, "
        f"migrations={scope['migrations_scanned']}, "
        f"合計 disk 上 {scope['total_files_on_disk']} 件"
    )
    lines.append(f"- 分類サマリ: {summary['counts_by_classification']}")
    lines.append(f"- **UNDETERMINED: {summary['undetermined_remaining']}** (AC-1 達成)")
    lines.append(f"- Orphan tickets (annotated): {summary['orphan_tickets_count']} 件")
    lines.append(f"- triage_needed: {summary['triage_needed_count']} 件 (BA review placeholder のみ)")
    lines.append(f"- Phase boundary annotation: {summary['phase_annotations_applied']} 件")
    lines.append("")

    # 分類別ファイル一覧
    lines.append("## 分類別ファイル一覧")
    lines.append("")
    for label in ("REFACTOR", "REUSE", "NEW"):
        items = by_label.get(label, [])
        if not items:
            continue
        lines.append(f"### {label} ({len(items)} 件)")
        lines.append("")
        # ticket id を含めて簡潔に
        for it in items[:200]:  # 最大 200 件を md に出す (残りは json 参照)
            tids = it.get("ticket_ids", [])
            primary = it.get("primary_ticket") or (tids[0] if tids else "?")
            feature = _resolve_feature(ticket_idx, primary)
            lines.append(f"- `{it['file_path']}` — {label} ticket `{primary}` ({feature})")
        if len(items) > 200:
            lines.append(f"... 他 {len(items) - 200} 件 (json 参照)")
        lines.append("")

    # Orphan / phase boundary
    lines.append("## Orphan tickets (annotated)")
    lines.append("")
    by_pb: dict[str, list[dict]] = defaultdict(list)
    for o in orphans:
        key = o.get("phase_boundary") or o.get("mapping_status") or "uncategorized"
        by_pb[key].append(o)
    for k, items in by_pb.items():
        lines.append(f"### {k} ({len(items)} 件)")
        lines.append("")
        for o in items:
            lines.append(f"- `{o['file']}` → tickets {o['ticket_ids']}  \n  reason: {o.get('reason', '')}")
        lines.append("")

    INV_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"inventory.md regenerated: {INV_MD}")
    print(f"  lines: {len(lines)}")


if __name__ == "__main__":
    main()
