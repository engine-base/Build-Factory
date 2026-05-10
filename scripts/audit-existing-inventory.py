#!/usr/bin/env python3
"""T-S0-13: 既存実装インベントリ監査

backend/ と supabase/migrations/ の実ファイルを走査し、tickets.json の
existing_files / label と突合して各ファイルを以下のいずれかに分類する。

- REUSE       : REUSE ラベルのチケットが exact path で参照
- REFACTOR    : REFACTOR ラベルのチケットが exact path で参照
- NEW         : チケット上は新規予定、現時点でファイル不在
- ARCHIVE    : ARCHIVE ラベルで削除予定 (現状 0 件)
- UNDETERMINED: 実ファイルあり、exact path 参照なし (dir-level 参照のみ)
                 → 個別チケット化が必要

加えて以下の整合性レポートを出す:
  - tickets が listed しているのに disk に存在しないファイル
  - disk にあるのに tickets で参照されていないファイル
  - 同一ファイルへの multi-ticket 参照のラベル整合性

Phase boundary annotations:
  - penpot_client.py        : Phase 1.5 で GrapesJS 統合に置換 (REFACTOR)
  - browser_use_service.py  : Phase 2 で評価/再採用判断 (UNDETERMINED)

Output: docs/audit/2026-05-10_v1/existing-inventory.json (機械可読)
        docs/audit/2026-05-10_v1/existing-inventory.md   (人間可読)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
OUT_JSON = ROOT / "docs" / "audit" / "2026-05-10_v1" / "existing-inventory.json"
OUT_MD = ROOT / "docs" / "audit" / "2026-05-10_v1" / "existing-inventory.md"

PHASE_ANNOTATIONS = {
    "backend/services/penpot_client.py": {
        "phase_boundary": "Phase 1.5",
        "phase_action": "S-3 GrapesJS 統合に伴い REFACTOR (Penpot 依存除去)",
    },
    "backend/services/browser_use_service.py": {
        "phase_boundary": "Phase 2",
        "phase_action": "browser-use の Phase 1 必要性を再評価 (現状 UNDETERMINED)",
    },
}

LABEL_PRIORITY = {"ARCHIVE": 0, "REFACTOR": 1, "REUSE": 2, "NEW": 3, "UNDETERMINED": 4}


def load_tickets() -> dict:
    with TICKETS.open() as f:
        return json.load(f)


def collect_file_refs(tickets_data: dict) -> tuple[dict[str, list[dict]], list[tuple[str, str]]]:
    """specific_refs[path] = [{id,label,feature}], dir_refs = [(ticket_id, dir_path)]"""
    specific: dict[str, list[dict]] = {}
    dir_refs: list[tuple[str, str]] = []
    for t in tickets_data["tickets"]:
        for f in t.get("existing_files") or []:
            entry = {"ticket": t["id"], "label": t.get("label"), "feature": t.get("feature")}
            if f.endswith("/") or "*" in f or not f.endswith(".py") and not f.endswith(".sql") and not f.endswith(".ts") and not f.endswith(".tsx") and not f.endswith(".json") and not f.endswith(".md"):
                # treat as dir or glob
                if f.endswith("/") or "*" in f:
                    dir_refs.append((t["id"], f))
                else:
                    specific.setdefault(f, []).append(entry)
            else:
                specific.setdefault(f, []).append(entry)
    return specific, dir_refs


def walk_disk_files() -> list[Path]:
    """走査対象 = backend/routers + backend/services + supabase/migrations"""
    targets: list[Path] = []
    for sub in ["backend/routers", "backend/services"]:
        d = ROOT / sub
        if d.exists():
            targets.extend(sorted(p for p in d.glob("*.py") if p.name != "__init__.py"))
    mig = ROOT / "supabase" / "migrations"
    if mig.exists():
        targets.extend(sorted(mig.glob("*.sql")))
    return targets


def classify(rel_path: str, specific: dict[str, list[dict]]) -> dict:
    refs = specific.get(rel_path, [])
    annotation = PHASE_ANNOTATIONS.get(rel_path, {})
    if not refs:
        result = {
            "classification": "UNDETERMINED",
            "rationale": "個別チケット参照なし (dir-level 参照のみ) — 実装着手前にチケット化が必要",
            "tickets": [],
        }
    else:
        labels = [r["label"] for r in refs]
        primary = sorted(labels, key=lambda x: LABEL_PRIORITY.get(x, 99))[0]
        if len(set(labels)) > 1:
            rationale = f"複数チケット参照 (labels={labels}) — 優先度で primary={primary} と決定"
        else:
            rationale = f"{primary} ラベルのチケット {refs[0]['ticket']} ({refs[0]['feature']}) で参照"
        result = {
            "classification": primary,
            "rationale": rationale,
            "tickets": refs,
        }
    if annotation:
        result.update(annotation)
    return result


def find_orphan_tickets(tickets_data: dict, disk_set: set[str]) -> list[dict]:
    """tickets が listed しているのに disk に不在のファイル"""
    orphans = []
    for t in tickets_data["tickets"]:
        for f in t.get("existing_files") or []:
            if f.endswith("/") or "*" in f:
                continue
            if f in disk_set:
                continue
            full = ROOT / f
            if not full.exists():
                orphans.append({"ticket": t["id"], "label": t.get("label"), "missing_file": f})
    return orphans


def main() -> int:
    tickets_data = load_tickets()
    specific, dir_refs = collect_file_refs(tickets_data)
    disk_files = walk_disk_files()
    disk_rel = [str(p.relative_to(ROOT)) for p in disk_files]
    disk_set = set(disk_rel)

    inventory: list[dict] = []
    for rel in disk_rel:
        entry = {"path": rel, **classify(rel, specific)}
        inventory.append(entry)

    # Counts
    counts: dict[str, int] = {}
    for e in inventory:
        c = e["classification"]
        counts[c] = counts.get(c, 0) + 1

    orphans = find_orphan_tickets(tickets_data, disk_set)

    summary = {
        "audit_id": "T-S0-13",
        "generated_at": "2026-05-10",
        "scope": {
            "routers_scanned": len([p for p in disk_rel if p.startswith("backend/routers/")]),
            "services_scanned": len([p for p in disk_rel if p.startswith("backend/services/")]),
            "migrations_scanned": len([p for p in disk_rel if p.startswith("supabase/migrations/")]),
            "total_files_on_disk": len(disk_rel),
            "specific_refs_in_tickets": len(specific),
            "dir_refs_in_tickets": len(dir_refs),
        },
        "counts_by_classification": counts,
        "orphan_tickets_count": len(orphans),
        "phase_annotations_applied": len([e for e in inventory if e.get("phase_boundary")]),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w") as f:
        json.dump(
            {
                "summary": summary,
                "inventory": inventory,
                "orphan_tickets": orphans,
                "dir_level_refs": [{"ticket": t, "dir": d} for t, d in dir_refs],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    # Markdown report
    lines: list[str] = []
    lines.append("# T-S0-13: 既存実装インベントリ監査結果")
    lines.append("")
    lines.append(f"- 走査対象: routers={summary['scope']['routers_scanned']}, services={summary['scope']['services_scanned']}, migrations={summary['scope']['migrations_scanned']}")
    lines.append(f"- 分類サマリ: {counts}")
    lines.append(f"- Orphan tickets (listed file 不在): {len(orphans)} 件")
    lines.append(f"- Phase boundary annotation: {summary['phase_annotations_applied']} 件")
    lines.append("")
    lines.append("## 分類別ファイル一覧")
    for cls in ["ARCHIVE", "REFACTOR", "REUSE", "NEW", "UNDETERMINED"]:
        items = [e for e in inventory if e["classification"] == cls]
        if not items:
            continue
        lines.append(f"\n### {cls} ({len(items)} 件)\n")
        for e in items[:200]:
            phase = f" `[{e.get('phase_boundary')}]`" if e.get("phase_boundary") else ""
            lines.append(f"- `{e['path']}`{phase} — {e['rationale']}")
    if orphans:
        lines.append("\n## Orphan: tickets が listed するが disk 不在のファイル\n")
        for o in orphans:
            lines.append(f"- `{o['missing_file']}` ({o['ticket']}, label={o['label']})")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWritten: {OUT_JSON.relative_to(ROOT)}")
    print(f"Written: {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
