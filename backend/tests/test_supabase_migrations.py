"""T-001-02 / T-001-04 / T-001-06 / T-019-01 検証テスト.

Supabase migration ファイル (SQL) が EARS AC を満たすか静的検証する。
DB を立てずに SQL テキストを読み、 必須テーブル定義・CHECK・UNIQUE・
RLS POLICY 行が含まれているかを確認する。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGS = ROOT / "supabase" / "migrations"


def read(name: str) -> str:
    return (MIGS / name).read_text()


# ─────────────────────────────────────────────────────────
# T-001-02: 認証 6 テーブル
# ─────────────────────────────────────────────────────────
AUTH_TABLES = [
    "users", "auth_sessions", "user_2fa_secrets",
    "user_2fa_recovery_codes", "oauth_connections", "auth_audit_log",
]


def test_auth_migration_creates_6_tables() -> None:
    """AC UBIQUITOUS: 6 auth tables の CREATE TABLE IF NOT EXISTS"""
    src = read("20260510000000_auth_tables.sql")
    for t in AUTH_TABLES:
        assert re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{t}\b", src, re.IGNORECASE,
        ), f"{t} CREATE TABLE missing"


def test_auth_migration_oauth_connections_unique() -> None:
    """AC UNWANTED: oauth_connections に (user_id, provider) UNIQUE"""
    src = read("20260510000000_auth_tables.sql")
    # oauth_connections の DDL ブロックを抽出
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+oauth_connections\s*\((.*?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert m, "oauth_connections DDL not found"
    body = m.group(1)
    has_unique = bool(re.search(
        r"UNIQUE\s*\(\s*user_id\s*,\s*provider\s*\)", body, re.IGNORECASE,
    )) or bool(re.search(
        r"UNIQUE\s*\(\s*provider\s*,\s*user_id\s*\)", body, re.IGNORECASE,
    ))
    assert has_unique, "UNIQUE (user_id, provider) constraint missing"


def test_auth_migration_rls_enabled_on_4_tables() -> None:
    """AC STATE: 4 テーブルに RLS enable"""
    src = read("20260510000000_auth_tables.sql")
    for t in ("auth_sessions", "user_2fa_secrets", "user_2fa_recovery_codes", "oauth_connections"):
        assert re.search(
            rf"ALTER TABLE\s+{t}\s+ENABLE ROW LEVEL SECURITY", src, re.IGNORECASE,
        ), f"RLS not enabled on {t}"


# ─────────────────────────────────────────────────────────
# T-001-04: BF 11 テーブル
# ─────────────────────────────────────────────────────────
BF_TABLES = [
    "bf_projects", "bf_phases", "bf_features", "bf_tasks",
    "bf_task_dependencies", "bf_acceptance_criteria",
    "bf_constitutions", "bf_constitution_revisions",
    "bf_mocks", "bf_deliveries", "audit_logs",
]


def test_bf_migration_creates_11_tables() -> None:
    """AC UBIQUITOUS: 11 BF tables の CREATE TABLE IF NOT EXISTS"""
    src = read("20260510000001_bf_project_tables.sql")
    for t in BF_TABLES:
        assert re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{t}\b", src, re.IGNORECASE,
        ), f"{t} CREATE TABLE missing"


def test_bf_migration_ears_type_check() -> None:
    """AC UNWANTED: bf_acceptance_criteria.ears_type に CHECK 制約"""
    src = read("20260510000001_bf_project_tables.sql")
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_acceptance_criteria\s*\((.*?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert m, "bf_acceptance_criteria DDL not found"
    body = m.group(1)
    # CHECK にすべての 5 EARS type が含まれる
    for ears in ("UBIQUITOUS", "EVENT", "STATE", "OPTIONAL", "UNWANTED"):
        assert ears in body, f"EARS type {ears} not in bf_acceptance_criteria CHECK"


def test_bf_migration_constitution_principles_jsonb() -> None:
    """AC OPTIONAL: bf_constitutions.principles is JSONB (with CHECK)"""
    src = read("20260510000001_bf_project_tables.sql")
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitutions\s*\((.*?)\);",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert m, "bf_constitutions DDL not found"
    body = m.group(1)
    assert "principles" in body.lower()
    assert "jsonb" in body.lower()


# ─────────────────────────────────────────────────────────
# T-001-06: RLS 全テーブル enable
# ─────────────────────────────────────────────────────────
def test_rls_full_enforcement_covers_43_user_data_tables() -> None:
    """AC UBIQUITOUS: 全 supabase migration を通じて 43 user-data tables に RLS"""
    total = 0
    for f in MIGS.glob("*.sql"):
        src = f.read_text()
        total += len(re.findall(
            r"ALTER TABLE\s+(\w+)\s+ENABLE ROW LEVEL SECURITY", src, re.IGNORECASE,
        ))
    assert total >= 43, f"expected >= 43 RLS enables across migrations, got {total}"


def test_rls_full_enforcement_covers_workspace_members() -> None:
    """AC STATE: workspace_members に RLS"""
    src = read("20260510000002_rls_full_enforcement.sql")
    assert re.search(
        r"ALTER TABLE\s+workspace_members\s+ENABLE ROW LEVEL SECURITY", src, re.IGNORECASE,
    )


def test_rls_full_enforcement_has_service_role_bypass() -> None:
    """AC STATE: service_role 経由は bypass (= service_role を USING true で許可)"""
    src = read("20260510000002_rls_full_enforcement.sql")
    # service_role を含む CREATE POLICY 行
    assert re.search(r"CREATE POLICY.*service_role", src, re.IGNORECASE | re.DOTALL)


# ─────────────────────────────────────────────────────────
# T-019-01: ARCHIVE (onlook / penpot 削除)
# ─────────────────────────────────────────────────────────
def test_onlook_directory_absent() -> None:
    """AC UBIQUITOUS: onlook/ ディレクトリは存在しない"""
    assert not (ROOT / "onlook").exists(), "onlook/ still present"


def test_penpot_directory_absent() -> None:
    """AC UBIQUITOUS: penpot/ ディレクトリは存在しない"""
    assert not (ROOT / "penpot").exists(), "penpot/ still present"


def test_frontend_no_onlook_components() -> None:
    """AC STATE: frontend/src/components/onlook が存在しない"""
    assert not (ROOT / "frontend" / "src" / "components" / "onlook").exists()


def test_no_onlook_imports_in_frontend() -> None:
    """AC UNWANTED: onlook の import が残っていない"""
    frontend_src = ROOT / "frontend" / "src"
    if not frontend_src.exists():
        pytest.skip("frontend/src not found")
    for f in frontend_src.rglob("*.ts*"):
        text = f.read_text(errors="ignore")
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if "import" in stripped and "onlook" in stripped.lower():
                pytest.fail(f"{f}: onlook import remains: {stripped}")


def test_backend_no_onlook_modules() -> None:
    """AC STATE: backend に onlook モジュール参照なし (テストファイル自身は除外)"""
    backend = ROOT / "backend"
    for f in backend.rglob("*.py"):
        # self-exclusion: テストファイル自身は "onlook" を関数名・コメントで参照する
        if f.name.startswith("test_supabase_migrations"):
            continue
        text = f.read_text(errors="ignore")
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if ("import" in stripped or "from " in stripped) and "onlook" in stripped.lower():
                pytest.fail(f"{f}: onlook import remains: {stripped}")
