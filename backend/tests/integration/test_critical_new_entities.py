"""T-V3-D-12: Critical NEW entity formalization batch 1.

Verifies that the new migration
``supabase/migrations/20260516190000_critical_new_entities.sql`` creates the 3
critical drift entities (E-009 SkillExecution / E-013 PhaseGate /
E-010 UserKnowledgeNamespace) with:

  - Idempotent ``CREATE TABLE IF NOT EXISTS``
  - Column set matching ``entities.json`` ``fields[]`` for each entity
  - ``ENABLE ROW LEVEL SECURITY``
  - Canonical access_policies_required:
      * ``skill_executions_service_role_all`` + ``skill_executions_workspace_member_select``
      * ``phase_gates_service_role_all`` + ``phase_gates_workspace_member_select``
      * ``user_knowledge_namespaces_service_role_all`` + ``user_knowledge_namespaces_owner_only``

Test strategy is static SQL invariant inspection (no live DB) — same pattern
as ``test_rls_bf_project_family.py`` (T-V3-D-07).  Aggregate RLS coverage
assertion is delegated to ``scripts/verify-rls-coverage.py`` (AC-R3 gate).

AC mapping (tickets-group-d-drift.json#T-V3-D-12):
  AC-F1 UBIQUITOUS : 3 new tables with column sets matching
                     entities.json E-009 / E-013 / E-010 ``fields[]``.
  AC-F2 EVENT      : skill execution → row in skill_executions with
                     workspace_id + skill_id + ai_employee_id + cost +
                     tokens + status + langfuse_trace_id.
  AC-F3 EVENT      : phase gate passed → ``passed_at`` + ``passed_by`` columns
                     exist + status enum includes ``passed``.
  AC-F4 EVENT      : user knowledge namespace insert → UNIQUE
                     (user_id, namespace_id) constraint + scope enum
                     (private/account/workspace).
  AC-F5 UNWANTED   : ``scripts/verify-rls-coverage.py`` reports
                     ``policy_count < 2`` → fail.  Static gate enforces
                     >= 2 canonical policy per table; aggregate run must
                     exit 0 with ``Missing RLS: 0``.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260516190000_critical_new_entities.sql"
)
VERIFY_RLS_SCRIPT = REPO_ROOT / "scripts" / "verify-rls-coverage.py"

TARGET_TABLES = (
    "skill_executions",
    "phase_gates",
    "user_knowledge_namespaces",
)

# Expected canonical policies per table (entries from
# tickets-group-d-drift.json#T-V3-D-12 access_policies_required).
EXPECTED_POLICIES: dict[str, tuple[str, ...]] = {
    "skill_executions": (
        "skill_executions_service_role_all",
        "skill_executions_workspace_member_select",
    ),
    "phase_gates": (
        "phase_gates_service_role_all",
        "phase_gates_workspace_member_select",
    ),
    "user_knowledge_namespaces": (
        "user_knowledge_namespaces_service_role_all",
        "user_knowledge_namespaces_owner_only",
    ),
}

# Column sets derived from entities.json E-009 / E-013 / E-010 ``fields[]``.
# Each entry is (column_name, must_be_NOT_NULL).
EXPECTED_COLUMNS: dict[str, tuple[tuple[str, bool], ...]] = {
    "skill_executions": (
        ("skill_id", True),
        ("ai_employee_id", False),
        ("user_id", False),
        ("workspace_id", True),
        ("session_id", False),
        ("input", True),
        ("output", True),
        ("cost", True),
        ("tokens", True),
        ("status", True),
        ("langfuse_trace_id", False),
        ("created_at", True),
        ("updated_at", True),
    ),
    "phase_gates": (
        ("phase_id", True),
        ("workspace_id", True),
        ("name", True),
        ("condition_type", True),
        ("criteria", True),
        ("status", True),
        ("passed_at", False),
        ("passed_by", False),
        ("created_at", True),
        ("updated_at", True),
    ),
    "user_knowledge_namespaces": (
        ("user_id", True),
        ("namespace_id", True),
        ("scope", True),
        ("created_at", True),
        ("updated_at", True),
    ),
}


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table_blocks(migration_sql: str) -> dict[str, str]:
    """Per-table CREATE TABLE ... );  block extraction (greedy until ');')."""
    blocks: dict[str, str] = {}
    for table in TARGET_TABLES:
        match = re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{re.escape(table)}\s*\((.*?)\n\)\s*;",
            migration_sql,
            re.DOTALL,
        )
        assert match, f"{table}: CREATE TABLE IF NOT EXISTS block not found"
        blocks[table] = match.group(1)
    return blocks


# ══════════════════════════════════════════════════════════════════════
# AC-F1 UBIQUITOUS — 3 new tables w/ entities.json column set
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_create_table_is_idempotent(
    migration_sql: str, table: str
) -> None:
    """CREATE TABLE IF NOT EXISTS で idempotent."""
    pattern = rf"CREATE TABLE IF NOT EXISTS\s+{re.escape(table)}"
    assert re.search(pattern, migration_sql), (
        f"{table}: CREATE TABLE IF NOT EXISTS missing (idempotency violation)"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_table_has_primary_key(
    table_blocks: dict[str, str], table: str
) -> None:
    """各 table が BIGSERIAL PRIMARY KEY を持つ (id column)."""
    body = table_blocks[table]
    assert re.search(r"\bid\s+BIGSERIAL\s+PRIMARY\s+KEY\b", body), (
        f"{table}: BIGSERIAL PRIMARY KEY (id) required"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_table_has_timestamps(
    table_blocks: dict[str, str], table: str
) -> None:
    """各 table が created_at / updated_at TIMESTAMPTZ を持つ."""
    body = table_blocks[table]
    assert re.search(
        r"\bcreated_at\s+TIMESTAMPTZ\s+NOT\s+NULL\s+DEFAULT\s+NOW\(\)",
        body,
    ), f"{table}: created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() required"
    assert re.search(
        r"\bupdated_at\s+TIMESTAMPTZ\s+NOT\s+NULL\s+DEFAULT\s+NOW\(\)",
        body,
    ), f"{table}: updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW() required"


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_column_set_matches_entities_json(
    table_blocks: dict[str, str], table: str
) -> None:
    """各 table の column set が entities.json E-009/E-013/E-010 fields[] と
    一致する (column 名の存在 + NOT NULL 制約)."""
    body = table_blocks[table]
    for column, must_not_null in EXPECTED_COLUMNS[table]:
        # Column existence — match start-of-word boundary and whitespace.
        col_pattern = rf"\b{re.escape(column)}\s+[A-Z]"
        assert re.search(col_pattern, body), (
            f"{table}: column `{column}` missing"
        )
        if must_not_null:
            nn_pattern = (
                rf"\b{re.escape(column)}\s+[A-Z][A-Z0-9_()\[\],\s]*\bNOT\s+NULL\b"
            )
            assert re.search(nn_pattern, body, re.IGNORECASE), (
                f"{table}: column `{column}` should be NOT NULL"
            )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_alter_table_enable_rls(
    migration_sql: str, table: str
) -> None:
    """各 target table が ENABLE ROW LEVEL SECURITY されている."""
    pattern = rf"ALTER TABLE\s+{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY"
    assert re.search(pattern, migration_sql), (
        f"{table}: missing ENABLE ROW LEVEL SECURITY"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_canonical_policies_declared(
    migration_sql: str, table: str
) -> None:
    """ticket access_policies_required の canonical 名 policy が宣言済."""
    for policy_name in EXPECTED_POLICIES[table]:
        assert f"CREATE POLICY {policy_name}" in migration_sql, (
            f"{table}: missing CREATE POLICY {policy_name}"
        )
        # idempotent DROP POLICY IF EXISTS が前置されている
        assert f"DROP POLICY IF EXISTS {policy_name}" in migration_sql, (
            f"{table}: missing DROP POLICY IF EXISTS {policy_name} "
            f"(idempotency violation)"
        )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_each_table_has_at_least_two_policies(
    migration_sql: str, table: str
) -> None:
    """各 table に >= 2 policy (AC-F5 / verify-rls-coverage.py policy_count >= 2)."""
    matches = re.findall(
        rf"CREATE POLICY\s+\S+\s+ON\s+{re.escape(table)}\b",
        migration_sql,
    )
    assert len(matches) >= 2, (
        f"{table}: policy_count {len(matches)} < 2 "
        f"(canonical {EXPECTED_POLICIES[table]} required)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F2 EVENT — skill execution records workspace_id + skill_id +
#                ai_employee_id + cost + tokens + status + langfuse_trace_id
# ══════════════════════════════════════════════════════════════════════


def test_ac_f2_skill_executions_workspace_id_fk_cascade(
    table_blocks: dict[str, str],
) -> None:
    """skill_executions.workspace_id は FK to workspaces ON DELETE CASCADE."""
    body = table_blocks["skill_executions"]
    assert re.search(
        r"workspace_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+workspaces\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "skill_executions.workspace_id must FK workspaces ON DELETE CASCADE"


def test_ac_f2_skill_executions_skill_id_fk(
    table_blocks: dict[str, str],
) -> None:
    """skill_executions.skill_id は FK to skill_definitions."""
    body = table_blocks["skill_executions"]
    assert re.search(
        r"skill_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+skill_definitions\(id\)",
        body,
        re.IGNORECASE,
    ), "skill_executions.skill_id must FK skill_definitions"


def test_ac_f2_skill_executions_ai_employee_id_fk(
    table_blocks: dict[str, str],
) -> None:
    """skill_executions.ai_employee_id は FK to ai_employees (NULL 許容)."""
    body = table_blocks["skill_executions"]
    assert re.search(
        r"ai_employee_id\s+BIGINT\s+REFERENCES\s+ai_employees\(id\)",
        body,
        re.IGNORECASE,
    ), "skill_executions.ai_employee_id must FK ai_employees"


def test_ac_f2_skill_executions_session_id_fk_nullable(
    table_blocks: dict[str, str],
) -> None:
    """skill_executions.session_id は FK to sessions (NULL 許容; spec NULL)."""
    body = table_blocks["skill_executions"]
    assert re.search(
        r"session_id\s+BIGINT\s+REFERENCES\s+sessions\(id\)",
        body,
        re.IGNORECASE,
    ), "skill_executions.session_id must FK sessions (nullable)"


def test_ac_f2_skill_executions_status_enum(
    table_blocks: dict[str, str],
) -> None:
    """status enum は entities.json E-009 と一致 (success/failed/cancelled)."""
    body = table_blocks["skill_executions"]
    assert re.search(
        r"status\s+TEXT[^,]*CHECK\s*\(\s*status\s+IN\s*\(\s*'success'\s*,\s*'failed'\s*,\s*'cancelled'\s*\)\s*\)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), "skill_executions.status enum must be (success/failed/cancelled)"


def test_ac_f2_skill_executions_cost_tokens_langfuse(
    table_blocks: dict[str, str],
) -> None:
    """cost (numeric), tokens (integer), langfuse_trace_id (text) が存在."""
    body = table_blocks["skill_executions"]
    assert re.search(r"\bcost\s+NUMERIC", body, re.IGNORECASE), (
        "skill_executions.cost must be NUMERIC"
    )
    assert re.search(r"\btokens\s+INTEGER", body, re.IGNORECASE), (
        "skill_executions.tokens must be INTEGER"
    )
    assert re.search(r"\blangfuse_trace_id\s+TEXT", body, re.IGNORECASE), (
        "skill_executions.langfuse_trace_id must be TEXT"
    )


def test_ac_f2_skill_executions_workspace_select_uses_helper(
    migration_sql: str,
) -> None:
    """skill_executions_workspace_member_select は bf_can_access_workspace
    helper を USING 句で呼ぶ (非 member は 0 row)."""
    block_match = re.search(
        r"CREATE POLICY\s+skill_executions_workspace_member_select\s+ON\s+skill_executions.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, "skill_executions workspace_member_select block missing"
    body = block_match.group(0)
    assert "bf_can_access_workspace(workspace_id)" in body, (
        "skill_executions workspace_member_select must call "
        "bf_can_access_workspace(workspace_id)"
    )
    assert re.search(r"FOR\s+SELECT\s+TO\s+authenticated", body, re.IGNORECASE), (
        "skill_executions workspace_member_select must be FOR SELECT TO authenticated"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F3 EVENT — phase gate passed → passed_at + passed_by recorded
# ══════════════════════════════════════════════════════════════════════


def test_ac_f3_phase_gates_phase_id_fk_cascade(
    table_blocks: dict[str, str],
) -> None:
    """phase_gates.phase_id は FK to bf_phases ON DELETE CASCADE."""
    body = table_blocks["phase_gates"]
    assert re.search(
        r"phase_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+bf_phases\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "phase_gates.phase_id must FK bf_phases ON DELETE CASCADE"


def test_ac_f3_phase_gates_workspace_id_fk_cascade(
    table_blocks: dict[str, str],
) -> None:
    """phase_gates.workspace_id (非正規化) は FK workspaces ON DELETE CASCADE."""
    body = table_blocks["phase_gates"]
    assert re.search(
        r"workspace_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+workspaces\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "phase_gates.workspace_id must FK workspaces ON DELETE CASCADE"


def test_ac_f3_phase_gates_condition_type_enum(
    table_blocks: dict[str, str],
) -> None:
    """condition_type enum (task_completion/review_approval/manual)."""
    body = table_blocks["phase_gates"]
    assert re.search(
        r"condition_type\s+TEXT[^,]*CHECK\s*\(\s*condition_type\s+IN\s*\(\s*'task_completion'\s*,\s*'review_approval'\s*,\s*'manual'\s*\)\s*\)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), "phase_gates.condition_type enum must be (task_completion/review_approval/manual)"


def test_ac_f3_phase_gates_status_enum_includes_passed(
    table_blocks: dict[str, str],
) -> None:
    """status enum (pending/passed/failed) — 'passed' transition mandatory."""
    body = table_blocks["phase_gates"]
    assert re.search(
        r"status\s+TEXT[^,]*CHECK\s*\(\s*status\s+IN\s*\(\s*'pending'\s*,\s*'passed'\s*,\s*'failed'\s*\)\s*\)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), "phase_gates.status enum must include 'passed' (transition column for AC-F3)"


def test_ac_f3_phase_gates_passed_at_and_passed_by_columns(
    table_blocks: dict[str, str],
) -> None:
    """passed_at TIMESTAMPTZ + passed_by TEXT columns exist (nullable until set)."""
    body = table_blocks["phase_gates"]
    assert re.search(r"\bpassed_at\s+TIMESTAMPTZ\b", body, re.IGNORECASE), (
        "phase_gates.passed_at TIMESTAMPTZ column required"
    )
    assert re.search(r"\bpassed_by\s+TEXT\b", body, re.IGNORECASE), (
        "phase_gates.passed_by TEXT column required"
    )
    # Both must be nullable (not declared NOT NULL) so that the transition
    # can record them later than row creation.
    assert not re.search(
        r"\bpassed_at\s+TIMESTAMPTZ\b[^,]*NOT\s+NULL",
        body,
        re.IGNORECASE,
    ), "phase_gates.passed_at must remain nullable"
    assert not re.search(
        r"\bpassed_by\s+TEXT\b[^,]*NOT\s+NULL",
        body,
        re.IGNORECASE,
    ), "phase_gates.passed_by must remain nullable"


def test_ac_f3_phase_gates_workspace_select_uses_helper(
    migration_sql: str,
) -> None:
    """phase_gates_workspace_member_select は bf_can_access_workspace を呼ぶ."""
    block_match = re.search(
        r"CREATE POLICY\s+phase_gates_workspace_member_select\s+ON\s+phase_gates.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, "phase_gates workspace_member_select block missing"
    body = block_match.group(0)
    assert "bf_can_access_workspace(workspace_id)" in body, (
        "phase_gates workspace_member_select must call "
        "bf_can_access_workspace(workspace_id)"
    )
    assert re.search(r"FOR\s+SELECT\s+TO\s+authenticated", body, re.IGNORECASE), (
        "phase_gates workspace_member_select must be FOR SELECT TO authenticated"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F4 EVENT — user knowledge namespace UNIQUE(user_id, namespace_id) +
#                scope enum (private/account/workspace)
# ══════════════════════════════════════════════════════════════════════


def test_ac_f4_user_knowledge_namespaces_unique_user_namespace(
    table_blocks: dict[str, str], migration_sql: str
) -> None:
    """UNIQUE (user_id, namespace_id) を強制 (AC-F4)."""
    body = table_blocks["user_knowledge_namespaces"]
    # UNIQUE 制約は table 内 CONSTRAINT または独立 ALTER で宣言され得る
    in_table = re.search(
        r"UNIQUE\s*\(\s*user_id\s*,\s*namespace_id\s*\)",
        body,
        re.IGNORECASE,
    )
    in_table_named = re.search(
        r"CONSTRAINT\s+\w+\s+UNIQUE\s*\(\s*user_id\s*,\s*namespace_id\s*\)",
        body,
        re.IGNORECASE,
    )
    standalone = re.search(
        r"ALTER\s+TABLE\s+user_knowledge_namespaces\s+ADD\s+CONSTRAINT[^;]*UNIQUE\s*\(\s*user_id\s*,\s*namespace_id\s*\)",
        migration_sql,
        re.IGNORECASE,
    )
    assert in_table or in_table_named or standalone, (
        "user_knowledge_namespaces: UNIQUE (user_id, namespace_id) must be enforced"
    )


def test_ac_f4_user_knowledge_namespaces_scope_enum(
    table_blocks: dict[str, str],
) -> None:
    """scope enum (private/account/workspace) — T-V3-D-12 spec."""
    body = table_blocks["user_knowledge_namespaces"]
    assert re.search(
        r"scope\s+TEXT[^,]*CHECK\s*\(\s*scope\s+IN\s*\(\s*'private'\s*,\s*'account'\s*,\s*'workspace'\s*\)\s*\)",
        body,
        re.IGNORECASE | re.DOTALL,
    ), "user_knowledge_namespaces.scope enum must be (private/account/workspace)"


def test_ac_f4_user_knowledge_namespaces_owner_only_policy_predicate(
    migration_sql: str,
) -> None:
    """owner_only policy: user_id = auth.uid()::text (本人 only)."""
    block_match = re.search(
        r"CREATE POLICY\s+user_knowledge_namespaces_owner_only\s+ON\s+user_knowledge_namespaces.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, "user_knowledge_namespaces owner_only block missing"
    body = block_match.group(0)
    assert re.search(r"FOR\s+ALL\s+TO\s+authenticated", body, re.IGNORECASE), (
        "user_knowledge_namespaces_owner_only must be FOR ALL TO authenticated"
    )
    assert re.search(
        r"USING\s*\(\s*user_id\s*=\s*auth\.uid\(\)::text\s*\)",
        body,
        re.IGNORECASE,
    ), "user_knowledge_namespaces_owner_only USING (user_id = auth.uid()::text) required"
    assert re.search(
        r"WITH\s+CHECK\s*\(\s*user_id\s*=\s*auth\.uid\(\)::text\s*\)",
        body,
        re.IGNORECASE,
    ), "user_knowledge_namespaces_owner_only WITH CHECK (user_id = auth.uid()::text) required"


# ══════════════════════════════════════════════════════════════════════
# AC-F5 UNWANTED — verify-rls-coverage.py policy_count < 2 → fail
# ══════════════════════════════════════════════════════════════════════


def test_ac_f5_verify_rls_coverage_script_exists() -> None:
    assert VERIFY_RLS_SCRIPT.exists(), (
        f"missing gate script: {VERIFY_RLS_SCRIPT}"
    )


def test_ac_f5_verify_rls_coverage_passes() -> None:
    """verify-rls-coverage.py が exit 0 で完走することを CI で常時保証."""
    result = subprocess.run(  # noqa: S603 — script lives inside repo
        [sys.executable, str(VERIFY_RLS_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"verify-rls-coverage.py failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "Missing RLS:                     0" in result.stdout, (
        f"unexpected RLS gap reported:\n{result.stdout}"
    )
    # The 3 new target tables must appear in the migrations corpus.
    for table in TARGET_TABLES:
        assert table not in result.stdout.split("以下の table")[-1] if "FAIL" in result.stdout else True, (
            f"{table}: reported as missing RLS"
        )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f5_service_role_uses_true_predicate(
    migration_sql: str, table: str
) -> None:
    """service_role_all policy が USING (true) WITH CHECK (true) で
    service_role による全 row access を確保."""
    policy_name = f"{table}_service_role_all"
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing service_role policy block"
    body = block_match.group(0)
    assert re.search(r"FOR\s+ALL\s+TO\s+postgres,\s*service_role", body, re.IGNORECASE), (
        f"{table}: service_role policy must be FOR ALL TO postgres, service_role"
    )
    assert re.search(r"USING\s*\(\s*true\s*\)", body), (
        f"{table}: service_role USING (true) required"
    )
    assert re.search(r"WITH\s+CHECK\s*\(\s*true\s*\)", body), (
        f"{table}: service_role WITH CHECK (true) required"
    )


# ══════════════════════════════════════════════════════════════════════
# Sanity / drift guards
# ══════════════════════════════════════════════════════════════════════


def test_migration_records_schema_version(migration_sql: str) -> None:
    """schema_versions に 20260516190000 が記録されている (idempotent INSERT)."""
    assert "20260516190000" in migration_sql
    assert (
        "INSERT INTO schema_versions" in migration_sql
        and "ON CONFLICT (version) DO NOTHING" in migration_sql
    )


def test_no_disable_row_level_security(migration_sql: str) -> None:
    """RLS を一切 DISABLE しない (T-001-06 invariant 継承)."""
    assert "DISABLE ROW LEVEL SECURITY" not in migration_sql.upper()


def test_no_for_all_to_public(migration_sql: str) -> None:
    """public ロールに対する FOR ALL を作らない (security baseline)."""
    assert not re.search(
        r"FOR\s+ALL\s+TO\s+public\b",
        migration_sql,
        re.IGNORECASE,
    )


def test_all_required_canonical_policies_present(migration_sql: str) -> None:
    """T-V3-D-12 ticket #access_policies_required[] の canonical 名が全て揃う."""
    required = (
        ("skill_executions", "skill_executions_service_role_all"),
        ("skill_executions", "skill_executions_workspace_member_select"),
        ("phase_gates", "phase_gates_service_role_all"),
        ("phase_gates", "phase_gates_workspace_member_select"),
        ("user_knowledge_namespaces", "user_knowledge_namespaces_service_role_all"),
        ("user_knowledge_namespaces", "user_knowledge_namespaces_owner_only"),
    )
    for table, policy in required:
        assert f"CREATE POLICY {policy} ON {table}" in migration_sql, (
            f"missing canonical policy: {policy} ON {table}"
        )
