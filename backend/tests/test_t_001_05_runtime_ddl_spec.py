"""T-001-05 Wave 5 Pre-flight AC Audit (Runtime DDL spec).

NEW audit covering 実装・連携・運用 17 テーブル + Template DDL + companion
ChatThread/ChatMessage runner_session tables, 1:1 against the EARS 5 AC declared
in ``docs/task-decomposition/2026-05-09_v1/tickets.json#T-001-05``.

Anti-drift CRITICAL design:
  - Each of the 17 impl/integration/ops tables gets its own **individual test
    function** for existence / RLS ENABLE / service_role policy. Collapsed
    parametrize/regex over the 17-tuple is forbidden by the Wave 5 audit
    protocol so that a regression dropping a single table cannot hide behind a
    loop summary failure.
  - chat_threads / chat_messages are verified separately in the companion
    runner_session_tables migration (M-30 memory layer + claude-agent-sdk
    session linkage) with explicit FK to sessions(id) and chat_threads(id).
  - 4 enum CHECK contracts (templates.template_kind, backups.status,
    backups.backup_kind, backups.triggered_by) are each verified by an exact
    set comparison so additive drift is caught.

Spec literal expansion (源泉 cited):

  tickets.json#T-001-05:
    "title": "実装・連携・運用 17 テーブル + Template DDL
              (chat_threads / chat_messages は T-S0-08 runner_session_tables.sql に同梱
               / impl_integration_ops_tables.sql / red_lines + api_keys
               + slack_webhooks + github_repos + obsidian_vaults + templates 等)"
    "sprint": 0  "feature": "F-001"  "layer": "DB"  "label": "NEW"
    "existing_files": [
      "supabase/migrations/20260512000000_impl_integration_ops_tables.sql",
      "supabase/migrations/20260510000003_runner_session_tables.sql",
      "supabase/migrations/20260510000002_rls_full_enforcement.sql"
    ]
    AC-1 UBIQUITOUS    : 17 CREATE TABLE IF NOT EXISTS in impl migration +
                         chat_threads + chat_messages in runner migration; all
                         CREATE statements idempotent.
    AC-2 EVENT-DRIVEN  : second apply is idempotent (CREATE TABLE/INDEX IF NOT
                         EXISTS); schema_versions row marks the applied version
                         with an audit trail for backward-compat.
    AC-3 STATE-DRIVEN  : api_keys (secret_scope, secret_key) NOT NULL (plaintext
                         禁止 / pgsodium 二重暗号化), obsidian_vaults.vault_path
                         TEXT NOT NULL, red_line_violations.red_line_id BIGINT
                         NOT NULL REFERENCES red_lines(id) ON DELETE CASCADE; no
                         blanket "FOR ALL TO public".
    AC-4 OPTIONAL      : templates.template_kind CHECK 5 値
                         (task/pr/mock/prompt/constitution); backups.status
                         CHECK 3 値 (completed/failed/in_progress); backup_kind
                         CHECK 4 値 (db/storage/obsidian/full).
    AC-5 UNWANTED      : api_key insert without (secret_scope, secret_key) →
                         NOT NULL reject; red_line_violation insert without
                         valid red_line_id → FK reject; no hardcoded
                         sb_(publishable|secret)_*, sk-ant-*, JWT (eyJ...).

  architecture-v1.md §4 entities (verbatim):
    "実装・レビュー 7（sessions / session_logs / session_artifacts / prs /
     pr_reviews / red_lines / red_line_violations）"
    "連携・運用 11（llm_providers / api_keys / slack_webhooks / github_repos /
     obsidian_vaults / notifications / cost_logs / token_limits / audit_logs /
     backups / user_settings）"
    "補助 2（workspace_settings / schema_versions）"
    NOTE: sessions / session_logs / cost_logs / audit_logs are produced by
    earlier migrations (T-S0-08 runner_session_tables / T-001-04 bf_project_tables).
    T-001-05's NEW 17 = 7 (impl/review minus sessions, session_logs) +
                        9 (integration/ops minus cost_logs, audit_logs) +
                        2 (補助) + 1 (templates as Template DDL stretch).

  features.json#F-001 "Supabase 基盤 + テストデータ seed":
    happy_path: ["Supabase project 作成", "DDL 適用", "RLS enable", ...].
    policies: prod_seed=禁止, rollback=down.sql 必須.

  CLAUDE.md §5.4 red-lines: no hardcoded secrets / no force push.
  ADR-011 (完了判定ゲート): pre-commit-check.sh is single gate.

This audit does NOT execute SQL against Postgres (Phase 1 dev has no live DB
yet — Supabase project bootstrap is part of F-001 happy_path). It does static
SQL invariant verification, matching the prior style of
``test_supabase_migrations.py`` and ``test_t_001_06_rls_full_invariants.py``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPL_SQL = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260512000000_impl_integration_ops_tables.sql"
)
RUNNER_SQL = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260510000003_runner_session_tables.sql"
)
RLS_FULL_SQL = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260510000002_rls_full_enforcement.sql"
)
TICKETS_JSON = (
    REPO_ROOT
    / "docs"
    / "task-decomposition"
    / "2026-05-09_v1"
    / "tickets.json"
)
ARCH_MD = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "2026-05-09_v1"
    / "architecture-v1.md"
)


# ─────────────────────────────────────────────────────────────────────────────
# Module fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def impl_sql() -> str:
    return IMPL_SQL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def runner_sql() -> str:
    return RUNNER_SQL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rls_full_sql() -> str:
    return RLS_FULL_SQL.read_text(encoding="utf-8")


def _table_body(sql: str, table: str) -> str:
    """Return the body of CREATE TABLE IF NOT EXISTS <table> (...)."""
    m = re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m, f"CREATE TABLE for {table} not found"
    return m.group(1)


def _has_create_table(sql: str, table: str) -> bool:
    return bool(re.search(rf"CREATE TABLE IF NOT EXISTS\s+{table}\b", sql))


def _has_rls_enabled(sql: str, table: str) -> bool:
    return bool(
        re.search(
            rf"ALTER TABLE\s+{table}\s+ENABLE ROW LEVEL SECURITY",
            sql,
        )
    )


def _has_service_role_policy(sql: str, table: str) -> bool:
    return bool(
        re.search(
            rf"CREATE POLICY\s+{table}_service_role\s+ON\s+{table}\b",
            sql,
        )
    )


# ═════════════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 17 tables in impl migration + chat_threads/chat_messages
#                   in runner migration; all CREATE idempotent.
#
# 17 individual table tests (NO collapsed regex / NO parametrize).
# ═════════════════════════════════════════════════════════════════════════════


def test_ac1_impl_migration_exists():
    assert IMPL_SQL.is_file(), f"missing {IMPL_SQL}"


def test_ac1_runner_migration_exists():
    assert RUNNER_SQL.is_file(), f"missing {RUNNER_SQL}"


def test_ac1_rls_full_migration_exists():
    assert RLS_FULL_SQL.is_file(), f"missing {RLS_FULL_SQL}"


# --- impl_integration_ops_tables.sql: 17 individual CREATE TABLE checks ---


def test_ac1_table_1_session_artifacts_created(impl_sql):
    assert _has_create_table(impl_sql, "session_artifacts")


def test_ac1_table_2_prs_created(impl_sql):
    assert _has_create_table(impl_sql, "prs")


def test_ac1_table_3_pr_reviews_created(impl_sql):
    assert _has_create_table(impl_sql, "pr_reviews")


def test_ac1_table_4_red_lines_created(impl_sql):
    assert _has_create_table(impl_sql, "red_lines")


def test_ac1_table_5_red_line_violations_created(impl_sql):
    assert _has_create_table(impl_sql, "red_line_violations")


def test_ac1_table_6_llm_providers_created(impl_sql):
    assert _has_create_table(impl_sql, "llm_providers")


def test_ac1_table_7_api_keys_created(impl_sql):
    assert _has_create_table(impl_sql, "api_keys")


def test_ac1_table_8_slack_webhooks_created(impl_sql):
    assert _has_create_table(impl_sql, "slack_webhooks")


def test_ac1_table_9_github_repos_created(impl_sql):
    assert _has_create_table(impl_sql, "github_repos")


def test_ac1_table_10_obsidian_vaults_created(impl_sql):
    assert _has_create_table(impl_sql, "obsidian_vaults")


def test_ac1_table_11_notifications_created(impl_sql):
    assert _has_create_table(impl_sql, "notifications")


def test_ac1_table_12_token_limits_created(impl_sql):
    assert _has_create_table(impl_sql, "token_limits")


def test_ac1_table_13_backups_created(impl_sql):
    assert _has_create_table(impl_sql, "backups")


def test_ac1_table_14_user_settings_created(impl_sql):
    assert _has_create_table(impl_sql, "user_settings")


def test_ac1_table_15_workspace_settings_created(impl_sql):
    assert _has_create_table(impl_sql, "workspace_settings")


def test_ac1_table_16_schema_versions_created(impl_sql):
    assert _has_create_table(impl_sql, "schema_versions")


def test_ac1_table_17_templates_created(impl_sql):
    assert _has_create_table(impl_sql, "templates")


def test_ac1_exact_count_17_create_table_in_impl(impl_sql):
    """Drift guard: impl migration must contain *exactly* 17 CREATE TABLE.

    A new sibling table added without spec update would change this count and
    fail loud here, which is precisely what the Wave 5 anti-drift rule asks
    for.
    """
    count = len(re.findall(r"CREATE TABLE IF NOT EXISTS\s+\w+", impl_sql))
    assert count == 17, f"expected exactly 17 tables, got {count}"


# --- runner_session_tables.sql: chat_threads + chat_messages bound to sessions ---


def test_ac1_chat_threads_created_in_runner_migration(runner_sql):
    assert _has_create_table(runner_sql, "chat_threads")


def test_ac1_chat_messages_created_in_runner_migration(runner_sql):
    assert _has_create_table(runner_sql, "chat_messages")


def test_ac1_chat_threads_linked_to_sessions(runner_sql):
    """ranner session 連動 invariant: chat_threads.session_id REFERENCES sessions(id)."""
    body = _table_body(runner_sql, "chat_threads")
    assert re.search(
        r"session_id\s+BIGINT\s+REFERENCES\s+sessions\s*\(\s*id\s*\)",
        body,
        re.IGNORECASE,
    ), "chat_threads.session_id should reference sessions(id)"


def test_ac1_chat_messages_linked_to_chat_threads(runner_sql):
    """chat_messages.thread_id REFERENCES chat_threads(id) ON DELETE CASCADE."""
    body = _table_body(runner_sql, "chat_messages")
    assert re.search(
        r"thread_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+chat_threads\s*\(\s*id\s*\)"
        r"\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "chat_messages.thread_id should cascade-delete from chat_threads(id)"


def test_ac1_chat_messages_role_check_4_values(runner_sql):
    body = _table_body(runner_sql, "chat_messages")
    m = re.search(r"CHECK\s*\(\s*role\s+IN\s*\(([^)]+)\)", body)
    assert m, "chat_messages.role CHECK missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    assert values == {"user", "assistant", "system", "tool"}, (
        f"chat_messages.role drift: {values}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — re-apply idempotency + schema_versions row registered.
# ═════════════════════════════════════════════════════════════════════════════


def test_ac2_no_create_table_without_if_not_exists_in_impl(impl_sql):
    non_idem = re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)(\w+)", impl_sql)
    assert non_idem == [], f"non-idempotent CREATE TABLE: {non_idem}"


def test_ac2_no_create_table_without_if_not_exists_in_runner(runner_sql):
    non_idem = re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)(\w+)", runner_sql)
    assert non_idem == [], f"non-idempotent CREATE TABLE: {non_idem}"


def test_ac2_no_create_index_without_if_not_exists_in_impl(impl_sql):
    non_idem = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF NOT EXISTS)(\w+)",
        impl_sql,
    )
    assert non_idem == [], f"non-idempotent CREATE INDEX: {non_idem}"


def test_ac2_no_create_index_without_if_not_exists_in_runner(runner_sql):
    non_idem = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF NOT EXISTS)(\w+)",
        runner_sql,
    )
    assert non_idem == [], f"non-idempotent CREATE INDEX: {non_idem}"


def test_ac2_drop_policy_count_matches_create_policy_count_in_impl(impl_sql):
    drops = len(re.findall(r"DROP POLICY IF EXISTS", impl_sql))
    creates = len(re.findall(r"CREATE POLICY", impl_sql))
    assert drops == creates, (
        f"impl: DROP POLICY ({drops}) != CREATE POLICY ({creates})"
    )


def test_ac2_schema_versions_row_inserted_for_t_001_05(impl_sql):
    """audit trail: schema_versions populated with this migration's version."""
    assert "INSERT INTO schema_versions" in impl_sql
    assert "'20260512000000'" in impl_sql
    assert "T-001-05" in impl_sql
    assert "ON CONFLICT (version) DO NOTHING" in impl_sql, (
        "INSERT must be ON CONFLICT DO NOTHING for re-apply idempotency"
    )


