#!/usr/bin/env python3
"""Generate Group C (UI / Vertical Slice) Part 1 tickets and audit MDs.

Part 1 scope: 9 categories (account / ai_management / auth / client / design-system /
dialog / email / export / extras). Dialog 5 screens are merged into parent screens
(structural AC nudge added) — not independent tasks.

Outputs:
  - docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part1.json
  - docs/task-decomposition/2026-05-16_v3_phase1/tasks-group-c-ui-part1.md
  - docs/audit/2026-05-16_v3/T-V3-C-NN.md (per task)
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FB = ROOT / "docs" / "functional-breakdown" / "2026-05-16_v3"
OUT_DIR = ROOT / "docs" / "task-decomposition" / "2026-05-16_v3_phase1"
AUDIT_DIR = ROOT / "docs" / "audit" / "2026-05-16_v3"


def load_json(p: Path) -> Any:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


SCREENS = {s["id"]: s for s in load_json(FB / "screens.json")["items"]}
FEATURES = {f["id"]: f for f in load_json(FB / "features.json")["items"]}

# Part 1 categories (per spec).
PART1_CATEGORIES = {"account", "ai_management", "auth", "client", "dialog", "email", "export", "extras"}

# Dialog merge mapping (dialog screen -> parent screen). Picks the most natural form-bearing
# parent within Part 1 scope.
DIALOG_PARENT = {
    "S-051": "S-008",  # confirm_delete -> account_members (delete member)
    "S-052": "S-007",  # unsaved_changes -> account_settings (form save)
    "S-053": "S-001",  # mfa_challenge -> login
    "S-054": "S-006",  # session_expired -> account_dashboard (first authenticated landing)
    "S-055": "S-007",  # danger_zone -> account_settings (delete account)
}

# Existing v3 backend task references for depends_on (from docs/task-decomposition/2026-05-15_v3/tickets.json).
# These are the canonical Group-B backend task IDs to wait on for the corresponding API.
# Where Group B Part 1 backend tasks have explicit IDs they map directly; for features without
# pre-existing backend tasks we use a placeholder T-V3-B-* identifier the Group B sessions own.
FEATURE_BACKEND_DEPS = {
    "F-001": ["T-V3-AUTH-01", "T-V3-AUTH-02", "T-V3-AUTH-03", "T-V3-AUTH-04", "T-V3-AUTH-05", "T-V3-AUTH-06"],
    "F-002": ["T-V3-B-SKILLS-01"],
    "F-003": ["T-V3-B-AI-01"],
    "F-004": ["T-V3-B-ACCOUNT-01"],
    "F-007": ["T-V3-B-TASK-01"],
    "F-008": ["T-V3-B-PHASE-01"],
    "F-013": ["T-V3-B-PR-01"],
    "F-017": ["T-V3-B-COST-01"],
    "F-018": ["T-V3-B-NOTIF-01", "T-V3-B-AUDIT-01"],
    "F-021": ["T-V3-B-RBAC-01"],
    "F-022": ["T-V3-B-AI-02"],
    "F-023": ["T-V3-B-PROFILE-01"],
    "F-024": ["T-V3-B-SEARCH-01"],
    "F-028": ["T-V3-B-EMAIL-01"],
    "F-029": ["T-V3-B-DS-01"],
    "F-030": ["T-V3-B-TOKEN-01"],
    "F-031": ["T-V3-B-EXPORT-01"],
    "F-032": [],  # dialog patterns — frontend-only
}


def normalise_entity(e: str) -> str:
    """Accept either 'E-002' or 'E-002 User' and return canonical 'E-NNN'-style string."""
    return e.strip()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def screen_to_route(screen: dict) -> str:
    """Derive a Next.js App Router path from a screen."""
    name = screen.get("screen_name") or slug(screen.get("name", ""))
    cat = screen.get("category", "")
    sid = screen["id"]
    overrides = {
        "S-001": "(auth)/login",
        "S-002": "(auth)/signup",
        "S-003": "(auth)/password-reset",
        "S-004": "(auth)/mfa-setup",
        "S-005": "(auth)/oauth-callback",
        "S-006": "(app)/dashboard",
        "S-007": "(app)/settings/account",
        "S-008": "(app)/settings/account/members",
        "S-009": "(app)/settings/profile",
        "S-010": "(app)/notifications",
        "S-011": "(app)/search",
        "S-036": "(app)/ai-employees",
        "S-037": "(app)/ai-employees/[employeeId]",
        "S-038": "(app)/skills",
        "S-042": "(client)/workspace/[shareToken]",
        "S-043": "(client)/workspace/[shareToken]/comments",
        "S-056": "(email)/signup-verify",
        "S-057": "(email)/password-reset",
        "S-058": "(email)/invitation",
        "S-059": "(email)/task-notification",
        "S-060": "(email)/weekly-summary",
        "S-061": "(app)/exports/spec/[exportId]",
        "S-062": "(app)/exports/delivery/[exportId]",
        "S-063": "(app)/search/results",
        "S-064": "(app)/settings/api-tokens",
    }
    return overrides.get(sid, f"(app)/{cat}/{name}")


def screen_to_page_path(screen: dict) -> str:
    route = screen_to_route(screen)
    return f"frontend/src/app/{route}/page.tsx"


def screen_to_test_path(screen: dict) -> str:
    sid = screen["id"]
    name = screen.get("screen_name") or slug(screen.get("name", ""))
    return f"frontend/tests/screens/{sid}-{name}.spec.tsx"


def screen_to_api_module(screen: dict) -> str | None:
    """Map feature → api client module name. Email/export with no API → None."""
    feats = screen.get("meta_tags", {}).get("bf-feature-id", []) or []
    f0 = feats[0] if feats else feature_for(screen)
    if not f0:
        return None
    api_modules = {
        "F-001": "frontend/src/api/auth.ts",
        "F-002": "frontend/src/api/skills.ts",
        "F-003": "frontend/src/api/ai-employees.ts",
        "F-004": "frontend/src/api/accounts.ts",
        "F-007": "frontend/src/api/tasks.ts",
        "F-008": "frontend/src/api/phases.ts",
        "F-013": "frontend/src/api/pr-client.ts",
        "F-017": "frontend/src/api/observability.ts",
        "F-018": "frontend/src/api/notifications.ts",
        "F-021": "frontend/src/api/rbac.ts",
        "F-022": "frontend/src/api/ai-employees.ts",
        "F-023": "frontend/src/api/profile.ts",
        "F-024": "frontend/src/api/search.ts",
        "F-028": "frontend/src/api/email.ts",
        "F-029": "frontend/src/api/design-system.ts",
        "F-030": "frontend/src/api/api-tokens.ts",
        "F-031": "frontend/src/api/exports.ts",
    }
    return api_modules.get(f0)


def feature_for(screen: dict) -> str | None:
    feats = screen.get("meta_tags", {}).get("bf-feature-id", []) or []
    if feats:
        return feats[0]
    # Fallback: derive from category + screen_id for screens whose meta lacks feature ids
    fallback = {
        "S-056": "F-028", "S-057": "F-028", "S-058": "F-028", "S-059": "F-028", "S-060": "F-028",
        "S-061": "F-031", "S-062": "F-031",
        "S-063": "F-024", "S-064": "F-030",
    }
    return fallback.get(screen["id"])


def filter_ears_for_screen(feat: dict, screen: dict) -> list[str]:
    """Return ears_ac_seed strings related to this screen's APIs/screen-id."""
    seeds = feat.get("ears_ac_seed", []) or []
    apis = set(screen.get("related_apis", []) or [])
    sid = screen["id"]
    out: list[str] = []
    for s in seeds:
        if not isinstance(s, str):
            continue
        # include if EARS mentions any of this screen's API paths or screen_id
        if any(a.split(" ")[-1] in s for a in apis):
            out.append(s)
            continue
        if sid in s:
            out.append(s)
    # Fallback: if no specific match, take first 2 as background
    if not out:
        out = [s for s in seeds[:2] if isinstance(s, str)]
    return out[:6]


