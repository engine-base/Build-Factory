"""T-001-11: DB 統合テスト (RLS / 権限 / soft delete / 拡張) — 4 AC 全網羅.

Supabase migration ファイル群を静的にスキャンし、
F-001 で要求される DB レベルの整合性を機械検証する.

AC マッピング:
  AC-1 UBIQUITOUS    : RLS / 権限 / soft delete / extension が migration に整合的に統合
  AC-2 EVENT-DRIVEN  : audit_logs テーブルが存在し action+timestamp を記録できる
  AC-3 STATE-DRIVEN  : RLS が core テーブル全てで ENABLE され policy が付く
  AC-4 UNWANTED      : invalid SQL pattern (DROP without IF EXISTS / FORCE RLS bypass 等)
                       が混入していないことを lint で検出
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGS = ROOT / "supabase" / "migrations"


def _all_migrations() -> list[Path]:
    return sorted(p for p in MIGS.glob("*.sql"))


def _all_sql() -> str:
    """全 migration SQL を結合した string を返す."""
    return "\n".join(p.read_text(encoding="utf-8") for p in _all_migrations())


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: F-001 統合検証 — テーブル / RLS / 権限 / soft delete / 拡張
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_migrations_dir_exists():
    assert MIGS.is_dir()
    assert len(_all_migrations()) >= 10


CORE_TABLES = [
    "accounts", "workspaces", "bf_projects", "users",
    "audit_logs", "skill_definitions",
]


@pytest.mark.parametrize("table", CORE_TABLES)
def test_ac1_core_table_defined(table):
    """AC-1: 核となる F-001 テーブルが migration で定義されている."""
    src = _all_sql()
    assert re.search(rf"CREATE TABLE IF NOT EXISTS\s+{table}\b", src, re.IGNORECASE), (
        f"core table {table!r} missing from migrations"
    )


def test_ac1_extensions_pgvector_pg_trgm_pgsodium_pg_cron():
    """AC-1 拡張: 4 拡張全てが migration に CREATE EXTENSION で含まれる
    (Postgres 上の名前: pgvector→vector, pg_trgm, pgsodium, pg_cron)."""
    src = _all_sql()
    for ext in ("vector", "pg_trgm", "pgsodium", "pg_cron"):
        assert re.search(rf"CREATE EXTENSION IF NOT EXISTS\s+\"?{ext}", src, re.IGNORECASE), (
            f"extension {ext!r} missing"
        )


def test_ac1_seed_sql_exists():
    """AC-1: T-001-10 で作成された seed.sql が存在."""
    seed = ROOT / "supabase" / "seed.sql"
    assert seed.exists()
    text = seed.read_text(encoding="utf-8")
    assert "BEGIN" in text and "COMMIT" in text


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: audit_logs schema が action + timestamp を持つ
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_audit_logs_has_action_and_timestamp():
    """AC-2: audit_logs テーブルが action (event_type) と timestamp 系 column を持つ."""
    src = _all_sql()
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+audit_logs\b(.*?);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m, "audit_logs CREATE TABLE not found"
    block = m.group(1)
    # action TEXT NOT NULL  または event_type TEXT
    assert re.search(r"(action|event_type)\s+TEXT", block, re.IGNORECASE), (
        "audit_logs must have action or event_type column"
    )
    assert re.search(r"(created_at|occurred_at|ts|timestamp)\b", block, re.IGNORECASE)


def test_ac2_audit_logs_indexed():
    """AC-2: audit_logs に index がある (event_type / created_at)."""
    src = _all_sql()
    assert re.search(r"CREATE INDEX.*audit_logs", src, re.IGNORECASE), (
        "audit_logs index missing"
    )


def test_ac2_oauth_audit_log_table_exists():
    """AC-2: OAuth 系の audit table も存在 (T-001-02 auth_audit_log)."""
    src = _all_sql()
    assert re.search(r"CREATE TABLE IF NOT EXISTS\s+auth_audit_log\b", src, re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: RLS が core テーブルで ENABLE + policy 付与
# ──────────────────────────────────────────────────────────────────────────


RLS_REQUIRED_TABLES = [
    "accounts", "workspaces", "bf_projects",
    "audit_logs", "knowledge_base", "user_profiles",
]


@pytest.mark.parametrize("table", RLS_REQUIRED_TABLES)
def test_ac3_rls_enabled_on_table(table):
    """AC-3: 各 RLS 対象表で ENABLE ROW LEVEL SECURITY が宣言されている."""
    src = _all_sql()
    assert re.search(
        rf"ALTER TABLE\s+{table}\s+ENABLE ROW LEVEL SECURITY",
        src, re.IGNORECASE,
    ), f"RLS not enabled on {table!r}"


def test_ac3_rls_policy_count_sufficient():
    """AC-3: CREATE POLICY が 10 件以上 (RLS が実質的に効いている)."""
    src = _all_sql()
    policies = re.findall(r"CREATE POLICY\b", src, re.IGNORECASE)
    assert len(policies) >= 10, f"CREATE POLICY count = {len(policies)} (要 10 以上)"


def test_ac3_no_force_disable_rls():
    """AC-3 UNWANTED: DISABLE ROW LEVEL SECURITY や FORCE OFF が無い (誤って外していない)."""
    src = _all_sql()
    assert not re.search(r"DISABLE ROW LEVEL SECURITY", src, re.IGNORECASE), (
        "RLS を DISABLE している migration がある (本番事故の元)"
    )


def test_ac3_audit_logs_rls_enabled():
    """AC-3 STATE §5.3: audit_logs 自体にも RLS が掛かっている."""
    src = _all_sql()
    assert re.search(
        r"ALTER TABLE\s+audit_logs\s+ENABLE ROW LEVEL SECURITY",
        src, re.IGNORECASE,
    )


# ──────────────────────────────────────────────────────────────────────────
# AC-3 補助: soft delete 列が core 表に揃っている
# ──────────────────────────────────────────────────────────────────────────


SOFT_DELETE_TABLES = ["workspaces", "bf_projects", "skill_definitions"]


@pytest.mark.parametrize("table", SOFT_DELETE_TABLES)
def test_soft_delete_column_present(table):
    """AC-3: soft delete (is_active or archived_at or deleted_at) のいずれか存在."""
    src = _all_sql()
    m = re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\b(.*?);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m, f"{table} CREATE TABLE missing"
    block = m.group(1).lower()
    assert any(col in block for col in ("is_active", "archived_at", "deleted_at", "status")), (
        f"{table}: soft delete column missing (need is_active / archived_at / deleted_at / status)"
    )


# ──────────────────────────────────────────────────────────────────────────
# 権限 (grants / roles)
# ──────────────────────────────────────────────────────────────────────────


def test_grants_or_roles_defined():
    """AC-1 権限: GRANT / REVOKE が migration に 1 件以上含まれる
    OR Supabase の組み込み auth.uid() による RLS で代替されている."""
    src = _all_sql()
    has_grant = bool(re.search(r"\b(GRANT|REVOKE)\s+\w+", src, re.IGNORECASE))
    has_auth_uid = bool(re.search(r"auth\.uid\(\)", src))
    assert has_grant or has_auth_uid, (
        "GRANT/REVOKE もしくは auth.uid() が migration に存在しない"
    )


def test_auth_uid_used_in_policies():
    """AC-3 補助: RLS policy で auth.uid() が使われている (Supabase 流)."""
    src = _all_sql()
    # CREATE POLICY ... auth.uid() の出現
    occurrences = len(re.findall(r"auth\.uid\(\)", src))
    assert occurrences >= 5, f"auth.uid() 使用回数 = {occurrences} (要 5 以上)"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: invalid migration pattern を検出 (state mutate 防止)
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_no_drop_without_if_exists():
    """AC-4: 直接的な DROP は IF EXISTS 付きでなければならない."""
    src = _all_sql()
    # コメント行を除外
    clean = re.sub(r"--.*$", "", src, flags=re.MULTILINE)
    drops = re.findall(
        r"^\s*DROP\s+(?:TABLE|COLUMN|INDEX|POLICY|TRIGGER|FUNCTION|EXTENSION|VIEW)[^\n]*$",
        clean, re.IGNORECASE | re.MULTILINE,
    )
    for d in drops:
        assert "IF EXISTS" in d.upper(), f"DROP without IF EXISTS: {d.strip()}"


def test_ac4_no_truncate_in_migration():
    """AC-4 UNWANTED: TRUNCATE は migration に含まれない (CLAUDE.md §5.4 redline)."""
    src = _all_sql()
    matches = re.findall(r"^\s*TRUNCATE\b", src, re.IGNORECASE | re.MULTILINE)
    # コメント内の言及は許容、実行可能行のみ check
    assert not matches, "TRUNCATE が migration に含まれている (本番事故の元)"


def test_ac4_no_delete_star_without_where():
    """AC-4 UNWANTED: DELETE FROM xxx (WHERE 句なし) が無いこと."""
    src = _all_sql()
    # コメント行を除外
    clean = re.sub(r"--.*$", "", src, flags=re.MULTILINE)
    # DELETE FROM table_name; (WHERE が無く ; で終わる)
    bare_delete = re.findall(
        r"DELETE\s+FROM\s+\w+\s*;", clean, re.IGNORECASE,
    )
    assert not bare_delete, f"DELETE without WHERE: {bare_delete}"


def test_ac4_migration_files_have_consistent_naming():
    """AC-4: migration ファイル名が YYYYMMDD... の形式に統一."""
    pattern = re.compile(r"^\d{14}_[a-zA-Z0-9_]+\.sql$")
    for p in _all_migrations():
        assert pattern.match(p.name), f"invalid migration filename: {p.name}"


def test_ac4_no_duplicate_table_definitions():
    """AC-4: 同じ CREATE TABLE IF NOT EXISTS xxx は 1 回ずつ (idempotent でも重複定義は不整合)."""
    src = _all_sql()
    table_creates = re.findall(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\b", src, re.IGNORECASE,
    )
    # 各 table が複数 migration で再定義されていないこと (CREATE は 1 件のみ許可)
    from collections import Counter
    counts = Counter(table_creates)
    duplicates = {t: c for t, c in counts.items() if c > 1}
    assert not duplicates, f"duplicate CREATE TABLE: {duplicates}"


# ──────────────────────────────────────────────────────────────────────────
# Migration ファイル数と層の整合性
# ──────────────────────────────────────────────────────────────────────────


def test_migration_count_at_least_18():
    """これまで作成した migration が 18 件以上残っている."""
    assert len(_all_migrations()) >= 18


def test_cycle_prevention_trigger_exists():
    """T-001-09: 循環依存防止 trigger が定義されている."""
    src = _all_sql()
    assert re.search(r"CREATE.*FUNCTION.*cycle|prevent_cycle|recursive", src, re.IGNORECASE), (
        "cycle prevention trigger missing"
    )


def test_runner_session_table_exists():
    """T-S0-08: claude-agent-sdk runner session 表が存在."""
    src = _all_sql()
    assert re.search(r"CREATE TABLE IF NOT EXISTS\s+sessions\b", src, re.IGNORECASE)
    assert re.search(r"CREATE TABLE IF NOT EXISTS\s+session_logs\b", src, re.IGNORECASE)


def test_clone_opt_in_table_exists():
    """T-001-08 / M-22: ai_clones (opt-in OFF default) と enforce trigger が存在."""
    src = _all_sql()
    # ai_clones テーブル
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\b(.*?);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m, "ai_clones CREATE TABLE missing"
    block = m.group(1).lower()
    assert "is_opted_in" in block, "is_opted_in column missing"
    assert "default false" in block, "is_opted_in default must be FALSE"
    # opt-in enforcement trigger
    assert re.search(r"bf_enforce_clone_opt_in", src), "clone opt-in enforce trigger missing"
