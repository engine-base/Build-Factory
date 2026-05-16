#!/usr/bin/env python3
"""v3 tickets.json generator.

124 task に Group H 99 件展開を加え、計 211 task の tickets.json を生成する。
"""
import json
import os
from pathlib import Path

V3_DIR = Path(__file__).parent
OUT_TICKETS = V3_DIR / "tickets.json"
OUT_DEPS = V3_DIR / "DEPENDENCIES.md"
OUT_DECISION = V3_DIR / "decision_log.json"
OUT_MIGRATION = V3_DIR / "migration_from_v1.md"

# ---------- COMMON HELPERS ----------

def ac(structural=None, functional=None, regression=None):
    """Build 3-tier AC dict."""
    return {
        "structural": structural or [],
        "functional": functional or [],
        "regression": regression or [
            "The system shall pass pytest on touched test files (>= 1 dedicated test_*.py).",
            "The system shall pass ruff (Python) and ESLint (TS) on touched files.",
            "The system shall pass pyright --strict with 0 errors on touched modules.",
            "The system shall maintain coverage >= 70% on touched files.",
            "The system shall pass all lint-mock.sh checks (1..19)."
        ]
    }


def task(tid, title, category, label, feature_ids, screen_ids, entity_ids,
         legacy_id, phase, wave, hours, sessions, depends, files,
         acceptance, spec_links=None, rls=None, notes=None):
    """Build a single task dict."""
    return {
        "id": tid,
        "title": title,
        "category": category,
        "label": label,
        "feature_ids": feature_ids,
        "screen_ids": screen_ids,
        "entity_ids": entity_ids,
        "legacy_task_id": legacy_id,
        "phase": phase,
        "wave": wave,
        "estimate_hours": hours,
        "estimate_sessions": sessions,
        "depends_on": depends,
        "files_changed": files,
        "acceptance_criteria": acceptance,
        "rls_policies_required": rls or [],
        "spec_links": spec_links or [],
        "audit_md_path": f"docs/audit/2026-05-15_v3/{tid}.md",
        "notes": notes or ""
    }


# ============================================================
# GROUP A — Infrastructure (Phase 0, 8 件)
# ============================================================

GROUP_A = [
    task("T-V3-INFRA-01",
         "ADR-013 起票: AUTH 戦略 (REST API として `/api/auth/*` 実装)",
         "doc", "NEW", ["F-001", "F-021"], ["S-001", "S-002", "S-003", "S-004", "S-005"],
         ["E-001", "E-008", "E-038"], None, 0, 1, 2, 1, [],
         ["docs/decisions/ADR-013-auth-strategy.md"],
         ac(functional=[
             "UBIQUITOUS: The ADR shall document why AUTH is implemented as REST API (`POST /api/auth/login` etc.) rather than client-side Supabase Auth delegation.",
             "UBIQUITOUS: The ADR shall list all 6 affected screens (S-001..S-005) and 6 affected endpoints.",
             "UBIQUITOUS: The ADR shall declare backward-incompatibility with v1 implicit Supabase Auth assumption."
         ])),
    task("T-V3-INFRA-02",
         "ADR-014 起票: 命名統一 (`bf_` prefix 廃止 / entity PascalCase ↔ table snake_case 1:1)",
         "doc", "NEW", ["F-001"], [], [],
         None, 0, 1, 2, 1, [],
         ["docs/decisions/ADR-014-naming-standard.md"],
         ac(functional=[
             "UBIQUITOUS: The ADR shall declare entity name (entities.json, PascalCase) maps 1:1 to DB table (snake_case_of_pascal).",
             "UBIQUITOUS: The ADR shall list all `bf_*` tables to be renamed (>= 5).",
             "UBIQUITOUS: The ADR shall include a migration timeline (Phase 0 freeze new bf_* / Phase 2 deletion of bf_* alias)."
         ])),
    task("T-V3-INFRA-03",
         "lint #17: scripts/lint-mock-impl-diff.sh (mock h1/KPI/sections ↔ impl page.tsx 比較)",
         "infra", "NEW", ["F-005b"], [], [],
         None, 0, 1, 8, 2, [],
         ["scripts/lint-mock-impl-diff.sh"],
         ac(functional=[
             "EVENT-DRIVEN: When invoked, the script shall for each S-XXX in screens.json: extract mock h1 + Hero KPI labels + h2 section titles from docs/mocks/.../<id>-*.html.",
             "EVENT-DRIVEN: When invoked, the script shall locate the corresponding implementation page.tsx and extract its h1 / KPI label props / section titles.",
             "UNWANTED: If any h1 / KPI / section text differs, the script shall exit code != 0 with a diff report listing screen_id, mock_path, impl_path, diff_lines.",
             "OPTIONAL: Where a screen has no implementation, the script shall log it as MISSING (not a failure unless --strict is set)."
         ]),
         notes="このスクリプトが Group D, E, F の Done 判定に直接使われる。"),
    task("T-V3-INFRA-04",
         "lint #18: scripts/lint-screens-api.py (screens.json の related_apis が backend に存在するか)",
         "infra", "NEW", ["F-001"], [], [],
         None, 0, 1, 4, 1, [],
         ["scripts/lint-screens-api.py"],
         ac(functional=[
             "EVENT-DRIVEN: When invoked, the script shall enumerate all `related_apis` strings in docs/functional-breakdown/.../screens.json.",
             "EVENT-DRIVEN: When invoked, the script shall enumerate all `@router.{get,post,put,delete,patch}` decorators with their paths in backend/.",
             "UNWANTED: If any spec API is not implemented in backend, the script shall exit code != 0 with a list of missing endpoints by screen_id.",
             "UBIQUITOUS: The script shall normalize path prefixes (/api/v1 vs /api vs /) per ADR-013."
         ])),
    task("T-V3-INFRA-05",
         "lint #19: scripts/lint-entity-table-naming.py (entity PascalCase ↔ table snake_case 1:1)",
         "infra", "NEW", ["F-001"], [], [],
         None, 0, 1, 4, 1, ["T-V3-INFRA-02"],
         ["scripts/lint-entity-table-naming.py"],
         ac(functional=[
             "EVENT-DRIVEN: When invoked, the script shall parse entities.json and enumerate entity names (PascalCase).",
             "EVENT-DRIVEN: When invoked, the script shall parse supabase/migrations/*.sql and enumerate CREATE TABLE statements.",
             "UNWANTED: If any entity has no matching table OR table uses `bf_` prefix without explicit ADR-014 exemption, the script shall exit != 0.",
             "OPTIONAL: Where a table has a snake_case name that doesn't match the entity's PascalCase, the script shall report it as a NAMING DRIFT."
         ])),
    task("T-V3-INFRA-06",
         "AC schema 拡張: validate-ears-ac.py に 3-tier 必須化 (structural/functional/regression)",
         "infra", "REFACTOR", ["F-006"], [], [],
         None, 0, 1, 4, 1, [],
         ["scripts/validate-ears-ac.py"],
         ac(functional=[
             "EVENT-DRIVEN: When invoked on a tickets.json, the script shall verify each task's acceptance_criteria has all 3 keys (structural, functional, regression).",
             "UNWANTED: If structural is non-empty but the task has no screen_ids, the script shall exit != 0.",
             "UNWANTED: If functional is empty, the script shall exit != 0 (every task must have functional AC).",
             "UNWANTED: If regression is empty, the script shall exit != 0."
         ])),
    task("T-V3-INFRA-07",
         "backend pyright strict 設定 (pyrightconfig.json 新規 + 既存型エラー解消 / 初回は --strict-only-changes で baseline)",
         "infra", "NEW", ["F-001"], [], [],
         None, 0, 1, 12, 3, [],
         ["pyrightconfig.json", ".pyright-baseline"],
         ac(functional=[
             "UBIQUITOUS: The pyrightconfig.json shall enable strict mode with reportMissingTypeStubs=warning.",
             "EVENT-DRIVEN: When pyright is run on the backend/ folder, it shall report 0 NEW errors compared to .pyright-baseline.",
             "UBIQUITOUS: The CI shall fail if a PR introduces new pyright strict errors."
         ])),
    task("T-V3-INFRA-08",
         "coverage gate 70% 強制 (CI / pytest --cov-fail-under=70 + .coverage-baseline 更新)",
         "infra", "REFACTOR", ["F-001"], [], [],
         None, 0, 1, 4, 1, [],
         [".github/workflows/ci.yml", ".coverage-baseline"],
         ac(functional=[
             "EVENT-DRIVEN: When CI runs on a PR, pytest shall be invoked with `--cov --cov-fail-under=70`.",
             "UNWANTED: If coverage drops below 70% on any touched module, the CI shall fail.",
             "UBIQUITOUS: The .coverage-baseline shall be updated atomically only on main branch merges."
         ])),
]


