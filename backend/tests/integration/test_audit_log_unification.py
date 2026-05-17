"""T-V3-D-14 / ADR-018: AuditLog 二重実装統合 — static SQL invariant tests.

`supabase/migrations/20260516210000_audit_log_unification.sql` の不変条件を
SQL テキストレベルで検証する (実 DB 不要 / fresh checkout で実行可能).

検証範囲:

  AC-F1 UBIQUITOUS  : audit_logs.source 列が enum 6 値 CHECK 制約付きで追加
                      されている. 旧 auth_audit_log の row を audit_logs に
                      移行する INSERT INTO ... SELECT block が存在する.
  AC-F2 EVENT       : INSERT 文に created_at preservation (a.created_at) と
                      source='auth' 固定の両方が含まれる.
  AC-F3 EVENT       : CHECK 制約名 audit_logs_source_check が DROP IF EXISTS
                      → ADD CONSTRAINT で idempotent に宣言されている.
  AC-F4 UNWANTED    : auth_audit_log が CREATE OR REPLACE VIEW で
                      audit_logs WHERE source='auth' に routing される.
                      INSERT/UPDATE は VIEW 経由で不可 (rule なし).
  AC-R3 (verify-rls): audit_logs に canonical policy
                      `audit_logs_service_role_all` /
                      `audit_logs_account_member_select` が CREATE される.
  Idempotency       : ADD COLUMN IF NOT EXISTS / DROP CONSTRAINT IF EXISTS
                      / CREATE OR REPLACE VIEW / NOT EXISTS dedupe が宣言
                      されている.
  Python model      : AuditLogSource enum が CHECK 制約 6 値と完全一致.
  audit_service     : emit_audit_event / emit_auth_event が API として公開
                      されている (シグネチャの sanity).

実行:
    pytest backend/tests/integration/test_audit_log_unification.py -v
"""
from __future__ import annotations

import json
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
    / "20260516210000_audit_log_unification.sql"
)
ADR018_PATH = REPO_ROOT / "docs/decisions/ADR-018-audit-log-unification.md"
ENTITIES_PATH = REPO_ROOT / "docs/functional-breakdown/2026-05-16_v3/entities.json"
MODEL_PATH = REPO_ROOT / "backend/app/models/audit_log.py"
SERVICE_PATH = REPO_ROOT / "backend/services/audit_service.py"
VERIFY_RLS_SCRIPT = REPO_ROOT / "scripts" / "verify-rls-coverage.py"

EXPECTED_SOURCE_ENUM = (
    "generic",
    "auth",
    "workspace",
    "system",
    "cost",
    "red_line",
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    assert MIGRATION_PATH.exists(), f"{MIGRATION_PATH} not found"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def entities() -> list[dict]:
    assert ENTITIES_PATH.exists(), f"{ENTITIES_PATH} not found"
    data = json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))
    items = data.get("entities", data) if isinstance(data, dict) else data
    assert isinstance(items, list), "entities.json must contain a list"
    return items


# ════════════════════════════════════════════════════════════════════
# AC-F1 UBIQUITOUS — source 列 + CHECK 制約 + INSERT INTO ... SELECT
# ════════════════════════════════════════════════════════════════════


def test_ac_f1_source_column_added_idempotent(migration_sql: str) -> None:
    """AC-F1: ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'generic'."""
    pattern = re.compile(
        r"ALTER TABLE\s+audit_logs\s+ADD COLUMN IF NOT EXISTS\s+source\s+TEXT\s+NOT NULL\s+DEFAULT\s+'generic'",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "audit_logs.source must be added with ADD COLUMN IF NOT EXISTS "
        "(idempotent) and NOT NULL DEFAULT 'generic'"
    )


