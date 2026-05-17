#!/usr/bin/env python3
"""Generate tickets-group-b1-api-missing.json from openapi.yaml + api-drift-summary.md.

This script produces 94 task entries for critical-missing endpoint implementation
in Build-Factory v3 Phase 1.0-fix Wave 0 Group B-1.

Output schema matches tickets-group-d-drift.json (v3 schema validated by
scripts/validate-tickets.py --check-file).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path("/home/user/Build-Factory/.claude/worktrees/agent-a6d7cfc1782cc2e6f")
OPENAPI = ROOT / "docs/api-design/2026-05-16_v3/openapi.yaml"
ENTITIES_JSON = ROOT / "docs/functional-breakdown/2026-05-16_v3/entities.json"
DRIFT_MD = ROOT / "docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md"
OUT_TICKETS = ROOT / "docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b1-api-missing.json"

# -------------------------------------------------------------
# Load sources
# -------------------------------------------------------------
spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
ents_data = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))

# entity_id -> {table_name, access_policy_names}
entity_lookup: dict[str, dict] = {}
for e in ents_data["entities"]:
    eid = e["id"]
    pols = e.get("access_control_policies") or []
    names = []
    for p in pols:
        if isinstance(p, dict):
            n = p.get("name")
            if n:
                names.append(n)
    entity_lookup[eid] = {
        "name": e.get("name"),
        "table_name": e.get("table_name"),
        "policies": names,
    }

# OpenAPI line numbers for spec_links
openapi_lines = OPENAPI.read_text(encoding="utf-8").splitlines()
path_line_map: dict[str, int] = {}
for i, line in enumerate(openapi_lines, 1):
    m = re.match(r"^  (/api/[^\s:]+):\s*$", line)
    if m:
        path_line_map[m.group(1)] = i

# drift-summary endpoint task_id -> line number (for spec_link)
drift_lines = DRIFT_MD.read_text(encoding="utf-8").splitlines()
drift_task_line: dict[str, int] = {}
for i, line in enumerate(drift_lines, 1):
    m = re.search(r"(T-V3-DRIFT-F-[0-9A-Za-z]+-\d+)", line)
    if m:
        drift_task_line[m.group(1)] = i


# -------------------------------------------------------------
# Collect 94 critical endpoints from openapi
# -------------------------------------------------------------
def normalize_entity_id(raw: str) -> str | None:
    """Convert 'E-002 User' -> 'E-002'."""
    m = re.match(r"(E-\d{3})", raw)
    return m.group(1) if m else None


def feature_module(feature_id: str) -> str:
    """Map F-XXX to backend module slug used in router/service/test path."""
    return {
        "F-001": "auth",
        "F-002": "skills",
        "F-003": "ai_employees",
        "F-004": "accounts",
        "F-005": "spec",
        "F-005b": "mocks",
        "F-006": "requirements",
        "F-007": "tasks",
        "F-008": "phases",
        "F-009": "dependencies",
        "F-010": "sessions",
        "F-012": "red_lines",
        "F-013": "github_pr",
        "F-016": "knowledge",
        "F-017": "observability",
        "F-018": "audit_notifications",
        "F-023": "me_profile",
        "F-024": "search_dashboard",
        "F-026": "constitution",
        "F-027": "onboarding",
        "F-028": "email_delivery",
    }.get(feature_id, feature_id.lower().replace("-", "_"))


def auth_role_for(role: str | None) -> str:
    return role or "authenticated"


def build_ac_structural(task_id: str, method: str, path: str, module: str, impl_path: str | None) -> list[str]:
    fn_name = (impl_path or "").split("::")[-1] if impl_path else ""
    if not fn_name:
        fn_name = f"{method.lower()}_{module}"
    return [
        f"UBIQUITOUS: The system shall expose a FastAPI route at `{method} {path}` registered via APIRouter in `backend/routers/{module}.py` and included in `backend/app/main.py`.",
        f"UBIQUITOUS: The route handler `{fn_name}` shall conform to the OpenAPI v3 spec at `docs/api-design/2026-05-16_v3/openapi.yaml` (operationId, request schema, response schema, status codes 1:1).",
        f"EVENT-DRIVEN: When `pytest backend/tests/contract/test_openapi_contract.py::test_{task_id.lower().replace('-','_')}` is executed via Schemathesis, the system shall pass the contract test with 0 drift against the OpenAPI document.",
    ]


def build_ac_functional(method: str, path: str, auth_role: str, errors: list[dict], rate_limit: str | None, responses: list[str], policies: list[str]) -> list[str]:
    ac: list[str] = []
    # Success path
    success_codes = [r for r in responses if r.startswith("2")]
    primary = success_codes[0] if success_codes else "200"
    ac.append(
        f"EVENT-DRIVEN: When a `{auth_role}` caller sends a syntactically valid `{method} {path}` request, the system shall return HTTP {primary} with a response body matching the OpenAPI schema for that operation."
    )
    # Per-error seed -> EARS AC (already in ears_form)
    for err in errors:
        ef = (err.get("ears_form") or "").strip()
        if ef:
            ac.append(ef)
        else:
            ac.append(
                f"UNWANTED: If {err.get('trigger', 'invalid request')}, the system shall return {err.get('status')}."
            )
    # RLS / access policy enforcement (if any)
    if policies:
        ac.append(
            f"STATE-DRIVEN: While the caller is authenticated as `{auth_role}`, the system shall enforce row-level access via Supabase RLS policies: {', '.join(policies)}."
        )
    elif auth_role and auth_role != "public":
        ac.append(
            f"UNWANTED: If the caller is not authenticated (`{auth_role}` required), the system shall return 401 without leaking row data."
        )
    # Rate limit
    if rate_limit:
        ac.append(
            f"OPTIONAL: Where rate limit `{rate_limit}` is configured, the system shall return 429 when the caller exceeds the per-window quota."
        )
    return ac


def build_ac_regression(task_id: str, module: str) -> list[str]:
    return [
        f"The system shall pass `pytest backend/tests/integration/test_{module}_endpoints.py -v -k {task_id}` with 0 failures and coverage >= 70% on the touched router and service modules.",
        "The system shall pass `pyright --strict backend/routers/ backend/services/` with 0 errors on edited files.",
        "The system shall pass `ruff check backend/routers/ backend/services/ backend/tests/` with 0 violations on edited files.",
        f"The system shall pass `python3 scripts/validate-tickets.py --check-file docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b1-api-missing.json` for entry {task_id}.",
        "The system shall pass `bash scripts/lint-mock.sh` with 17/17 rules OK.",
        f"The system shall pass `bash scripts/audit-md-check.sh {task_id}`.",
    ]


def risk_flags_for(feature_id: str, path: str, auth_role: str | None) -> list[str]:
    flags: list[str] = []
    if feature_id in ("F-001",):
        flags.append("security_critical: authentication endpoint (token issuance / credential handling)")
    if "/mfa/" in path:
        flags.append("security_critical: MFA (TOTP) — encrypted_secret column access")
    if "/oauth/" in path:
        flags.append("external_api_dependent: OAuth provider callback (Anthropic / Slack / GitHub)")
    if "/api/client/" in path:
        flags.append("public_token_path: client portal — token-based RBAC instead of Supabase JWT")
    if feature_id == "F-013" and "/merge" in path:
        flags.append("destructive: PR merge — irreversible side effect on github_repos")
    if feature_id == "F-010" and ("kill" in path or "rollback" in path):
        flags.append("destructive: session kill / rollback — terminates running Claude Code worker")
    if feature_id == "F-012":
        flags.append("policy_critical: red-line enforcement — blocks downstream automation")
    if feature_id == "F-028":
        flags.append("external_api_dependent: email delivery provider (Resend / SendGrid)")
    if feature_id == "F-017":
        flags.append("external_api_dependent: Langfuse self-host (cost/observability)")
    if feature_id == "F-016":
        flags.append("external_api_dependent: Obsidian Vault filesystem (ADR-012)")
    if auth_role == "public":
        flags.append("unauthenticated_endpoint: must enforce strict rate-limit and input validation")
    return flags


def wave_for(feature_id: str) -> int:
    """Wave 1 = auth + account + skills (foundation user-data layer).
    Wave 2 = workspace-scoped CRUD endpoints (depends on auth).
    Wave 3 = cross-cutting (sessions / pr / notifications / search / extras).
    """
    if feature_id in ("F-001",):
        return 1
    if feature_id in ("F-002", "F-003", "F-004", "F-023", "F-027"):
        return 1
    if feature_id in ("F-005", "F-005b", "F-006", "F-007", "F-008", "F-009", "F-026"):
        return 2
    return 3


# -------------------------------------------------------------
# Walk openapi paths and produce tasks
# -------------------------------------------------------------
critical_eps: list[tuple[str, dict]] = []  # (drift_task_id, info)
for path, methods in spec["paths"].items():
    for method, op in methods.items():
        if method.startswith("x-"):
            continue
        if not isinstance(op, dict):
            continue
        drift = op.get("x-bf-drift") or {}
        if drift.get("severity") != "critical":
            continue
        tid = drift.get("task_id")
        critical_eps.append(
            (
                tid,
                {
                    "method": method.upper(),
                    "path": path,
                    "feature_id": op.get("x-bf-feature-id"),
                    "screen_ids": op.get("x-bf-screen-ids") or [],
                    "entities_raw": op.get("x-bf-related-entities") or [],
                    "auth_role": op.get("x-bf-auth-role") or "authenticated",
                    "access_policies": op.get("x-bf-access-control-policies") or [],
                    "impl_path": op.get("x-bf-implementation-path"),
                    "rate_limit": op.get("x-bf-rate-limit"),
                    "errors": op.get("x-bf-error-seeds") or [],
                    "responses": list(op.get("responses", {}).keys()),
                },
            )
        )

# Sort by feature_id then drift_task_id for deterministic numbering
critical_eps.sort(key=lambda t: (t[1]["feature_id"] or "", t[0] or ""))
assert len(critical_eps) == 94, f"expected 94, got {len(critical_eps)}"

# -------------------------------------------------------------
# Build tasks
# -------------------------------------------------------------
tasks: list[dict] = []
# Map feature_id -> list of T-V3-B1 IDs already produced (for dep edges)
auth_task_ids: list[str] = []  # F-001 endpoints — foundation deps

for idx, (legacy_id, info) in enumerate(critical_eps, 1):
    tid = f"T-V3-B1-{idx:03d}"
    fid = info["feature_id"]
    module = feature_module(fid)
    method = info["method"]
    path = info["path"]
    auth_role = info["auth_role"]

    # entity ids
    entity_ids_full = info["entities_raw"]  # list like 'E-002 User'
    entity_ids = []
    for e in entity_ids_full:
        nid = normalize_entity_id(e)
        if nid:
            entity_ids.append(e)  # keep full readable form

    # access policy compute: collect from openapi if present, else fall back to entity policies
    polset: list[str] = []
    if info["access_policies"]:
        for p in info["access_policies"]:
            if isinstance(p, dict):
                n = p.get("name")
                if n:
                    polset.append(n)
            elif isinstance(p, str):
                polset.append(p)
    if not polset:
        # fallback: gather entity service_role + member_select policies
        for e in entity_ids_full:
            nid = normalize_entity_id(e)
            if nid and nid in entity_lookup:
                tbl = entity_lookup[nid]["table_name"]
                pols = entity_lookup[nid]["policies"]
                for pn in pols:
                    if pn:
                        polset.append(f"{tbl}:{pn}")
    polset = list(dict.fromkeys(polset))  # dedupe preserving order

    # title — short, action-oriented
    title = f"Implement {method} {path} endpoint ({fid} / {legacy_id})"

    # files_changed — concrete paths
    files_changed = [
        f"backend/routers/{module}.py (modify or new)",
        f"backend/services/{module}.py (modify or new)",
        f"backend/schemas/{module}.py (modify or new)",
        f"backend/tests/integration/test_{module}_endpoints.py (modify or new)",
        f"backend/tests/contract/test_openapi_contract.py (modify: add operationId test stub)",
    ]
    if module != "auth" and fid != "F-001":
        # main.py only needs to be touched on truly new modules; conservatively list it as readonly
        pass

    # work_package_boundary
    editable = [
        f"backend/routers/{module}.py",
        f"backend/services/{module}.py",
        f"backend/schemas/{module}.py",
        f"backend/tests/integration/test_{module}_endpoints.py",
        f"docs/audit/2026-05-16_v3/{tid}.md",
    ]
    shared_no_concurrent_edit = [
        "backend/app/main.py",
        "backend/tests/contract/test_openapi_contract.py",
    ]
    readonly = [
        "docs/api-design/2026-05-16_v3/openapi.yaml",
        "docs/functional-breakdown/2026-05-16_v3/features.json",
        "docs/functional-breakdown/2026-05-16_v3/entities.json",
        "docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md",
    ]
    forbidden = [
        "frontend/",
        "supabase/migrations/",
        "scripts/lint-mock.sh",
        "scripts/validate-tickets.py",
        ".claude/settings.json",
    ]

    # 3-tier AC
    structural = build_ac_structural(tid, method, path, module, info["impl_path"])
    functional = build_ac_functional(
        method, path, auth_role, info["errors"], info["rate_limit"], info["responses"], polset
    )
    regression = build_ac_regression(tid, module)

    # spec_links
    spec_links = [
        f"docs/api-design/2026-05-16_v3/openapi.yaml#L{path_line_map.get(path, '?')}",
        f"docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md#L{drift_task_line.get(legacy_id, '?')}",
        f"docs/functional-breakdown/2026-05-16_v3/features.json#{fid}",
    ]

    # depends_on
    depends_on: list[str] = []
    # auth/foundation endpoints are independent (Wave 1 head)
    if fid == "F-001":
        # serial within auth: each later auth endpoint depends on login + signup
        if legacy_id not in ("T-V3-DRIFT-F-001-01", "T-V3-DRIFT-F-001-02"):
            # depend on login + signup (first two)
            pass  # filled in after auth_task_ids is built
    else:
        # non-auth endpoints depend on login (first F-001 task)
        pass  # filled in after auth_task_ids is built

    # estimate
    if fid in ("F-001",):
        estimate_hours = 4
    elif fid in ("F-013", "F-010", "F-012"):
        # webhook-like / external deps / complex
        estimate_hours = 4
    elif method == "GET" and "/" not in path[len("/api/") :].split("{")[0].rstrip("/").split("/", 1)[-1]:
        # plain list endpoint — simpler
        estimate_hours = 2
    elif method == "DELETE":
        estimate_hours = 2
    else:
        estimate_hours = 3

    # Track F-001 ids for dependency edges
    if fid == "F-001":
        auth_task_ids.append(tid)

    risk_flags = risk_flags_for(fid, path, auth_role)

    task = {
        "id": tid,
        "title": title,
        "category": "backend",
        "label": "NEW",
        "feature_id": fid,
        "screen_ids": info["screen_ids"],
        "entity_ids": entity_ids,
        "legacy_task_id": legacy_id,
        "phase": "Phase 1.0-fix",
        "wave": wave_for(fid),
        "group": "B-1",
        "deliverable_layer": "backend",
        "estimate_hours": estimate_hours,
        "estimate_sessions": 1,
        "depends_on": [],  # filled below after collecting auth ids
        "files_changed": files_changed,
        "work_package_boundary": {
            "editable": editable,
            "shared_no_concurrent_edit": shared_no_concurrent_edit,
            "readonly": readonly,
            "forbidden": forbidden,
        },
        "acceptance_criteria": {
            "structural": structural,
            "functional": functional,
            "regression": regression,
        },
        "access_policies_required": polset,
        "spec_links": spec_links,
        "audit_md_path": f"docs/audit/2026-05-16_v3/{tid}.md",
        "branch": f"claude/{tid}",
        "risk_flags": risk_flags,
    }
    tasks.append(task)

# -------------------------------------------------------------
# Fill dependencies (second pass — needs full auth_task_ids list)
# -------------------------------------------------------------
# Foundation auth deps:
# F-001-01 (login) and F-001-02 (signup) are independent.
# Other F-001 endpoints (password-reset, mfa/enroll, mfa/verify, oauth/callback) depend on signup or login.
# All non-F-001 endpoints depend on login.
auth_login_id: str | None = None
auth_signup_id: str | None = None
for t in tasks:
    if t["legacy_task_id"] == "T-V3-DRIFT-F-001-01":
        auth_login_id = t["id"]
    if t["legacy_task_id"] == "T-V3-DRIFT-F-001-02":
        auth_signup_id = t["id"]

for t in tasks:
    fid = t["feature_id"]
    lid = t["legacy_task_id"]
    deps: list[str] = []
    if fid == "F-001":
        if lid in ("T-V3-DRIFT-F-001-01", "T-V3-DRIFT-F-001-02"):
            deps = []
        elif lid == "T-V3-DRIFT-F-001-03":  # password-reset depends on signup
            deps = [x for x in [auth_signup_id] if x]
        elif lid in ("T-V3-DRIFT-F-001-04", "T-V3-DRIFT-F-001-05"):  # mfa enroll/verify depend on login
            deps = [x for x in [auth_login_id] if x]
        elif lid == "T-V3-DRIFT-F-001-06":  # oauth callback depends on login
            deps = [x for x in [auth_login_id] if x]
    else:
        # Every non-auth endpoint depends on the login endpoint having shipped
        # (so tests can authenticate)
        deps = [x for x in [auth_login_id] if x]
    t["depends_on"] = deps

# -------------------------------------------------------------
# Summary
# -------------------------------------------------------------
by_wave: dict[int, int] = {}
by_feature: dict[str, int] = {}
total_hours = 0
for t in tasks:
    by_wave[t["wave"]] = by_wave.get(t["wave"], 0) + 1
    by_feature[t["feature_id"]] = by_feature.get(t["feature_id"], 0) + 1
    total_hours += t["estimate_hours"]

doc = {
    "version": "v3",
    "project": "Build-Factory",
    "profile": "skills/task-decomposition/references/profiles/build-factory.md",
    "phase_target": "Phase 1.0-fix (Wave 0 / Group B-1 critical-missing endpoint implementation)",
    "created_at": "2026-05-17",
    "group": "B-1",
    "summary": {
        "total_tasks": len(tasks),
        "by_group": {"B-1 (critical missing API)": len(tasks)},
        "by_category": {"backend": len(tasks)},
        "by_label": {"NEW": len(tasks)},
        "by_deliverable_layer": {"backend": len(tasks)},
        "by_phase": {"Phase 1.0-fix": len(tasks)},
        "by_wave": {str(k): v for k, v in sorted(by_wave.items())},
        "by_feature": dict(sorted(by_feature.items())),
        "total_estimate_hours": total_hours,
        "total_estimate_sessions": len(tasks),
        "parallel_capacity_used": 6,
        "real_time_estimate_hours": max(8, total_hours // 6),
        "drift_coverage": {
            "critical_missing_endpoints": len(tasks),
            "source": "docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md (critical severity 94 件)",
        },
        "notes": "Group B-1 は 94 critical-missing endpoint を 3 wave (W1: auth+foundation 13 件 / W2: workspace-scoped CRUD 40 件 / W3: cross-cutting 41 件) で並列実装する。全 task は backend カテゴリの NEW 実装で、Foundation OpenAPI contract (openapi.yaml) との 1:1 整合を Schemathesis で gate する。Wave 1 の F-001 auth エンドポイント完成が他 Wave の前提条件 (token-issuing endpoint 無しでは他 API テストが authenticate できない)。",
    },
    "tasks": tasks,
}

OUT_TICKETS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT_TICKETS} ({len(tasks)} tasks, total {total_hours}h)")
print(f"by_wave: {by_wave}")
print(f"by_feature: {by_feature}")