# ============================================================
# GROUP B — AUTH 完全実装 (15 件)
# ============================================================

GROUP_B = [
    task("T-V3-AUTH-01", "POST /api/auth/login 実装",
         "backend", "NEW", ["F-001", "F-021"], ["S-001"], ["E-001 User", "E-038 AuthSession"],
         None, 1, 1, 8, 2, ["T-V3-INFRA-01"],
         ["backend/routers/auth.py", "backend/services/auth_service.py", "tests/test_T-V3-AUTH-01.py"],
         ac(functional=[
             "EVENT-DRIVEN: When valid email+password is POSTed, the system shall return 200 with { access_token, expires_in } AND set-cookie: refresh_token=...; HttpOnly; SameSite=Strict.",
             "UNWANTED: If credentials are invalid (wrong password OR user not found), the system shall return 401 with body {\"error\":\"invalid_credentials\"} (no user enumeration distinction).",
             "EVENT-DRIVEN: When 6 requests come from same IP within 60s, the system shall return 429.",
             "STATE-DRIVEN: While user.mfa_enabled = TRUE, the system shall return 202 with { mfa_challenge_id, expires_in } instead of access_token.",
             "UNWANTED: If POST body lacks email or password, the system shall return 422."
         ]),
         rls=["users:select_self", "auth_sessions:insert_owner"]),
    task("T-V3-AUTH-02", "POST /api/auth/signup 実装",
         "backend", "NEW", ["F-001", "F-004"], ["S-002"], ["E-001 User", "E-008 Account", "E-002 AccountMember"],
         None, 1, 1, 8, 2, ["T-V3-AUTH-01"],
         ["backend/routers/auth.py", "backend/services/auth_service.py"],
         ac(functional=[
             "EVENT-DRIVEN: When valid email+password+display_name is POSTed, the system shall (within a transaction) create User + Account + AccountMember and return 201 with same body as /login.",
             "UNWANTED: If email is already taken, the system shall return 409 (email_taken).",
             "UNWANTED: If password is shorter than 12 chars or fails complexity check, the system shall return 422 (weak_password) with detail.",
             "EVENT-DRIVEN: When signup succeeds, the system shall enqueue a welcome email job (async, no synchronous wait)."
         ]),
         rls=["users:insert_self", "accounts:insert_via_signup", "account_members:insert_self_as_owner"]),
    task("T-V3-AUTH-03", "POST /api/auth/password-reset 実装",
         "backend", "NEW", ["F-001"], ["S-003"], ["E-039 PasswordReset"],
         None, 1, 1, 4, 1, ["T-V3-AUTH-01"],
         ["backend/routers/auth.py"],
         ac(functional=[
             "EVENT-DRIVEN: When valid email is POSTed, the system shall return 202 with no body AND enqueue a reset-email with a single-use token (24h TTL).",
             "UBIQUITOUS: The system shall return 202 regardless of whether the email exists (no user enumeration).",
             "EVENT-DRIVEN: When the token is later POSTed with new_password, the system shall update users.password_hash and invalidate all existing auth_sessions for that user."
         ]),
         rls=["password_resets:insert_anon", "password_resets:consume_with_token"]),
    task("T-V3-AUTH-04", "POST /api/auth/mfa/enroll 実装",
         "backend", "NEW", ["F-001"], ["S-004"], ["E-001 User"],
         None, 1, 1, 4, 1, ["T-V3-AUTH-01"],
         ["backend/routers/auth.py"],
         ac(functional=[
             "EVENT-DRIVEN: When an authenticated user POSTs /mfa/enroll, the system shall generate a TOTP secret + 10 recovery codes, return otpauth://... URI + QR PNG + codes (only shown once).",
             "UBIQUITOUS: The system shall store the secret in user_2fa_secrets (pgsodium encrypted) but NOT yet flip user.mfa_enabled.",
             "EVENT-DRIVEN: When the user later POSTs /mfa/verify with a valid TOTP code, the system shall flip user.mfa_enabled = TRUE."
         ]),
         rls=["user_2fa_secrets:insert_self", "user_2fa_secrets:select_self_only"]),
    task("T-V3-AUTH-05", "POST /api/auth/mfa/verify 実装",
         "backend", "NEW", ["F-001"], ["S-004"], ["E-001 User"],
         None, 1, 1, 4, 1, ["T-V3-AUTH-04"],
         ["backend/routers/auth.py"],
         ac(functional=[
             "EVENT-DRIVEN: When { mfa_challenge_id, code } is POSTed and code is a valid TOTP for that user, the system shall return 200 with { access_token, expires_in } and rotate mfa_challenge_id (no replay).",
             "UNWANTED: If code is invalid OR challenge expired, the system shall return 401 (mfa_invalid).",
             "EVENT-DRIVEN: When 5 wrong codes are entered within 5 minutes, the system shall lock MFA for 15 minutes and return 429."
         ])),
    task("T-V3-AUTH-06", "GET /api/auth/oauth/{provider}/callback 移設 + 統合 signup",
         "backend", "REFACTOR", ["F-001"], ["S-005"], ["E-040 OAuthConnection"],
         None, 1, 1, 4, 1, ["T-V3-AUTH-02"],
         ["backend/routers/auth.py", "backend/routers/oauth.py (delete)"],
         ac(functional=[
             "EVENT-DRIVEN: When the OAuth provider redirects to /api/auth/oauth/{provider}/callback with code, the system shall exchange the code for tokens, locate or create User by provider_user_id, return 200 with auth tokens like /login.",
             "UBIQUITOUS: The legacy /api/oauth/{provider}/callback shall return 308 → /api/auth/oauth/{provider}/callback for one Phase 1 cycle, then be deleted in Phase 2.",
             "UNWANTED: If the OAuth state nonce is missing or wrong, the system shall return 400 (csrf_check_failed)."
         ])),
    task("T-V3-AUTH-07", "FastAPI dependency require_auth / require_role 実装",
         "backend", "NEW", ["F-001", "F-021"], [], ["E-001 User"],
         None, 1, 1, 4, 1, ["T-V3-AUTH-01"],
         ["backend/dependencies/auth.py"],
         ac(functional=[
             "EVENT-DRIVEN: When require_auth is used as a FastAPI Depends, the system shall verify Authorization: Bearer <JWT> OR refresh_token cookie, decode it, and inject current_user.",
             "UNWANTED: If no token or token invalid, the system shall return 401.",
             "EVENT-DRIVEN: When require_role('account_owner') is used, the system shall additionally verify the current_user has the requested role on the path's account_id/workspace_id; otherwise return 403.",
             "UBIQUITOUS: The dependency shall set Postgres session-level GUC `app.current_user_id` for RLS context."
         ])),
    task("T-V3-AUTH-08", "S-001 /login page.tsx 実装",
         "frontend", "NEW", ["F-001"], ["S-001"], [],
         None, 1, 2, 4, 1, ["T-V3-AUTH-01", "T-V3-INFRA-03"],
         ["frontend/src/app/login/page.tsx", "frontend/src/components/auth/LoginForm.tsx"],
         ac(
             structural=[
                 "STATE-DRIVEN: While the page is rendered at /login, the system shall display an h1 element with exact text matching mock docs/mocks/2026-05-09_v1/auth/S-001-login.html h1.",
                 "STATE-DRIVEN: While the page is rendered, the form shall contain input[type=email][required], input[type=password][required], and a submit button.",
             ],
             functional=[
                 "EVENT-DRIVEN: When the form is submitted with valid values, the page shall POST to /api/auth/login and on 200 redirect to /.",
                 "EVENT-DRIVEN: When the response is 202 (MFA required), the page shall navigate to /mfa-challenge?id={challenge_id}.",
                 "UNWANTED: If the response is 401, the page shall display 'メールアドレスかパスワードが正しくありません' inline (no user enumeration)."
             ])),
    task("T-V3-AUTH-09", "S-002 /signup page.tsx 実装",
         "frontend", "NEW", ["F-001", "F-004"], ["S-002"], [],
         None, 1, 2, 4, 1, ["T-V3-AUTH-02", "T-V3-INFRA-03"],
         ["frontend/src/app/signup/page.tsx"],
         ac(
             structural=["STATE-DRIVEN: While rendered at /signup, the h1 shall match the mock h1 exactly."],
             functional=[
                 "EVENT-DRIVEN: When the form is submitted, POST /api/auth/signup, on 201 redirect to /.",
                 "UNWANTED: If 409 email_taken, show 'すでに登録されているメールアドレスです' inline.",
                 "UNWANTED: If 422 weak_password, show password requirement hints."
             ])),
    task("T-V3-AUTH-10", "S-003 /password-reset page.tsx 実装",
         "frontend", "NEW", ["F-001"], ["S-003"], [],
         None, 1, 2, 3, 1, ["T-V3-AUTH-03", "T-V3-INFRA-03"],
         ["frontend/src/app/password-reset/page.tsx"],
         ac(
             structural=["STATE-DRIVEN: h1 matches mock exactly."],
             functional=[
                 "EVENT-DRIVEN: When email is submitted, POST /api/auth/password-reset, then show 'メールを送信しました' regardless of result.",
                 "EVENT-DRIVEN: When the URL contains ?token=..., the page shall switch to new-password mode."
             ])),
    task("T-V3-AUTH-11", "S-004 /mfa-setup page.tsx 実装 (TOTP QR + recovery codes)",
         "frontend", "NEW", ["F-001"], ["S-004"], [],
         None, 1, 2, 4, 1, ["T-V3-AUTH-04", "T-V3-AUTH-05"],
         ["frontend/src/app/mfa-setup/page.tsx"],
         ac(
             structural=["STATE-DRIVEN: h1 matches mock; QR image + recovery codes block render."],
             functional=[
                 "EVENT-DRIVEN: When the page loads, POST /api/auth/mfa/enroll once and render the returned QR + recovery codes.",
                 "EVENT-DRIVEN: When a TOTP code is entered and submitted, POST /api/auth/mfa/verify.",
                 "UBIQUITOUS: The recovery codes shall be shown only on this page (refresh = lost)."
             ])),
    task("T-V3-AUTH-12", "S-005 /oauth/callback page.tsx 実装",
         "frontend", "NEW", ["F-001"], ["S-005"], [],
         None, 1, 2, 3, 1, ["T-V3-AUTH-06"],
         ["frontend/src/app/oauth/callback/page.tsx"],
         ac(
             structural=["STATE-DRIVEN: Spinner + 'ログイン中...' message; h1 matches mock."],
             functional=[
                 "EVENT-DRIVEN: When the page loads with ?code=...&state=..., it shall GET /api/auth/oauth/{provider}/callback and redirect to /.",
                 "UNWANTED: If state mismatch, redirect to /login?error=oauth_csrf."
             ])),
    task("T-V3-AUTH-13", "AUTH backend unit tests (8+ ケース × 6 endpoint)",
         "test", "NEW", ["F-001"], [], [],
         None, 1, 3, 8, 2, ["T-V3-AUTH-01", "T-V3-AUTH-02", "T-V3-AUTH-03", "T-V3-AUTH-04", "T-V3-AUTH-05", "T-V3-AUTH-06"],
         ["tests/test_T-V3-AUTH-01.py", "tests/test_T-V3-AUTH-02.py", "tests/test_T-V3-AUTH-03.py", "tests/test_T-V3-AUTH-04.py", "tests/test_T-V3-AUTH-05.py", "tests/test_T-V3-AUTH-06.py"],
         ac(functional=[
             "UBIQUITOUS: Each test file shall contain >= 8 test cases covering success / wrong_input / sql_injection / csrf / replay / rate_limit / mfa_branch / token_expiry."
         ])),
    task("T-V3-AUTH-14", "AUTH Playwright e2e (signup → login → MFA enroll → MFA verify → logout)",
         "test", "NEW", ["F-001"], ["S-001", "S-002", "S-003", "S-004", "S-005"], [],
         None, 1, 3, 6, 2, ["T-V3-AUTH-08", "T-V3-AUTH-09", "T-V3-AUTH-10", "T-V3-AUTH-11", "T-V3-AUTH-12"],
         ["frontend/e2e/auth.spec.ts"],
         ac(functional=[
             "EVENT-DRIVEN: The e2e shall walk signup → email-verify-skip → login → mfa-setup → mfa-verify → / dashboard render → logout, all asserting expected URLs and DOM elements."
         ])),
    task("T-V3-AUTH-15", "AUTH session table RLS policy",
         "db", "NEW", ["F-001"], [], ["E-038 AuthSession", "E-039 PasswordReset"],
         None, 1, 1, 4, 1, ["T-V3-AUTH-07"],
         ["supabase/migrations/20260515000001_auth_rls.sql"],
         ac(functional=[
             "UBIQUITOUS: RLS shall be ENABLED on auth_sessions, password_resets, user_2fa_secrets.",
             "UBIQUITOUS: Policies shall restrict SELECT/INSERT/UPDATE/DELETE to current_user_id only.",
             "UBIQUITOUS: scripts/verify-rls-coverage.py shall list these 3 tables as covered."
         ]),
         rls=["auth_sessions:owner_only", "password_resets:owner_only", "user_2fa_secrets:owner_only"]),
]