def structural_ac(screen: dict) -> list[str]:
    sid = screen["id"]
    h1 = screen.get("h1_text", "") or ""
    section_h2 = screen.get("section_h2_texts", []) or []
    kpi = screen.get("kpi_labels", []) or []
    ac: list[str] = []
    ac.append(
        f"STATE-DRIVEN: While {sid} page is rendered, the system shall include a `data-screen-id=\"{sid}\"` attribute on the root element."
    )
    if h1:
        ac.append(
            f"STATE-DRIVEN: While {sid} page is rendered, the system shall display an h1 element with text matching screens.json[{sid}].h1_text (\"{h1}\")."
        )
    if section_h2:
        # Cap 12 per spec.
        capped = section_h2[:12]
        joined = " / ".join(capped)
        ac.append(
            f"STATE-DRIVEN: While {sid} page is rendered, the system shall render h2 section headings matching screens.json[{sid}].section_h2_texts (cap 12): {joined}."
        )
    if kpi:
        capped = kpi[:8]
        joined = " / ".join(capped)
        ac.append(
            f"UBIQUITOUS: The system shall expose KPI labels on {sid} matching screens.json[{sid}].kpi_labels: {joined}."
        )
    return ac


def functional_ac(screen: dict, feat: dict | None, merged_dialogs: list[dict]) -> list[str]:
    out: list[str] = []
    sid = screen["id"]
    # API-driven AC
    apis = screen.get("related_apis", []) or []
    for api in apis:
        # naive parse "METHOD /path"
        parts = api.split(" ", 1)
        if len(parts) != 2:
            continue
        method, path = parts
        out.append(
            f"EVENT-DRIVEN: When the {sid} page performs its primary action, the system shall call {method} {path} via the typed API client."
        )
    # Error / generic
    out.append(
        f"UNWANTED: If a backing API call from {sid} returns 4xx or 5xx, the system shall surface a non-technical error toast referencing the failing endpoint without leaking server stack traces."
    )
    # State transitions
    transitions = screen.get("transitions", []) or []
    for t in transitions[:2]:
        out.append(
            f"EVENT-DRIVEN: When the user completes the primary flow on {sid}, the system shall navigate to {t}."
        )
    # Feature-level EARS (verbatim from features.json)
    if feat is not None:
        out.extend(filter_ears_for_screen(feat, screen))
    # Merged dialog AC
    for d in merged_dialogs:
        did = d["id"]
        dname = d.get("screen_name") or d["name"]
        if did == "S-051":
            out.append(
                "EVENT-DRIVEN: When the user requests a destructive action, the system shall show the confirm_delete dialog (S-051 pattern) requiring typed-name confirmation before submitting."
            )
        elif did == "S-052":
            out.append(
                "UNWANTED: If the user attempts to navigate away from a dirty form, the system shall block navigation by showing the unsaved_changes dialog (S-052 pattern) until confirmed."
            )
        elif did == "S-053":
            out.append(
                "STATE-DRIVEN: While the login response indicates mfa_required=true, the system shall show the mfa_challenge dialog (S-053 pattern) for TOTP entry before completing login."
            )
        elif did == "S-054":
            out.append(
                "EVENT-DRIVEN: When the server returns 401 with session_expired code, the system shall show the session_expired dialog (S-054 pattern) and preserve in-flight form data in localStorage."
            )
        elif did == "S-055":
            out.append(
                "STATE-DRIVEN: While the user is in the Danger Zone region (S-055 pattern), the system shall require typed-name confirmation for any irreversible action."
            )
    return out