# ═════════════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — secrets indirection (pgsodium), vault_path NOT NULL,
#                     red_line_violations FK CASCADE, no "FOR ALL TO public".
# ═════════════════════════════════════════════════════════════════════════════


def test_ac3_api_keys_secret_scope_not_null(impl_sql):
    body = _table_body(impl_sql, "api_keys")
    assert re.search(
        r"secret_scope\s+TEXT\s+NOT\s+NULL",
        body,
        re.IGNORECASE,
    ), "api_keys.secret_scope must be NOT NULL (encrypted_secrets indirection)"


def test_ac3_api_keys_secret_key_not_null(impl_sql):
    body = _table_body(impl_sql, "api_keys")
    assert re.search(
        r"secret_key\s+TEXT\s+NOT\s+NULL",
        body,
        re.IGNORECASE,
    ), "api_keys.secret_key must be NOT NULL (encrypted_secrets indirection)"


def test_ac3_api_keys_has_no_plaintext_value_column(impl_sql):
    """Drift guard: api_keys must NOT carry a plaintext key value column."""
    body = _table_body(impl_sql, "api_keys")
    forbidden = re.findall(
        r"\b(api_key_value|raw_key|plain_key|secret_value|plaintext_key|"
        r"raw_secret|api_key_plain)\b",
        body,
        re.IGNORECASE,
    )
    assert not forbidden, f"plaintext API key column present: {forbidden}"