# ============================================================
# GROUP C — DB + RLS (28 件)
# ============================================================

GROUP_C = []

# C-1: 不在 entity の table 新設
_c1 = [
    ("T-V3-DB-01", "E-013 PhaseGate", "phase_gates", ["S-016"], ["E-013"]),
    ("T-V3-DB-02", "E-024 ScreenComponent (中間 table)", "screen_components", ["S-023", "S-024"], ["E-024"]),
    ("T-V3-DB-03", "E-021 ArtifactVersion", "artifact_versions", ["S-022", "S-023"], ["E-021"]),
    ("T-V3-DB-04", "E-010 UserKnowledgeNamespace", "user_knowledge_namespaces", ["S-036", "S-037"], ["E-010"]),
]
for tid, ent_label, table, screens, eids in _c1:
    GROUP_C.append(task(tid,
        f"{ent_label} table 新設 + RLS",
        "db", "NEW", ["F-001"], screens, eids,
        None, 1, 1, 4, 1, ["T-V3-INFRA-05"],
        [f"supabase/migrations/2026051500_{table}.sql", f"backend/models/{table}.py"],
        ac(functional=[
            f"UBIQUITOUS: The migration shall CREATE TABLE {table} with the columns declared in entities.json for this entity.",
            f"UBIQUITOUS: RLS shall be ENABLED on {table} with appropriate scope policy.",
            f"EVENT-DRIVEN: When verify-rls-coverage.py runs, {table} shall be listed as covered."
        ]),
        rls=[f"{table}:scope_owner"]))