def regression_ac(task_id: str, screen_ids: list[str], has_structural: bool) -> list[str]:
    out = [
        f"The system shall pass `vitest run frontend/tests/screens/` covering the new tests for {task_id} with >= 5 test cases PASS.",
        "The system shall pass `cd frontend && tsc --noEmit` with 0 errors on touched modules.",
        "The system shall pass `cd frontend && pnpm run lint` with 0 warnings on touched modules.",
        f"The system shall maintain coverage >= 70% on files changed by {task_id}.",
        "The system shall pass `bash scripts/lint-mock.sh` with all 16+ rules OK.",
    ]
    if has_structural:
        sids = " ".join(screen_ids)
        out.append(
            f"The system shall pass `python3 scripts/lint-mock-impl-diff.py --strict {sids}` (Gate #8 / mock-impl structural diff)."
        )
    out.append(
        "The system shall pass `python3 scripts/validate-tickets.py` with no errors for this task entry."
    )
    out.append(
        f"The system shall pass `bash scripts/audit-md-check.sh {task_id}` (audit MD exists, 3 sections present, no generic phrase)."
    )
    return out


def build_task(idx: int, screen: dict, merged: list[dict]) -> dict:
    sid = screen["id"]
    fid = feature_for(screen)
    feat = FEATURES.get(fid) if fid else None
    page_path = screen_to_page_path(screen)
    test_path = screen_to_test_path(screen)
    api_mod = screen_to_api_module(screen)
    entities = [normalise_entity(e) for e in (screen.get("related_entities") or [])]
    feats_meta = screen.get("meta_tags", {}).get("bf-feature-id", []) or ([fid] if fid else [])
    if not feats_meta and fid:
        feats_meta = [fid]
    deps: list[str] = []
    for f in feats_meta:
        deps.extend(FEATURE_BACKEND_DEPS.get(f, []))
    # Foundation is prerequisite
    deps_set: list[str] = []
    seen = set()
    for d in ["T-FOUNDATION-08", *deps]:
        if d not in seen:
            seen.add(d)
            deps_set.append(d)

    files_changed = [f"{page_path} (new)"]
    if api_mod:
        files_changed.append(f"{api_mod} (modify)")
    files_changed.append(f"{test_path} (new)")

    editable = [page_path, test_path]
    if api_mod:
        editable.append(api_mod)

    has_structural = bool(screen.get("h1_text")) or bool(screen.get("section_h2_texts")) or bool(screen.get("kpi_labels"))
    task_id = f"T-V3-C-{idx:02d}"

    title = f"{sid} {screen.get('name','')} 画面実装 (Vertical Slice / UI)"
    if merged:
        merged_ids = ", ".join(m["id"] for m in merged)
        title += f" +dialog {merged_ids}"

    spec_links = [
        f"docs/functional-breakdown/2026-05-16_v3/screens.json#{sid}",
        screen.get("mock_path", f"docs/mocks/2026-05-15_v3/{screen['category']}/{sid}.html"),
    ]
    if fid:
        spec_links.append(f"docs/functional-breakdown/2026-05-16_v3/features.json#{fid}")

    screen_ids_combined = [sid] + [m["id"] for m in merged]

    task: dict = {
        "id": task_id,
        "title": title,
        "category": "frontend",
        "label": "NEW",
        "feature_id": fid,
        "feature_ids": feats_meta,
        "screen_ids": screen_ids_combined,
        "entity_ids": entities,
        "phase": "Phase 1B",
        "wave": 2,
        "group": "C",
        "deliverable_layer": "ui",
        "estimate_hours": 4 if not merged else 5,
        "estimate_sessions": 1,
        "depends_on": deps_set,
        "files_changed": files_changed,
        "work_package_boundary": {
            "editable": editable,
            "shared_no_concurrent_edit": [
                "frontend/src/api/index.ts",
                "frontend/src/app/layout.tsx",
            ],
            "readonly": [
                screen.get("mock_path", f"docs/mocks/2026-05-15_v3/{screen['category']}/{sid}.html"),
                f"docs/functional-breakdown/2026-05-16_v3/screens.json",
                f"docs/functional-breakdown/2026-05-16_v3/features.json",
                "backend/",
            ],
            "forbidden": [
                "scripts/",
                "data/",
                ".github/",
            ],
        },
        "acceptance_criteria": {
            "structural": structural_ac(screen),
            "functional": functional_ac(screen, feat, merged),
            "regression": regression_ac(task_id, screen_ids_combined, has_structural),
        },
        "access_policies_required": [],
        "spec_links": spec_links,
        "audit_md_path": f"docs/audit/2026-05-16_v3/{task_id}.md",
        "branch": f"claude/{task_id}",
    }
    return task


