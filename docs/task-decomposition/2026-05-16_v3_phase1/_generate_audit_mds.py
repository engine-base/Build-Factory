#!/usr/bin/env python3
"""Audit MD pre-flight template generator for Part 2 (30 tasks).

For each task in tickets-group-c-ui-part2.json, emit a fully-tailored
docs/audit/2026-05-16_v3/T-V3-C-NN.md that:
  - Embeds all 3-tier AC verbatim (no generic "shall implement T-XXX as specified")
  - Has all 3 required section headers (Tier 1 / Tier 2 / Tier 3)
  - Includes impl_path placeholders aligned to files_changed
  - Captures depends_on / mock_path / spec_link
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TICKETS = json.loads((ROOT / "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part2.json").read_text())
TASKS = TICKETS["tasks"]
OUT_DIR = ROOT / "docs/audit/2026-05-16_v3"


def render(task: dict) -> str:
    tid = task["id"]
    title = task["title"]
    label = task["label"]
    feature = task.get("feature_id") or "(none)"
    screen_ids = ", ".join(task.get("screen_ids") or [])
    entity_ids = ", ".join(task.get("entity_ids") or []) or "(none)"
    mock = next((sl for sl in task["spec_links"] if sl.endswith(".html")), "(no mock path)")
    feat_links = [sl for sl in task["spec_links"] if "features.json" in sl]
    depends = ", ".join(task.get("depends_on") or []) or "(none — leaf)"
    files_str = "\n".join(f"  - {f}" for f in task["files_changed"])
    editable = "\n".join(f"  - {f}" for f in task["work_package_boundary"]["editable"])

    ac = task["acceptance_criteria"]

    def tier_lines(prefix: str, items: list[str]) -> str:
        if not items:
            return f"(該当なし / {prefix} は空)"
        lines = []
        for i, ac_text in enumerate(items, start=1):
            ac_id = f"AC-{prefix[0]}{i}"
            # impl_path hint: first editable file
            impl_hint = task["work_package_boundary"]["editable"][0] if task["work_package_boundary"]["editable"] else "(file:line を埋める)"
            lines.append(f"- [ ] {ac_id}: {ac_text} → impl: {impl_hint}:Lxx-Lyy")
        return "\n".join(lines)

    tier1 = tier_lines("Structural", ac["structural"])
    tier2 = tier_lines("Functional", ac["functional"])

    # Tier 3 — list verbatim with empty check + run log placeholder
    tier3_lines = []
    for i, r in enumerate(ac["regression"], start=1):
        tier3_lines.append(f"- [ ] AC-R{i}: {r} → 実行ログ: (実行後に貼り付け)")
    tier3 = "\n".join(tier3_lines)

    return f"""# {tid} audit (pre-flight)

> {title}
> 3-tier AC を逐語コピーした pre-flight checklist。着手時点では全 unchecked。実装完了で全 check + 実行ログ貼付。

## メタ

- Task: **{tid}**
- Title: {title}
- Label: **{label}**
- Phase: Phase 1 / Wave 1 / Group C (UI Vertical Slice)
- Feature: {feature}
- Screen(s): {screen_ids}
- Entity(s): {entity_ids}
- Mock: {mock}
- Spec links: {", ".join(feat_links) or "(none)"}
- Depends on: {depends}
- Branch: {task["branch"]}
- Estimate: {task["estimate_hours"]}h / {task["estimate_sessions"]} session

### files_changed
{files_str}

### work_package_boundary.editable
{editable}

---

## Tier 1: Structural

{tier1}

## Tier 2: Functional

{tier2}

## Tier 3: Regression

{tier3}

---

## 着手記録
- 着手日: (YYYY-MM-DD)
- 担当 session: (worktree id)
- branch: {task["branch"]}

## 完了記録
- 完了日: (YYYY-MM-DD)
- Decision: PLANNED | IMPL_DONE | TEST_PASS | VERIFIED
- PR: (#NNN を埋める)

## ノート
- mock-impl diff (Tier 1 構造一致) は `bash scripts/lint-mock-impl-diff.sh {screen_ids}` を実装後に実行し 0 件で PASS。
- ARIA / accessibility はデフォルトの role/aria-live を最低限含める。
- API 連携は MSW でモックして単体テストを書き、E2E は別 Group D で実装する。
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for t in TASKS:
        path = OUT_DIR / f"{t['id']}.md"
        path.write_text(render(t))
        written += 1
    print(f"wrote {written} audit MD files under {OUT_DIR}")


if __name__ == "__main__":
    main()
