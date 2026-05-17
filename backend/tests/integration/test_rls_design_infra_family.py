"""T-V3-D-08: RLS policy 補完 batch 4 — design & infrastructure family.

Verifies that the new migration
``supabase/migrations/20260516180000_rls_design_infra_family.sql`` adds the
required ``workspace_member_select`` policy (plus an idempotent
``service_role_all`` declaration) for 7 v3 entities
(E-062 / E-063 / E-064 / E-065 / E-066 / E-067 / E-068):

  - design_frames        (E-062)
  - design_canvas_state  (E-063)
  - design_mocks         (E-064)
  - approval_queue       (E-065)
  - checkpoints          (E-066) — scoped via chat_threads.id::text
  - schema_versions      (E-067) — service_role only (ops-internal)
  - knowledge_base       (E-068) — workspace_member overlay (account_scoped)

Test strategy is static SQL invariant inspection (no live DB) — same pattern
as ``backend/tests/integration/test_rls_ai_family.py`` (T-V3-D-05).  The
aggregate policy_count assertion is delegated to
``scripts/verify-rls-coverage.py`` (gate covered by AC-R2).

AC mapping (tickets-group-d-drift.json#T-V3-D-08):

  AC-F1 UBIQUITOUS : >= 2 policies per table (service_role_all + the
                     explicit workspace_member_select / service_role_select)
                     — direct static assertion.
  AC-F2 EVENT      : non-member auth user queries design_frames → 0 row.
                     We verify the policy `USING` clause restricts on
                     ``bf_can_access_workspace(workspace_id)`` for design_*
                     tables and on the chat_threads join for checkpoints,
                     which is the SQL mechanism that produces the 0-row
                     behaviour at runtime.
  AC-F3 EVENT      : service_role queries schema_versions → all rows.
                     We verify a ``FOR ALL TO postgres, service_role
                     USING (true)`` policy + the explicit
                     ``schema_versions_service_role_select`` exist.
  AC-F4 OPTIONAL   : knowledge_base.workspace_id IS NOT NULL row →
                     workspace_members 経由で SELECT 制限.  We verify the
                     policy body contains
                     ``workspace_id IS NOT NULL AND bf_can_access_workspace``.
  AC-F5 UNWANTED   : verify-rls-coverage.py reports policy_count < 2 →
                     regression gate fails.  We assert this script is
                     shipped + runs cleanly today.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
RLS_DESIGN_INFRA_MIGRATION = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260516180000_rls_design_infra_family.sql"
)
VERIFY_RLS_SCRIPT = REPO_ROOT / "scripts" / "verify-rls-coverage.py"

# 7 target tables (E-062〜E-068)
TARGET_TABLES = (
    "design_frames",
    "design_canvas_state",
    "design_mocks",
    "approval_queue",
    "checkpoints",
    "schema_versions",
    "knowledge_base",
)

# workspace_member_select policy を持つ table (= schema_versions 以外)
WORKSPACE_MEMBER_SELECT_TABLES = (
    "design_frames",
    "design_canvas_state",
    "design_mocks",
    "approval_queue",
    "checkpoints",
    "knowledge_base",
)

WORKSPACE_MEMBER_SELECT_POLICY_NAMES = {
    "design_frames": "design_frames_workspace_member_select",
    "design_canvas_state": "design_canvas_state_workspace_member_select",
    "design_mocks": "design_mocks_workspace_member_select",
    "approval_queue": "approval_queue_workspace_member_select",
    "checkpoints": "checkpoints_workspace_member_select",
    "knowledge_base": "knowledge_base_workspace_member_select",
}

SERVICE_ROLE_ALL_POLICY_NAMES = {
    "design_frames": "design_frames_service_role_all",
    "design_canvas_state": "design_canvas_state_service_role_all",
    "design_mocks": "design_mocks_service_role_all",
    "approval_queue": "approval_queue_service_role_all",
    "checkpoints": "checkpoints_service_role_all",
    "schema_versions": "schema_versions_service_role_all",
    "knowledge_base": "knowledge_base_service_role_all",
}

# schema_versions 専用: 2 個目の policy
SCHEMA_VERSIONS_SECONDARY_POLICY = "schema_versions_service_role_select"


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert RLS_DESIGN_INFRA_MIGRATION.exists(), (
        f"missing migration: {RLS_DESIGN_INFRA_MIGRATION}"
    )
    return RLS_DESIGN_INFRA_MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-F1 UBIQUITOUS — service_role + secondary policy per target table
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
    """service_role_all policy が宣言されている (FOR ALL TO postgres, service_role)."""
    policy_name = SERVICE_ROLE_ALL_POLICY_NAMES[table]
    assert f"CREATE POLICY {policy_name} ON {table}" in migration_sql, (
        f"{table}: missing CREATE POLICY {policy_name}"
    )
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}"
        rf"\s+FOR\s+ALL\s+TO\s+postgres,\s*service_role\s+USING\s*\(\s*true\s*\)"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        f"{table}: service_role_all policy must be "
        "FOR ALL TO postgres, service_role USING (true)"
    )


@pytest.mark.parametrize("table", WORKSPACE_MEMBER_SELECT_TABLES)
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
        f"{table}: workspace_member_select policy must be "
        "FOR SELECT TO authenticated"
    )


def test_ac_f1_schema_versions_has_secondary_policy(
    migration_sql: str,
) -> None:
    """schema_versions は AC-F1 (policy_count >= 2) のため
    service_role_select を二重宣言する.
    """
    assert (
        f"CREATE POLICY {SCHEMA_VERSIONS_SECONDARY_POLICY} ON schema_versions"
        in migration_sql
    ), (
        "schema_versions: missing secondary service_role_select policy "
        "(required to satisfy AC-F1 policy_count >= 2)"
    )
    fragment_pattern = (
        rf"CREATE POLICY\s+{re.escape(SCHEMA_VERSIONS_SECONDARY_POLICY)}"
        rf"\s+ON\s+schema_versions"
        rf"\s+FOR\s+SELECT\s+TO\s+postgres,\s*service_role"
    )
    assert re.search(fragment_pattern, migration_sql, re.IGNORECASE), (
        "schema_versions_service_role_select must be "
        "FOR SELECT TO postgres, service_role"
    )


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f1_policy_idempotent_drop_pair(
    migration_sql: str, table: str
) -> None:
    """各 policy に DROP POLICY IF EXISTS が前置されている (再 apply 安全)."""
    expected_policies: list[str] = [SERVICE_ROLE_ALL_POLICY_NAMES[table]]
    if table in WORKSPACE_MEMBER_SELECT_POLICY_NAMES:
        expected_policies.append(WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table])
    if table == "schema_versions":
        expected_policies.append(SCHEMA_VERSIONS_SECONDARY_POLICY)

    for policy_name in expected_policies:
        assert (
            f"DROP POLICY IF EXISTS {policy_name} ON {table}" in migration_sql
        ), (
            f"{table}: missing DROP POLICY IF EXISTS {policy_name} "
            f"(idempotency violation)"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-F2 EVENT-DRIVEN — non-member auth user → 0 row
#   For design_*/approval_queue tables: USING bf_can_access_workspace
#   For checkpoints: USING chat_threads join via thread_id
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "table",
    ("design_frames", "design_canvas_state", "design_mocks"),
)
def test_ac_f2_design_tables_use_bf_can_access_workspace(
    migration_sql: str, table: str
) -> None:
    """design_* tables の workspace_member_select は
    ``bf_can_access_workspace(workspace_id)`` で workspace_member を判定する.
    """
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES[table]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, (
        f"{table}: could not find CREATE POLICY {policy_name} block"
    )
    body = block_match.group(0)
    assert "bf_can_access_workspace(workspace_id)" in body, (
        f"{table}: workspace_member_select must filter via "
        "bf_can_access_workspace(workspace_id)"
    )


def test_ac_f2_approval_queue_requires_non_null_workspace_id(
    migration_sql: str,
) -> None:
    """approval_queue.workspace_id は NULL 可なので、 NULL row を漏らさないため
    `workspace_id IS NOT NULL AND bf_can_access_workspace(...)` を要求.
    """
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES["approval_queue"]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+approval_queue.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match
    body = block_match.group(0)
    assert "workspace_id IS NOT NULL" in body, (
        "approval_queue: must require workspace_id IS NOT NULL"
    )
    assert "bf_can_access_workspace(workspace_id)" in body


def test_ac_f2_checkpoints_scoped_via_chat_threads(
    migration_sql: str,
) -> None:
    """checkpoints は workspace_id 列を持たないため chat_threads.id::text 経由で
    workspace_member を判定する.  policy 本体に
    ``thread_id IN (SELECT id::text FROM chat_threads ... bf_can_access_workspace)``
    が含まれることを確認.
    """
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES["checkpoints"]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+checkpoints.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match
    body = block_match.group(0)
    assert "thread_id IN (" in body, (
        "checkpoints: must restrict thread_id via chat_threads subquery"
    )
    assert "FROM chat_threads" in body, (
        "checkpoints: must join chat_threads to resolve workspace_id"
    )
    assert "id::text" in body, (
        "checkpoints: thread_id is TEXT so chat_threads.id must be cast to text"
    )
    assert "bf_can_access_workspace(workspace_id)" in body, (
        "checkpoints: must call bf_can_access_workspace via chat_threads.workspace_id"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F3 EVENT-DRIVEN — service_role queries schema_versions → all rows
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", TARGET_TABLES)
def test_ac_f3_service_role_bypass_returns_all(
    migration_sql: str, table: str
) -> None:
    """service_role_all policy が USING (true) WITH CHECK (true) で全 row 返却.
    Postgres は service_role を含む POLICY ROLE list にマッチした場合
    USING(true) で行 filter を bypass する.
    """
    policy_name = SERVICE_ROLE_ALL_POLICY_NAMES[table]
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


def test_ac_f3_schema_versions_service_role_select_returns_all(
    migration_sql: str,
) -> None:
    """schema_versions の 2 個目 policy (service_role_select) も USING (true) で
    全 row 返却 (defense-in-depth).
    """
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(SCHEMA_VERSIONS_SECONDARY_POLICY)}"
        rf"\s+ON\s+schema_versions.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match
    body = block_match.group(0)
    assert re.search(r"USING\s*\(\s*true\s*\)", body), (
        "schema_versions_service_role_select must USING (true)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F4 OPTIONAL — knowledge_base workspace-scoped overlay
# ══════════════════════════════════════════════════════════════════════


def test_ac_f4_knowledge_base_workspace_scoped(
    migration_sql: str,
) -> None:
    """knowledge_base の workspace_member_select は
    ``workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id)`` を
    要求する (OPTIONAL AC-F4).
    """
    policy_name = WORKSPACE_MEMBER_SELECT_POLICY_NAMES["knowledge_base"]
    block_match = re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+knowledge_base.*?;",
        migration_sql,
        re.DOTALL,
    )
    assert block_match, (
        f"knowledge_base: missing CREATE POLICY {policy_name} block"
    )
    body = block_match.group(0)
    assert "workspace_id IS NOT NULL" in body, (
        "knowledge_base: OPTIONAL workspace-scoped overlay must require "
        "workspace_id IS NOT NULL"
    )
    assert "bf_can_access_workspace(workspace_id)" in body, (
        "knowledge_base: must call bf_can_access_workspace(workspace_id)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-F5 UNWANTED — verify-rls-coverage.py reports policy_count < 2 → fail
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
        f"unexpected RLS gap reported by verify-rls-coverage:\n{result.stdout}"
    )


def test_ac_f5_policy_count_at_least_two_per_table() -> None:
    """7 target tables の累積 CREATE POLICY 数が table ごとに 2 以上であること.
    verify-rls-coverage.py が policy_count check を未実装でも、 本 test で
    静的に保証する (drift fix の retro-active 検証).
    """
    migration_dir = REPO_ROOT / "supabase" / "migrations"
    counts: dict[str, int] = {table: 0 for table in TARGET_TABLES}
    for sql_path in sorted(migration_dir.glob("*.sql")):
        text = sql_path.read_text(encoding="utf-8")
        for table in TARGET_TABLES:
            # CREATE POLICY <name> ON <table>(\s|$)
            pattern = (
                rf"CREATE POLICY\s+[a-z_][a-z0-9_]*\s+ON\s+{re.escape(table)}\b"
            )
            counts[table] += len(re.findall(pattern, text, re.IGNORECASE))

    failures = [t for t, n in counts.items() if n < 2]
    assert not failures, (
        f"policy_count < 2 for tables: {failures} (actual counts: {counts})"
    )


# ══════════════════════════════════════════════════════════════════════
# Sanity / drift guards
# ══════════════════════════════════════════════════════════════════════


def test_migration_records_schema_version(migration_sql: str) -> None:
    """schema_versions に 20260516180000 が記録されている (idempotent INSERT)."""
    assert "20260516180000" in migration_sql
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


def test_schema_versions_has_no_authenticated_select(
    migration_sql: str,
) -> None:
    """schema_versions は ops-internal table のため authenticated 向け SELECT を
    作らない (security baseline).
    """
    schema_versions_blocks = re.findall(
        r"CREATE POLICY\s+[a-z_][a-z0-9_]*\s+ON\s+schema_versions[^;]*;",
        migration_sql,
        re.DOTALL,
    )
    for block in schema_versions_blocks:
        assert "TO authenticated" not in block, (
            "schema_versions must not expose any authenticated policy: "
            f"{block.splitlines()[0]}"
        )