def main() -> None:
    # Collect all part 1 screens
    part1 = [s for s in SCREENS.values() if s["category"] in PART1_CATEGORIES]
    # Sort by ID for deterministic numbering
    part1.sort(key=lambda s: s["id"])
    # Separate dialogs from parents
    dialogs = [s for s in part1 if s["category"] == "dialog"]
    primaries = [s for s in part1 if s["category"] != "dialog"]
    # Index dialogs by parent
    dialog_by_parent: dict[str, list[dict]] = {}
    for d in dialogs:
        parent = DIALOG_PARENT.get(d["id"])
        if not parent:
            continue
        dialog_by_parent.setdefault(parent, []).append(d)

    tasks: list[dict] = []
    for idx, screen in enumerate(primaries, start=1):
        merged = dialog_by_parent.get(screen["id"], [])
        tasks.append(build_task(idx, screen, merged))

    # Compose summary
    by_category: dict[str, int] = {}
    for t in tasks:
        sid = t["screen_ids"][0]
        cat = SCREENS[sid]["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

    out_doc = {
        "version": "v3-phase1-group-c-part1",
        "project": "Build-Factory",
        "profile": "build-factory",
        "phase_target": "Phase 1B (UI / Vertical Slice)",
        "group": "C",
        "scope": "9 categories (account / ai_management / auth / client / dialog / email / export / extras); dialog 5 merged into parent screens",
        "created_at": "2026-05-16",
        "summary": {
            "total_tasks": len(tasks),
            "by_category": by_category,
            "merged_dialog_screens": [
                {"dialog": k, "parent": v} for k, v in {d["id"]: DIALOG_PARENT[d["id"]] for d in dialogs}.items()
            ],
            "total_estimate_hours": sum(t["estimate_hours"] for t in tasks),
        },
        "tasks": tasks,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "tickets-group-c-ui-part1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_doc, f, ensure_ascii=False, indent=2)
    print(f"Wrote {out_path} ({len(tasks)} tasks)")

    # Markdown
    md_lines = [
        "# Group C — UI Vertical Slice (Part 1) tasks",
        "",
        f"- 生成日: 2026-05-16",
        f"- スコープ: 9 categories (account / ai_management / auth / client / design-system 該当無 / dialog / email / export / extras)",
        f"- dialog 5 件は親画面に merge: " + ", ".join(f"{d['id']}→{DIALOG_PARENT[d['id']]}" for d in dialogs),
        f"- 総タスク数: {len(tasks)}",
        f"- 総工数: {sum(t['estimate_hours'] for t in tasks)} h",
        "",
        "| # | task_id | screen(s) | feature | est h | depends_on | mock |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in tasks:
        sid = t["screen_ids"][0]
        scr = SCREENS[sid]
        deps = ", ".join(t["depends_on"]) or "—"
        md_lines.append(
            f"| {t['id'].rsplit('-',1)[-1]} | {t['id']} | {' + '.join(t['screen_ids'])} | {t['feature_id'] or '—'} | {t['estimate_hours']} | {deps} | {scr.get('mock_path','—')} |"
        )
    md_lines.append("")
    md_lines.append("## ファイル境界 (file-level mutex)")
    md_lines.append("")
    md_lines.append("- 各 task は `frontend/src/app/<route>/page.tsx` を 1 つだけ新規作成し、衝突なし。")
    md_lines.append("- `frontend/src/api/*.ts` は feature 単位で共有のため、Group B 完了後に touch。同 feature 内の複数 task が並列実行する場合は依存タスクで直列化。")
    md_lines.append("- `frontend/src/app/layout.tsx` / `frontend/src/api/index.ts` は shared_no_concurrent_edit (同 Wave で 1 task のみ touch)。")

    md_path = OUT_DIR / "tasks-group-c-ui-part1.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")
    print(f"Wrote {md_path}")

    # Audit MDs
    for t in tasks:
        sid = t["screen_ids"][0]
        scr = SCREENS[sid]
        struct_lines = []
        for i, ac in enumerate(t["acceptance_criteria"]["structural"], 1):
            struct_lines.append(f"- [ ] AC-S{i}: {ac} → impl: <page.tsx 行範囲を着手時に追記>")
        if not struct_lines:
            struct_lines.append("(該当なし / 該当画面に h1 / KPI / section_h2 が未定義のため structural 層は対象外)")
        func_lines = []
        for i, ac in enumerate(t["acceptance_criteria"]["functional"], 1):
            func_lines.append(f"- [ ] AC-F{i}: {ac} → impl: <該当 hook / mutation 行範囲を着手時に追記>")
        reg_lines = []
        for i, ac in enumerate(t["acceptance_criteria"]["regression"], 1):
            reg_lines.append(f"- [ ] AC-R{i}: {ac} → 実行ログを着手時に貼付")

        audit_md = f"""# {t['id']} audit

> {t['title']}
> 3-tier AC を逐語コピーし、impl line と実行ログを記録する **pre-flight template**。
> 着手前にこの MD を埋めること (auto-generate は禁止 / generic 文言は CI gate で reject)。

## メタ

- screen(s): {' / '.join(t['screen_ids'])}
- feature_id: {t['feature_id'] or '—'}  (related: {', '.join(t['feature_ids'])})
- entity_ids: {', '.join(t['entity_ids']) or '—'}
- mock_path: {scr.get('mock_path','—')}
- depends_on: {', '.join(t['depends_on']) or '—'}
- branch: {t['branch']}

## Tier 1: Structural

{chr(10).join(struct_lines)}

## Tier 2: Functional

{chr(10).join(func_lines)}

## Tier 3: Regression

{chr(10).join(reg_lines)}

### 凡例

- [ ] = 未着手
- [x] = PASS (実行ログ貼付済)
- [/] = SKIP-WITH-REASON (新規 regression ではなく pre-existing baseline drift)
- [!] = FAIL (修正必要)

## 着手記録

- 着手日: (着手時に追記)
- 担当 session: (worktree-id を追記)
- branch: {t['branch']}

## 完了記録

- 完了日: (完了時に追記)
- Decision: TBD (DONE | BLOCKED | GAP)
- PR: (subagent が PR 作成後に追記)

## ノート

- (実装中の気付きを追記)
"""
        audit_path = AUDIT_DIR / f"{t['id']}.md"
        with open(audit_path, "w", encoding="utf-8") as f:
            f.write(audit_md)
    print(f"Wrote {len(tasks)} audit MDs under {AUDIT_DIR}/T-V3-C-*.md")


if __name__ == "__main__":
    main()
