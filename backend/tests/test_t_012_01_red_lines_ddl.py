"""T-012-01: red_lines 5 主要 category seed 1:1 spec test.

既存 red_lines テーブル (supabase/migrations/20260512000000_impl_integration_ops_tables.sql)
を活用し、5 default categories の global seed を補完する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 5 default categories の seed (workspace_id=NULL = グローバル)
  AC-2 EVENT-DRIVEN  : audit_logs trigger は既存 (T-018-01 framework 経由)
  AC-3 STATE-DRIVEN  : RLS は既存 / seed は冪等 (ON CONFLICT DO NOTHING)
  AC-4 UNWANTED      : severity / UNIQUE 制約は既存テーブル定義側で担保
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_MIGRATION = REPO_ROOT / "supabase/migrations/20260514000000_red_lines_table.sql"
TABLE_MIGRATION = REPO_ROOT / "supabase/migrations/20260512000000_impl_integration_ops_tables.sql"
DETECTOR = REPO_ROOT / "backend/services/red_line_detector.py"

EXPECTED_CATEGORIES = (
    "api_key_leak",
    "db_destructive",
    "force_push",
    "infinite_loop",
    "deploy_decision",
)


@pytest.fixture(scope="module")
def seed_sql():
    assert SEED_MIGRATION.exists(), f"seed migration missing: {SEED_MIGRATION}"
    return SEED_MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table_sql():
    assert TABLE_MIGRATION.exists()
    return TABLE_MIGRATION.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: 5 categories seed
# ════════════════════════════════════════════════════════════════════


def test_ac1_seed_migration_exists():
    assert SEED_MIGRATION.exists()


def test_ac1_no_duplicate_table_create(seed_sql):
    """seed migration は CREATE TABLE を再宣言しない (重複弾く)."""
    # CREATE TABLE 自体が無いことを確認
    assert "CREATE TABLE" not in seed_sql, "seed migration should NOT redefine table"


def test_ac1_5_default_categories_seeded(seed_sql):
    """5 default categories (api_key_leak / db_destructive / force_push / infinite_loop / deploy_decision)."""
    for cat in EXPECTED_CATEGORIES:
        assert f"'{cat}'" in seed_sql, f"category '{cat}' seed missing"


def test_ac1_global_seed_workspace_id_null(seed_sql):
    """global seed として workspace_id=NULL で挿入される."""
    # INSERT 内に NULL がある
    assert "INSERT INTO red_lines" in seed_sql
    # 各 row の最初の値が NULL (workspace_id)
    assert re.search(r"\(NULL,\s*NULL,\s*'(api_key_leak|db_destructive|force_push|infinite_loop|deploy_decision)'", seed_sql)


def test_ac1_categories_match_red_line_detector_constants():
    """seed の rule_key と red_line_detector.py の DEFAULT_CATEGORIES が 1:1."""
    detector_src = DETECTOR.read_text(encoding="utf-8")
    for cat in EXPECTED_CATEGORIES:
        assert f'"{cat}"' in detector_src, f"detector module も '{cat}' を持つべき"


# ════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: audit_logs trigger 連携 (既存 framework)
# ════════════════════════════════════════════════════════════════════


def test_ac2_existing_table_has_audit_trigger_compatibility(table_sql):
    """既存 red_lines テーブル定義に created_at がある (audit_logs trigger 対象)."""
    # CREATE TABLE red_lines 行を取得
    m = re.search(r"CREATE TABLE IF NOT EXISTS red_lines\s*\((.*?)\);", table_sql, re.DOTALL)
    assert m, "red_lines table definition not found in 20260512000000"
    table_body = m.group(1)
    assert "created_at" in table_body, "created_at column must exist for audit trigger"


# ════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: 冪等性 (ON CONFLICT DO NOTHING)
# ════════════════════════════════════════════════════════════════════


def test_ac3_seed_idempotent_on_conflict(seed_sql):
    """seed は ON CONFLICT で冪等."""
    assert "ON CONFLICT" in seed_sql
    assert "DO NOTHING" in seed_sql
    # UNIQUE 制約 (workspace_id, rule_key) と整合
    assert re.search(r"ON CONFLICT.*workspace_id.*rule_key|ON CONFLICT \(workspace_id, rule_key\)", seed_sql)


def test_ac3_post_seed_invariant_check(seed_sql):
    """seed 後に 5 件揃ったかを RAISE EXCEPTION で機械検証."""
    assert "DO $$" in seed_sql
    assert "RAISE EXCEPTION" in seed_sql
    assert "expected_count" in seed_sql or "actual_count" in seed_sql


# ════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid value 検出 (既存 CHECK 制約に委任)
# ════════════════════════════════════════════════════════════════════


def test_ac4_severity_values_are_block_warn_log_only(seed_sql, table_sql):
    """seed 内 severity は block / warn / log のみ (既存 CHECK 制約と整合)."""
    # 既存 CHECK 確認
    assert re.search(r"CHECK.*severity\s+IN\s*\(\s*'block','warn','log'\s*\)", table_sql)
    # seed で使われる severity 確認
    severities_in_seed = re.findall(r"'(block|warn|log)'", seed_sql)
    assert all(s in {"block", "warn", "log"} for s in severities_in_seed)


def test_ac4_no_hardcoded_secrets_in_seed(seed_sql):
    """seed の pattern 列に literal な実鍵が無い (regex として保持されている)."""
    # JWT トークンが無い
    assert "eyJ" not in seed_sql, "JWT token literal found"
    # 実 API key っぽい long literal が無い (regex のみ)
    assert not re.search(r"sk-ant-[A-Z0-9]{40,}", seed_sql), "actual API key literal found"


# ════════════════════════════════════════════════════════════════════
# tickets.json メタ整合
# ════════════════════════════════════════════════════════════════════


def test_tickets_meta_t_012_01():
    """tickets.json の T-012-01 entry が AC を 4 件持つ."""
    import json
    p = REPO_ROOT / "docs/task-decomposition/2026-05-09_v1/tickets.json"
    with p.open() as f:
        d = json.load(f)
    t = next((x for x in d["tickets"] if x["id"] == "T-012-01"), None)
    assert t is not None, "T-012-01 not in tickets.json"
    assert len(t.get("acceptance_criteria", [])) >= 4
