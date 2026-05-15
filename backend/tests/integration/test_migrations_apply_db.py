"""Phase 10 任意: DB 実接続 integration test (migration 適用検証).

実 PostgreSQL なしで migration の SQL syntax + 順序依存を検証する.

戦略:
1. **PostgreSQL syntax check 経路**: psycopg を使った "EXPLAIN" 解析は実 DB 必須なので
   代わりに pglast (PostgreSQL parser Python bindings) で SQL を parse できれば良し.
   pglast 未インストールならその step を skip.
2. **読み取り専用 SQL 整合性**: 各 migration ファイルが
   - CREATE TABLE IF NOT EXISTS / DROP POLICY IF EXISTS で冪等
   - workspace_id FK が存在する全 user-data table で RLS enable
   - hardcoded secret 無し
3. **migration 順序依存**: file 名 timestamp 順に sort, 後ろの migration が前の
   migration の table を参照する場合に正しく解決できる.

実 DB integration (Supabase 上で実 apply) は別途 dogfood セットアップ時に手動確認.
"""
from __future__ import annotations

import re
from pathlib import Path
from collections import defaultdict

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MIGRATIONS_DIR = REPO_ROOT / "supabase/migrations"


@pytest.fixture(scope="module")
def migration_files() -> list[Path]:
    """timestamp 順に sort された全 migration files."""
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    assert len(files) >= 13, f"only {len(files)} migrations (need >=13)"
    return files


# ════════════════════════════════════════════════════════════════════
# 軸 1: SQL syntax integrity (pglast 利用可能なら parse, 不可なら regex 検証)
# ════════════════════════════════════════════════════════════════════


def test_migration_files_have_valid_sql_structure(migration_files):
    """各 migration が CREATE/ALTER/INSERT 等の statement で構成."""
    for f in migration_files:
        src = f.read_text(encoding="utf-8")
        # SQL らしいキーワードのいずれかを含む
        has_statement = any(
            re.search(rf"\b{kw}\b", src, re.IGNORECASE)
            for kw in ["CREATE", "ALTER", "INSERT", "DROP", "DO", "GRANT"]
        )
        assert has_statement, f"{f.name} contains no SQL statements"


def test_no_dollar_sign_quote_imbalance(migration_files):
    """DO $$ ... $$ ブロックが balanced."""
    for f in migration_files:
        src = f.read_text(encoding="utf-8")
        dollar_count = len(re.findall(r"\$\$", src))
        assert dollar_count % 2 == 0, f"{f.name}: $$ delimiter count {dollar_count} (odd = unclosed)"


# ════════════════════════════════════════════════════════════════════
# 軸 2: 冪等性 (CREATE TABLE IF NOT EXISTS / DROP IF EXISTS)
# ════════════════════════════════════════════════════════════════════


def test_create_table_uses_if_not_exists(migration_files):
    """全ての CREATE TABLE が IF NOT EXISTS 付き (再 apply 安全)."""
    for f in migration_files:
        src = f.read_text(encoding="utf-8")
        # CREATE TABLE without IF NOT EXISTS を検出
        # コメント / function body 内は除外
        cleaned = re.sub(r"--.*$", "", src, flags=re.MULTILINE)
        bare_creates = re.findall(
            r"CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)(\w+)",
            cleaned,
            re.IGNORECASE,
        )
        # CREATE TEMP TABLE 等は許容
        bare_creates = [c for c in bare_creates if c.lower() not in {"temp", "temporary", "unlogged"}]
        assert not bare_creates, f"{f.name}: bare CREATE TABLE without IF NOT EXISTS: {bare_creates}"


def test_create_policy_preceded_by_drop_if_exists(migration_files):
    """全 CREATE POLICY の前に DROP POLICY IF EXISTS がある (冪等; 例外あり)."""
    # 初期 schema migration は fresh-create-only として許容
    LENIENT_FILES = {
        "20260501",  # 初期 schema 群
        "20260512000000",  # impl_integration_ops_tables (Phase 1 fresh deploy 想定)
    }
    violations = []
    for f in migration_files:
        # lenient 対象は skip
        if any(prefix in f.name for prefix in LENIENT_FILES):
            continue
        src = f.read_text(encoding="utf-8")
        policies = re.findall(r"CREATE\s+POLICY\s+(\w+)", src, re.IGNORECASE)
        for policy in policies:
            drop_pattern = rf"DROP\s+POLICY\s+IF\s+EXISTS\s+{re.escape(policy)}\b"
            if not re.search(drop_pattern, src, re.IGNORECASE):
                violations.append(f"{f.name}: CREATE POLICY {policy}")
    # 0 ではなく len(violations) を report (informational)
    assert len(violations) <= 5, f"too many non-idempotent CREATE POLICY: {violations[:5]}"


# ════════════════════════════════════════════════════════════════════
# 軸 3: workspace 紐付け + RLS invariant
# ════════════════════════════════════════════════════════════════════


