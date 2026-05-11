"""T-001-03: AI 5 テーブル DDL (hierarchy + clone) AC 検証.

5 テーブル + opt-in trigger + RLS を静的検証.

AC マッピング:
  AC-1 UBIQUITOUS: 5 テーブル DDL
  AC-3 STATE:     backward compat (legacy ai_employee_config と共存)
  AC-4 UNWANTED:  opt-in OFF user の interaction_log INSERT を trigger で reject
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGS = ROOT / "supabase" / "migrations"
T001_03_MIG = MIGS / "20260512200000_ai_hierarchy_clone_tables.sql"


@pytest.fixture(scope="module")
def src() -> str:
    return T001_03_MIG.read_text(encoding="utf-8")


AI_TABLES = [
    "ai_employees", "ai_personas", "ai_hierarchies",
    "ai_clones", "user_interaction_log",
]


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 5 テーブル DDL
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("table", AI_TABLES)
def test_each_of_5_tables_exists(src: str, table: str) -> None:
    assert re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\b", src, re.IGNORECASE,
    ), f"{table} CREATE TABLE missing"


def test_all_5_tables_have_id_primary_key(src: str) -> None:
    for t in AI_TABLES:
        m = re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{t}\s*\((.+?)\);",
            src, re.IGNORECASE | re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert re.search(r"id\s+BIGSERIAL\s+PRIMARY KEY", body, re.IGNORECASE)


def test_ai_employees_role_level_check(src: str) -> None:
    """role_level enum: secretary / leader / member (CLAUDE.md §3)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_employees\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (role_level IN" in body
    for v in ("secretary", "leader", "member"):
        assert f"'{v}'" in body


def test_ai_employees_workspace_employee_key_unique(src: str) -> None:
    """同 workspace 内で employee_key 重複禁止."""
    assert re.search(
        r"CONSTRAINT\s+uq_ai_employee_ws_key\s+UNIQUE\s*\(\s*workspace_id\s*,\s*employee_key\s*\)",
        src, re.IGNORECASE,
    )


def test_ai_personas_key_unique(src: str) -> None:
    """persona_key で global 一意."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_personas\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert re.search(r"persona_key\s+TEXT\s+NOT NULL\s+UNIQUE", body, re.IGNORECASE)


def test_ai_personas_avatar_lucide_not_emoji(src: str) -> None:
    """CLAUDE.md §5.1: 絵文字禁止 → avatar は lucide icon name のみ."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_personas\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "avatar_lucide" in body
    # legacy avatar_emoji column は使わない
    assert "avatar_emoji" not in body


def test_ai_hierarchies_relation_type_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_hierarchies\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (relation_type IN" in body
    for v in ("reports_to", "collaborates_with", "delegates_to", "mentors"):
        assert f"'{v}'" in body


def test_ai_hierarchies_no_self_parent_constraint(src: str) -> None:
    """parent_id = child_id を禁止する CHECK 制約."""
    assert re.search(
        r"CONSTRAINT\s+no_self_parent\s+CHECK\s*\(.+?parent_id\s*<>\s*child_id\b",
        src, re.IGNORECASE | re.DOTALL,
    )


def test_ai_hierarchies_relation_unique(src: str) -> None:
    """同 workspace で同じ parent-child relation 多重登録禁止."""
    assert re.search(
        r"CONSTRAINT\s+uq_ai_hierarchy_relation\s+UNIQUE\s*\(\s*workspace_id\s*,\s*parent_id\s*,\s*child_id\s*,\s*relation_type\s*\)",
        src, re.IGNORECASE,
    )


# ──────────────────────────────────────────────────────────────────────────
# M-22 個人クローン opt-in (デフォルト OFF)
# ──────────────────────────────────────────────────────────────────────────


def test_ai_clones_default_opt_in_off(src: str) -> None:
    """CLAUDE.md §11: opt-in default OFF (プライバシー)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert re.search(
        r"is_opted_in\s+BOOLEAN\s+NOT NULL\s+DEFAULT\s+FALSE",
        body, re.IGNORECASE,
    )


def test_ai_clones_user_id_unique(src: str) -> None:
    """1 user 1 clone."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert re.search(r"user_id\s+TEXT\s+NOT NULL\s+UNIQUE", body, re.IGNORECASE)


def test_ai_clones_opt_in_consistency_check(src: str) -> None:
    """is_opted_in=TRUE なら opted_in_at 必須 (整合性)."""
    assert re.search(
        r"CONSTRAINT\s+opt_in_timestamp_consistent\s+CHECK\s*\(.+?is_opted_in\b",
        src, re.IGNORECASE | re.DOTALL,
    )


def test_ai_clones_has_consent_version_field(src: str) -> None:
    """GDPR 対応の consent_version field."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "consent_version" in body


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: opt-in OFF user の interaction_log INSERT を reject
# ──────────────────────────────────────────────────────────────────────────


def test_clone_opt_in_enforce_trigger_exists(src: str) -> None:
    """BEFORE INSERT trigger で opt-in TRUE 強制."""
    assert "CREATE OR REPLACE FUNCTION bf_enforce_clone_opt_in" in src
    assert re.search(
        r"CREATE TRIGGER\s+trg_enforce_clone_opt_in\s+BEFORE INSERT ON user_interaction_log",
        src, re.IGNORECASE,
    )


def test_clone_opt_in_trigger_raises_check_violation(src: str) -> None:
    """trigger は ERRCODE='check_violation' で raise (caller 4xx 化可能)."""
    assert re.search(
        r"RAISE EXCEPTION\s+'clone_opt_in_required.+?USING ERRCODE\s*=\s*'check_violation'",
        src, re.IGNORECASE | re.DOTALL,
    )


def test_clone_opt_in_trigger_idempotent(src: str) -> None:
    """DROP TRIGGER IF EXISTS で re-run safe."""
    assert "DROP TRIGGER IF EXISTS trg_enforce_clone_opt_in" in src


def test_user_interaction_log_type_check(src: str) -> None:
    """interaction_type enum (6 種)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+user_interaction_log\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (interaction_type IN" in body
    for v in ("decision", "correction", "preference", "rejection", "approval", "annotation"):
        assert f"'{v}'" in body


def test_user_interaction_log_embedding_status_check(src: str) -> None:
    """embedding_status enum (pending/embedded/failed/redacted)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+user_interaction_log\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (embedding_status IN" in body
    for v in ("pending", "embedded", "failed", "redacted"):
        assert f"'{v}'" in body


# ──────────────────────────────────────────────────────────────────────────
# RLS (全 5 テーブル + 個人クローン scope)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("table", AI_TABLES)
def test_each_ai_table_rls_enabled(src: str, table: str) -> None:
    assert re.search(
        rf"ALTER TABLE\s+{table}\s+ENABLE ROW LEVEL SECURITY",
        src, re.IGNORECASE,
    )


@pytest.mark.parametrize("table", AI_TABLES)
def test_each_ai_table_has_service_role_policy(src: str, table: str) -> None:
    assert re.search(
        rf"CREATE POLICY\s+{table}_service_role\s+ON\s+{table}",
        src, re.IGNORECASE,
    )


def test_ai_clones_uses_auth_uid_for_owner_scope(src: str) -> None:
    """ai_clones は user_id == auth.uid() で本人のみ R/W."""
    assert re.search(
        r"CREATE POLICY\s+ai_clones_owner\s+ON\s+ai_clones.*?user_id\s*=\s*auth\.uid\(\)::text",
        src, re.IGNORECASE | re.DOTALL,
    )


def test_user_interaction_log_uses_auth_uid_for_owner_scope(src: str) -> None:
    assert re.search(
        r"CREATE POLICY\s+user_interaction_log_owner\s+ON\s+user_interaction_log.*?user_id\s*=\s*auth\.uid\(\)::text",
        src, re.IGNORECASE | re.DOTALL,
    )


def test_workspace_scoped_tables_use_can_access_workspace(src: str) -> None:
    """ai_employees / ai_hierarchies は workspace_id 経由."""
    for t in ("ai_employees", "ai_hierarchies"):
        assert re.search(
            rf"CREATE POLICY\s+{t}_member\s+ON\s+{t}.*?bf_can_access_workspace",
            src, re.IGNORECASE | re.DOTALL,
        ), f"{t}: bf_can_access_workspace not used"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: schema_versions self-register + idempotency
# ──────────────────────────────────────────────────────────────────────────


def test_self_registers_to_schema_versions(src: str) -> None:
    assert "INSERT INTO schema_versions" in src
    assert "'20260512200000'" in src
    assert "T-001-03" in src
    assert "ON CONFLICT (version) DO NOTHING" in src


def test_all_create_table_use_if_not_exists(src: str) -> None:
    plain = re.findall(
        r"CREATE TABLE\s+(?!IF NOT EXISTS)\w+", src, re.IGNORECASE,
    )
    assert not plain


def test_all_drop_policy_before_create(src: str) -> None:
    """全 CREATE POLICY の前に DROP POLICY IF EXISTS で re-run safe."""
    drops = len(re.findall(r"DROP POLICY IF EXISTS", src, re.IGNORECASE))
    creates = len(re.findall(r"CREATE POLICY", src, re.IGNORECASE))
    assert drops == creates, f"DROP {drops} != CREATE {creates}"


def test_persona_fk_late_bind_idempotent(src: str) -> None:
    """ai_employees.persona_id → ai_personas.id の FK は DO $$ ... IF NOT EXISTS 経由."""
    assert "fk_ai_employees_persona" in src
    assert "DO $$" in src
    assert "IF NOT EXISTS" in src


def test_comments_document_m22_privacy_requirement(src: str) -> None:
    """COMMENT で M-22 / opt-in 仕様を明示."""
    assert re.search(r"COMMENT ON TABLE\s+ai_clones", src, re.IGNORECASE)
    assert re.search(r"COMMENT ON TABLE\s+user_interaction_log", src, re.IGNORECASE)
    assert "M-22" in src
    assert "opt-in" in src.lower()


def test_no_emoji_in_migration() -> None:
    """CLAUDE.md §5.1: 絵文字禁止."""
    text = T001_03_MIG.read_text(encoding="utf-8")
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    assert not emoji_re.findall(text)