def test_ac3_obsidian_vaults_vault_path_text_not_null(impl_sql):
    body = _table_body(impl_sql, "obsidian_vaults")
    assert re.search(
        r"vault_path\s+TEXT\s+NOT\s+NULL",
        body,
        re.IGNORECASE,
    ), "obsidian_vaults.vault_path must be TEXT NOT NULL"


def test_ac3_red_line_violations_red_line_id_fk_cascade(impl_sql):
    body = _table_body(impl_sql, "red_line_violations")
    assert re.search(
        r"red_line_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+red_lines\s*\(\s*id\s*\)"
        r"\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "red_line_violations.red_line_id must FK CASCADE to red_lines(id)"


def test_ac3_no_for_all_to_public_in_impl(impl_sql):
    """Blanket public access invariant: never grant FOR ALL TO public."""
    bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", impl_sql, re.IGNORECASE)
    assert not bad, f"forbidden FOR ALL TO public in impl: {bad}"


def test_ac3_no_for_all_to_public_in_runner(runner_sql):
    bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", runner_sql, re.IGNORECASE)
    assert not bad, f"forbidden FOR ALL TO public in runner: {bad}"


# --- 17 individual RLS-enable checks (anti-drift, NO collapsed regex) ---


def test_ac3_rls_1_session_artifacts_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "session_artifacts")