# C-2: 既存 partial entity の整合化
_c2 = [
    ("T-V3-DB-05", "E-022 Screen consolidate (design_frames → screens)", "screens", ["S-023"], ["E-022"]),
    ("T-V3-DB-06", "E-023 Component consolidate (design_mocks → components)", "components", ["S-024"], ["E-023"]),
    ("T-V3-DB-07", "bf_acceptance_criteria → acceptance_criteria rename", "acceptance_criteria", ["S-021"], ["E-016"]),
    ("T-V3-DB-08", "bf_constitutions → constitutions rename", "constitutions", ["S-018"], ["E-017"]),
    ("T-V3-DB-09", "bf_tasks → tasks rename", "tasks", ["S-027", "S-030"], ["E-018"]),
    ("T-V3-DB-10", "bf_features / bf_mocks dead table 削除", "(dropped)", [], []),
]
for tid, title, table, screens, eids in _c2:
    GROUP_C.append(task(tid, title,
        "db", "REFACTOR", ["F-001"], screens, eids,
        None, 1, 2, 4, 1, ["T-V3-INFRA-02"],
        [f"supabase/migrations/2026051500_{table}_rename.sql"],
        ac(functional=[
            f"UBIQUITOUS: The migration shall ALTER TABLE bf_{table} RENAME TO {table} (or CREATE + INSERT + DROP if columns also change).",
            "UBIQUITOUS: All backend SQLAlchemy models / queries shall be updated atomically.",
            "EVENT-DRIVEN: When lint #19 runs, no bf_ prefix shall remain."
        ])))

# C-3: 既存 entity の RLS (1 task = 1 entity group)
_rls_groups = [
    ("T-V3-RLS-01", "E-001/E-002/E-003 (User / AccountMember / WorkspaceMember)",
     ["E-001", "E-002", "E-003"], ["users:select_member", "account_members:rls", "workspace_members:rls"]),
    ("T-V3-RLS-02", "E-008/E-009 (Account / Workspace)",
     ["E-008", "E-009"], ["accounts:scope_member", "workspaces:scope_member"]),
    ("T-V3-RLS-03", "E-018/E-019 (Task / TaskDependency)",
     ["E-018", "E-019"], ["tasks:workspace_member", "task_dependencies:workspace_member"]),
    ("T-V3-RLS-04", "E-025/E-026 (Session / SessionLog)",
     ["E-025", "E-026"], ["sessions:workspace_member", "session_logs:workspace_member"]),
    ("T-V3-RLS-05", "E-027/E-028 (CostLog / TokenUsage)",
     ["E-027", "E-028"], ["cost_logs:account_owner", "token_usage:account_owner"]),
    ("T-V3-RLS-06", "E-029 (AuditLog) read-only",
     ["E-029"], ["audit_logs:read_only_owner_monitor"]),
    ("T-V3-RLS-07", "E-030/E-031 (RedLine / RedLineViolation)",
     ["E-030", "E-031"], ["red_lines:workspace", "red_line_violations:workspace"]),
    ("T-V3-RLS-08", "E-013/E-014 (PhaseGate / PhaseGateDecision)",
     ["E-013", "E-014"], ["phase_gates:workspace", "phase_gate_decisions:workspace"]),
    ("T-V3-RLS-09", "E-016 (AcceptanceCriterion)",
     ["E-016"], ["acceptance_criteria:workspace"]),
    ("T-V3-RLS-10", "E-017 (Constitution)",
     ["E-017"], ["constitutions:workspace"]),
    ("T-V3-RLS-11", "E-021 (ArtifactVersion)",
     ["E-021"], ["artifact_versions:workspace"]),
    ("T-V3-RLS-12", "E-022/E-023/E-024 (Screen / Component / ScreenComponent)",
     ["E-022", "E-023", "E-024"], ["screens:workspace", "components:workspace", "screen_components:workspace"]),
    ("T-V3-RLS-13", "E-032/E-033 (ChatThread / ChatMessage)",
     ["E-032", "E-033"], ["chat_threads:workspace_member", "chat_messages:workspace_member"]),
    ("T-V3-RLS-14", "E-034/E-035/E-036 (AIEmployee / EmployeeSkill / SkillRun)",
     ["E-034", "E-035", "E-036"], ["ai_employees:workspace", "employee_skills:workspace", "skill_runs:workspace"]),
    ("T-V3-RLS-15", "E-040/E-041 (ChatThread legacy / KnowledgeNamespace)",
     ["E-040", "E-041"], ["chat_threads:legacy", "knowledge_namespaces:workspace_member"]),
    ("T-V3-RLS-16", "E-042/E-043 (Notification / Invitation)",
     ["E-042", "E-043"], ["notifications:owner_only", "invitations:account_owner_or_invitee"]),
    ("T-V3-RLS-17", "E-038/E-039 (AuthSession / PasswordReset) — T-V3-AUTH-15 と統合 / 確認 task",
     ["E-038", "E-039"], ["auth_sessions:owner_only", "password_resets:owner_only"]),
    ("T-V3-RLS-18", "verify-rls-coverage 拡張 (全 43 entity に CREATE POLICY 必須化)",
     [], []),
]
for tid, title, eids, rls in _rls_groups:
    GROUP_C.append(task(tid, f"RLS policy 追加: {title}",
        "db", "NEW", ["F-001"], [], eids,
        None, 1, 2, 4, 1, ["T-V3-INFRA-05"],
        [f"supabase/migrations/2026051500_rls_{tid.lower()}.sql"],
        ac(functional=[
            "UBIQUITOUS: For each listed table, RLS shall be ENABLED.",
            "UBIQUITOUS: Each table shall have at least one CREATE POLICY for SELECT enforcing the scope listed in entities.json.",
            "EVENT-DRIVEN: When verify-rls-coverage.py runs, all listed tables shall be reported as covered."
        ]),
        rls=rls))


