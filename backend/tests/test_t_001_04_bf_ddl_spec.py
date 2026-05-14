"""T-001-04 (NEW audit / Wave 5) — BF DDL + RLS per-table spec.

Pre-flight audit on:
    supabase/migrations/20260510000001_bf_project_tables.sql

Audit policy (anti-drift CRITICAL):
    - 11 tables individually verified (no collapsed parametrize regex).
    - RLS policy NAMES enumerated in audit doc are 1:1 verified against
      the SQL literal policy names (so renames / drops surface immediately).
    - Each FK / CHECK / enum constraint asserted on the *named* column
      inside the *named* table body, never with a global file-scan regex
      (which would mask cross-table drift).
    - 4 EARS AC each get their own dedicated section (UBIQUITOUS /
      EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED — ticket carries
      5 ACs; audit folds OPTIONAL+UNWANTED extras into AC-4/AC-5 below).

Companion audit doc:
    docs/audit/2026-05-13_v2/T-001-04.md

This audit ADDS coverage on top of the existing
test_t_001_04_bf_tables_invariants.py (32 tests, mostly collapsed
regex). This file holds per-table specificity that the older tests
intentionally skipped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260510000001_bf_project_tables.sql"

# ---------------------------------------------------------------------------
# 11 tables declared in the migration (literal order from the SQL header)
# ---------------------------------------------------------------------------
BF_TABLES = (
    "bf_projects",
    "bf_phases",
    "bf_features",
    "bf_tasks",
    "bf_task_dependencies",
    "bf_acceptance_criteria",
    "bf_constitutions",
    "bf_constitution_revisions",
    "bf_mocks",
    "bf_deliveries",
    "audit_logs",
)

# Workspace-scoped tables (RLS member-policy applies).
# bf_constitution_revisions has SELECT-only member-policy; all others FOR ALL.
WORKSPACE_SCOPED_TABLES = (
    "bf_projects",
    "bf_phases",
    "bf_features",
    "bf_tasks",
    "bf_task_dependencies",
    "bf_acceptance_criteria",
    "bf_constitutions",
    "bf_constitution_revisions",
    "bf_mocks",
    "bf_deliveries",
)

# Exact RLS policy names declared in the migration (1:1 list).
# Drift guard: if any name here disappears or a new one appears, the audit
# doc MUST be updated in lockstep — that is the whole point of pinning these.
RLS_POLICY_NAMES = (
    # bf_projects
    "bf_projects_service_role",
    "bf_projects_member",
    # bf_phases
    "bf_phases_service_role",
    "bf_phases_member",
    # bf_features
    "bf_features_service_role",
    "bf_features_member",
    # bf_tasks
    "bf_tasks_service_role",
    "bf_tasks_member",
    # bf_task_dependencies
    "bf_deps_service_role",
    "bf_deps_member",
    # bf_acceptance_criteria
    "bf_ac_service_role",
    "bf_ac_member",
    # bf_constitutions
    "bf_const_service_role",
    "bf_const_member",
    # bf_constitution_revisions (SELECT-only member)
    "bf_const_rev_service_role",
    "bf_const_rev_member",
    # bf_mocks
    "bf_mocks_service_role",
    "bf_mocks_member",
    # bf_deliveries
    "bf_deliveries_service_role",
    "bf_deliveries_member",
    # audit_logs (SELECT-only member)
    "audit_service_role",
    "audit_member_read",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _table_body(sql_text: str, table: str) -> str:
    """Return the CREATE TABLE body (inside parens) for `table` or fail."""
    m = re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{re.escape(table)}\s*\(([\s\S]+?)\);",
        sql_text,
    )
    assert m, f"CREATE TABLE for {table} not found"
    return m.group(1)


# ===========================================================================
# AC-1 UBIQUITOUS — exactly 11 tables, idempotent CREATE TABLE
# ===========================================================================


def test_ac1_migration_file_exists():
    assert MIGRATION.exists(), f"migration file missing: {MIGRATION}"


def test_ac1_exactly_eleven_create_table_statements(sql):
    """Migration shall declare exactly 11 CREATE TABLE statements."""
    matches = re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql)
    assert len(matches) == 11, (
        f"expected exactly 11 CREATE TABLE, got {len(matches)}: {matches}"
    )
    assert set(matches) == set(BF_TABLES), (
        f"table set mismatch: missing={set(BF_TABLES) - set(matches)}, "
        f"extra={set(matches) - set(BF_TABLES)}"
    )


# --- per-table presence (11 individual tests, NOT a parametrize collapse) ---


def test_table_bf_projects_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_projects" in sql


def test_table_bf_phases_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_phases" in sql


def test_table_bf_features_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_features" in sql


def test_table_bf_tasks_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_tasks" in sql


def test_table_bf_task_dependencies_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_task_dependencies" in sql


def test_table_bf_acceptance_criteria_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_acceptance_criteria" in sql


def test_table_bf_constitutions_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_constitutions" in sql


def test_table_bf_constitution_revisions_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_constitution_revisions" in sql


def test_table_bf_mocks_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_mocks" in sql


def test_table_bf_deliveries_present(sql):
    assert "CREATE TABLE IF NOT EXISTS bf_deliveries" in sql


def test_table_audit_logs_present(sql):
    assert "CREATE TABLE IF NOT EXISTS audit_logs" in sql


# --- per-table workspace_id / project_id FK on the correct named column ---


def test_bf_projects_workspace_fk_on_workspace_id_column(sql):
    body = _table_body(sql, "bf_projects")
    assert re.search(
        r"workspace_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+workspaces\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    ), "bf_projects.workspace_id must be NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE"


def test_bf_phases_project_fk_cascade(sql):
    body = _table_body(sql, "bf_phases")
    assert re.search(
        r"project_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_projects\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )


def test_bf_features_project_fk_cascade(sql):
    body = _table_body(sql, "bf_features")
    assert re.search(
        r"project_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_projects\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )


def test_bf_tasks_project_fk_cascade_plus_feature_phase_set_null(sql):
    body = _table_body(sql, "bf_tasks")
    assert re.search(
        r"project_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_projects\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )
    assert re.search(
        r"feature_id\s+BIGINT\s+REFERENCES\s+bf_features\s*\(id\)\s+ON\s+DELETE\s+SET\s+NULL",
        body,
    )
    assert re.search(
        r"phase_id\s+BIGINT\s+REFERENCES\s+bf_phases\s*\(id\)\s+ON\s+DELETE\s+SET\s+NULL",
        body,
    )


def test_bf_task_dependencies_both_fks_cascade(sql):
    body = _table_body(sql, "bf_task_dependencies")
    assert re.search(
        r"task_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_tasks\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )
    assert re.search(
        r"depends_on_task_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_tasks\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )


def test_bf_acceptance_criteria_task_fk_cascade(sql):
    body = _table_body(sql, "bf_acceptance_criteria")
    assert re.search(
        r"task_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_tasks\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )


def test_bf_constitutions_project_fk_cascade(sql):
    body = _table_body(sql, "bf_constitutions")
    assert re.search(
        r"project_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_projects\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )


def test_bf_constitution_revisions_fk_cascade(sql):
    body = _table_body(sql, "bf_constitution_revisions")
    assert re.search(
        r"constitution_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_constitutions\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )


def test_bf_mocks_project_fk_cascade_plus_feature_set_null(sql):
    body = _table_body(sql, "bf_mocks")
    assert re.search(
        r"project_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_projects\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )
    assert re.search(
        r"feature_id\s+BIGINT\s+REFERENCES\s+bf_features\s*\(id\)\s+ON\s+DELETE\s+SET\s+NULL",
        body,
    )


def test_bf_deliveries_project_fk_cascade(sql):
    body = _table_body(sql, "bf_deliveries")
    assert re.search(
        r"project_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_projects\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )


def test_audit_logs_workspace_fk_cascade_nullable(sql):
    """audit_logs.workspace_id is nullable (for system-level events).
    The FK exists but NOT NULL is absent (drift guard for the "nullable"
    invariant — see AC-3 audit_member_read NULL-tolerant clause)."""
    body = _table_body(sql, "audit_logs")
    assert re.search(
        r"workspace_id\s+BIGINT\s+REFERENCES\s+workspaces\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
    )
    # explicit non-NOT-NULL invariant: must NOT have NOT NULL on workspace_id
    assert not re.search(
        r"workspace_id\s+BIGINT\s+NOT\s+NULL", body
    ), "audit_logs.workspace_id must remain nullable for system-level events"


# ===========================================================================
# AC-2 EVENT-DRIVEN — full idempotency
# ===========================================================================


def test_ac2_every_create_table_uses_if_not_exists(sql):
    no_if = re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)(\w+)", sql)
    assert not no_if, f"non-idempotent CREATE TABLE: {no_if}"


def test_ac2_every_create_index_uses_if_not_exists(sql):
    no_if = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF NOT EXISTS)(\w+)", sql
    )
    assert not no_if, f"non-idempotent CREATE INDEX: {no_if}"


def test_ac2_every_create_policy_preceded_by_drop_policy(sql):
    """For each `CREATE POLICY <name>` there must be a `DROP POLICY IF EXISTS
    <name>` above it in the same file. 1:1 pairing."""
    creates = re.findall(r"CREATE POLICY\s+(\w+)\s+ON\s+\w+", sql)
    drops = re.findall(r"DROP POLICY IF EXISTS\s+(\w+)\s+ON\s+\w+", sql)
    assert len(creates) == len(drops), (
        f"CREATE POLICY ({len(creates)}) and DROP POLICY IF EXISTS "
        f"({len(drops)}) count mismatch"
    )
    assert set(creates) == set(drops), (
        f"CREATE/DROP policy name set mismatch: "
        f"only_create={set(creates) - set(drops)}, "
        f"only_drop={set(drops) - set(creates)}"
    )


# ===========================================================================
# AC-3 STATE-DRIVEN — RLS per-table policy names verified 1:1
# ===========================================================================


def test_ac3_every_table_enables_rls(sql):
    for table in BF_TABLES:
        assert re.search(
            rf"ALTER TABLE\s+{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY",
            sql,
        ), f"{table} missing ALTER TABLE ... ENABLE ROW LEVEL SECURITY"


def test_ac3_every_expected_policy_name_present(sql):
    """Drift guard: every RLS policy name listed in the audit doc must
    appear verbatim in the SQL. New / renamed / deleted policy names
    break this test on purpose (force audit doc update)."""
    for name in RLS_POLICY_NAMES:
        assert re.search(
            rf"CREATE POLICY\s+{re.escape(name)}\b", sql
        ), f"missing CREATE POLICY {name}"


def test_ac3_no_unexpected_policy_names(sql):
    """Inverse drift guard: SQL must NOT introduce policy names that the
    audit doc does not enumerate. New policies → update audit then this
    list together."""
    found = set(re.findall(r"CREATE POLICY\s+(\w+)\s+ON\s+\w+", sql))
    extras = found - set(RLS_POLICY_NAMES)
    assert not extras, (
        f"unexpected CREATE POLICY names not in audit doc: {extras}"
    )
    missing = set(RLS_POLICY_NAMES) - found
    assert not missing, (
        f"audit doc lists policies absent from SQL: {missing}"
    )


def test_ac3_service_role_policy_per_table(sql):
    """Each of the 11 tables must have a service_role policy with
    `FOR ALL TO postgres, service_role`."""
    for table in BF_TABLES:
        # find the CREATE POLICY ... ON <table> that grants service_role
        m = re.search(
            rf"CREATE POLICY\s+\w+\s+ON\s+{re.escape(table)}\s+FOR\s+ALL\s+TO\s+postgres,\s*service_role\s+USING\s*\(\s*true\s*\)\s+WITH\s+CHECK\s*\(\s*true\s*\)",
            sql,
        )
        assert m, f"{table} missing service_role FOR ALL policy"


def test_ac3_member_policy_uses_bf_can_access_workspace(sql):
    """Workspace-scoped member policies all delegate to
    bf_can_access_workspace() helper (either directly or via project_id IN
    subquery). audit_logs uses bf_can_access_workspace(workspace_id) too."""
    assert sql.count("bf_can_access_workspace(") >= 18, (
        "expected bf_can_access_workspace() referenced in USING / WITH CHECK "
        "for member policies (>=18 occurrences)"
    )


def test_ac3_bf_can_access_workspace_function_defined(sql):
    """SECURITY DEFINER helper function must be defined with STABLE
    volatility and `auth.uid()::text` membership check on
    workspace_members."""
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_can_access_workspace\s*\(\s*ws_id\s+BIGINT\s*\)\s+"
        r"RETURNS\s+BOOLEAN\s+LANGUAGE\s+sql\s+STABLE\s+SECURITY\s+DEFINER\s+AS\s+\$\$"
        r"([\s\S]+?)\$\$;",
        sql,
    )
    assert m, "bf_can_access_workspace function not defined per spec"
    body = m.group(1)
    assert "workspace_members" in body
    assert "auth.uid()::text" in body


def test_ac3_no_for_all_to_public_anywhere(sql):
    """AC-3 invariant: no blanket FOR ALL TO public."""
    bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", sql, re.IGNORECASE)
    assert not bad, f"forbidden FOR ALL TO public: {bad}"


def test_ac3_bf_constitution_revisions_member_is_select_only(sql):
    """bf_const_rev_member is SELECT-only (revisions are immutable audit
    rows, member can read but not write — service_role writes only)."""
    m = re.search(
        r"CREATE POLICY\s+bf_const_rev_member\s+ON\s+bf_constitution_revisions\s+FOR\s+(\w+)",
        sql,
    )
    assert m, "bf_const_rev_member policy not found"
    assert m.group(1).upper() == "SELECT", (
        f"bf_const_rev_member must be FOR SELECT, got FOR {m.group(1)}"
    )


def test_ac3_audit_logs_member_read_is_select_only(sql):
    m = re.search(
        r"CREATE POLICY\s+audit_member_read\s+ON\s+audit_logs\s+FOR\s+(\w+)",
        sql,
    )
    assert m, "audit_member_read policy not found"
    assert m.group(1).upper() == "SELECT"


# ===========================================================================
# AC-4 OPTIONAL — constitutions NOT NULL principles + EARS 5-enum
# ===========================================================================


def test_ac4_bf_constitutions_principles_jsonb_not_null(sql):
    body = _table_body(sql, "bf_constitutions")
    assert re.search(
        r"principles\s+JSONB\s+NOT\s+NULL", body
    ), "bf_constitutions.principles must be JSONB NOT NULL"


def test_ac4_bf_constitutions_principles_non_empty_check(sql):
    body = _table_body(sql, "bf_constitutions")
    assert "principles_non_empty" in body
    assert "jsonb_typeof(principles) = 'object'" in body
    assert "principles <> '{}'::jsonb" in body


def test_ac4_bf_acceptance_criteria_ears_enum_5_values(sql):
    body = _table_body(sql, "bf_acceptance_criteria")
    m = re.search(
        r"ears_type\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*ears_type\s+IN\s*\(([^)]+)\)\s*\)",
        body,
    )
    assert m, "ears_type CHECK enum not found in bf_acceptance_criteria"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"UBIQUITOUS", "EVENT", "STATE", "OPTIONAL", "UNWANTED"}, (
        f"ears_type enum mismatch: {values}"
    )


def test_ac4_bf_phases_status_enum(sql):
    body = _table_body(sql, "bf_phases")
    m = re.search(
        r"status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'pending'\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)",
        body,
    )
    assert m, "bf_phases.status CHECK enum not found"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"pending", "in_progress", "completed", "blocked", "skipped"}


def test_ac4_bf_projects_status_enum_includes_all_phases(sql):
    body = _table_body(sql, "bf_projects")
    m = re.search(
        r"status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'planning'\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)",
        body,
    )
    assert m, "bf_projects.status CHECK enum not found"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {
        "planning", "hearing", "requirements", "architecture",
        "functional", "tech", "feature", "task", "mocks",
        "implementation", "review", "delivered", "cancelled",
    }
    assert values == expected, f"bf_projects.status enum mismatch: {values}"


def test_ac4_bf_tasks_label_enum(sql):
    body = _table_body(sql, "bf_tasks")
    m = re.search(
        r"label\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*label\s+IN\s*\(([^)]+)\)\s*\)",
        body,
    )
    assert m, "bf_tasks.label CHECK enum not found"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"REUSE", "REFACTOR", "NEW", "ARCHIVE"}


def test_ac4_bf_tasks_status_enum(sql):
    body = _table_body(sql, "bf_tasks")
    m = re.search(
        r"status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'todo'\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)",
        body,
    )
    assert m, "bf_tasks.status CHECK enum not found"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"todo", "in_progress", "review", "done", "blocked", "cancelled"}


def test_ac4_bf_features_priority_enum(sql):
    body = _table_body(sql, "bf_features")
    m = re.search(
        r"priority\s+TEXT\s+DEFAULT\s+'must'\s+CHECK\s*\(\s*priority\s+IN\s*\(([^)]+)\)\s*\)",
        body,
    )
    assert m, "bf_features.priority CHECK enum not found"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"must", "should", "could", "wont"}


def test_ac4_bf_task_dependencies_dep_type_enum(sql):
    body = _table_body(sql, "bf_task_dependencies")
    m = re.search(
        r"dep_type\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'blocks'\s+CHECK\s*\(\s*dep_type\s+IN\s*\(([^)]+)\)\s*\)",
        body,
    )
    assert m
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"blocks", "related", "informs"}


def test_ac4_bf_phases_phase_no_range_check(sql):
    body = _table_body(sql, "bf_phases")
    assert re.search(
        r"phase_no\s+INTEGER\s+NOT\s+NULL\s+CHECK\s*\(\s*phase_no\s+BETWEEN\s+1\s+AND\s+10\s*\)",
        body,
    )


# ===========================================================================
# AC-5 UNWANTED — no_self_dep CHECK + no hardcoded secret
# ===========================================================================


def test_ac5_no_self_dep_check_present(sql):
    body = _table_body(sql, "bf_task_dependencies")
    assert re.search(
        r"CONSTRAINT\s+no_self_dep\s+CHECK\s*\(\s*task_id\s*<>\s*depends_on_task_id\s*\)",
        body,
    ), "no_self_dep CHECK on bf_task_dependencies must reject self-loops"


def test_ac5_unique_dep_constraint_present(sql):
    body = _table_body(sql, "bf_task_dependencies")
    assert re.search(
        r"CONSTRAINT\s+uq_bf_dep\s+UNIQUE\s*\(\s*task_id\s*,\s*depends_on_task_id\s*\)",
        body,
    )


def test_ac5_no_hardcoded_supabase_or_anthropic_or_jwt(sql):
    # sb_publishable_*, sb_secret_*, sk-ant-*, JWT (eyJ...)
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", sql)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", sql)
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", sql)


def test_ac5_uniqueness_constraints_named_per_table(sql):
    """Each natural-key UNIQUE constraint is named (drift guard against
    accidentally dropping uniqueness via anonymous CHECK)."""
    expected_named_constraints = (
        ("bf_projects", "uq_bf_project_slug", r"\(workspace_id,\s*slug\)"),
        ("bf_phases", "uq_bf_phase", r"\(project_id,\s*phase_no\)"),
        ("bf_features", "uq_bf_feature", r"\(project_id,\s*feature_id\)"),
        ("bf_tasks", "uq_bf_task", r"\(project_id,\s*task_id\)"),
        ("bf_task_dependencies", "uq_bf_dep", r"\(task_id,\s*depends_on_task_id\)"),
        ("bf_acceptance_criteria", "uq_bf_ac", r"\(task_id,\s*order_index\)"),
        ("bf_constitutions", "uq_bf_constitution_version", r"\(project_id,\s*version\)"),
        ("bf_mocks", "uq_bf_mock", r"\(project_id,\s*mock_id,\s*version\)"),
        ("bf_deliveries", "uq_bf_delivery_no", r"\(project_id,\s*delivery_no\)"),
    )
    for table, cname, cols_re in expected_named_constraints:
        body = _table_body(sql, table)
        pattern = rf"CONSTRAINT\s+{re.escape(cname)}\s+UNIQUE\s+{cols_re}"
        assert re.search(pattern, body), (
            f"{table} missing CONSTRAINT {cname} UNIQUE {cols_re}"
        )


# ===========================================================================
# Per-table TIMESTAMPTZ created_at audit (10/11 tables; revisions uses
# revised_at instead — explicitly named)
# ===========================================================================


def test_created_at_defaults_now_on_each_table_with_created_at(sql):
    tables_with_created_at = (
        "bf_projects", "bf_phases", "bf_features", "bf_tasks",
        "bf_task_dependencies", "bf_acceptance_criteria",
        "bf_constitutions", "bf_mocks", "audit_logs",
    )
    for table in tables_with_created_at:
        body = _table_body(sql, table)
        assert re.search(
            r"created_at\s+TIMESTAMPTZ\s+DEFAULT\s+NOW\(\)", body
        ), f"{table}.created_at must be TIMESTAMPTZ DEFAULT NOW()"


def test_bf_constitution_revisions_revised_at_defaults_now(sql):
    body = _table_body(sql, "bf_constitution_revisions")
    assert re.search(
        r"revised_at\s+TIMESTAMPTZ\s+DEFAULT\s+NOW\(\)", body
    ), "bf_constitution_revisions.revised_at must be TIMESTAMPTZ DEFAULT NOW()"


def test_bf_deliveries_delivered_at_defaults_now(sql):
    body = _table_body(sql, "bf_deliveries")
    assert re.search(
        r"delivered_at\s+TIMESTAMPTZ\s+DEFAULT\s+NOW\(\)", body
    )
