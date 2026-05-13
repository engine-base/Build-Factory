"""T-001-05: 実装・連携・運用 17 テーブル + Template DDL — 5 AC.

PR #59 で production artifact 完成済
(supabase/migrations/20260512000000_impl_integration_ops_tables.sql /
17 tables + companion runner_session_tables for chat_threads /
chat_messages).

AC マッピング:
  AC-1: 17 table CREATE / chat_threads+chat_messages 別 migration.
  AC-2: 全 CREATE TABLE/INDEX IF NOT EXISTS / schema_versions row.
  AC-3: api_keys (secret_scope, secret_key) NOT NULL / obsidian_vaults
        vault_path NOT NULL / red_line_violations FK / no public FOR ALL.
  AC-4: templates.template_kind 5 CHECK / backups.status 3 CHECK +
        backup_kind 4 CHECK.
  AC-5: api_keys NOT NULL / red_line_violations FK / no secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPL = REPO_ROOT / "supabase" / "migrations" / "20260512000000_impl_integration_ops_tables.sql"
RUNNER = REPO_ROOT / "supabase" / "migrations" / "20260510000003_runner_session_tables.sql"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"

IMPL_TABLES = (
    "session_artifacts", "prs", "pr_reviews",
    "red_lines", "red_line_violations",
    "llm_providers", "api_keys",
    "slack_webhooks", "github_repos", "obsidian_vaults",
    "notifications", "token_limits",
    "backups", "user_settings", "workspace_settings",
    "schema_versions", "templates",
)


@pytest.fixture(scope="module")
def sql():
    return IMPL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def runner_sql():
    return RUNNER.read_text(encoding="utf-8") if RUNNER.exists() else ""


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 17 + 2 (chat) tables
# ══════════════════════════════════════════════════════════════════════


def test_ac1_impl_migration_exists():
    assert IMPL.exists()


def test_ac1_runner_migration_exists_for_chat_tables():
    assert RUNNER.exists()


@pytest.mark.parametrize("table", IMPL_TABLES)
def test_ac1_impl_table_created(table, sql):
    assert re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\b",
        sql,
    ), f"missing CREATE TABLE {table}"


def test_ac1_chat_threads_in_runner_migration(runner_sql):
    assert re.search(
        r"CREATE TABLE IF NOT EXISTS\s+chat_threads\b",
        runner_sql,
    )


def test_ac1_chat_messages_in_runner_migration(runner_sql):
    assert re.search(
        r"CREATE TABLE IF NOT EXISTS\s+chat_messages\b",
        runner_sql,
    )


def test_ac1_exactly_17_impl_tables(sql):
    """impl_integration_ops_tables.sql に 17 CREATE TABLE (extra なし)."""
    count = len(re.findall(r"CREATE TABLE IF NOT EXISTS\s+\w+", sql))
    # 厳密一致 = 17
    assert count == 17, f"expected exactly 17 tables, got {count}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — idempotent + schema_versions row
# ══════════════════════════════════════════════════════════════════════


def test_ac2_all_create_table_idempotent(sql):
    no_if = re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)(\w+)", sql)
    assert not no_if, f"non-idempotent: {no_if}"


def test_ac2_all_create_index_idempotent(sql):
    no_if = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF NOT EXISTS)(\w+)",
        sql,
    )
    assert not no_if, f"non-idempotent indexes: {no_if}"


def test_ac2_schema_versions_table_created(sql):
    assert re.search(r"CREATE TABLE IF NOT EXISTS\s+schema_versions\b", sql)


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — api_keys / obsidian_vaults / red_line_violations
# ══════════════════════════════════════════════════════════════════════


def test_ac3_api_keys_uses_encrypted_secrets_reference(sql):
    """api_keys.secret_scope + secret_key NOT NULL (encrypted_secrets ref)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+api_keys\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m
    body = m.group(1)
    assert re.search(r"secret_scope\s+\w+[^,]*NOT\s+NULL", body, re.IGNORECASE)
    assert re.search(r"secret_key\s+\w+[^,]*NOT\s+NULL", body, re.IGNORECASE)


def test_ac3_obsidian_vault_path_not_null(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+obsidian_vaults\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert re.search(
        r"vault_path\s+TEXT\s+NOT\s+NULL",
        body,
        re.IGNORECASE,
    )


def test_ac3_red_line_violations_fk_cascade(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+red_line_violations\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    # red_line_id BIGINT NOT NULL REFERENCES red_lines(id) ON DELETE CASCADE
    assert re.search(
        r"red_line_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+red_lines\s*\(id\)\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    )


def test_ac3_no_public_for_all(sql):
    bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", sql, re.IGNORECASE)
    assert not bad, f"forbidden FOR ALL TO public: {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — templates 5 kind / backups 3 status + 4 kind
# ══════════════════════════════════════════════════════════════════════


def test_ac4_templates_template_kind_5_enum(sql):
    m = re.search(
        r"template_kind\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*template_kind\s+IN\s*\(([^)]+)\)",
        sql,
    )
    assert m
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"task", "pr", "mock", "prompt", "constitution"}
    assert values == expected, f"template_kind enum drift: {values}"


def test_ac4_backups_status_3_enum(sql):
    m = re.search(
        r"status\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'completed'\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)",
        sql,
    )
    assert m
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"completed", "failed", "in_progress"}
    assert values == expected, f"backups.status drift: {values}"


def test_ac4_backups_kind_4_enum(sql):
    m = re.search(
        r"backup_kind\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*backup_kind\s+IN\s*\(([^)]+)\)",
        sql,
    )
    assert m
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"db", "storage", "obsidian", "full"}
    assert values == expected, f"backup_kind drift: {values}"


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — NOT NULL / FK / no secret hardcoded
# ══════════════════════════════════════════════════════════════════════


def test_ac5_api_keys_provider_key_not_null(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+api_keys\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert re.search(r"provider_key\s+TEXT\s+NOT\s+NULL", body, re.IGNORECASE)


def test_ac5_red_line_violations_red_line_id_not_null(sql):
    """red_line_id が NOT NULL (FK 必須)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+red_line_violations\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert re.search(
        r"red_line_id\s+\w+\s+NOT\s+NULL\s+REFERENCES",
        body,
        re.IGNORECASE,
    )


def test_ac5_no_hardcoded_jwt():
    src = IMPL.read_text(encoding="utf-8")
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", src)


def test_ac5_no_hardcoded_supabase_or_anthropic():
    src = IMPL.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_05_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-05"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_05_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-05"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("20260512000000_impl_integration_ops_tables.sql" in f for f in files)
    assert any("runner_session_tables" in f for f in files)


def test_tickets_t_001_05_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-05"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "20260512000000_impl_integration_ops_tables.sql",
        "session_artifacts", "prs", "red_lines",
        "api_keys", "obsidian_vaults", "templates",
        "chat_threads", "chat_messages",
        "secret_scope", "secret_key",
        "template_kind", "backup_kind",
    ):
        assert sym in full, f"T-001-05 AC missing: {sym}"
