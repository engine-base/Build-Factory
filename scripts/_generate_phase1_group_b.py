#!/usr/bin/env python3
"""Phase 1A Group B (Backend) tickets generator.

Inputs:
  - docs/functional-breakdown/2026-05-16_v3/features.json
  - docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md

Outputs:
  - docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json
  - docs/task-decomposition/2026-05-16_v3_phase1/tasks-group-b-backend.md
  - docs/audit/2026-05-16_v3/T-V3-B-NN.md (one per task)

Logic:
  Each feature with critical-missing endpoints gets 1 or more tasks (~3-4 endpoints / task,
  estimate_hours <= 6h). Each task carries:
    - Tier 1 structural: 1 EARS UBIQUITOUS line referencing features.json api_endpoints
    - Tier 2 functional: features.json ears_ac_seed (verbatim) + per-endpoint generated EARS
    - Tier 3 regression: BF profile 8 gates (verbatim)
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = ROOT / "docs/functional-breakdown/2026-05-16_v3/features.json"
DRIFT_PATH = ROOT / "docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md"
OUT_DIR = ROOT / "docs/task-decomposition/2026-05-16_v3_phase1"
AUDIT_DIR = ROOT / "docs/audit/2026-05-16_v3"
TICKETS_OUT = OUT_DIR / "tickets-group-b-backend.json"
TASKS_MD_OUT = OUT_DIR / "tasks-group-b-backend.md"

# ---------------------------------------------------------------------------
# 1. Parse drift summary → critical missing endpoints by feature
# ---------------------------------------------------------------------------
def parse_drift() -> dict[str, list[tuple[str, str, str]]]:
    """Return {feature_id: [(METHOD, path, task_id_legacy), ...]}."""
    text = DRIFT_PATH.read_text(encoding="utf-8")
    m = re.search(r"## critical 詳細.*?\n\n(.*?)## high 詳細", text, re.DOTALL)
    assert m, "could not find critical section"
    rows = re.findall(
        r"\| (F-[\w]+) [^|]+\| `([A-Z]+) ([^`]+)` \| (T-V3-DRIFT-F-[\w-]+) \|",
        m.group(1),
    )
    by_feat: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for fid, method, path, legacy_id in rows:
        by_feat[fid].append((method, path, legacy_id))
    return dict(by_feat)


# ---------------------------------------------------------------------------
# 2. Load features.json
# ---------------------------------------------------------------------------
def load_features() -> dict[str, dict]:
    data = json.loads(FEATURES_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item for item in data["items"]}


# ---------------------------------------------------------------------------
# 3. Task grouping plan
# ---------------------------------------------------------------------------
# Each entry: (task_id, feature_id, title_suffix, endpoint_paths)
# endpoint_paths is the list of paths assigned to this task.
# If endpoint_paths is None → all critical endpoints of the feature.
TASK_PLAN: list[tuple[str, str, str, list[str] | None]] = [
    ("T-V3-B-01", "F-001", "Auth backend (login/signup/password-reset)",
     ["/api/auth/login", "/api/auth/signup", "/api/auth/password-reset"]),
    ("T-V3-B-02", "F-001", "Auth backend (MFA + OAuth callback)",
     ["/api/auth/mfa/enroll", "/api/auth/mfa/verify", "/api/auth/oauth/{provider}/callback"]),
    ("T-V3-B-03", "F-002", "Skill manager backend (test endpoint)", None),
    ("T-V3-B-04", "F-003", "AI employees backend (org-chart / test / clone-from-user)", None),
    ("T-V3-B-05", "F-004", "Account/workspace backend (transfer-owner / invitations CRUD)",
     ["/api/accounts/{id}/transfer-owner",
      "/api/accounts/{id}/invitations",
      "/api/accounts/{id}/members/{user_id}",
      "/api/invitations/{token}"]),
    ("T-V3-B-06", "F-004", "Workspace member role + invitation revocation backend",
     ["/api/workspaces/{id}/members/{user_id}/role",
      "/api/workspaces/{id}/invitations/{token}"]),
    ("T-V3-B-07", "F-005", "Hearing → spec backend (save / specs CRUD + comments)", None),
    ("T-V3-B-08", "F-005b", "Mocks backend (mocks list / detail / html GET/PUT)",
     ["/api/workspaces/{id}/mocks",
      "/api/workspaces/{id}/mocks/{screen_id}",
      "/api/workspaces/{id}/mocks/{screen_id}/html"]),  # GET+PUT same path 1 entry
    ("T-V3-B-09", "F-005b", "Mocks backend (ai-edit / components / screen-flow)",
     ["/api/workspaces/{id}/mocks/{screen_id}/ai-edit",
      "/api/workspaces/{id}/components",
      "/api/workspaces/{id}/components/{id}/usage",
      "/api/workspaces/{id}/screen-flow"]),
    ("T-V3-B-10", "F-006", "Requirements backend (CRUD / versions / task comments)", None),
    ("T-V3-B-11", "F-007", "Tasks backend (bulk-play / bulk-archive / export.csv / dag)",
     ["/api/workspaces/{id}/tasks/bulk-play",
      "/api/workspaces/{id}/tasks/bulk-archive",
      "/api/workspaces/{id}/tasks/export.csv",
      "/api/workspaces/{id}/tasks/dag"]),
    ("T-V3-B-12", "F-007", "Tasks backend (play single / play-all)",
     ["/api/tasks/{id}/play",
      "/api/workspaces/{id}/tasks/play-all",
      "/api/workspaces/{id}/play-all"]),
    ("T-V3-B-13", "F-008", "Phase management backend (phases list/create/gate)", None),
    ("T-V3-B-14", "F-009", "Dependency graph backend (edges + impact-analysis)", None),
    ("T-V3-B-15", "F-010", "Sessions backend (list / detail / kill / kill-all)",
     ["/api/workspaces/{id}/sessions",
      "/api/sessions/{id}",
      "/api/sessions/{id}/kill",
      "/api/workspaces/{id}/sessions/kill-all"]),
    ("T-V3-B-16", "F-010", "Sessions backend (pause / resume / rollback)",
     ["/api/sessions/{id}/pause",
      "/api/sessions/{id}/resume",
      "/api/sessions/{id}/rollback"]),
    ("T-V3-B-17", "F-012", "Red-lines backend (CRUD + test)",
     ["/api/workspaces/{id}/red-lines",
      "/api/workspaces/{id}/red-lines/test"]),
    ("T-V3-B-18", "F-012", "Violations backend (list / approve / reject)",
     ["/api/workspaces/{id}/violations",
      "/api/violations/{id}/approve",
      "/api/violations/{id}/reject"]),
    ("T-V3-B-19", "F-013", "PR review backend (get / approve / comments / merge)",
     ["/api/workspaces/{id}/prs/{pr_number}",
      "/api/prs/{id}/approve",
      "/api/prs/{id}/comments",
      "/api/prs/{id}/merge"]),
    ("T-V3-B-20", "F-013", "Client portal backend (workspaces / spec / comments)",
     ["/api/client/workspaces/{token}",
      "/api/client/workspaces/{token}/spec",
      "/api/client/comments/{thread_id}",
      "/api/client/comments",
      "/api/comments/{id}/resolve"]),
    ("T-V3-B-21", "F-013", "Delivery backend (delivery pack / approve / send-client)",
     ["/api/workspaces/{id}/delivery",
      "/api/workspaces/{id}/delivery/approve",
      "/api/workspaces/{id}/delivery/send-client"]),
    ("T-V3-B-22", "F-016", "Knowledge base backend (list + search)", None),
    ("T-V3-B-23", "F-017", "Observability backend (cost-summary export + token-limit)", None),
    ("T-V3-B-24", "F-018", "Audit logs backend (list / export.csv / export.json)",
     ["/api/audit-logs",
      "/api/audit-logs/export.csv",
      "/api/audit-logs/export.json"]),
    ("T-V3-B-25", "F-018", "Notifications backend (list / read / read-all)",
     ["/api/notifications",
      "/api/notifications/{id}/read",
      "/api/notifications/read-all"]),
    ("T-V3-B-26", "F-023", "Account profile backend (/me CRUD / api-keys / oauth unlink)", None),
    ("T-V3-B-27", "F-024", "Global search + account dashboard backend", None),
    ("T-V3-B-28", "F-026", "Constitution backend (get / versions / approve)", None),
    ("T-V3-B-29", "F-027", "Onboarding backend (get / advance / skip)", None),
    ("T-V3-B-30", "F-028", "Email backend (templates list + test-send)", None),
]


# ---------------------------------------------------------------------------
# 4. Helpers
# ---------------------------------------------------------------------------
def feature_files(fid: str) -> list[str]:
    """Map feature id → backend module path stem(s)."""
    return {
        "F-001": ["auth"],
        "F-002": ["skills"],
        "F-003": ["ai_employees"],
        "F-004": ["accounts", "workspaces", "invitations"],
        "F-005": ["hearing", "specs"],
        "F-005b": ["mocks", "components", "screen_flow"],
        "F-006": ["requirements", "task_comments"],
        "F-007": ["tasks"],
        "F-008": ["phases"],
        "F-009": ["dependencies"],
        "F-010": ["sessions"],
        "F-012": ["red_lines", "violations"],
        "F-013": ["pull_requests", "delivery", "client_portal", "comments"],
        "F-016": ["knowledge"],
        "F-017": ["observability"],
        "F-018": ["audit_logs", "notifications"],
        "F-023": ["me", "api_keys"],
        "F-024": ["search", "dashboard"],
        "F-026": ["constitution"],
        "F-027": ["onboarding"],
        "F-028": ["email"],
    }[fid]


def feature_entities_short(fid: str, feature: dict) -> list[str]:
    """Return entity IDs (short form: 'E-NNN Name')."""
    return feature.get("related_entities", [])


def access_policies(fid: str, feature: dict) -> list[str]:
    """Generate access_policies_required strings.

    Pattern: <table>:<policy_name>. We derive plausible policy names from
    related_entities + auth requirement.
    """
    ents = feature.get("related_entities", [])
    out: list[str] = []
    for e in ents:
        # E-002 User → table=users, policy=self_select
        m = re.match(r"E-\d+\s+(\w+)", e)
        if not m:
            continue
        name = m.group(1)
        table = _to_snake_plural(name)
        # Choose policy name heuristically
        if fid == "F-001":
            policy = "user_own_select"
        elif fid in ("F-018",):
            policy = "workspace_admin_select"
        elif fid in ("F-013",) and "Delivery" in e:
            policy = "workspace_owner_select"
        elif fid == "F-024" and "AuditLog" in e:
            policy = "workspace_member_select"
        elif "Comment" in e:
            policy = "workspace_member_select_insert"
        else:
            policy = "workspace_member_select"
        out.append(f"{table}:{policy}")
    return out


_PLURAL_OVERRIDES = {
    "ApiKey": "api_keys",
    "KnowledgeItem": "knowledge_items",
    "AuditLog": "audit_logs",
    "RedLine": "red_lines",
    "RedLineViolation": "red_line_violations",
    "PullRequest": "pull_requests",
    "EmailTemplate": "email_templates",
    "EmailDelivery": "email_deliveries",
    "ObsidianVault": "obsidian_vaults",
    "ChatThread": "chat_threads",
}


def _to_snake_plural(name: str) -> str:
    if name in _PLURAL_OVERRIDES:
        return _PLURAL_OVERRIDES[name]
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    # naive plural
    if s.endswith("s"):
        return s
    if s.endswith("y") and len(s) >= 2 and s[-2] not in "aeiou":
        return s[:-1] + "ies"
    return s + "s"


def endpoints_for_task(
    feature: dict, paths: list[str] | None, drift_paths: list[str]
) -> list[dict]:
    """Filter feature.api_endpoints to those critical-missing AND assigned to this task."""
    eps = feature.get("api_endpoints", [])
    # Critical-missing path set (just the path strings)
    crit = set(drift_paths)
    if paths is None:
        # all critical endpoints of this feature
        out = [ep for ep in eps if ep["path"] in crit]
    else:
        sel = set(paths)
        out = [ep for ep in eps if ep["path"] in sel and ep["path"] in crit]
    return out


def build_functional_ac(feature: dict, eps: list[dict]) -> list[str]:
    """Functional AC = features.json ears_ac_seed (verbatim, filtered by endpoint paths) +
    per-endpoint EVENT-DRIVEN happy path."""
    # 1. all verbatim ears_ac_seed entries that mention any of our endpoint paths
    paths = {ep["path"] for ep in eps}
    out: list[str] = []
    seed = feature.get("ears_ac_seed", [])
    for ac in seed:
        # include if the AC mentions any of the assigned paths OR if it's a generic
        # AC for this feature (we include all because the task represents a slice
        # of this feature's responsibility). Filter to those referencing relevant paths.
        if any(p in ac for p in paths):
            out.append(ac)
    # Fallback: if nothing matched, include the full seed
    if not out:
        out = list(seed)
    # 2. per-endpoint structural EVENT-DRIVEN derived from endpoint spec
    for ep in eps:
        method = ep["method"]
        path = ep["path"]
        out2xx_keys = list(ep.get("outputs_2xx", {}).keys())
        sample = out2xx_keys[0] if out2xx_keys else "2xx response"
        out.append(
            f"EVENT-DRIVEN: When {method} {path} is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#{feature['id']} (incl. {sample})."
        )
        # Add UNWANTED for 401/403/422 if specified
        out4xx = ep.get("outputs_4xx", {})
        if "401" in out4xx:
            out.append(
                f"UNWANTED: If {method} {path} is called without a valid auth token, the system shall return 401."
            )
        elif "403" in out4xx:
            out.append(
                f"UNWANTED: If {method} {path} is called by a caller lacking required role, the system shall return 403."
            )
        if "422" in out4xx:
            out.append(
                f"UNWANTED: If {method} {path} receives a request body failing validation, the system shall return 422 with a field-level error map."
            )
        if "429" in out4xx and ep.get("rate_limit"):
            out.append(
                f"UNWANTED: If {method} {path} is called above the rate limit ({ep['rate_limit']}), the system shall return 429."
            )
    return out


def build_regression_ac(task_id: str, entity_short_ids: list[str]) -> list[str]:
    """BF profile 8 gates - verbatim."""
    files_glob = "modified files"
    ent_codes = [e.split(" ")[0] for e in entity_short_ids if e.startswith("E-")]
    rls_target = "/".join(ent_codes) if ent_codes else "this task's entities"
    return [
        "Gate 1 (mock lint): bash scripts/lint-mock.sh 16/16 OK (rule_id 1-19, includes mock-impl-diff #17 / screens-API #18 / entity-table-naming #19)",
        f"Gate 2 (3-tier AC validator): python3 scripts/validate-ears-ac.py docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json PASS for {task_id}",
        f"Gate 3 (audit MD validator): python3 scripts/validate-audit-md.py docs/audit/2026-05-16_v3/{task_id}.md PASS (no generic phrase, 3-tier present, impl line ranges recorded)",
        f"Gate 4 (RLS coverage): python3 scripts/verify-rls-coverage.py PASS for {rls_target}",
        f"Gate 5 (pytest + coverage): pytest backend/tests/ --cov --cov-fail-under=70 PASS (>= 10 new tests for {task_id}, coverage on touched {files_glob} >= 70%)",
        "Gate 6 (pyright strict): pyright --strict backend/app/ 0 errors on touched files",
        "Gate 7 (TS strict / N/A for backend): skip — this task does not touch frontend/",
        "Gate 8 (mock-impl diff): N/A — backend-only task, structural AC is empty",
        f"bash scripts/audit-md-check.sh {task_id} PASS",
        f"python3 scripts/validate-tickets.py --check-file docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json PASS for {task_id}",
        "ruff check backend/app/ 0 warnings on touched files",
    ]


def build_structural_ac(feature: dict, eps: list[dict]) -> list[str]:
    """Tier 1 structural — 1 EARS UBIQUITOUS line referencing api_endpoints contract."""
    methods = ", ".join(f"{ep['method']} {ep['path']}" for ep in eps)
    fid = feature["id"]
    return [
        f"UBIQUITOUS: The system shall expose the endpoints [{methods}] with method/path/inputs/outputs_2xx/outputs_4xx exactly matching docs/functional-breakdown/2026-05-16_v3/features.json#{fid}.api_endpoints (no drift)."
    ]


def make_files_changed(feature_id: str, modules: list[str]) -> list[str]:
    out: list[str] = []
    for m in modules:
        out.append(f"backend/app/routers/{m}.py (modify)")
        out.append(f"backend/app/services/{m}.py (modify)")
        out.append(f"backend/app/schemas/{m}.py (modify)")
        out.append(f"backend/tests/routers/test_{m}.py (new)")
    return out


def make_boundary(modules: list[str]) -> dict[str, list[str]]:
    editable: list[str] = []
    for m in modules:
        editable.extend([
            f"backend/app/routers/{m}.py",
            f"backend/app/services/{m}.py",
            f"backend/app/schemas/{m}.py",
            f"backend/tests/routers/test_{m}.py",
        ])
    return {
        "editable": editable,
        "shared_no_concurrent_edit": [
            "backend/app/main.py",  # router registration only
            "backend/app/dependencies.py",
        ],
        "readonly": [
            "docs/functional-breakdown/2026-05-16_v3/",
            "supabase/migrations/",
            "docs/mocks/2026-05-15_v3/",
        ],
        "forbidden": [
            "frontend/",
            "scripts/lint-mock.sh",
            "scripts/validate-tickets.py",
            "docs/decisions/",
        ],
    }


def estimate_for_task(eps: list[dict]) -> tuple[float, int]:
    n = len(eps)
    # 1.3 h per endpoint baseline (router + service + schema + tests), min 2h
    hours = max(2.0, round(1.3 * n + 1.0, 1))
    if hours > 6.0:
        hours = 6.0
    sessions = 1 if hours <= 4.0 else 2
    return hours, sessions


def make_screen_ids(feature: dict) -> list[str]:
    return feature.get("related_screens", [])


# ---------------------------------------------------------------------------
# 5. Main builder
# ---------------------------------------------------------------------------
def build_tasks() -> tuple[list[dict], dict[str, list[tuple[str, str, str]]]]:
    drift = parse_drift()
    feats = load_features()
    tasks: list[dict] = []

    # Track which critical endpoints have been assigned to verify full coverage
    assigned: dict[str, set[str]] = defaultdict(set)
    # Track per-feature previous task ID for depends_on chaining (file mutex within same feature)
    prev_task_by_feature: dict[str, str] = {}

    for task_id, fid, title_suffix, paths in TASK_PLAN:
        feat = feats[fid]
        drift_paths = [p for _, p, _ in drift[fid]]
        eps = endpoints_for_task(feat, paths, drift_paths)
        if not eps:
            raise RuntimeError(f"{task_id}: no endpoints matched ({paths=})")
        for ep in eps:
            assigned[fid].add(ep["path"])

        modules = feature_files(fid)
        # Choose module(s) for this task. Simplification: include all modules
        # of the feature when paths span them; otherwise reduce. For boundary
        # safety we list all modules of the feature on every task of that feature.
        # File mutex is enforced at module file level — each task within a feature
        # MUST split editable files cleanly. We achieve this by tagging each task
        # with a sub-set of modules based on path prefix when possible.
        chosen_modules = _modules_for_paths([ep["path"] for ep in eps], modules)

        hours, sessions = estimate_for_task(eps)
        ent_ids = feature_entities_short(fid, feat)
        ac_struct = []  # backend-only → empty
        ac_func = build_functional_ac(feat, eps)
        ac_reg = build_regression_ac(task_id, ent_ids)

        # File mutex enforcement: if a task within the same feature shares editable
        # files with a previous task, chain via depends_on so they run sequentially
        # in different waves. Otherwise tasks can run in parallel in Wave 1.
        depends_on: list[str] = []
        wave = 1
        feature_task_count = sum(1 for t in tasks if t["feature_id"] == fid)
        if feature_task_count > 0:
            # find latest task of this feature so far
            prev = [t for t in tasks if t["feature_id"] == fid][-1]
            depends_on = [prev["id"]]
            wave = int(prev["wave"]) + 1
        prev_task_by_feature[fid] = task_id

        task = {
            "id": task_id,
            "title": f"Backend: {title_suffix} ({fid})",
            "category": "backend",
            "label": "NEW",
            "feature_id": fid,
            "screen_ids": make_screen_ids(feat),
            "entity_ids": ent_ids,
            "legacy_task_id": None,
            "phase": "Phase 1A",
            "wave": str(wave),
            "wave_priority": "First" if wave == 1 else "Second",
            "group": "B",
            "deliverable_layer": "backend",
            "estimate_hours": hours,
            "estimate_sessions": sessions,
            "depends_on": depends_on,
            "files_changed": make_files_changed(fid, chosen_modules),
            "work_package_boundary": make_boundary(chosen_modules),
            "acceptance_criteria": {
                "structural": ac_struct,
                "functional": ac_func,
                "regression": ac_reg,
            },
            "access_policies_required": access_policies(fid, feat),
            "spec_links": [
                f"docs/functional-breakdown/2026-05-16_v3/features.json#{fid}",
                "docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md",
                "docs/functional-breakdown/2026-05-16_v3/entities.json",
                "skills/task-decomposition/references/profiles/build-factory.md",
            ],
            "audit_md_path": f"docs/audit/2026-05-16_v3/{task_id}.md",
            "branch": f"claude/{task_id}",
            "risk_flags": [],
            "endpoint_count": len(eps),
            "endpoint_paths": [f"{ep['method']} {ep['path']}" for ep in eps],
        }
        tasks.append(task)

    # Verify coverage
    coverage_report = {}
    for fid, drift_eps in drift.items():
        crit_paths = {p for _, p, _ in drift_eps}
        assigned_paths = assigned.get(fid, set())
        missing = crit_paths - assigned_paths
        if missing:
            coverage_report[fid] = missing
    if coverage_report:
        raise RuntimeError(f"coverage gap: {coverage_report}")

    return tasks, drift


def _modules_for_paths(paths: list[str], modules: list[str]) -> list[str]:
    """Pick the minimal set of modules whose names appear in the path strings.

    Fallback: if no module name is matched, return all modules (single-module feature).
    """
    chosen: list[str] = []
    plower = " ".join(paths).lower()
    for m in modules:
        # match either snake or hyphen variants in path
        m_variants = [m, m.replace("_", "-")]
        if any(v in plower for v in m_variants):
            chosen.append(m)
    if not chosen:
        # single-module fallback
        chosen = modules[:1] if len(modules) == 1 else modules
    return chosen


# ---------------------------------------------------------------------------
# 6. Emit outputs
# ---------------------------------------------------------------------------
def emit_tickets_json(tasks: list[dict]) -> None:
    by_wave: dict[str, int] = defaultdict(int)
    for t in tasks:
        by_wave[t["wave"]] += 1
    summary = {
        "total_tasks": len(tasks),
        "by_group": {"B": len(tasks)},
        "by_category": {"backend": len(tasks)},
        "by_label": {"NEW": len(tasks)},
        "by_deliverable_layer": {"backend": len(tasks)},
        "by_phase": {"Phase 1A": len(tasks)},
        "by_wave": dict(by_wave),
        "total_estimate_hours": round(sum(t["estimate_hours"] for t in tasks), 1),
        "total_estimate_sessions": sum(t["estimate_sessions"] for t in tasks),
        "total_endpoint_count": sum(t["endpoint_count"] for t in tasks),
    }
    payload = {
        "version": "v3",
        "project": "Build-Factory",
        "phase": "Phase 1A: Backend",
        "group": "B",
        "profile": "skills/task-decomposition/references/profiles/build-factory.md",
        "created_at": "2026-05-16",
        "source_drift_summary": "docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md",
        "source_features": "docs/functional-breakdown/2026-05-16_v3/features.json",
        "summary": summary,
        "tasks": tasks,
    }
    TICKETS_OUT.parent.mkdir(parents=True, exist_ok=True)
    TICKETS_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {TICKETS_OUT} ({len(tasks)} tasks)")


def emit_tasks_md(tasks: list[dict]) -> None:
    lines: list[str] = []
    lines.append("# Phase 1A Group B (Backend) Task Cards\n")
    lines.append(
        f"> Generated: 2026-05-16 / source: features.json + api-drift-summary.md / "
        f"total tasks: {len(tasks)} / total endpoints covered: "
        f"{sum(t['endpoint_count'] for t in tasks)}\n"
    )
    for t in tasks:
        lines.append(f"## {t['id']}: {t['title']}")
        lines.append("")
        lines.append(f"- **feature**: {t['feature_id']} / **screens**: {', '.join(t['screen_ids']) or 'n/a'}")
        lines.append(f"- **entities**: {', '.join(t['entity_ids']) or 'n/a'}")
        lines.append(f"- **wave**: {t['wave']} / **group**: {t['group']} / **deliverable**: {t['deliverable_layer']}")
        lines.append(f"- **estimate**: {t['estimate_hours']}h / {t['estimate_sessions']} session(s)")
        lines.append(f"- **endpoint paths** ({t['endpoint_count']}):")
        for ep in t["endpoint_paths"]:
            lines.append(f"  - `{ep}`")
        lines.append(f"- **branch**: `{t['branch']}` / **audit**: `{t['audit_md_path']}`")
        lines.append("")
        lines.append("### files_changed")
        for fc in t["files_changed"]:
            lines.append(f"- {fc}")
        lines.append("")
        lines.append("### acceptance_criteria.functional (excerpt, first 5)")
        for ac in t["acceptance_criteria"]["functional"][:5]:
            lines.append(f"- {ac}")
        if len(t["acceptance_criteria"]["functional"]) > 5:
            lines.append(f"- (+{len(t['acceptance_criteria']['functional']) - 5} more — see tickets.json)")
        lines.append("")
        lines.append("### access_policies_required")
        for p in t["access_policies_required"] or ["(none)"]:
            lines.append(f"- {p}")
        lines.append("")
        lines.append("---\n")
    TASKS_MD_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {TASKS_MD_OUT}")


def emit_audit_mds(tasks: list[dict]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        tid = t["id"]
        fid = t["feature_id"]
        ac_struct = t["acceptance_criteria"]["structural"]
        ac_func = t["acceptance_criteria"]["functional"]
        ac_reg = t["acceptance_criteria"]["regression"]
        body: list[str] = []
        body.append(f"# {tid} audit\n")
        body.append(f"> {t['title']}")
        body.append(
            "> 3-tier AC を逐語コピーし、impl line と実行ログを記録する pre-flight template。\n"
            "> 着手前に impl 行を埋め、完了時に [x] と実行ログを追記すること。\n"
        )
        body.append(f"- **Task**: {tid} — {t['title']}")
        body.append(f"- **Feature**: {fid} / **Screens**: {', '.join(t['screen_ids']) or 'n/a'}")
        body.append(f"- **Entities**: {', '.join(t['entity_ids']) or 'n/a'}")
        body.append(f"- **Label**: {t['label']} / **Layer**: {t['deliverable_layer']} / **Wave**: {t['wave']}")
        body.append(f"- **Estimate**: {t['estimate_hours']}h / {t['estimate_sessions']} session(s)")
        body.append(f"- **Branch**: `{t['branch']}`")
        body.append(f"- **Spec links**:")
        for s in t["spec_links"]:
            body.append(f"  - {s}")
        body.append("")
        body.append("## Tier 1: Structural\n")
        if not ac_struct:
            body.append("(該当なし / backend-only task: structural AC は backend-only のため `[]`)\n")
        else:
            for i, ac in enumerate(ac_struct, 1):
                body.append(f"- [ ] AC-S{i}: {ac} → impl: <path>:<lines>")
        body.append("")
        body.append("## Tier 2: Functional\n")
        body.append("(AC verbatim — features.json#ears_ac_seed をコピー + 各 endpoint の派生 EARS)\n")
        for i, ac in enumerate(ac_func, 1):
            body.append(f"- [ ] AC-F{i}: {ac} → impl: <backend/app/routers|services|schemas/...>:<lines>, test: <backend/tests/routers/test_*.py>::<test_func>")
        body.append("")
        body.append("## Tier 3: Regression\n")
        for i, ac in enumerate(ac_reg, 1):
            body.append(f"- [ ] AC-R{i}: {ac} → 実行ログ: <pending>")
        body.append("")
        body.append("## Decision: PLANNED | DONE | BLOCKED | GAP\n")
        body.append("着手記録 / 完了記録 / ノートを以下に追記する.\n")
        body.append("## 着手記録\n- 着手日: (yyyy-mm-dd)\n- 担当 session: (session_id)\n- branch: " + t['branch'] + "\n")
        body.append("## 完了記録\n- 完了日: (yyyy-mm-dd)\n- Decision: PLANNED\n- PR: (subagent が PR 作成後に追記)\n")
        body.append("## ノート\n- (impl 時の判断 / drift / skip-with-reason をここに記録)\n")
        path = AUDIT_DIR / f"{tid}.md"
        path.write_text("\n".join(body), encoding="utf-8")
    print(f"wrote {len(tasks)} audit MD files to {AUDIT_DIR}")


def main() -> int:
    tasks, drift = build_tasks()
    # final coverage report (print)
    total_crit = sum(len(v) for v in drift.values())
    covered = sum(t["endpoint_count"] for t in tasks)
    print(f"critical endpoints in drift summary: {total_crit}")
    print(f"endpoints covered by tasks: {covered}")
    emit_tickets_json(tasks)
    emit_tasks_md(tasks)
    emit_audit_mds(tasks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
