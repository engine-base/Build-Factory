"""T-V3-D-06: RLS policy 補完 batch 2 — auth & profile family.

Verifies that the new migration
`supabase/migrations/20260516160000_rls_auth_profile_family.sql` adds the
required canonical `<table>_service_role_all` + `<table>_owner_only` (or
`auth_audit_log_account_member_select`) policies for the 9 v3 entities
(E-047〜E-055):

  - user_clone_optin          (E-047)
  - user_deletion_requests    (E-048)
  - user_profiles             (E-049)
  - encrypted_secrets         (E-050)
  - auth_sessions             (E-051)
  - oauth_connections         (E-052)
  - user_2fa_secrets          (E-053, SECURITY CRITICAL)
  - user_2fa_recovery_codes   (E-054, SECURITY CRITICAL)
  - auth_audit_log            (E-055)

Test strategy is static SQL invariant inspection (no live DB) — same pattern
as `test_rls_ai_family.py` (T-V3-D-05). The aggregate policy_count assertion
is delegated to `scripts/verify-rls-coverage.py` (gate covered by AC-R2).

AC mapping (tickets-group-d-drift.json#T-V3-D-06):
  AC-F1 UBIQUITOUS : >= 2 canonical policies per table
                     (service_role_all + owner_scoped) — direct static
                     assertion.
  AC-F2 EVENT      : user_id != auth.uid() で user_profiles を query → 0 row.
                     owner_only policy の USING clause が
                     `user_id = auth.uid()::text` であることで保証.
  AC-F3 EVENT      : 他人の auth_audit_log event を query → 0 row.
                     account_member_select policy の USING clause が
                     `auth.uid() = user_id` であることで保証.
  AC-F4 UNWANTED   : verify-rls-coverage.py policy_count < 2 → fail.
                     スクリプトの exit 0 を保証.
  AC-F5 UNWANTED   : encrypted_secrets.encrypted_value を non-service_role
                     に直接公開しない. owner_only policy の predicate が
                     polymorphic owner check (owner_id = auth.uid()::text)
                     であることで non-owner には 0 row, 列直接公開不可.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RLS_AUTH_PROFILE_MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260516160000_rls_auth_profile_family.sql"
)
VERIFY_RLS_SCRIPT = REPO_ROOT / "scripts" / "verify-rls-coverage.py"

# 9 target tables (E-047〜E-055).
TARGET_TABLES = (
    "user_clone_optin",
    "user_deletion_requests",
    "user_profiles",
    "encrypted_secrets",
    "auth_sessions",
    "oauth_connections",
    "user_2fa_secrets",
    "user_2fa_recovery_codes",
    "auth_audit_log",
)

# 8 tables use *_owner_only policy. auth_audit_log uses account_member_select.
OWNER_ONLY_TABLES = (
    "user_clone_optin",
    "user_deletion_requests",
    "user_profiles",
    "encrypted_secrets",
    "auth_sessions",
    "oauth_connections",
    "user_2fa_secrets",
    "user_2fa_recovery_codes",
)

# user_id column is TEXT in these tables (auth.uid()::text comparison).
TEXT_USER_ID_TABLES = {
    "user_clone_optin",
    "user_deletion_requests",
    "user_profiles",
}

# encrypted_secrets uses owner_id (polymorphic) TEXT.
POLY_OWNER_TABLES = {"encrypted_secrets"}

# user_id column is UUID in these tables (auth.uid() = user_id comparison).
UUID_USER_ID_TABLES = {
    "auth_sessions",
    "oauth_connections",
    "user_2fa_secrets",
    "user_2fa_recovery_codes",
    "auth_audit_log",
}

SERVICE_ROLE_POLICY_NAMES = {t: f"{t}_service_role_all" for t in TARGET_TABLES}
OWNER_ONLY_POLICY_NAMES = {t: f"{t}_owner_only" for t in OWNER_ONLY_TABLES}
AUDIT_SELECT_POLICY_NAME = "auth_audit_log_account_member_select"

SECURITY_CRITICAL_TABLES = {"user_2fa_secrets", "user_2fa_recovery_codes"}


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert RLS_AUTH_PROFILE_MIGRATION.exists(), (
        f"missing migration: {RLS_AUTH_PROFILE_MIGRATION}"
    )
    return RLS_AUTH_PROFILE_MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-F1 UBIQUITOUS — service_role_all + owner_scoped per target table
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_alter_table_enable_rls(migration_sql: str, table: str) -> None:
    """各 target table が ENABLE ROW LEVEL SECURITY されている (idempotent)."""
    pattern = rf"ALTER TABLE\s+{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY"
    assert re.search(pattern, migration_sql), (
        f"{table}: missing ENABLE ROW LEVEL SECURITY"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_service_role_all_policy_declared(
    migration_sql: str, table: str
) -> None:
    """service_role_all policy が canonical 命名で宣言 (FOR ALL TO postgres, service_role)."""
    policy_name = SERVICE_ROLE_POLICY_NAMES[table]
    assert f"CREATE POLICY {policy_name} ON {table}" in migration_sql, (
        f"{table}: missing CREATE POLICY {policy_name}"
    )
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+ALL\s+TO\s+postgres,\s*service_role\s+USING\s*\(\s*true\s*\)"
        rf"\s+WITH\s+CHECK\s*\(\s*true\s*\)"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: service_role_all policy must be "
        f"FOR ALL TO postgres, service_role USING (true) WITH CHECK (true)"
    )


@pytest.mark.parametrize("table", OWNER_ONLY_TABLES)
def test_ac_f1_owner_only_policy_declared(
    migration_sql: str, table: str
) -> None:
    """owner_only policy が canonical 命名で宣言 (FOR ALL TO authenticated)."""
    policy_name = OWNER_ONLY_POLICY_NAMES[table]
    assert f"CREATE POLICY {policy_name} ON {table}" in migration_sql, (
        f"{table}: missing CREATE POLICY {policy_name}"
    )
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+ALL\s+TO\s+authenticated"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: owner_only policy must be FOR ALL TO authenticated"
    )


def test_ac_f1_auth_audit_log_account_member_select_declared(
    migration_sql: str,
) -> None:
    """auth_audit_log は account_member_select policy (FOR SELECT) で宣言."""
    assert (
        f"CREATE POLICY {AUDIT_SELECT_POLICY_NAME} ON auth_audit_log"
        in migration_sql
    ), f"missing CREATE POLICY {AUDIT_SELECT_POLICY_NAME}"
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(AUDIT_SELECT_POLICY_NAME)}\s+"
        rf"ON\s+auth_audit_log\s+FOR\s+SELECT\s+TO\s+authenticated"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        "auth_audit_log_account_member_select must be FOR SELECT TO authenticated"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_policy_idempotent_drop_pair(
    migration_sql: str, table: str
) -> None:
    """各 policy に DROP POLICY IF EXISTS が前置されている (再 apply 安全)."""
    names = [SERVICE_ROLE_POLICY_NAMES[table]]
    if table in OWNER_ONLY_POLICY_NAMES:
        names.append(OWNER_ONLY_POLICY_NAMES[table])
    if table == "auth_audit_log":
        names.append(AUDIT_SELECT_POLICY_NAME)

    for policy_name in names:
        assert (
            f"DROP POLICY IF EXISTS {policy_name} ON {table}" in migration_sql
        ), (
            f"{table}: missing DROP POLICY IF EXISTS {policy_name} "
            "(idempotency violation)"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-F2 EVENT-DRIVEN — user_id != auth.uid() → 0 row
# user_profiles owner_only USING clause must restrict on
# `user_id = auth.uid()::text`.
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", sorted(TEXT_USER_ID_TABLES))
def test_ac_f2_text_user_id_owner_only_predicate(
    migration_sql: str, table: str
) -> None:
    """TEXT user_id 系 (user_profiles ほか) は user_id = auth.uid()::text で
    owner-scoped filter. 非所有者 query は 0 row."""
    policy_name = OWNER_ONLY_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing owner_only policy block"
    body = block_match.group(0)
    assert re.search(
        r"USING\s*\(\s*user_id\s*=\s*auth\.uid\(\)::text\s*\)",
        body,
    ), (
        f"{table}: owner_only USING clause must be "
        "(user_id = auth.uid()::text) for AC-F2"
    )
    assert re.search(
        r"WITH\s+CHECK\s*\(\s*user_id\s*=\s*auth\.uid\(\)::text\s*\)",
        body,
    ), (
        f"{table}: owner_only WITH CHECK must mirror USING (defence in depth)"
    )


@pytest.mark.parametrize("table", sorted(UUID_USER_ID_TABLES - {"auth_audit_log"}))
def test_ac_f2_uuid_user_id_owner_only_predicate(
    migration_sql: str, table: str
) -> None:
    """UUID user_id 系 (auth_sessions / oauth_connections / 2FA ほか) は
    auth.uid() = user_id で owner-scoped filter."""
    policy_name = OWNER_ONLY_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, f"{table}: missing owner_only policy block"
    body = block_match.group(0)
    assert re.search(
        r"USING\s*\(\s*auth\.uid\(\)\s*=\s*user_id\s*\)",
        body,
    ), (
        f"{table}: owner_only USING clause must be "
        "(auth.uid() = user_id) for AC-F2 (UUID comparison)"
    )
    assert re.search(
        r"WITH\s+CHECK\s*\(\s*auth\.uid\(\)\s*=\s*user_id\s*\)",
        body,
    ), f"{table}: owner_only WITH CHECK must mirror USING (UUID)"


# ══════════════════════════════════════════════════════════════════════
# AC-F3 EVENT-DRIVEN — 他人の auth_audit_log event を query → 0 row
# account_member_select USING clause must restrict on
# `auth.uid() = user_id`.
# ══════════════════════════════════════════════════════════════════════


def test_ac_f3_auth_audit_log_account_member_select_predicate(
    migration_sql: str,
) -> None:
    """auth_audit_log_account_member_select policy の USING clause が
    auth.uid() = user_id であることを確認.
    user_id != auth.uid() の row は SELECT 不可 → 0 row return.
    """
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(AUDIT_SELECT_POLICY_NAME)}\s+"
        rf"ON\s+auth_audit_log.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, "missing auth_audit_log account_member_select block"
    body = block_match.group(0)
    assert re.search(
        r"USING\s*\(\s*auth\.uid\(\)\s*=\s*user_id\s*\)",
        body,
    ), (
        "auth_audit_log_account_member_select USING clause must be "
        "(auth.uid() = user_id) for AC-F3"
    )
    # FOR SELECT only — UPDATE/DELETE は service_role 経由のみ.
    assert re.search(
        r"FOR\s+SELECT\s+TO\s+authenticated",
        body,
        re.IGNORECASE,
    ), "auth_audit_log_account_member_select must be FOR SELECT only"


# ══════════════════════════════════════════════════════════════════════
# AC-F4 UNWANTED — verify-rls-coverage.py reports policy_count < 2 → fail
# ══════════════════════════════════════════════════════════════════════


def test_ac_f4_verify_rls_coverage_script_exists() -> None:
    assert VERIFY_RLS_SCRIPT.exists(), (
        f"missing gate script: {VERIFY_RLS_SCRIPT}"
    )


def test_ac_f4_verify_rls_coverage_passes() -> None:
    """verify-rls-coverage.py が exit 0 で完走することを CI で常時保証.

    全 target table が RLS enabled かつ少なくとも 2 policy 以上を持つことを
    aggregate 検証する. (本 migration で追加した 2 policy + 既存の self_* policy
    で各 table の policy_count は 4 以上になる)
    """
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
        f"unexpected RLS gap reported by verify-rls-coverage:\n{result.stdout}"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f4_per_table_canonical_policy_count_at_least_two(
    table: str,
) -> None:
    """各 target table が canonical 命名で >= 2 policy を持つことを静的検証.

    migration ファイル群を走査し、 各 table に対する CREATE POLICY の総数を
    数える. T-V3-D-06 migration で追加した 2 policy + 既存 (D-06 以前の)
    migration policy で合計 >= 2 になることを保証.
    """
    migrations_dir = REPO_ROOT / "supabase" / "migrations"
    count = 0
    for migration_file in sorted(migrations_dir.glob("*.sql")):
        text = migration_file.read_text(encoding="utf-8")
        for _ in re.finditer(
            rf"CREATE POLICY\s+[a-z_][a-z0-9_]*\s+ON\s+{re.escape(table)}\b",
            text,
        ):
            count += 1
    assert count >= 2, (
        f"{table}: total policy count across migrations = {count} < 2 "
        f"(AC-F4 violation)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F5 UNWANTED — encrypted_secrets.encrypted_value は non-service_role に
#                   直接公開されない. owner_only policy が owner_id scoped
#                   であることを静的に保証.
# ══════════════════════════════════════════════════════════════════════


def test_ac_f5_encrypted_secrets_owner_only_scoped_by_owner_id(
    migration_sql: str,
) -> None:
    """encrypted_secrets_owner_only policy が owner_id = auth.uid()::text で
    scoped されていることを確認 (non-owner には 0 row → encrypted_value 列の
    直接公開不可).
    """
    block_match = re.search(
        r"CREATE POLICY\s+encrypted_secrets_owner_only\s+ON\s+encrypted_secrets.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, "missing encrypted_secrets_owner_only block"
    body = block_match.group(0)
    assert re.search(
        r"USING\s*\(\s*owner_id\s*=\s*auth\.uid\(\)::text\s*\)",
        body,
    ), (
        "encrypted_secrets_owner_only USING clause must be "
        "(owner_id = auth.uid()::text) for AC-F5"
    )
    # public ロールへの開放を一切しない (defense in depth)
    assert not re.search(
        r"CREATE POLICY\s+encrypted_secrets_[a-z_]+\s+ON\s+encrypted_secrets"
        r"\s+FOR\s+\w+\s+TO\s+public\b",
        migration_sql,
        re.IGNORECASE,
    ), "encrypted_secrets policies must not open to public role"


def test_ac_f5_no_for_all_to_public_anywhere(migration_sql: str) -> None:
    """全 9 table で FOR ALL TO public が一切ないことを baseline 保証."""
    assert not re.search(
        r"FOR\s+ALL\s+TO\s+public\b",
        migration_sql,
        re.IGNORECASE,
    ), "no FOR ALL TO public allowed (security baseline)"


# ══════════════════════════════════════════════════════════════════════
# Security critical guardrails — 2FA secret / recovery codes
# (risk_flags: security_critical)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", sorted(SECURITY_CRITICAL_TABLES))
def test_security_critical_no_authenticated_select_for_others(
    migration_sql: str, table: str
) -> None:
    """2FA secret / recovery codes table に対する authenticated policy が
    必ず owner-scoped (auth.uid() = user_id) であり、 cross-user path を
    持たないことを確認.
    """
    # この migration で追加した owner_only policy のみが authenticated 向け.
    # 「FOR ALL TO authenticated USING (true)」 が無いことを保証.
    for_all_pattern = (
        rf"CREATE POLICY\s+[a-z_][a-z0-9_]*\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+ALL\s+TO\s+authenticated\s+USING\s*\(\s*true\s*\)"
    )
    assert not re.search(for_all_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: SECURITY CRITICAL — must not have authenticated USING (true)"
    )


# ══════════════════════════════════════════════════════════════════════
# Sanity / drift guards (inherits T-V3-D-05 invariants)
# ══════════════════════════════════════════════════════════════════════


def test_migration_records_schema_version(migration_sql: str) -> None:
    """schema_versions に 20260516160000 が記録されている (idempotent INSERT)."""
    assert "20260516160000" in migration_sql
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