# ============================================================
# GROUP D — 重大 drift 修正 (5 件)
# ============================================================

GROUP_D = [
    task("T-V3-DRIFT-01", "GET /api/accounts/{id}/dashboard backend 実装 (S-006 API)",
         "backend", "NEW", ["F-024", "F-018", "F-008", "F-007", "F-017"], ["S-006"],
         ["E-008", "E-009", "E-018", "E-025", "E-027", "E-029"],
         None, 1, 2, 8, 2, ["T-V3-RLS-02"],
         ["backend/routers/accounts.py"],
         ac(functional=[
             "EVENT-DRIVEN: When an authenticated account_owner GETs /api/accounts/{id}/dashboard, the system shall return 200 with { active_projects: int, running_sessions: { current: int, max: int }, monthly_cost: { current: number, budget: number }, anomalies_24h: int, workspaces: Workspace[], ai_employee_usage: AIEmployeeUsage[], recent_activity: ActivityLog[], phase_progress: PhaseProgress[], pending_reviews: PendingReview[] }.",
             "UNWANTED: If caller is not a member of the account, the system shall return 403.",
             "UBIQUITOUS: The endpoint shall accept an optional ?period=24h|7d|30d query parameter that filters anomalies_24h and recent_activity windows."
         ])),
    task("T-V3-DRIFT-02", "S-006 root `/` 完全 rewrite (10 案件俯瞰)",
         "frontend", "REFACTOR", ["F-024", "F-008"], ["S-006"], [],
         "company-dashboard-bleed", 1, 2, 12, 3, ["T-V3-DRIFT-01", "T-V3-INFRA-03"],
         ["frontend/src/app/page.tsx", "frontend/src/components/dashboard/AccountDashboard.tsx"],
         ac(
             structural=[
                 "STATE-DRIVEN: While rendered at /, the page h1 shall be '10 案件 俯瞰' (exact match with mock docs/mocks/2026-05-09_v1/account/S-006-account-dashboard.html).",
                 "STATE-DRIVEN: The 4 Hero KPI cards shall have labels 'Active Projects', 'Running Sessions', 'Monthly Cost', 'Anomalies (24h)' in this order (mock-impl lint #17 PASS).",
                 "STATE-DRIVEN: The page shall contain sections 'Pending Reviews', 'Phase 進捗', '完了タスク (7d)', '全 Workspaces', 'AI 社員 使用率', '直近の Activity' (h2 elements).",
             ],
             functional=[
                 "EVENT-DRIVEN: When the page mounts, it shall call GET /api/accounts/{current_account_id}/dashboard and render the returned data into the 4 Hero KPI cards + 6 sections."
             ])),
    task("T-V3-DRIFT-03", "既存 AI 社員 KPI を /ai-employees-legacy に退避 or 完全削除 + ADR-015",
         "frontend", "ARCHIVE", ["F-022"], [], [],
         None, 1, 2, 4, 1, ["T-V3-DRIFT-02"],
         ["frontend/src/app/ai-employees-legacy/page.tsx (move) or DELETE", "docs/decisions/ADR-015-company-dashboard-bleed-removal.md"],
         ac(functional=[
             "UBIQUITOUS: The legacy KPI (今月売上 / パイプライン / 今月受注 / タスク・コンタクト) shall NOT exist at /.",
             "UBIQUITOUS: ADR-015 shall document why this content was at /, the bleed source, and the resolution (move-or-delete decision)."
         ])),
    task("T-V3-DRIFT-04", "S-036 h1 統一 (実装 'AI社員（組織図）' → mock 'AI 社員 組織図')",
         "frontend", "REFACTOR", ["F-003"], ["S-036"], [],
         None, 1, 2, 0.5, 1, ["T-V3-INFRA-03"],
         ["frontend/src/app/ai-employees/page.tsx"],
         ac(
             structural=["STATE-DRIVEN: The page h1 shall be 'AI 社員 組織図' (exact match, half-width spaces, no full-width parens)."],
             functional=[])),
    task("T-V3-DRIFT-05", "S-040 h1 日本語化 (実装 'Cost Dashboard' → mock 'コスト ダッシュボード')",
         "frontend", "REFACTOR", ["F-017"], ["S-040"], [],
         None, 1, 2, 0.5, 1, ["T-V3-INFRA-03"],
         ["frontend/src/app/dashboard/costs/page.tsx"],
         ac(
             structural=["STATE-DRIVEN: The page h1 shall be 'コスト ダッシュボード' (exact match with mock)."],
             functional=[])),
]


# ============================================================
# GROUP E — 未実装 15 画面 (S-001..S-005 を除く / Group B でカバー済)
# ============================================================

_e_screens = [
    ("T-V3-SCR-01", "S-008 /account/members", "/account/members", "F-004", 8, ["E-001", "E-002"], ["T-V3-RLS-01", "T-V3-AUTH-07"]),
    ("T-V3-SCR-02", "S-010 /notifications", "/notifications", "F-018", 8, ["E-042"], ["T-V3-RLS-16"]),
    ("T-V3-SCR-03", "S-011 /search + Cmd+K", "/search", "F-024", 12, ["E-001", "E-018", "E-009"], ["T-V3-AUTH-07"]),
    ("T-V3-SCR-04", "S-015 /workspaces/[id]/invite", "/workspaces/[id]/invite", "F-004", 4, ["E-043"], ["T-V3-RLS-16"]),
    ("T-V3-SCR-05", "S-020 /workspaces/[id]/hearing", "/workspaces/[id]/hearing", "F-005", 16, ["E-016"], ["T-V3-RLS-02"]),
    ("T-V3-SCR-06", "S-021 /workspaces/[id]/requirements (EARS editor)", "/workspaces/[id]/requirements", "F-006", 16, ["E-016"], ["T-V3-DB-07"]),
    ("T-V3-SCR-07", "S-022 /workspaces/[id]/specs (7 種 HTML report viewer)", "/workspaces/[id]/specs", "F-005", 12, ["E-021"], ["T-V3-DB-03"]),
    ("T-V3-SCR-08", "S-023 /workspaces/[id]/mocks (GUI/AI/HTML edit)", "/workspaces/[id]/mocks", "F-005b", 16, ["E-022"], ["T-V3-DB-05", "T-V3-RLS-12"]),
    ("T-V3-SCR-09", "S-024 /workspaces/[id]/components catalog", "/workspaces/[id]/components", "F-005b", 8, ["E-023"], ["T-V3-DB-06"]),
    ("T-V3-SCR-10", "S-025 /workspaces/[id]/flow (screen flow map)", "/workspaces/[id]/flow", "F-005b", 8, ["E-024"], ["T-V3-DB-02"]),
    ("T-V3-SCR-11", "S-030 /tasks/[id] task detail page", "/tasks/[id]", "F-007", 4, ["E-018"], ["T-V3-RLS-03"]),
    ("T-V3-SCR-12", "S-033 /approval/pr PR review", "/approval/pr", "F-013", 12, ["E-018"], ["T-V3-RLS-02"]),
    ("T-V3-SCR-13", "S-037 /ai-employees/[id] detail", "/ai-employees/[id]", "F-003", 8, ["E-034"], ["T-V3-RLS-14"]),
    ("T-V3-SCR-14", "S-042 /client/workspaces/[id] (client portal)", "/client/workspaces/[id]", "F-013", 12, ["E-009"], ["T-V3-RLS-02"]),
    ("T-V3-SCR-15", "S-043 client_comment (embedded in S-042)", "/client/workspaces/[id]#comments", "F-013", 4, ["E-033"], ["T-V3-SCR-14"]),
]

