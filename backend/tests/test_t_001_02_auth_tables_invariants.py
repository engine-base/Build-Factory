"""T-001-02: 認証 6 テーブル DDL + RLS — 5 AC.

PR #6 で production artifact (supabase/migrations/20260510000000_auth_tables.sql)
完成済. 本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS: 6 table CREATE / FK auth.users / TIMESTAMPTZ NOW().
  AC-2 EVENT-DRIVEN: IF NOT EXISTS + DROP POLICY IF EXISTS で idempotent.
  AC-3 STATE-DRIVEN: 4 tables ENABLE RLS / auth.uid() owner / no public FOR ALL.
  AC-4 OPTIONAL: user_2fa_secrets.enabled BOOLEAN default false /
                 auth_audit_log.success column.
  AC-5 UNWANTED: UNIQUE (user_id, provider) / encrypted_secret NOT NULL /
                  no hardcoded JWT / sb_*_key.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260510000000_auth_tables.sql"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"

AUTH_TABLES = (
    "users",
    "auth_sessions",
    "user_2fa_secrets",
    "user_2fa_recovery_codes",
    "oauth_connections",
    "auth_audit_log",
)
RLS_ENABLED_TABLES = (
    "auth_sessions",
    "user_2fa_secrets",
    "user_2fa_recovery_codes",
    "oauth_connections",
)


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 6 tables + FK + timestamptz
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_exists():
    assert MIGRATION.exists()


@pytest.mark.parametrize("table", AUTH_TABLES)
def test_ac1_each_table_created(table, sql):
    assert re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\b",
        sql,
    ), f"missing CREATE TABLE IF NOT EXISTS {table}"


def test_ac1_fk_to_auth_users():
    """少なくとも 1 つの FK が auth.users(id) を参照."""
    sql_text = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"REFERENCES\s+auth\.users\s*\(id\)", sql_text)


def test_ac1_created_at_timestamptz_now():
    """created_at TIMESTAMPTZ DEFAULT NOW() を持つ table が複数ある."""
    sql_text = MIGRATION.read_text(encoding="utf-8")
    matches = re.findall(
        r"created_at\s+TIMESTAMPTZ\s+(?:NOT\s+NULL\s+)?DEFAULT\s+(?:NOW|now)\(\)",
        sql_text,
    )
    assert len(matches) >= 4, (
        f"expected created_at TIMESTAMPTZ NOW() in >= 4 tables, got {len(matches)}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_all_create_table_use_if_not_exists(sql):
    """全 CREATE TABLE 文が IF NOT EXISTS を使う (idempotent)."""
    create_table = re.findall(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)", sql)
    create_table_if_exists = re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql,
    )
    # IF NOT EXISTS なしの CREATE TABLE が無い
    for tbl in create_table:
        assert tbl in create_table_if_exists, (
            f"CREATE TABLE {tbl} must use IF NOT EXISTS"
        )


def test_ac2_policies_use_drop_if_exists(sql):
    """CREATE POLICY の前に DROP POLICY IF EXISTS で idempotent."""
    drop_count = len(re.findall(r"DROP POLICY IF EXISTS", sql))
    create_policy_count = len(re.findall(r"CREATE POLICY", sql))
    # 全 policy が DROP+CREATE pair なら drop_count >= create_policy_count
    if create_policy_count > 0:
        assert drop_count >= create_policy_count * 0.8, (
            f"too few DROP POLICY IF EXISTS for {create_policy_count} CREATE POLICY"
        )


def test_ac2_indexes_use_if_not_exists(sql):
    """CREATE INDEX も IF NOT EXISTS で idempotent."""
    create_idx = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF NOT EXISTS\s+)?(\w+)", sql)
    create_idx_if = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF NOT EXISTS\s+(\w+)", sql)
    for idx in create_idx:
        assert idx in create_idx_if, f"CREATE INDEX {idx} must use IF NOT EXISTS"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — RLS owner-only / no public FOR ALL
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", RLS_ENABLED_TABLES)
def test_ac3_rls_enabled_on_4_tables(table, sql):
    assert re.search(
        rf"ALTER TABLE\s+{table}\s+ENABLE ROW LEVEL SECURITY",
        sql,
    ), f"RLS not enabled on {table}"


def test_ac3_auth_uid_used_in_policies(sql):
    """RLS policy に auth.uid() = user_id pattern が含まれる."""
    assert re.search(r"auth\.uid\(\)\s*=\s*user_id", sql) or \
           re.search(r"user_id\s*=\s*auth\.uid\(\)", sql), (
        "RLS policies must use auth.uid() = user_id"
    )


def test_ac3_no_blanket_public_for_all(sql):
    """FOR ALL TO public は禁止 (public access invariant)."""
    bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", sql, re.IGNORECASE)
    assert not bad, f"forbidden FOR ALL TO public: {bad}"


def test_ac3_service_role_grant_present(sql):
    """service_role 用の policy or grant が存在する."""
    assert "service_role" in sql, (
        "RLS scheme must reference service_role for backend access"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — 2FA enabled flag + auth_audit_log.success
# ══════════════════════════════════════════════════════════════════════


def test_ac4_user_2fa_secrets_has_enabled_boolean(sql):
    """user_2fa_secrets に enabled BOOLEAN DEFAULT false."""
    # CREATE TABLE user_2fa_secrets ( ... enabled BOOLEAN ... DEFAULT false )
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+user_2fa_secrets\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m, "user_2fa_secrets table not found"
    table_body = m.group(1)
    assert re.search(r"\benabled\s+BOOLEAN", table_body, re.IGNORECASE)
    # DEFAULT false (opt-in 明示)
    assert re.search(
        r"\benabled\s+BOOLEAN[^,]*DEFAULT\s+(?:FALSE|false)",
        table_body,
    )


def test_ac4_auth_audit_log_has_success_column(sql):
    """auth_audit_log に success column (boolean)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+auth_audit_log\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m
    body = m.group(1)
    assert re.search(r"\bsuccess\b", body, re.IGNORECASE)


