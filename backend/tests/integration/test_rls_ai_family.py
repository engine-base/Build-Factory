"""T-V3-D-05: RLS policy 補完 batch 1 — AI hierarchy / clone family.

Verifies that the new migration
`supabase/migrations/20260516150000_rls_ai_family.sql` adds the required
`account_member_select` policy + idempotent `service_role_all` policy for the
3 v3 entities (E-044 / E-045 / E-046):

  - ai_clones        (E-044)
  - ai_hierarchies   (E-045)
  - ai_personas      (E-046)

Test strategy is static SQL invariant inspection (no live DB) — same pattern
as existing tests under `backend/tests/test_t_001_06_rls_*.py`. The aggregate
policy_count assertion is delegated to `scripts/verify-rls-coverage.py` (gate
covered by AC-R2).

AC mapping (tickets-group-d-drift.json#T-V3-D-05):
  AC-F1 UBIQUITOUS : >= 2 policies per table (service_role_all +
                     account_member_select) — direct static assertion.
  AC-F2 EVENT      : non-member auth user → 0 row.  We verify the policy
                     `USING` clause restricts on `account_members.user_id =
                     auth.uid()::text`, which is the SQL mechanism that
                     produces the 0-row behaviour at runtime.
  AC-F3 EVENT      : service_role → all rows.  We verify a `FOR ALL TO
                     postgres, service_role USING (true)` policy exists per
                     table.
  AC-F4 UNWANTED   : verify-rls-coverage.py policy_count < 2 → fail.  We
                     assert this script is shipped + run-cleanly today.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RLS_AI_FAMILY_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations" / "20260516150000_rls_ai_family.sql"
)
VERIFY_RLS_SCRIPT = REPO_ROOT / "scripts" / "verify-rls-coverage.py"

TARGET_TABLES = ("ai_clones", "ai_hierarchies", "ai_personas")
ACCOUNT_MEMBER_SELECT_POLICY_NAMES = {
    "ai_clones": "ai_clones_account_member_select",
    "ai_hierarchies": "ai_hierarchies_account_member_select",
    "ai_personas": "ai_personas_account_member_select",
}
SERVICE_ROLE_POLICY_NAMES = {
    "ai_clones": "ai_clones_service_role_all",
    "ai_hierarchies": "ai_hierarchies_service_role_all",
    "ai_personas": "ai_personas_service_role_all",
}


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert RLS_AI_FAMILY_MIGRATION.exists(), (
        f"missing migration: {RLS_AI_FAMILY_MIGRATION}"
    )
    return RLS_AI_FAMILY_MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-F1 UBIQUITOUS — service_role + account_member_select per target table
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_alter_table_enable_rls(migration_sql: str, table: str) -> None:
    """各 target table が ENABLE ROW LEVEL SECURITY されている (idempotent)."""
    pattern = rf"ALTER TABLE\s+{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY"
    assert re.search(pattern, migration_sql), (
        f"{table}: missing ENABLE ROW LEVEL SECURITY"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_service_role_policy_declared(migration_sql: str, table: str) -> None:
    """service_role_all policy が宣言されている (FOR ALL TO postgres, service_role)."""
    policy_name = SERVICE_ROLE_POLICY_NAMES[table]
    assert f"CREATE POLICY {policy_name} ON {table}" in migration_sql, (
        f"{table}: missing CREATE POLICY {policy_name}"
    )
    # service_role に対する USING (true) bypass
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+ALL\s+TO\s+postgres,\s*service_role\s+USING\s*\(\s*true\s*\)"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: service_role policy must be FOR ALL TO postgres, service_role USING (true)"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_account_member_select_policy_declared(
    migration_sql: str, table: str
) -> None:
    """account_member_select policy が FOR SELECT TO authenticated として宣言."""
    policy_name = ACCOUNT_MEMBER_SELECT_POLICY_NAMES[table]
    assert f"CREATE POLICY {policy_name} ON {table}" in migration_sql, (
        f"{table}: missing CREATE POLICY {policy_name}"
    )
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+SELECT\s+TO\s+authenticated"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: account_member_select policy must be FOR SELECT TO authenticated"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_policy_idempotent_drop_pair(
    migration_sql: str, table: str
) -> None:
    """各 policy に DROP POLICY IF EXISTS が前置されている (再 apply 安全)."""
    for policy_name in (
        SERVICE_ROLE_POLICY_NAMES[table],
        ACCOUNT_MEMBER_SELECT_POLICY_NAMES[table],
    ):
        assert (
            f"DROP POLICY IF EXISTS {policy_name} ON {table}" in migration_sql
        ), (
            f"{table}: missing DROP POLICY IF EXISTS {policy_name} "
            f"(idempotency violation)"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-F2 EVENT-DRIVEN — non-member auth user → 0 row
#   Static check: account_member_select policy USING clause references
#   account_members.user_id = auth.uid()::text (directly or via helper),
#   which is the SQL mechanism that yields 0 rows for non-member queries.
# ══════════════════════════════════════════════════════════════════════


def test_ac_f2_helper_function_defined(migration_sql: str) -> None:
    """bf_current_user_account_ids helper を定義して RLS で再利用可能にする."""
    assert "CREATE OR REPLACE FUNCTION bf_current_user_account_ids" in migration_sql
    assert "account_members" in migration_sql
    assert re.search(
        r"user_id\s*=\s*auth\.uid\(\)::text",
        migration_sql,
    ), "helper must filter by auth.uid()::text against account_members.user_id"


@pytest.mark.parametrize("table", ("ai_clones", "ai_hierarchies"))
def test_ac_f2_account_member_select_filters_via_workspaces_account_id(
    migration_sql: str, table: str
) -> None:
    """ai_clones / ai_hierarchies は workspace_id → workspaces.account_id 経由で
    account 紐付けを判定する.  policy 本体に
    `workspace_id IN (SELECT id FROM workspaces WHERE account_id IN ...)`
    が含まれることを確認.
    """
    policy_name = ACCOUNT_MEMBER_SELECT_POLICY_NAMES[table]
    # policy 定義からその CREATE POLICY ブロック全体を抜き出す (次の ; まで)
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: could not find CREATE POLICY {policy_name} block"
    body = block_match.group(0)
    assert "workspace_id IN (" in body, (
        f"{table}: account_member_select must restrict workspace_id"
    )
    assert "FROM workspaces" in body, (
        f"{table}: must join workspaces to resolve account_id"
    )
    assert "account_id IN" in body, (
        f"{table}: must filter account_id via bf_current_user_account_ids()"
    )
    assert "bf_current_user_account_ids" in body, (
        f"{table}: must call bf_current_user_account_ids() helper"
    )


def test_ac_f2_ai_personas_select_requires_account_membership(
    migration_sql: str,
) -> None:
    """ai_personas (global seed table) は account_members に
    1 件以上参加している user に限定する.  policy 本体に
    `EXISTS (SELECT 1 FROM account_members WHERE user_id = auth.uid()::text)`
    が含まれることを確認.
    """
    policy_name = ACCOUNT_MEMBER_SELECT_POLICY_NAMES["ai_personas"]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+ai_personas.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match
    body = block_match.group(0)
    assert "EXISTS" in body
    assert "account_members" in body
    assert re.search(
        r"user_id\s*=\s*auth\.uid\(\)::text",
        body,
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
        f"verify-rls-coverage.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    # 3 target tables が ALL set に含まれていること (script output に missing が無い)
    assert "Missing RLS:                     0" in result.stdout, (
        f"unexpected RLS gap reported by verify-rls-coverage:\n{result.stdout}"
    )


# ══════════════════════════════════════════════════════════════════════
# Sanity / drift guards
# ══════════════════════════════════════════════════════════════════════


def test_migration_records_schema_version(migration_sql: str) -> None:
    """schema_versions に 20260516150000 が記録されている (idempotent INSERT)."""
    assert "20260516150000" in migration_sql
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