def test_ac_f1_check_constraint_enumerates_all_6_values(migration_sql: str) -> None:
    """AC-F1: CHECK 制約に 6 enum 値全てが含まれる."""
    pattern = re.compile(
        r"ADD CONSTRAINT\s+audit_logs_source_check\s+CHECK\s*\(\s*source\s+IN\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    m = pattern.search(migration_sql)
    assert m, "audit_logs_source_check CHECK constraint must be declared"
    in_list = m.group(1)
    for v in EXPECTED_SOURCE_ENUM:
        assert f"'{v}'" in in_list, (
            f"CHECK constraint must enumerate '{v}'; got: {in_list.strip()}"
        )


def test_ac_f1_data_migrate_block_present(migration_sql: str) -> None:
    """AC-F1: INSERT INTO audit_logs ... SELECT ... FROM auth_audit_log."""
    insert_pattern = re.compile(
        r"INSERT INTO\s+audit_logs\s*\([^)]*source[^)]*\)\s*SELECT[\s\S]+?FROM\s+auth_audit_log",
        re.IGNORECASE,
    )
    assert insert_pattern.search(migration_sql), (
        "migration must INSERT INTO audit_logs ... SELECT ... FROM auth_audit_log"
    )


def test_ac_f1_index_on_source_created(migration_sql: str) -> None:
    """AC-F1: source 列に index を作成 (source, created_at DESC)."""
    pattern = re.compile(
        r"CREATE INDEX IF NOT EXISTS\s+ix_audit_logs_source\s+ON\s+audit_logs\s*\(\s*source\s*,\s*created_at\s+DESC\s*\)",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "ix_audit_logs_source(source, created_at DESC) index must be created"
    )


# ════════════════════════════════════════════════════════════════════
# AC-F2 EVENT — created_at preserved + source='auth' on migrate
# ════════════════════════════════════════════════════════════════════


def test_ac_f2_insert_preserves_created_at(migration_sql: str) -> None:
    """AC-F2: INSERT SELECT 文で a.created_at を source 行と一緒に保持."""
    # source='auth' AS source の宣言と a.created_at AS created_at の宣言が同じ SELECT に
    pattern = re.compile(
        r"'auth'\s+AS\s+source[\s\S]+?a\.created_at\s+AS\s+created_at",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "data-migrate SELECT must yield source='auth' AND a.created_at AS created_at"
    )


def test_ac_f2_dedupe_via_legacy_id_in_payload(migration_sql: str) -> None:
    """AC-F2: payload->>'legacy_auth_audit_log_id' で重複排除する NOT EXISTS 句."""
    pattern = re.compile(
        r"NOT EXISTS\s*\([\s\S]*?audit_logs\s+al[\s\S]*?al\.source\s*=\s*'auth'[\s\S]*?al\.payload\s*->>\s*'legacy_auth_audit_log_id'\s*=\s*a\.id::text",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "NOT EXISTS dedupe must check al.source='auth' AND "
        "al.payload->>'legacy_auth_audit_log_id' = a.id::text"
    )


# ════════════════════════════════════════════════════════════════════
# AC-F3 EVENT — CHECK 制約が DROP IF EXISTS → ADD で idempotent
# ════════════════════════════════════════════════════════════════════


def test_ac_f3_check_constraint_idempotent_drop_then_add(migration_sql: str) -> None:
    """AC-F3: DROP CONSTRAINT IF EXISTS → ADD CONSTRAINT で idempotent."""
    drop_pattern = re.compile(
        r"ALTER TABLE\s+audit_logs\s+DROP CONSTRAINT IF EXISTS\s+audit_logs_source_check",
        re.IGNORECASE,
    )
    add_pattern = re.compile(
        r"ALTER TABLE\s+audit_logs\s+ADD CONSTRAINT\s+audit_logs_source_check\s+CHECK",
        re.IGNORECASE,
    )
    assert drop_pattern.search(migration_sql), "must DROP CONSTRAINT IF EXISTS first"
    assert add_pattern.search(migration_sql), "must ADD CONSTRAINT after drop"
    # 順序: drop が add より先に出る (idempotent 順序)
    drop_pos = drop_pattern.search(migration_sql).start()  # type: ignore[union-attr]
    add_pos = add_pattern.search(migration_sql).start()  # type: ignore[union-attr]
    assert drop_pos < add_pos, "DROP CONSTRAINT must precede ADD CONSTRAINT"


# ════════════════════════════════════════════════════════════════════
# AC-F4 UNWANTED — auth_audit_log → backward-compat VIEW
# ════════════════════════════════════════════════════════════════════


def test_ac_f4_view_replaces_table(migration_sql: str) -> None:
    """AC-F4: CREATE OR REPLACE VIEW auth_audit_log で SELECT routing."""
    pattern = re.compile(
        r"CREATE OR REPLACE VIEW\s+auth_audit_log[\s\S]+?FROM\s+audit_logs[\s\S]+?WHERE\s+al\.source\s*=\s*'auth'",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "auth_audit_log VIEW must be CREATE OR REPLACE selecting "
        "FROM audit_logs WHERE source='auth'"
    )


def test_ac_f4_view_has_security_barrier(migration_sql: str) -> None:
    """AC-F4: VIEW は security_barrier=true (RLS bypass 防止)."""
    pattern = re.compile(
        r"CREATE OR REPLACE VIEW\s+auth_audit_log[\s\S]{0,200}?security_barrier\s*=\s*true",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "auth_audit_log VIEW must declare WITH (security_barrier = true)"
    )


def test_ac_f4_old_table_renamed_to_archived_prefix(migration_sql: str) -> None:
    """AC-F4: 旧 table は _archived_auth_audit_log に rename (history 保全)."""
    pattern = re.compile(
        r"ALTER TABLE\s+auth_audit_log\s+RENAME TO\s+_archived_auth_audit_log",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "old auth_audit_log must be RENAMED TO _archived_auth_audit_log "
        "(history preserved, ADR-015 pattern)"
    )


def test_ac_f4_rename_guarded_by_relkind_check(migration_sql: str) -> None:
    """AC-F4: relkind = 'r' (table) のときのみ RENAME (idempotent)."""
    # DO $$ block 内に relkind = 'r' チェック
    pattern = re.compile(
        r"relkind\s*=\s*'r'",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "RENAME must be guarded by relkind='r' check (idempotent: skip if already view)"
    )


# ════════════════════════════════════════════════════════════════════
# AC-R3 (verify-rls) — canonical policies declared
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("policy_name", [
    "audit_logs_service_role_all",
    "audit_logs_account_member_select",
])
def test_ac_r3_canonical_policy_created(migration_sql: str, policy_name: str) -> None:
    """AC-R3: ticket access_policies_required の 2 canonical policy が CREATE される."""
    pattern = re.compile(
        rf"CREATE POLICY\s+{policy_name}\s+ON\s+audit_logs\b",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        f"canonical policy {policy_name} must be CREATE POLICY ON audit_logs"
    )


def test_ac_r3_service_role_all_is_for_all(migration_sql: str) -> None:
    """AC-R3: service_role policy は FOR ALL TO postgres, service_role."""
    pattern = re.compile(
        r"CREATE POLICY\s+audit_logs_service_role_all\s+ON\s+audit_logs\s+FOR\s+ALL\s+TO\s+postgres,\s*service_role",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "audit_logs_service_role_all must be FOR ALL TO postgres, service_role"
    )


def test_ac_r3_account_member_select_predicate(migration_sql: str) -> None:
    """AC-R3: account_member_select predicate = bf_can_access_workspace + NOT NULL."""
    pattern = re.compile(
        r"CREATE POLICY\s+audit_logs_account_member_select\s+ON\s+audit_logs\s+FOR\s+SELECT\s+TO\s+authenticated\s+USING\s*\(\s*workspace_id\s+IS\s+NOT\s+NULL\s+AND\s+bf_can_access_workspace\s*\(\s*workspace_id\s*\)\s*\)",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "audit_logs_account_member_select USING clause must be "
        "(workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id))"
    )


# ════════════════════════════════════════════════════════════════════
# Idempotency invariants
# ════════════════════════════════════════════════════════════════════


def test_idempotent_view_create_or_replace(migration_sql: str) -> None:
    """二度実行で view 再生成が安全 (CREATE OR REPLACE)."""
    pattern = re.compile(r"CREATE OR REPLACE VIEW\s+auth_audit_log", re.IGNORECASE)
    assert pattern.search(migration_sql)


def test_idempotent_no_unconditional_drop_table(migration_sql: str) -> None:
    """auth_audit_log を無条件 DROP TABLE しない (RENAME のみ)."""
    # DROP TABLE auth_audit_log があったら NG (実装は RENAME のみ)
    bad = re.compile(r"DROP\s+TABLE\s+(IF\s+EXISTS\s+)?auth_audit_log\b", re.IGNORECASE)
    assert not bad.search(migration_sql), (
        "must NOT DROP TABLE auth_audit_log unconditionally; "
        "data must migrate first (RENAME to _archived prefix only)"
    )


def test_idempotent_data_migrate_via_not_exists(migration_sql: str) -> None:
    """データ移行は NOT EXISTS dedupe で二度実行しても 0 row."""
    assert re.search(r"NOT EXISTS", migration_sql, re.IGNORECASE), (
        "data migrate must dedupe via NOT EXISTS for idempotency"
    )


# ════════════════════════════════════════════════════════════════════
# Python AuditLogSource enum integrity
# ════════════════════════════════════════════════════════════════════


def test_python_enum_matches_db_check_values() -> None:
    """AuditLogSource enum と DB CHECK 制約 enum 値の完全一致."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from backend.app.models.audit_log import AuditLogSource
    finally:
        sys.path.pop(0)
    py_values = set(AuditLogSource.values())
    db_values = set(EXPECTED_SOURCE_ENUM)
    assert py_values == db_values, (
        f"AuditLogSource enum ({py_values}) must equal DB CHECK enum ({db_values})"
    )


def test_audit_service_emit_apis_exposed() -> None:
    """audit_service が emit_audit_event / emit_auth_event を公開."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from backend.services import audit_service
    finally:
        sys.path.pop(0)
    assert hasattr(audit_service, "emit_audit_event"), "emit_audit_event must be exposed"
    assert hasattr(audit_service, "emit_auth_event"), "emit_auth_event must be exposed"
    assert hasattr(audit_service, "AuditServiceError"), "AuditServiceError must be exposed"


def test_audit_service_emit_auth_event_uses_enum() -> None:
    """emit_auth_event は内部で AuditLogSource.AUTH を使う (source 列の真実源)."""
    text = SERVICE_PATH.read_text(encoding="utf-8")
    assert "AuditLogSource.AUTH" in text, (
        "emit_auth_event must use AuditLogSource.AUTH (typed source) not string literal"
    )


# ════════════════════════════════════════════════════════════════════
# ADR / entities.json sanity
# ════════════════════════════════════════════════════════════════════


def test_adr018_file_exists_and_accepted() -> None:
    """ADR-018 が存在し Status: Accepted."""
    assert ADR018_PATH.exists(), f"{ADR018_PATH} not found"
    body = ADR018_PATH.read_text(encoding="utf-8")
    assert "**Status**: Accepted" in body, "ADR-018 must be Accepted"
    assert "audit_logs" in body and "auth_audit_log" in body
    assert "T-V3-D-14" in body


def test_entities_json_e037_marks_unified(entities: list[dict]) -> None:
    """entities.json E-037: legacy_drift_notes.diff_severity = resolved_by_adr_018."""
    e037 = next((e for e in entities if e.get("id") == "E-037"), None)
    assert e037 is not None, "E-037 AuditLog must exist in entities.json"
    notes = e037.get("legacy_drift_notes", {})
    assert notes.get("diff_severity") == "resolved_by_adr_018"
    assert notes.get("adr_ref") == "ADR-018"
    fields = {f.get("name") for f in e037.get("fields", [])}
    assert "source" in fields, "E-037 fields must include 'source' after T-V3-D-14"


def test_entities_json_e055_archived_as_view(entities: list[dict]) -> None:
    """entities.json E-055: status = archived_as_view (VIEW 化)."""
    e055 = next((e for e in entities if e.get("id") == "E-055"), None)
    assert e055 is not None, "E-055 AuthAuditLog must exist in entities.json"
    assert e055.get("status") == "archived_as_view"
    notes = e055.get("legacy_drift_notes", {})
    assert notes.get("diff_severity") == "resolved_by_adr_018"
    assert notes.get("adr_ref") == "ADR-018"
    assert notes.get("merged_into_entity", "").startswith("E-037")


# ════════════════════════════════════════════════════════════════════
# verify-rls-coverage smoke (script exit 0)
# ════════════════════════════════════════════════════════════════════


def test_verify_rls_coverage_passes() -> None:
    """AC-R3: scripts/verify-rls-coverage.py exit 0 (audit_logs に RLS あり)."""
    assert VERIFY_RLS_SCRIPT.exists(), f"{VERIFY_RLS_SCRIPT} not found"
    result = subprocess.run(
        [sys.executable, str(VERIFY_RLS_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"verify-rls-coverage failed: rc={result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ════════════════════════════════════════════════════════════════════
# schema_versions registration
# ════════════════════════════════════════════════════════════════════


def test_migration_registered_in_schema_versions(migration_sql: str) -> None:
    """migration は schema_versions に '20260516210000' / 'T-V3-D-14' を INSERT."""
    pattern = re.compile(
        r"INSERT INTO schema_versions[\s\S]+?'20260516210000'[\s\S]+?T-V3-D-14",
        re.IGNORECASE,
    )
    assert pattern.search(migration_sql), (
        "migration must INSERT INTO schema_versions with version 20260516210000 and T-V3-D-14"
    )
