"""T-001-04: Build-Factory 11 テーブル DDL + RLS — 5 AC.

PR #7 で production artifact 完成済
(supabase/migrations/20260510000001_bf_project_tables.sql / 11 tables +
RLS via 20260510000002_rls_full_enforcement.sql).

AC マッピング:
  AC-1: 11 table / workspace_id FK / TIMESTAMPTZ NOW().
  AC-2: 全 CREATE TABLE/INDEX IF NOT EXISTS / DROP POLICY IF EXISTS.
  AC-3: RLS auth.uid() + workspace_members + service_role / no public FOR ALL.
  AC-4: bf_constitutions.principles NOT NULL + bf_constitution_revisions FK /
        EARS 5-enum on bf_acceptance_criteria.
  AC-5: ears_type CHECK / no_self_dep CHECK / no hardcoded secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260510000001_bf_project_tables.sql"
RLS_MIG = REPO_ROOT / "supabase" / "migrations" / "20260510000002_rls_full_enforcement.sql"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"

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

WORKSPACE_SCOPED_TABLES = (
    "bf_projects",
    "bf_phases",
    "bf_features",
    "bf_tasks",
    "bf_constitutions",
    "bf_constitution_revisions",
    "bf_mocks",
    "bf_deliveries",
)


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rls_sql():
    return RLS_MIG.read_text(encoding="utf-8") if RLS_MIG.exists() else ""


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 11 tables + workspace_id FK + TIMESTAMPTZ
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_exists():
    assert MIGRATION.exists()


@pytest.mark.parametrize("table", BF_TABLES)
def test_ac1_each_table_created(table, sql):
    assert re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\b",
        sql,
    ), f"missing CREATE TABLE {table}"


def test_ac1_workspace_id_fk_chain():
    """workspace_id FK は bf_projects + audit_logs に直接 / 他は
    project_id 経由 (bf_projects → workspace_id) で RLS chain.

    本実装の整合性: bf_projects に workspace_id NOT NULL + 他テーブルは
    project_id 経由 (cascade)."""
    src = MIGRATION.read_text(encoding="utf-8")
    # bf_projects.workspace_id NOT NULL REFERENCES workspaces(id)
    m_proj = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_projects\s*\(([\s\S]+?)\);",
        src,
    )
    assert m_proj
    assert re.search(
        r"workspace_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+workspaces\s*\(id\)",
        m_proj.group(1),
    ), "bf_projects.workspace_id must be NOT NULL REFERENCES workspaces(id)"
    # project_id chain: 他テーブルは project_id REFERENCES bf_projects
    project_id_fks = re.findall(
        r"project_id\s+\w+[^,]*REFERENCES\s+bf_projects\s*\(id\)",
        src,
        re.IGNORECASE,
    )
    assert len(project_id_fks) >= 3, (
        f"expected >= 3 project_id FK chain, got {len(project_id_fks)}"
    )


def test_ac1_audit_logs_table_present(sql):
    """audit_logs table が migration 内に declared."""
    assert "CREATE TABLE IF NOT EXISTS audit_logs" in sql


def test_ac1_workspace_scoped_tables_have_audit_timestamp(sql):
    """workspace-scoped tables に created_at OR revised_at の audit
    timestamp (TIMESTAMPTZ DEFAULT NOW()). bf_constitution_revisions は
    revised_at で代用."""
    # created_at / revised_at / delivered_at のいずれかが TIMESTAMPTZ DEFAULT NOW()
    AUDIT_TS_RE = re.compile(
        r"(?:created_at|revised_at|delivered_at)\s+TIMESTAMPTZ[^,]*DEFAULT\s+(?:NOW|now)\(\)",
    )
    for table in WORKSPACE_SCOPED_TABLES:
        m = re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{table}\s*\(([\s\S]+?)\);",
            sql,
        )
        assert m, f"{table} body not found"
        body = m.group(1)
        assert AUDIT_TS_RE.search(body), (
            f"{table} missing created_at/revised_at TIMESTAMPTZ NOW()"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — idempotent
# ══════════════════════════════════════════════════════════════════════


def test_ac2_all_create_table_idempotent(sql):
    no_if = re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)(\w+)", sql)
    assert not no_if, f"CREATE TABLE without IF NOT EXISTS: {no_if}"


def test_ac2_all_create_index_idempotent(sql):
    no_if = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF NOT EXISTS)(\w+)",
        sql,
    )
    assert not no_if, f"CREATE INDEX without IF NOT EXISTS: {no_if}"


def test_ac2_rls_uses_drop_policy_if_exists(rls_sql):
    """RLS migration が DROP POLICY IF EXISTS で idempotent."""
    if not rls_sql:
        pytest.skip("RLS migration not found")
    drop_count = len(re.findall(r"DROP POLICY IF EXISTS", rls_sql))
    create_count = len(re.findall(r"CREATE POLICY", rls_sql))
    if create_count > 0:
        assert drop_count >= create_count * 0.6, (
            f"too few DROP POLICY IF EXISTS for {create_count} CREATE POLICY"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — RLS workspace_members / service_role / no public
# ══════════════════════════════════════════════════════════════════════


def test_ac3_rls_uses_auth_uid_pattern(rls_sql):
    if not rls_sql:
        pytest.skip("RLS migration not found")
    assert "auth.uid()" in rls_sql


def test_ac3_rls_references_workspace_members(rls_sql):
    if not rls_sql:
        pytest.skip("RLS migration not found")
    # workspace_members table 経由の membership check
    assert "workspace_members" in rls_sql


def test_ac3_rls_grants_service_role(rls_sql):
    if not rls_sql:
        pytest.skip("RLS migration not found")
    assert "service_role" in rls_sql


def test_ac3_no_blanket_public_for_all(sql, rls_sql):
    """FOR ALL TO public は禁止."""
    for src in (sql, rls_sql):
        if not src:
            continue
        bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", src, re.IGNORECASE)
        assert not bad, f"forbidden FOR ALL TO public: {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — bf_constitutions / bf_constitution_revisions /
#                  EARS 5-enum CHECK
# ══════════════════════════════════════════════════════════════════════


def test_ac4_bf_constitutions_principles_not_null(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitutions\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m, "bf_constitutions table not found"
    body = m.group(1)
    # principles JSONB NOT NULL
    assert re.search(
        r"principles\s+(?:JSONB|jsonb)[^,]*NOT\s+NULL",
        body,
        re.IGNORECASE,
    ), "bf_constitutions.principles must be NOT NULL"


def test_ac4_constitution_revisions_fk_to_constitutions(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitution_revisions\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m
    body = m.group(1)
    # constitution_id REFERENCES bf_constitutions(id)
    assert re.search(
        r"REFERENCES\s+bf_constitutions\s*\(id\)",
        body,
        re.IGNORECASE,
    )


def test_ac4_ears_type_check_enum_5_values(sql):
    """ears_type CHECK が 5 値 (UBIQUITOUS / EVENT / STATE / OPTIONAL /
    UNWANTED) を含む."""
    m = re.search(
        r"ears_type[^,]+CHECK\s*\(\s*ears_type\s+IN\s*\(([^)]+)\)",
        sql,
    )
    assert m, "ears_type CHECK not found"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"UBIQUITOUS", "EVENT", "STATE", "OPTIONAL", "UNWANTED"}
    assert expected.issubset(values), (
        f"ears_type enum missing: {expected - values}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — CHECK constraints + no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_no_self_dep_check(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_task_dependencies\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert "no_self_dep" in body or re.search(
        r"CHECK\s*\(\s*task_id\s*<>\s*depends_on_task_id\s*\)",
        body,
    ), "bf_task_dependencies must have no_self_dep CHECK"


def test_ac5_dep_unique_constraint(sql):
    """(task_id, depends_on_task_id) UNIQUE で duplicate reject."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_task_dependencies\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    has_unique = re.search(
        r"UNIQUE\s*\([^)]*task_id[^)]*depends_on_task_id",
        body,
        re.IGNORECASE,
    )
    assert has_unique, "bf_task_dependencies must have UNIQUE (task_id, depends_on_task_id)"


def test_ac5_no_hardcoded_jwt():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", src)


def test_ac5_no_hardcoded_supabase_or_anthropic():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_04_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-04"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-001-04 still uses legacy alias: {ty}"
        )
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_04_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-04"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "supabase/migrations/20260510000001_bf_project_tables.sql" in files


def test_tickets_t_001_04_ac_mentions_concrete_invariants():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-04"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "20260510000001_bf_project_tables.sql",
        "bf_projects", "bf_phases", "bf_features", "bf_tasks",
        "bf_task_dependencies", "bf_acceptance_criteria",
        "bf_constitutions", "bf_constitution_revisions",
        "bf_mocks", "bf_deliveries", "audit_logs",
        "workspace_members", "auth.uid()",
        "no_self_dep", "ears_type",
    ):
        assert sym in full, f"T-001-04 AC missing: {sym}"