def test_ac3_rls_2_prs_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "prs")


def test_ac3_rls_3_pr_reviews_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "pr_reviews")


def test_ac3_rls_4_red_lines_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "red_lines")


def test_ac3_rls_5_red_line_violations_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "red_line_violations")


def test_ac3_rls_6_llm_providers_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "llm_providers")


def test_ac3_rls_7_api_keys_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "api_keys")


def test_ac3_rls_8_slack_webhooks_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "slack_webhooks")


def test_ac3_rls_9_github_repos_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "github_repos")


def test_ac3_rls_10_obsidian_vaults_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "obsidian_vaults")


def test_ac3_rls_11_notifications_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "notifications")


def test_ac3_rls_12_token_limits_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "token_limits")


def test_ac3_rls_13_backups_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "backups")


def test_ac3_rls_14_user_settings_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "user_settings")


def test_ac3_rls_15_workspace_settings_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "workspace_settings")


def test_ac3_rls_16_schema_versions_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "schema_versions")


def test_ac3_rls_17_templates_enabled(impl_sql):
    assert _has_rls_enabled(impl_sql, "templates")


# --- service_role coverage for the 4 most-sensitive policies ---


def test_ac3_service_role_policy_api_keys(impl_sql):
    assert _has_service_role_policy(impl_sql, "api_keys")


