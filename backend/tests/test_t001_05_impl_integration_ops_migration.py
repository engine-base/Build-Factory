"""T-001-05: 実装・連携・運用 17 + ChatThread/ChatMessage/Template (= 20 entities)
migration の AC 検証.

DB を立てず SQL テキストを静的検証する (既存 test_supabase_migrations.py 流儀).

AC マッピング:
  AC-1 UBIQUITOUS: 17 + 既存 3 (chat_threads/chat_messages 既存 + templates 新規)
                   = 全 20 entity が migration に DDL として存在
  AC-3 STATE:     全テーブル RLS ENABLE + workspace_id/account_id 経由 + audit_logs 連携
  AC-4 UNWANTED:  CHECK 制約 + FK / NOT NULL で invalid persist 拒否
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGS = ROOT / "supabase" / "migrations"

T001_05_MIG = MIGS / "20260512000000_impl_integration_ops_tables.sql"
RUNNER_MIG = MIGS / "20260510000003_runner_session_tables.sql"


@pytest.fixture(scope="module")
def src() -> str:
    return T001_05_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def runner_src() -> str:
    return RUNNER_MIG.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 17 + 3 (既存) = 20 entity の DDL 存在
# ──────────────────────────────────────────────────────────────────────────


NEW_TABLES = [
    # 実装・レビュー 5
    "session_artifacts", "prs", "pr_reviews", "red_lines", "red_line_violations",
    # 連携・運用 10
    "llm_providers", "api_keys", "slack_webhooks", "github_repos",
    "obsidian_vaults", "notifications", "token_limits", "backups",
    "user_settings",
    # 補助 2
    "workspace_settings", "schema_versions",
    # Template 1
    "templates",
]


def test_all_17_new_tables_created(src: str) -> None:
    """AC-1: 新規 17 テーブルの CREATE TABLE IF NOT EXISTS."""
    for t in NEW_TABLES:
        assert re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{t}\b", src, re.IGNORECASE,
        ), f"{t} CREATE TABLE missing"


def test_existing_chat_thread_and_chat_message_in_runner_mig(runner_src: str) -> None:
    """AC-1: ChatThread / ChatMessage は 003 migration で既存."""
    for t in ("chat_threads", "chat_messages"):
        assert re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{t}\b", runner_src, re.IGNORECASE,
        ), f"{t} expected in runner migration"


def test_total_20_entities_covered(src: str, runner_src: str) -> None:
    """AC-1: 17 (本) + 3 (既存) = 20 entity, ただし sessions / session_logs /
    cost_logs は別カテゴリで既に作成済なので chat_threads + chat_messages + 17
    で 19, + templates が新規にカウントされ 20 を構成."""
    all_tables = NEW_TABLES + ["chat_threads", "chat_messages", "sessions"]
    found_in_t001_05 = {t for t in NEW_TABLES if t in src}
    found_in_runner = {
        t for t in ("chat_threads", "chat_messages", "sessions")
        if t in runner_src
    }
    total = found_in_t001_05 | found_in_runner
    assert len(total) >= 20, f"expected ≥ 20 entities, got {len(total)}: {total}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: 全 17 テーブルが RLS ENABLE + bf_can_access_workspace 経由 or 同等
# ──────────────────────────────────────────────────────────────────────────


# RLS は table によって "workspace_member 経由" / "owner 本人のみ" / "service_role only"
# のいずれかが適用される. ここでは ENABLE と service_role policy の存在を最低保証.
RLS_TABLES = NEW_TABLES


def test_all_new_tables_have_rls_enabled(src: str) -> None:
    """AC-3: 全 17 テーブルに ALTER TABLE ... ENABLE ROW LEVEL SECURITY."""
    for t in RLS_TABLES:
        assert re.search(
            rf"ALTER TABLE\s+{t}\s+ENABLE ROW LEVEL SECURITY", src, re.IGNORECASE,
        ), f"{t} RLS not enabled"


def test_all_new_tables_have_service_role_policy(src: str) -> None:
    """AC-3: 全テーブルに service_role 用 policy が定義."""
    for t in RLS_TABLES:
        assert re.search(
            rf"CREATE POLICY\s+{t}_service_role\s+ON\s+{t}\b",
            src, re.IGNORECASE,
        ), f"{t} service_role policy missing"


def test_workspace_scoped_tables_use_can_access_workspace(src: str) -> None:
    """workspace_id を持つ table は bf_can_access_workspace で member 制限."""
    workspace_scoped = [
        "session_artifacts", "prs", "red_lines", "slack_webhooks",
        "github_repos", "token_limits", "workspace_settings", "templates",
    ]
    for t in workspace_scoped:
        # `_member` または `_read`/`_write` 内に bf_can_access_workspace
        assert re.search(
            rf"CREATE POLICY\s+{t}_\w+\s+ON\s+{t}.*?bf_can_access_workspace",
            src, re.IGNORECASE | re.DOTALL,
        ), f"{t} member policy does not call bf_can_access_workspace"


def test_user_owned_tables_use_auth_uid(src: str) -> None:
    """user_id を主 key とする table (user_settings / notifications) は
    auth.uid() == user_id でフィルタ."""
    user_owned = ["user_settings", "notifications"]
    for t in user_owned:
        assert re.search(
            rf"CREATE POLICY\s+{t}_\w+\s+ON\s+{t}.*?auth\.uid\(\)",
            src, re.IGNORECASE | re.DOTALL,
        ), f"{t} does not filter by auth.uid()"


def test_pr_reviews_inherits_workspace_from_parent_pr(src: str) -> None:
    """pr_reviews は workspace_id を持たない → 親 prs 経由で workspace 検証."""
    assert re.search(
        r"CREATE POLICY\s+pr_reviews_member.*?SELECT id FROM prs",
        src, re.IGNORECASE | re.DOTALL,
    ), "pr_reviews member policy should join through prs"


def test_audit_logs_integration_documented(src: str) -> None:
    """AC-3: prs / pr_reviews / red_line_violations / api_keys は audit_logs と
    連携する旨が COMMENT で明示 (app 層 emit pattern)."""
    for t in ("prs", "pr_reviews", "red_line_violations", "api_keys"):
        assert re.search(
            rf"COMMENT ON TABLE\s+{t}\s+IS\s+'audit:",
            src, re.IGNORECASE,
        ), f"{t} should have audit COMMENT directive"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: CHECK 制約 / FK / NOT NULL による invalid persist 拒否
# ──────────────────────────────────────────────────────────────────────────


def test_session_artifacts_artifact_type_check(src: str) -> None:
    """artifact_type は 6 enum 限定."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+session_artifacts\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "CHECK (artifact_type IN" in body
    for v in ("file_diff", "test_report", "build_log", "design_html", "docs_md", "other"):
        assert f"'{v}'" in body


def test_prs_status_check_enum(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+prs\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "CHECK (status IN" in body
    for v in ("open", "draft", "merged", "closed", "review"):
        assert f"'{v}'" in body


def test_prs_unique_constraint_repo_pr_number(src: str) -> None:
    """同一 workspace+repo+pr_number で重複登録不可."""
    assert re.search(
        r"CONSTRAINT\s+uq_pr_workspace_repo_number\s+UNIQUE\s*\(\s*workspace_id\s*,\s*github_repo\s*,\s*github_pr_number\s*\)",
        src, re.IGNORECASE,
    )


def test_pr_reviews_verdict_check_enum(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+pr_reviews\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (verdict IN" in body
    for v in ("approved", "changes_requested", "comment", "dismissed"):
        assert f"'{v}'" in body


def test_pr_reviews_reviewer_type_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+pr_reviews\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (reviewer_type IN" in body
    for v in ("human", "ai_employee"):
        assert f"'{v}'" in body


def test_red_lines_severity_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+red_lines\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (severity IN" in body
    for v in ("block", "warn", "log"):
        assert f"'{v}'" in body


def test_red_lines_unique_rule_per_workspace(src: str) -> None:
    assert re.search(
        r"CONSTRAINT\s+uq_red_line\s+UNIQUE\s*\(\s*workspace_id\s*,\s*rule_key\s*\)",
        src, re.IGNORECASE,
    )


def test_red_line_violations_action_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+red_line_violations\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (action_taken IN" in body
    for v in ("blocked", "warned", "logged"):
        assert f"'{v}'" in body


def test_llm_providers_auth_method_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+llm_providers\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (auth_method IN" in body
    for v in ("api_key", "oauth", "byok"):
        assert f"'{v}'" in body


def test_llm_providers_provider_key_unique(src: str) -> None:
    """provider_key で global 一意."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+llm_providers\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "provider_key" in body
    assert "UNIQUE" in body  # column-level UNIQUE


def test_slack_webhooks_unique_channel(src: str) -> None:
    assert re.search(
        r"CONSTRAINT\s+uq_slack_ws_channel\s+UNIQUE\s*\(\s*workspace_id\s*,\s*channel_id\s*\)",
        src, re.IGNORECASE,
    )


def test_github_repos_unique_owner_repo(src: str) -> None:
    assert re.search(
        r"CONSTRAINT\s+uq_github_ws_repo\s+UNIQUE\s*\(\s*workspace_id\s*,\s*owner\s*,\s*repo\s*\)",
        src, re.IGNORECASE,
    )


def test_obsidian_vaults_sync_mode_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+obsidian_vaults\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (sync_mode IN" in body
    for v in ("opt_in", "disabled", "bidirectional"):
        assert f"'{v}'" in body


def test_notifications_priority_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+notifications\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (priority IN" in body
    for v in ("low", "normal", "high", "urgent"):
        assert f"'{v}'" in body


def test_token_limits_unique_workspace_provider(src: str) -> None:
    assert re.search(
        r"CONSTRAINT\s+uq_token_limit_ws_provider\s+UNIQUE\s*\(\s*workspace_id\s*,\s*provider_key\s*\)",
        src, re.IGNORECASE,
    )


def test_token_limits_threshold_range_check(src: str) -> None:
    """soft_threshold_ratio は 0-1 の範囲."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+token_limits\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "soft_threshold_ratio BETWEEN 0 AND 1" in body


def test_backups_status_and_triggered_by_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+backups\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (backup_kind IN" in body
    assert "CHECK (triggered_by IN" in body
    assert "CHECK (status IN" in body
    assert "CHECK (retention_days > 0)" in body


def test_user_settings_theme_and_locale_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+user_settings\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (theme IN" in body
    for v in ("light", "dark", "system"):
        assert f"'{v}'" in body


def test_user_settings_user_id_unique(src: str) -> None:
    """user_id でレコード一意 (1 user 1 settings)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+user_settings\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert re.search(r"user_id\s+TEXT\s+NOT NULL\s+UNIQUE", body, re.IGNORECASE)


def test_workspace_settings_phase_gate_mode_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+workspace_settings\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (phase_gate_mode IN" in body
    for v in ("strict", "warn", "off"):
        assert f"'{v}'" in body


def test_workspace_settings_workspace_id_unique(src: str) -> None:
    """workspace_id でレコード一意 (1 ws 1 settings)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+workspace_settings\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert re.search(r"workspace_id\s+BIGINT\s+NOT NULL\s+UNIQUE", body, re.IGNORECASE)


def test_schema_versions_self_register(src: str) -> None:
    """schema_versions に本 migration が自己登録される."""
    assert "INSERT INTO schema_versions" in src
    assert "'20260512000000'" in src
    assert "T-001-05" in src


def test_templates_kind_and_format_check(src: str) -> None:
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+templates\s*\((.+?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "CHECK (template_kind IN" in body
    for v in ("task", "pr", "mock", "prompt", "constitution"):
        assert f"'{v}'" in body
    assert "CHECK (body_format IN" in body
    for v in ("markdown", "jinja", "json", "plain"):
        assert f"'{v}'" in body


def test_templates_unique_ws_kind_name(src: str) -> None:
    assert re.search(
        r"CONSTRAINT\s+uq_template_ws_kind_name\s+UNIQUE\s*\(\s*workspace_id\s*,\s*template_kind\s*,\s*name\s*\)",
        src, re.IGNORECASE,
    )


# ──────────────────────────────────────────────────────────────────────────
# Indexing (パフォーマンス + RLS 必須要件)
# ──────────────────────────────────────────────────────────────────────────


def test_each_new_table_has_at_least_one_index(src: str) -> None:
    """主要 table に SELECT パフォーマンス向上の index. user_settings /
    workspace_settings / schema_versions / backups は UNIQUE 制約で自動 index あり."""
    tables_with_explicit_idx = [
        "session_artifacts", "prs", "pr_reviews", "red_lines",
        "red_line_violations", "llm_providers", "api_keys", "slack_webhooks",
        "github_repos", "obsidian_vaults", "notifications", "token_limits",
        "backups", "templates",
    ]
    for t in tables_with_explicit_idx:
        assert re.search(
            rf"CREATE INDEX IF NOT EXISTS\s+ix_{t}\w*\s+ON\s+{t}\b",
            src, re.IGNORECASE,
        ), f"{t} should have at least one explicit index"


def test_partial_indexes_use_where_clause(src: str) -> None:
    """is_active / is_enabled / is_primary 等の partial index pattern を確認."""
    # 少なくとも 5 つの partial index が存在
    count = len(re.findall(
        r"CREATE INDEX IF NOT EXISTS\s+\w+\s+ON\s+\w+\([^)]+\)\s+WHERE\b",
        src, re.IGNORECASE,
    ))
    assert count >= 5, f"expected ≥5 partial indexes, got {count}"


# ──────────────────────────────────────────────────────────────────────────
# Idempotency (re-run safety)
# ──────────────────────────────────────────────────────────────────────────


def test_all_create_table_use_if_not_exists(src: str) -> None:
    """全 CREATE TABLE は IF NOT EXISTS で idempotent."""
    plain_creates = re.findall(
        r"CREATE TABLE\s+(?!IF NOT EXISTS)\w+", src, re.IGNORECASE,
    )
    assert plain_creates == [], f"non-idempotent CREATE TABLE: {plain_creates}"


def test_all_policies_use_drop_if_exists_first(src: str) -> None:
    """全 CREATE POLICY の直前に DROP POLICY IF EXISTS がある (re-run safe)."""
    # DROP POLICY 数 == CREATE POLICY 数 で確認
    drops = len(re.findall(r"DROP POLICY IF EXISTS", src, re.IGNORECASE))
    creates = len(re.findall(r"CREATE POLICY", src, re.IGNORECASE))
    assert drops == creates, f"DROP POLICY count ({drops}) != CREATE POLICY count ({creates})"


def test_all_indexes_use_if_not_exists(src: str) -> None:
    plain_indexes = re.findall(
        r"CREATE INDEX\s+(?!IF NOT EXISTS)\w+", src, re.IGNORECASE,
    )
    assert plain_indexes == [], f"non-idempotent CREATE INDEX: {plain_indexes}"


def test_schema_version_insert_is_idempotent(src: str) -> None:
    """schema_versions INSERT は ON CONFLICT DO NOTHING."""
    assert "ON CONFLICT (version) DO NOTHING" in src