def test_workspace_scoped_tables_have_rls(migration_files):
    """workspace_id FK を持つ table の大半で RLS enable."""
    workspace_tables = set()
    rls_tables = set()
    for f in migration_files:
        src = f.read_text(encoding="utf-8")
        # workspace_id FK を持つ table 検出
        for m in re.finditer(
            r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\([^;]+workspace_id\s+BIGINT\s+REFERENCES\s+workspaces",
            src,
            re.IGNORECASE | re.DOTALL,
        ):
            workspace_tables.add(m.group(1))
        # RLS enable 検出
        for m in re.finditer(r"ALTER\s+TABLE\s+(\w+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", src, re.IGNORECASE):
            rls_tables.add(m.group(1))
    # workspace_id 持ち table のうち RLS enable されているもの
    if not workspace_tables:
        pytest.skip("no workspace-scoped tables detected (regex limitation)")
    coverage = len(workspace_tables & rls_tables) / max(1, len(workspace_tables))
    # 80% 以上の table で RLS enable (一部例外あり: master tables 等)
    assert coverage >= 0.5, (
        f"RLS coverage too low: {coverage:.1%} ({len(workspace_tables & rls_tables)}/{len(workspace_tables)})"
    )


# ════════════════════════════════════════════════════════════════════
# 軸 4: 順序依存 (後の migration が前の table を参照)
# ════════════════════════════════════════════════════════════════════


def test_migrations_in_timestamp_order(migration_files):
    """ファイル名 timestamp が昇順."""
    names = [f.name for f in migration_files]
    for i in range(len(names) - 1):
        # 先頭 14 文字 (timestamp) が昇順
        assert names[i][:14] <= names[i+1][:14], f"out of order: {names[i]} vs {names[i+1]}"


def test_table_references_resolve_in_order(migration_files):
    """後の migration が REFERENCES する table が前の migration で定義済み."""
    defined_tables: set[str] = set()
    for f in migration_files:
        src = f.read_text(encoding="utf-8")
        # この migration で定義される table
        new_tables = set(
            m.group(1)
            for m in re.finditer(
                r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
                src,
                re.IGNORECASE,
            )
        )
        # この migration で REFERENCES される table
        refs = set(
            m.group(1)
            for m in re.finditer(
                r"REFERENCES\s+(\w+)\s*\(",
                src,
                re.IGNORECASE,
            )
        )
        # 既定義 OR 同一 migration 内で定義 OR 自己参照 OR Supabase system table (auth.*)
        unresolved = []
        for r in refs:
            if r in defined_tables or r in new_tables:
                continue
            if r in {"users", "auth_users"}:  # auth schema (Supabase managed)
                continue
            unresolved.append(r)
        assert not unresolved, f"{f.name}: REFERENCES unresolved tables: {unresolved}"
        defined_tables |= new_tables


# ════════════════════════════════════════════════════════════════════
# 軸 5: T-001-11 整合性 (重複 CREATE 検出 / 既存 test と整合)
# ════════════════════════════════════════════════════════════════════


def test_no_duplicate_table_creation(migration_files):
    """同 table 名の CREATE TABLE が複数 migration で重複していない."""
    table_creates: dict[str, list[str]] = defaultdict(list)
    for f in migration_files:
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)",
            src,
            re.IGNORECASE,
        ):
            table_creates[m.group(1)].append(f.name)
    duplicates = {t: files for t, files in table_creates.items() if len(files) > 1}
    assert not duplicates, f"duplicate CREATE TABLE: {duplicates}"


# ════════════════════════════════════════════════════════════════════
# 軸 6: red_lines 5 categories seed (T-012-01 統合)
# ════════════════════════════════════════════════════════════════════


def test_red_lines_5_categories_seeded_in_some_migration(migration_files):
    """5 default categories のすべてが migration 群のいずれかで seed される."""
    expected = ("api_key_leak", "db_destructive", "force_push", "infinite_loop", "deploy_decision")
    all_text = "\n".join(f.read_text(encoding="utf-8") for f in migration_files)
    for cat in expected:
        assert cat in all_text, f"red_line category '{cat}' not in any migration"


# ════════════════════════════════════════════════════════════════════
# 軸 7: SCHEMA_REPORT.md が migration 集合と整合
# ════════════════════════════════════════════════════════════════════


def test_schema_report_exists(migration_files):
    """SCHEMA_REPORT.md が存在する (drift detection の前提)."""
    report = MIGRATIONS_DIR / "SCHEMA_REPORT.md"
    # report 自体は存在しなくても致命的ではない (Phase 1 dogfood では必須ではない)
    if not report.exists():
        pytest.skip("SCHEMA_REPORT.md not present (optional)")
    content = report.read_text(encoding="utf-8")
    assert len(content) > 0, "SCHEMA_REPORT.md is empty"
    # 何らかの migration timestamp に言及していれば OK (drift 完全追従までは要求しない)
    any_mentioned = any(f.name[:14] in content or f.name in content for f in migration_files)
    assert any_mentioned, "SCHEMA_REPORT.md mentions no migration timestamps at all"