GROUP_E = []
for tid, title, route, feat, hours, eids, deps in _e_screens:
    screen_id = title.split()[0]  # S-XXX
    GROUP_E.append(task(tid, title,
        "full-stack", "NEW", [feat], [screen_id], eids,
        None, 1, 3, hours, max(1, hours // 4), deps,
        [f"frontend/src/app{route}/page.tsx", "backend/routers/* (new endpoints as needed)"],
        ac(
            structural=[f"STATE-DRIVEN: While rendered at {route}, the page h1, KPI labels, and section h2s shall match the mock for {screen_id} (lint #17 PASS)."],
            functional=[f"EVENT-DRIVEN: When the page mounts, it shall call the related_apis declared for {screen_id} in screens.json and render their responses."]
        )))


# ============================================================
# GROUP F — 既存 22 画面 REFACTOR (R-1..R-4 一括適用)
# ============================================================

_f_screens = [
    ("T-V3-RF-01", "S-007", "account_settings", "/account/settings", 4),
    ("T-V3-RF-02", "S-009", "profile_settings", "/account/profile", 4),
    ("T-V3-RF-03", "S-012", "workspace_dashboard", "/workspaces/[id]", 8),
    ("T-V3-RF-04", "S-013", "workspace_settings", "/workspaces/[id]/settings", 4),
    ("T-V3-RF-05", "S-014", "workspace_members", "/workspaces/[id]/members", 4),
    ("T-V3-RF-06", "S-016", "phase_management", "/workspaces/[id]/phases", 8),
    ("T-V3-RF-07", "S-017", "dependency_graph", "/workspaces/[id]/dependencies", 4),
    ("T-V3-RF-08", "S-018", "constitution_editor", "/workspaces/[id]/constitution", 4),
    ("T-V3-RF-09", "S-019", "red_line_settings", "/workspaces/[id]/red-lines", 4),
    ("T-V3-RF-10", "S-026", "design_html_editor", "/workspaces/[id]/design-html", 8),
    ("T-V3-RF-11", "S-027", "task_kanban", "/workspaces/[id]/tasks", 8),
    ("T-V3-RF-12", "S-028", "task_list", "/tasks", 4),
    ("T-V3-RF-13", "S-029", "task_dag_view", "/workspaces/[id]/tasks/dag", 4),
    ("T-V3-RF-14", "S-031", "swarm_grid", "/sessions", 8),
    ("T-V3-RF-15", "S-032", "swarm_session_detail", "/sessions/[id]", 8),
    ("T-V3-RF-16", "S-034", "red_line_approval", "/approval/red-line", 4),
    ("T-V3-RF-17", "S-035", "delivery_approval", "/approval/delivery", 4),
    ("T-V3-RF-18", "S-036", "ai_employees_org_chart", "/ai-employees", 4),
    ("T-V3-RF-19", "S-038", "skill_manager", "/skills", 4),
    ("T-V3-RF-20", "S-039", "knowledge_base", "/knowledge", 4),
    ("T-V3-RF-21", "S-040", "cost_dashboard", "/dashboard/costs", 4),
    ("T-V3-RF-22", "S-041", "audit_log_viewer", "/audit-logs", 4),
]
GROUP_F = []
for tid, sid, name, route, hours in _f_screens:
    GROUP_F.append(task(tid, f"{sid} {name} REFACTOR (R-1〜R-4 適用)",
        "frontend", "REFACTOR", [], [sid], [],
        f"v1-impl-of-{sid}", 1, 3, hours, max(1, hours // 4),
        ["T-V3-INFRA-03", "T-V3-INFRA-06"],
        [f"frontend/src/app{route}/page.tsx"],
        ac(
            structural=[f"STATE-DRIVEN: The page at {route} shall match the mock for {sid} h1/KPI/h2 (lint #17 PASS).",
                        "STATE-DRIVEN: 3-tier acceptance_criteria shall be added to docs/audit/2026-05-15_v3/<TASK_ID>.md."],
            functional=[f"UBIQUITOUS: The page shall call only the related_apis declared in screens.json for {sid} (lint #18 PASS).",
                        f"UBIQUITOUS: All entity references shall use the new naming (no bf_ prefix, lint #19 PASS)."])))


# ============================================================
# GROUP G — 確定 gap 4 件
# ============================================================

GROUP_G = [
    task("T-V3-FIX-01", "T-008-04 フェーズ削除 UI 完全実装",
         "frontend", "FIX", ["F-008"], ["S-016"], ["E-013"],
         "T-008-04", 1, 3, 4, 1, ["T-V3-DB-01"],
         ["frontend/src/app/workspaces/[id]/phases/_components/PhaseDeleteDialog.tsx"],
         ac(functional=[
             "EVENT-DRIVEN: When the user clicks 'delete' on a phase, a confirmation dialog shall appear with the phase name and dependent task count.",
             "EVENT-DRIVEN: When confirmed, DELETE /api/workspaces/{id}/phases/{phase_id} shall be called.",
             "UNWANTED: If the phase has dependent active tasks, the dialog shall block deletion and show the count."
         ])),
    task("T-V3-FIX-02", "T-013-04b merge conflict AI 完全実装",
         "backend", "FIX", ["F-013"], ["S-033"], [],
         "T-013-04b", 1, 4, 8, 2, [],
         ["backend/services/merge_conflict_resolver.py", "tests/test_T-V3-FIX-02.py"],
         ac(functional=[
             "EVENT-DRIVEN: When given two file blobs with conflict markers, the service shall return a proposed resolution string + confidence score.",
             "UBIQUITOUS: The service shall log all resolutions to audit_logs with input hash + output."
         ])),
    task("T-V3-FIX-03", "T-007-03b DAG semantic fix 完全実装 + audit MD",
         "full-stack", "FIX", ["F-009"], ["S-017", "S-029"], ["E-019"],
         "T-007-03b", 1, 3, 4, 1, [],
         ["frontend/src/components/dag/SemanticEdge.tsx", "docs/audit/2026-05-15_v3/T-V3-FIX-03.md"],
         ac(functional=[
             "EVENT-DRIVEN: When the DAG renders task dependencies, semantic edges (data-flow / blocks / refs) shall be styled distinctly.",
             "UBIQUITOUS: An audit MD shall document the semantic taxonomy."
         ])),
    task("T-V3-FIX-04", "T-BTSTRAP-04 build-factory project migrate 実装",
         "backend", "FIX", ["F-019"], [], [],
         "T-BTSTRAP-04", 1, 4, 6, 2, [],
         ["backend/services/build_factory_migrate.py", "tests/test_T-V3-FIX-04.py"],
         ac(functional=[
             "EVENT-DRIVEN: When templates/CHANGELOG.md is updated, the migrate service shall apply diffs to all existing workspaces under management.",
             "UBIQUITOUS: The service shall be idempotent — re-running with the same CHANGELOG shall be a no-op."
         ])),
]


# ============================================================
# GROUP H — 99 件 1:1 展開
# Subgroup H-1: 怪しい 63 件再検証 (1 task = 1 v1 task)
# Subgroup H-2: audit MD 不在 36 件 retrofit (1 task = 1 v1 task)
# ============================================================

# 怪しい 63 件 (Agent B report より)
SUSPICIOUS_V1 = """T-001-11 T-003-03 T-003-04 T-004-02 T-004-03 T-004-04 T-004-06 T-005-04
T-005b-04 T-006-01 T-006-03 T-007-02 T-008-02 T-008-03 T-009-01 T-009-03
T-010a-02 T-010a-03 T-010a-04 T-010b-02 T-010b-03 T-010b-04 T-010b-05
T-010c-02 T-010c-03 T-010c-04 T-010c-05 T-010d-01 T-011-03 T-012-01
T-013-01 T-013-02 T-013-03 T-013-04 T-014-02 T-015-03 T-016-02 T-016-03
T-018-01 T-018-02 T-020-03 T-020-04 T-022-02 T-024-03 T-024-04
T-026-01 T-026-02 T-026-03 T-AI-04 T-AI-08 T-AI-MEM-04
T-BTSTRAP-03 T-IT-S0 T-IT-S1 T-IT-S2 T-IT-S3 T-IT-S4 T-IT-S5 T-IT-S6 T-IT-S7
T-M12-01 T-M27-01 T-M27-01b T-M28-01 T-M28-02 T-M28-03""".split()
# Dedupe + slice to 63
SUSPICIOUS_V1 = sorted(set(SUSPICIOUS_V1))[:63]

# audit MD 不在 36 件
MISSING_AUDIT_V1 = """T-001-09 T-002-01 T-004-01 T-005-01 T-006-01 T-007-03b T-008-04
T-013-04b T-015-03 T-024-02b T-024-04 T-025-01 T-025-02
T-M12-01 T-M27-01 T-M27-01b T-M27-02 T-M27-03
T-M28-02 T-M28-04 T-M29-03
T-S0-01 T-S0-05 T-S0-09b T-S0-10
T-AI-03 T-AI-04 T-AI-05 T-AI-07
T-BTSTRAP-01 T-BTSTRAP-02 T-BTSTRAP-03 T-AI-MEM-04
T-001-09b T-002-02 T-005b-04""".split()
MISSING_AUDIT_V1 = sorted(set(MISSING_AUDIT_V1))[:36]

# Group H 削減 (2026-05-15 PM 判断):
# v3 が新 source of truth なので v1 legacy audit を 1:1 retrofit する必要無し。
# 99 task を 1 task に集約し、v1 freeze 宣言を REVIEW_REPORT で明記する形にする。
# 過剰な「audit on audit」の地獄パターンを構造的に回避。
GROUP_H = [
    task("T-V3-AUDIT-SUMMARY",
         "v1 legacy freeze 宣言 + v3 移行レポート起票",
         "doc", "ARCHIVE",
         [], [], [],
         None, 2, 5, 4, 1,
         ["T-V3-INFRA-06"],
         ["docs/REVIEW_REPORT_2026-05-16_v3_migration.md"],
         ac(functional=[
             "UBIQUITOUS: The report shall declare v1 (docs/task-decomposition/2026-05-09_v1/) as FROZEN; no further updates allowed.",
             "UBIQUITOUS: The report shall confirm that v3 is the new single source of truth, with all v1 spec gaps (21 drift/未実装画面 + 8 API gap + 28 RLS不足 + 4 確定gap + 5 surplus + 10 命名drift) covered by v3 tasks T-V3-INFRA-* / T-V3-AUTH-* / T-V3-DB-* / T-V3-RLS-* / T-V3-DRIFT-* / T-V3-SCR-* / T-V3-RF-* / T-V3-FIX-* / T-V3-CLEANUP-* / T-V3-RENAME-*.",
             "UBIQUITOUS: The report shall explicitly drop the 99-task 1:1 audit retrofit (v1 怪しい 63件 + v1 audit 不在 36件) with rationale: v3 CI gates (lint #17-19 + 3-tier AC validator + verify-rls-coverage + validate-audit-md) provide structural leakage prevention without recursive auditing.",
             "UBIQUITOUS: The report shall list the 4 v1 confirmed gaps (T-008-04 / T-013-04b / T-007-03b / T-BTSTRAP-04) and their v3 mapping (T-V3-FIX-01..04)."
         ]),
         notes="v1 legacy の audit 履歴は freeze。v3 が新規 task で全 gap を直接潰すため、過去 audit の再構築は不要。")
]


# ============================================================
# GROUP I — 余剰整理 (5 件)
# ============================================================

GROUP_I = [
    task("T-V3-CLEANUP-01", "ai_employee_config (legacy) 削除 + migration",
         "db", "ARCHIVE", ["F-003"], [], [],
         None, 2, 6, 4, 1, ["T-V3-RLS-14"],
         ["supabase/migrations/2026051500_drop_ai_employee_config.sql"],
         ac(functional=[
             "UBIQUITOUS: The table ai_employee_config shall be DROPped.",
             "UBIQUITOUS: All references in backend code shall be removed."
         ])),
    task("T-V3-CLEANUP-02", "projects (legacy) → phases 移行 + DROP",
         "db", "ARCHIVE", ["F-008"], [], ["E-013"],
         None, 2, 6, 4, 1, ["T-V3-DB-01"],
         ["supabase/migrations/2026051500_drop_projects_legacy.sql"],
         ac(functional=[
             "UBIQUITOUS: All projects data shall be migrated into phase_gates / phases.",
             "UBIQUITOUS: The projects table shall be DROPped."
         ])),
    task("T-V3-CLEANUP-03", "threads (legacy conversation) 削除",
         "db", "ARCHIVE", ["F-022"], [], ["E-041"],
         None, 2, 6, 4, 1, ["T-V3-RLS-15"],
         ["supabase/migrations/2026051500_drop_threads_legacy.sql"],
         ac(functional=[
             "UBIQUITOUS: Data in threads (legacy) shall be migrated into chat_threads (E-041).",
             "UBIQUITOUS: The threads (legacy) table shall be DROPped."
         ])),
    task("T-V3-CLEANUP-04", "dead router 探索 + 削除 (screens.json 参照なし)",
         "backend", "ARCHIVE", [], [], [],
         None, 2, 6, 4, 1, ["T-V3-INFRA-04"],
         ["backend/routers/* (dead routers removed)"],
         ac(functional=[
             "EVENT-DRIVEN: When lint #18 (screens-API) runs, all backend routers shall be referenced by at least one screen OR documented as infrastructure (in router_index.md).",
             "UBIQUITOUS: Routers without spec reference and not in the infrastructure list shall be DELETEd."
         ])),
    task("T-V3-CLEANUP-05", "onlook/penpot 完全削除 確認",
         "infra", "ARCHIVE", [], [], [],
         None, 2, 6, 1, 1, [],
         [],
         ac(functional=[
             "UBIQUITOUS: The repo root shall not contain onlook/ or penpot/ folders.",
             "UBIQUITOUS: lint-mock.sh check #3 shall PASS."
         ])),
]


# ============================================================
# GROUP J — 命名 migration (10 件)
# ============================================================

GROUP_J = [
    task("T-V3-RENAME-01", "bf_tasks → tasks rename + ORM",
         "db", "REFACTOR", [], [], ["E-018"],
         None, 2, 6, 4, 1, ["T-V3-DB-09"],
         ["supabase/migrations/2026051500_rename_bf_tasks.sql", "backend/models/task.py"],
         ac(functional=["UBIQUITOUS: bf_tasks shall be renamed to tasks. All references updated."])),
    task("T-V3-RENAME-02", "bf_constitutions → constitutions rename",
         "db", "REFACTOR", [], [], ["E-017"],
         None, 2, 6, 4, 1, ["T-V3-DB-08"],
         [],
         ac(functional=["UBIQUITOUS: bf_constitutions shall be renamed to constitutions."])),
    task("T-V3-RENAME-03", "bf_acceptance_criteria → acceptance_criteria",
         "db", "REFACTOR", [], [], ["E-016"],
         None, 2, 6, 4, 1, ["T-V3-DB-07"],
         [],
         ac(functional=["UBIQUITOUS: bf_acceptance_criteria shall be renamed."])),
    task("T-V3-RENAME-04", "bf_features → features rename",
         "db", "REFACTOR", [], [], [],
         None, 2, 6, 4, 1, ["T-V3-DB-10"],
         [],
         ac(functional=["UBIQUITOUS: bf_features shall be renamed or dropped per dead-code review."])),
    task("T-V3-RENAME-05", "bf_mocks → mocks (or split into screens / components)",
         "db", "REFACTOR", [], [], ["E-022", "E-023"],
         None, 2, 6, 4, 1, ["T-V3-DB-05", "T-V3-DB-06"],
         [],
         ac(functional=["UBIQUITOUS: bf_mocks shall be split into screens + components per ADR-014."])),
    task("T-V3-RENAME-06", "bf_project_tables migration を ADR-014 準拠に書き換え",
         "db", "REFACTOR", [], [], [],
         None, 2, 6, 4, 1, ["T-V3-INFRA-02"],
         ["supabase/migrations/20260510000001_bf_project_tables.sql (refactor)"],
         ac(functional=["UBIQUITOUS: The migration file shall be updated to use spec naming."])),
    task("T-V3-RENAME-07", "SQLAlchemy model class 名整合 (PascalCase 強制)",
         "backend", "REFACTOR", [], [], [],
         None, 2, 6, 4, 1, ["T-V3-INFRA-05"],
         ["backend/models/*.py"],
         ac(functional=["UBIQUITOUS: All model classes shall use PascalCase matching entities.json."])),
    task("T-V3-RENAME-08", "API response schema 整合 (snake_case JSON, PascalCase TS type)",
         "full-stack", "REFACTOR", [], [], [],
         None, 2, 6, 4, 1, ["T-V3-RENAME-07"],
         ["backend/schemas/*.py", "frontend/src/lib/types/*.ts"],
         ac(functional=["UBIQUITOUS: API JSON shall use snake_case; frontend TS types shall use PascalCase generated from entities.json."])),
    task("T-V3-RENAME-09", "TypeScript types 自動生成 (pnpm codegen from entities.json)",
         "infra", "NEW", [], [], [],
         None, 2, 6, 8, 2, [],
         ["frontend/scripts/codegen.ts", "frontend/src/lib/types/generated.ts"],
         ac(functional=[
             "EVENT-DRIVEN: When `pnpm run codegen` is invoked, the script shall regenerate frontend/src/lib/types/generated.ts from entities.json.",
             "UBIQUITOUS: The CI shall fail if generated.ts is out of sync with entities.json."
         ])),
    task("T-V3-RENAME-10", "lint #19 baseline 化 + CI gate",
         "infra", "REFACTOR", [], [], [],
         None, 2, 6, 2, 1, ["T-V3-INFRA-05", "T-V3-RENAME-01", "T-V3-RENAME-02", "T-V3-RENAME-03", "T-V3-RENAME-04", "T-V3-RENAME-05"],
         [".github/workflows/ci.yml"],
         ac(functional=[
             "EVENT-DRIVEN: When CI runs, lint #19 shall be invoked.",
             "UNWANTED: If any bf_ prefix returns, the CI shall fail."
         ])),
]


# ============================================================
# ASSEMBLE FINAL JSON
# ============================================================

ALL_TASKS = (GROUP_A + GROUP_B + GROUP_C + GROUP_D + GROUP_E + GROUP_F +
             GROUP_G + GROUP_H + GROUP_I + GROUP_J)

# Add structural integrity counters by category
cat_counts = {}
for t in ALL_TASKS:
    c = t["category"]
    cat_counts[c] = cat_counts.get(c, 0) + 1

label_counts = {}
for t in ALL_TASKS:
    l = t["label"]
    label_counts[l] = label_counts.get(l, 0) + 1

phase_counts = {}
for t in ALL_TASKS:
    p = t["phase"]
    phase_counts[p] = phase_counts.get(p, 0) + 1

total_hours = sum(t["estimate_hours"] for t in ALL_TASKS)
total_sessions = sum(t["estimate_sessions"] for t in ALL_TASKS)

OUT = {
    "meta": {
        "version": "v3",
        "created_at": "2026-05-15",
        "project": "Build-Factory",
        "supersedes": [
            "docs/task-decomposition/2026-05-09_v1/ (187 task, formally done but spec-drifted)",
            "docs/task-decomposition/2026-05-14_v2/ (vertical slice attempt)"
        ],
        "total_tasks": len(ALL_TASKS),
        "estimate_total_hours": total_hours,
        "estimate_total_sessions": total_sessions,
        "estimate_total_person_days_8h": round(total_hours / 8, 1),
        "by_category": cat_counts,
        "by_label": label_counts,
        "by_phase": phase_counts,
        "ac_schema": "3-tier (structural + functional + regression)",
        "must_pass_to_done": "all 3 tiers + lint 1-19 + 3-tier AC validator",
        "new_lints": ["#17 mock-impl-diff", "#18 screens-API", "#19 entity-table naming"],
        "new_adrs": ["ADR-013 auth strategy", "ADR-014 naming standard", "ADR-015 company-dashboard bleed removal"]
    },
    "tickets": ALL_TASKS
}

OUT_TICKETS.write_text(json.dumps(OUT, ensure_ascii=False, indent=2))
print(f"wrote {OUT_TICKETS} ({len(ALL_TASKS)} tasks, {total_hours} hours, {total_sessions} sessions)")
print(f"by_category: {cat_counts}")
print(f"by_label: {label_counts}")
print(f"by_phase: {phase_counts}")