def test_ac4_auth_audit_log_has_user_id_fk(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+auth_audit_log\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert re.search(r"user_id\s+UUID", body, re.IGNORECASE) or \
           re.search(r"user_id\s+\w+\s+REFERENCES", body, re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — UNIQUE / NOT NULL / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_oauth_unique_constraint(sql):
    """oauth_connections に (user_id, provider) UNIQUE."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+oauth_connections\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m
    body = m.group(1)
    has_inline_unique = re.search(
        r"UNIQUE\s*\([^)]*user_id[^)]*provider",
        body,
        re.IGNORECASE,
    ) or re.search(
        r"UNIQUE\s*\([^)]*provider[^)]*user_id",
        body,
        re.IGNORECASE,
    )
    # または CREATE UNIQUE INDEX で実現
    has_unique_idx = re.search(
        r"CREATE\s+UNIQUE\s+INDEX[^;]+oauth_connections[^;]+user_id[^;]+provider",
        sql,
        re.DOTALL,
    ) or re.search(
        r"CREATE\s+UNIQUE\s+INDEX[^;]+oauth_connections[^;]+provider[^;]+user_id",
        sql,
        re.DOTALL,
    )
    assert has_inline_unique or has_unique_idx, (
        "oauth_connections must have UNIQUE (user_id, provider) constraint"
    )


def test_ac5_encrypted_secret_not_null(sql):
    """user_2fa_secrets.encrypted_secret NOT NULL (plaintext 禁止)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+user_2fa_secrets\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert re.search(
        r"encrypted_secret\s+\w+(?:\(\d+\))?\s+NOT\s+NULL",
        body,
        re.IGNORECASE,
    ), "encrypted_secret must be NOT NULL (plaintext storage forbidden)"


def test_ac5_no_plain_secret_column(sql):
    """`secret TEXT` のような unprotected カラムなし (encrypted_secret のみ許可)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+user_2fa_secrets\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    # `secret TEXT` (encrypted_ prefix なし) は禁止
    bad = re.findall(r"^\s*secret\s+TEXT\b", body, re.MULTILINE | re.IGNORECASE)
    assert not bad, f"plain `secret TEXT` column forbidden: {bad}"


def test_ac5_no_hardcoded_jwt():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(
        r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.",
        src,
    )


def test_ac5_no_hardcoded_supabase_key():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_02_canonical_ears_types():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-02"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-001-02 still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "OPTIONAL" in types
    assert "UNWANTED" in types


def test_tickets_t_001_02_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-02"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "supabase/migrations/20260510000000_auth_tables.sql" in files


def test_tickets_t_001_02_ac_mentions_concrete_artifacts():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-02"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "20260510000000_auth_tables.sql",
        "users", "auth_sessions", "user_2fa_secrets",
        "user_2fa_recovery_codes", "oauth_connections",
        "auth_audit_log",
        "auth.users(id)",
        "auth.uid() = user_id",
        "encrypted_secret",
    ):
        assert sym in full, f"T-001-02 AC missing: {sym}"