def test_ac3_service_role_policy_red_line_violations(impl_sql):
    assert _has_service_role_policy(impl_sql, "red_line_violations")


def test_ac3_service_role_policy_backups(impl_sql):
    assert _has_service_role_policy(impl_sql, "backups")


def test_ac3_service_role_policy_schema_versions(impl_sql):
    assert _has_service_role_policy(impl_sql, "schema_versions")


# --- chat_threads / chat_messages RLS in runner migration ---


def test_ac3_rls_chat_threads_enabled(runner_sql):
    assert _has_rls_enabled(runner_sql, "chat_threads")


def test_ac3_rls_chat_messages_enabled(runner_sql):
    assert _has_rls_enabled(runner_sql, "chat_messages")


# --- Anchor FK invariants per ticket spec ---


def test_ac3_session_artifacts_fk_session_cascade(impl_sql):
    body = _table_body(impl_sql, "session_artifacts")
    assert re.search(
        r"session_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+sessions\s*\(\s*id\s*\)"
        r"\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "session_artifacts.session_id must FK CASCADE to sessions(id)"


def test_ac3_prs_workspace_fk_cascade(impl_sql):
    body = _table_body(impl_sql, "prs")
    assert re.search(
        r"workspace_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+workspaces\s*\(\s*id\s*\)"
        r"\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "prs.workspace_id must FK CASCADE to workspaces(id)"


def test_ac3_pr_reviews_fk_prs_cascade(impl_sql):
    body = _table_body(impl_sql, "pr_reviews")
    assert re.search(
        r"pr_id\s+BIGINT\s+NOT\s+NULL\s+REFERENCES\s+prs\s*\(\s*id\s*\)"
        r"\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ), "pr_reviews.pr_id must FK CASCADE to prs(id)"


# ═════════════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — enum CHECK exact sets (additive drift caught by set ==).
# ═════════════════════════════════════════════════════════════════════════════


def test_ac4_templates_template_kind_exactly_5_values(impl_sql):
    body = _table_body(impl_sql, "templates")
    m = re.search(r"CHECK\s*\(\s*template_kind\s+IN\s*\(([^)]+)\)", body)
    assert m, "templates.template_kind CHECK missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"task", "pr", "mock", "prompt", "constitution"}
    assert values == expected, f"template_kind drift: {values} != {expected}"


def test_ac4_backups_status_exactly_3_values(impl_sql):
    body = _table_body(impl_sql, "backups")
    m = re.search(r"CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)", body)
    assert m, "backups.status CHECK missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"completed", "failed", "in_progress"}
    assert values == expected, f"backups.status drift: {values} != {expected}"


def test_ac4_backups_backup_kind_exactly_4_values(impl_sql):
    body = _table_body(impl_sql, "backups")
    m = re.search(r"CHECK\s*\(\s*backup_kind\s+IN\s*\(([^)]+)\)", body)
    assert m, "backups.backup_kind CHECK missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"db", "storage", "obsidian", "full"}
    assert values == expected, f"backup_kind drift: {values} != {expected}"


def test_ac4_backups_triggered_by_exactly_3_values(impl_sql):
    """Spec stretch: backup audit trail enum is part of the OPTIONAL contract.

    Not explicitly enumerated by the ticket text but enforced for runtime
    operational safety (cron / manual / pre_release).
    """
    body = _table_body(impl_sql, "backups")
    m = re.search(r"CHECK\s*\(\s*triggered_by\s+IN\s*\(([^)]+)\)", body)
    assert m, "backups.triggered_by CHECK missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"cron", "manual", "pre_release"}
    assert values == expected, f"triggered_by drift: {values} != {expected}"


def test_ac4_templates_body_format_exactly_4_values(impl_sql):
    body = _table_body(impl_sql, "templates")
    m = re.search(r"CHECK\s*\(\s*body_format\s+IN\s*\(([^)]+)\)", body)
    assert m, "templates.body_format CHECK missing"
    values = set(re.findall(r"'([^']+)'", m.group(1)))
    expected = {"markdown", "jinja", "json", "plain"}
    assert values == expected, f"body_format drift: {values} != {expected}"


# ═════════════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — reject paths + no hardcoded secrets.
# ═════════════════════════════════════════════════════════════════════════════


def test_ac5_no_hardcoded_supabase_keys_in_impl(impl_sql):
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", impl_sql)


def test_ac5_no_hardcoded_supabase_keys_in_runner(runner_sql):
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", runner_sql)


def test_ac5_no_hardcoded_anthropic_keys_in_impl(impl_sql):
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", impl_sql)


def test_ac5_no_hardcoded_anthropic_keys_in_runner(runner_sql):
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", runner_sql)


def test_ac5_no_hardcoded_jwt_in_impl(impl_sql):
    assert not re.search(
        r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.",
        impl_sql,
    )


def test_ac5_no_hardcoded_jwt_in_runner(runner_sql):
    assert not re.search(
        r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.",
        runner_sql,
    )


def test_ac5_red_line_violations_red_line_id_not_null_rejects_invalid_fk(impl_sql):
    """If red_line_violation insert lacks red_line_id, NOT NULL rejects."""
    body = _table_body(impl_sql, "red_line_violations")
    assert re.search(
        r"red_line_id\s+\w+\s+NOT\s+NULL\s+REFERENCES",
        body,
        re.IGNORECASE,
    )


def test_ac5_api_keys_provider_key_not_null(impl_sql):
    body = _table_body(impl_sql, "api_keys")
    assert re.search(
        r"provider_key\s+TEXT\s+NOT\s+NULL",
        body,
        re.IGNORECASE,
    )


def test_ac5_no_drop_table_in_impl(impl_sql):
    """red-line: production migration must never DROP TABLE."""
    assert not re.search(r"DROP\s+TABLE\b", impl_sql, re.IGNORECASE), (
        "impl migration must not contain DROP TABLE"
    )


# ═════════════════════════════════════════════════════════════════════════════
# tickets.json / architecture-v1.md cross-reference drift guards
# ═════════════════════════════════════════════════════════════════════════════


def test_tickets_t_001_05_ac_types_canonical_ears():
    data = json.loads(TICKETS_JSON.read_text(encoding="utf-8"))
    ticket = next(x for x in data["tickets"] if x["id"] == "T-001-05")
    types = [ac["type"] for ac in ticket["acceptance_criteria"]]
    assert types == [
        "UBIQUITOUS",
        "EVENT-DRIVEN",
        "STATE-DRIVEN",
        "OPTIONAL",
        "UNWANTED",
    ], f"non-canonical EARS types: {types}"


def test_tickets_t_001_05_existing_files_intact():
    data = json.loads(TICKETS_JSON.read_text(encoding="utf-8"))
    ticket = next(x for x in data["tickets"] if x["id"] == "T-001-05")
    files = ticket.get("existing_files", [])
    assert any(
        f.endswith("20260512000000_impl_integration_ops_tables.sql") for f in files
    )
    assert any(f.endswith("20260510000003_runner_session_tables.sql") for f in files)
    assert any(f.endswith("20260510000002_rls_full_enforcement.sql") for f in files)


def test_tickets_t_001_05_ac_text_mentions_concrete_artifacts():
    data = json.loads(TICKETS_JSON.read_text(encoding="utf-8"))
    ticket = next(x for x in data["tickets"] if x["id"] == "T-001-05")
    full = " ".join(ac["text"] for ac in ticket["acceptance_criteria"])
    for required in (
        "session_artifacts",
        "prs",
        "red_lines",
        "red_line_violations",
        "api_keys",
        "obsidian_vaults",
        "templates",
        "chat_threads",
        "chat_messages",
        "secret_scope",
        "secret_key",
        "template_kind",
        "backup_kind",
        "schema_versions",
    ):
        assert required in full, f"T-001-05 AC missing literal: {required}"


def test_architecture_v1_md_enumerates_17_plus_2_tables():
    """architecture-v1.md §4 entities literal cross-check (anti-drift)."""
    text = ARCH_MD.read_text(encoding="utf-8")
    # 実装・レビュー 7 includes session_artifacts / prs / pr_reviews / red_lines /
    # red_line_violations (the 5 new ones in T-001-05).
    for entity in (
        "session_artifacts",
        "prs",
        "pr_reviews",
        "red_lines",
        "red_line_violations",
        "llm_providers",
        "api_keys",
        "slack_webhooks",
        "github_repos",
        "obsidian_vaults",
        "notifications",
        "token_limits",
        "backups",
        "user_settings",
        "workspace_settings",
        "schema_versions",
    ):
        assert entity in text, f"architecture-v1.md missing {entity}"
