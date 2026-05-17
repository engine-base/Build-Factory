"""T-V3-D-07: RLS policy 補完 batch 3 — bf_project family.

Verifies that the new migration
`supabase/migrations/20260516170000_rls_bf_project_family.sql` adds the
required canonical `workspace_member_select` policy + idempotent
`service_role_all` policy for the 6 v3 entities (E-056 / E-057 / E-058 /
E-059 / E-060 / E-061):

  - bf_projects                (E-056 BFProject)
  - bf_features                (E-057 BFFeature)
  - bf_mocks                   (E-058 BFMock)
  - bf_deliveries              (E-059 BFDelivery)
  - bf_constitution_revisions  (E-060 BFConstitutionRevision)
  - session_artifacts          (E-061 SessionArtifact)

Test strategy is static SQL invariant inspection (no live DB) — same pattern
as `test_rls_ai_family.py` (T-V3-D-05). The aggregate policy_count
assertion is delegated to `scripts/verify-rls-coverage.py` (gate covered by
AC-R2).

AC mapping (tickets-group-d-drift.json#T-V3-D-07):
  AC-F1 UBIQUITOUS : >= 2 policies per table (service_role_all +
                     workspace_member_select) — direct static assertion.
  AC-F2 EVENT      : non-member auth user → 0 row.  We verify the policy
                     `USING` clause restricts via
                     `bf_can_access_workspace(workspace_id)` (or join
                     through bf_projects / bf_constitutions), which is the
                     SQL mechanism that produces 0-row behaviour at runtime
                     for non-member queries.
  AC-F3 EVENT      : service_role → all rows.  We verify a `FOR ALL TO
                     postgres, service_role USING (true) WITH CHECK (true)`
                     policy exists per table.
  AC-F4 UNWANTED   : verify-rls-coverage.py policy_count < 2 → fail.  We
                     assert this script is shipped + runs cleanly today
                     with the new migration in place.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RLS_BF_PROJECT_FAMILY_MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260516170000_rls_bf_project_family.sql"
)
VERIFY_RLS_SCRIPT = REPO_ROOT / "scripts" / "verify-rls-coverage.py"

TARGET_TABLES = (
    "bf_projects",
    "bf_features",
    "bf_mocks",
    "bf_deliveries",
    "bf_constitution_revisions",
    "session_artifacts",
)

# Tables that filter directly via workspace_id (bf_can_access_workspace).
WORKSPACE_DIRECT_TABLES = ("bf_projects",)

# Tables that filter via project_id -> bf_projects -> workspace_id.
PROJECT_JOINED_TABLES = ("bf_features", "bf_mocks", "bf_deliveries")

# Tables that filter via constitution_id -> bf_constitutions -> bf_projects.
CONSTITUTION_JOINED_TABLES = ("bf_constitution_revisions",)

# Tables that store workspace_id directly but nullable (session_artifacts).
WORKSPACE_NULLABLE_TABLES = ("session_artifacts",)

WORKSPACE_MEMBER_SELECT_POLICY_NAMES = {
    t: f"{t}_workspace_member_select" for t in TARGET_TABLES
}
SERVICE_ROLE_POLICY_NAMES = {t: f"{t}_service_role_all" for t in TARGET_TABLES}


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert RLS_BF_PROJECT_FAMILY_MIGRATION.exists(), (
        f"missing migration: {RLS_BF_PROJECT_FAMILY_MIGRATION}"
    )
    return RLS_BF_PROJECT_FAMILY_MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-F1 UBIQUITOUS — service_role_all + workspace_member_select per target table
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_alter_table_enable_rls(migration_sql: str, table: str) -> None:
    """各 target table が ENABLE ROW LEVEL SECURITY されている (idempotent)."""
    pattern = rf"ALTER TABLE\s+{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY"
    assert re.search(pattern, migration_sql), (
        f"{table}: missing ENABLE ROW LEVEL SECURITY"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_service_role_policy_declared(
    migration_sql: str, table: str
) -> None:
    """service_role_all policy が宣言されている (FOR ALL TO postgres, service_role)."""
    policy_name = SERVICE_ROLE_POLICY_NAMES[table]
    assert f"CREATE POLICY {policy_name} ON {table}" in migration_sql, (
        f"{table}: missing CREATE POLICY {policy_name}"
    )
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+ALL\s+TO\s+postgres,\s*service_role\s+USING\s*\(\s*true\s*\)"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: service_role policy must be FOR ALL TO postgres, service_role USING (true)"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_workspace_member_select_policy_declared(
    migration_sql: str, table: str
) -> None:
    """workspace_member_select policy が FOR SELECT TO authenticated として宣言."""
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table]
    assert f"CREATE POLICY {policy_name} ON {table}" in migration_sql, (
        f"{table}: missing CREATE POLICY {policy_name}"
    )
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+SELECT\s+TO\s+authenticated"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: workspace_member_select policy must be FOR SELECT TO authenticated"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_policy_idempotent_drop_pair(
    migration_sql: str, table: str
) -> None:
    """各 policy に DROP POLICY IF EXISTS が前置されている (再 apply 安全)."""
    for policy_name in (
        SERVICE_ROLE_POLICY_NAMES[table],
        WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table],
    ):
        assert (
            f"DROP POLICY IF EXISTS {policy_name} ON {table}" in migration_sql
        ), (
            f"{table}: missing DROP POLICY IF EXISTS {policy_name} "
            f"(idempotency violation)"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-F2 EVENT-DRIVEN — non-member auth user → 0 row
#   Static check: workspace_member_select policy USING clause references
#   bf_can_access_workspace() (directly or via join), which is the SQL
#   mechanism that yields 0 rows for non-member queries.
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", WORKSPACE_DIRECT_TABLES)
def test_ac_f2_workspace_direct_uses_bf_can_access(
    migration_sql: str, table: str
) -> None:
    """bf_projects は workspace_id を直接保有 → bf_can_access_workspace(workspace_id)
    を policy USING 句で直接呼ぶ."""
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing workspace_member_select block"
    body = block_match.group(0)
    assert "bf_can_access_workspace(workspace_id)" in body, (
        f"{table}: must call bf_can_access_workspace(workspace_id) directly"
    )


@pytest.mark.parametrize("table", PROJECT_JOINED_TABLES)
def test_ac_f2_project_joined_uses_bf_projects_join(
    migration_sql: str, table: str
) -> None:
    """bf_features / bf_mocks / bf_deliveries は project_id → bf_projects →
    workspace_id の join 経由でアクセス制御する."""
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing workspace_member_select block"
    body = block_match.group(0)
    assert "project_id IN" in body, (
        f"{table}: must restrict project_id via subquery"
    )
    assert "FROM bf_projects" in body, (
        f"{table}: must join bf_projects to resolve workspace_id"
    )
    assert "bf_can_access_workspace(workspace_id)" in body, (
        f"{table}: must call bf_can_access_workspace(workspace_id)"
    )


@pytest.mark.parametrize("table", CONSTITUTION_JOINED_TABLES)
def test_ac_f2_constitution_joined_uses_double_join(
    migration_sql: str, table: str
) -> None:
    """bf_constitution_revisions は constitution_id → bf_constitutions →
    bf_projects → workspace_id の 2-hop join 経由."""
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing workspace_member_select block"
    body = block_match.group(0)
    assert "constitution_id IN" in body, (
        f"{table}: must restrict constitution_id"
    )
    assert "FROM bf_constitutions" in body, (
        f"{table}: must join bf_constitutions"
    )
    assert "JOIN bf_projects" in body, (
        f"{table}: must join bf_projects to resolve workspace_id"
    )
    assert "bf_can_access_workspace" in body, (
        f"{table}: must call bf_can_access_workspace"
    )


@pytest.mark.parametrize("table", WORKSPACE_NULLABLE_TABLES)
def test_ac_f2_workspace_nullable_handles_null(
    migration_sql: str, table: str
) -> None:
    """session_artifacts は workspace_id NULL を許容. canonical workspace_member_select
    では `workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id)` で
    NULL row は exposing しない (非所属 user に対する fail-closed)."""
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing workspace_member_select block"
    body = block_match.group(0)
    assert "workspace_id IS NOT NULL" in body, (
        f"{table}: must guard workspace_id IS NOT NULL"
    )
    assert "bf_can_access_workspace(workspace_id)" in body, (
        f"{table}: must call bf_can_access_workspace(workspace_id)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F3 EVENT-DRIVEN — service_role → all rows
#   service_role_all policy must be FOR ALL TO postgres, service_role
#   USING (true) WITH CHECK (true) per target table.
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f3_service_role_bypass_returns_all(
    migration_sql: str, table: str
) -> None:
    """service_role policy が USING (true) WITH CHECK (true) で全 row 返却.
    PostgreSQL は service_role を含む POLICY ROLE list にマッチした場合
    USING(true) で行 filter を bypass する.
    """
    policy_name = SERVICE_ROLE_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing service_role policy block"
    body = block_match.group(0)
    assert re.search(r"USING\s*\(\s*true\s*\)", body), (
        f"{table}: service_role USING (true) required for AC-F3"
    )
    assert re.search(r"WITH\s+CHECK\s*\(\s*true\s*\)", body), (
        f"{table}: service_role WITH CHECK (true) required for AC-F3"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F4 UNWANTED — verify-rls-coverage.py reports policy_count < 2 → fail
# ══════════════════════════════════════════════════════════════════════


def test_ac_f4_verify_rls_coverage_script_exists() -> None:
    assert VERIFY_RLS_SCRIPT.exists(), (
        f"missing gate script: {VERIFY_RLS_SCRIPT}"
    )


def test_ac_f4_verify_rls_coverage_passes() -> None:
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
    # 6 target tables が ALL set に含まれていること (script output に missing が無い)
    assert "Missing RLS:                     0" in result.stdout, (
        f"unexpected RLS gap reported by verify-rls-coverage:\n{result.stdout}"
    )


# ══════════════════════════════════════════════════════════════════════
# Sanity / drift guards
# ══════════════════════════════════════════════════════════════════════


def test_migration_records_schema_version(migration_sql: str) -> None:
    """schema_versions に 20260516170000 が記録されている (idempotent INSERT)."""
    assert "20260516170000" in migration_sql
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
    """T-V3-D-07 ticket #access_policies_required[] に列挙された
    canonical 名がすべて migration に含まれていること (spec ↔ impl drift gate)."""
    required = (
        "bf_projects:bf_projects_service_role_all",
        "bf_projects:bf_projects_workspace_member_select",
        "bf_features:bf_features_workspace_member_select",
        "bf_mocks:bf_mocks_workspace_member_select",
        "bf_deliveries:bf_deliveries_workspace_member_select",
        "bf_constitution_revisions:bf_constitution_revisions_workspace_member_select",
        "session_artifacts:session_artifacts_workspace_member_select",
    )
    for spec in required:
        table, policy = spec.split(":", 1)
        assert (
            f"CREATE POLICY {policy} ON {table}" in migration_sql
        ), f"missing canonical policy: {policy} ON {table} ({spec})"
