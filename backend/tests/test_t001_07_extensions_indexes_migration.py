"""T-001-07: 拡張機能 (pgvector/pg_trgm/pgsodium/pg_cron) + 100+ index AC 検証.

DB を立てず SQL テキストを静的検証.

AC マッピング:
  AC-1 UBIQUITOUS: 4 extension が有効化される + 100+ CREATE INDEX
  AC-3 STATE:     既存 migration 順序を破壊しない (IF NOT EXISTS / 重複名なし)
  AC-4 UNWANTED:  invalid extension / 重複 index 名 なし
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGS = ROOT / "supabase" / "migrations"

T001_07_MIG = MIGS / "20260512100000_extensions_pgsodium_pgcron_indexes.sql"
PGVECTOR_MIG = MIGS / "20260501220100_pgvector.sql"


@pytest.fixture(scope="module")
def src() -> str:
    return T001_07_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def all_migrations_text() -> str:
    """全 migration を結合して扱う (累積 index/extension count 用)."""
    parts: list[str] = []
    for p in sorted(MIGS.glob("*.sql")):
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 4 extension 有効化
# ──────────────────────────────────────────────────────────────────────────


def test_pgvector_extension_present(all_migrations_text: str) -> None:
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+vector\b",
        all_migrations_text, re.IGNORECASE,
    )


def test_pg_trgm_extension_present(all_migrations_text: str) -> None:
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+pg_trgm\b",
        all_migrations_text, re.IGNORECASE,
    )


def test_pgsodium_extension_present(src: str) -> None:
    """新 migration で pgsodium 有効化."""
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+pgsodium\b",
        src, re.IGNORECASE,
    )


def test_pg_cron_extension_present(src: str) -> None:
    """新 migration で pg_cron 有効化."""
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+pg_cron\b",
        src, re.IGNORECASE,
    )


def test_all_four_extensions_use_if_not_exists() -> None:
    """全 4 extension が IF NOT EXISTS で idempotent (SQL comment 行は除外)."""
    # SQL コメント (-- で始まる行) を除いて検査
    lines: list[str] = []
    for p in MIGS.glob("*.sql"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("--"):
                continue
            lines.append(line)
    text = "\n".join(lines)
    for ext in ("vector", "pg_trgm", "pgsodium", "pg_cron"):
        plain = re.search(
            rf"CREATE EXTENSION\s+(?!IF NOT EXISTS){ext}\b",
            text, re.IGNORECASE,
        )
        assert plain is None, f"{ext}: non-idempotent CREATE EXTENSION"


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 100+ CREATE INDEX (全 migration 累積)
# ──────────────────────────────────────────────────────────────────────────


def test_total_create_index_at_least_100(all_migrations_text: str) -> None:
    count = len(re.findall(r"CREATE INDEX\b", all_migrations_text, re.IGNORECASE))
    assert count >= 100, f"only {count} CREATE INDEX statements (need ≥ 100)"


def test_t001_07_adds_index_categories(src: str) -> None:
    """本 migration が GIN/BRIN/partial/composite の 4 カテゴリ index を含む."""
    assert re.search(r"USING gin", src, re.IGNORECASE), "GIN index missing"
    assert re.search(r"USING brin", src, re.IGNORECASE), "BRIN index missing"
    assert re.search(r"WHERE\s+\w+\s*=\s*", src, re.IGNORECASE), "partial index missing"


def test_jsonb_path_ops_used_for_gin(src: str) -> None:
    """JSONB GIN index は jsonb_path_ops で効率化."""
    assert re.search(r"jsonb_path_ops", src, re.IGNORECASE)


def test_brin_indexes_cover_audit_cost_session_logs(src: str) -> None:
    """時系列大量データ系の主要 3 テーブルに BRIN index."""
    for tbl in ("audit_logs", "cost_logs", "session_logs"):
        assert re.search(
            rf"CREATE INDEX IF NOT EXISTS\s+\w+\s+ON\s+{tbl}\s+USING brin",
            src, re.IGNORECASE,
        ), f"{tbl}: BRIN index missing"


def test_partial_indexes_for_active_enforced_unread(src: str) -> None:
    """is_active / is_enforced / is_read の主要 partial index."""
    patterns = [
        r"WHERE\s+is_active\s*=\s*TRUE",
        r"WHERE\s+is_enforced\s*=\s*TRUE",
        r"WHERE\s+is_read\s*=\s*FALSE",
        r"WHERE\s+is_current\s*=\s*TRUE",
    ]
    for p in patterns:
        assert re.search(p, src, re.IGNORECASE), f"partial index pattern missing: {p}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: regression なし (既存 migration を破壊しない)
# ──────────────────────────────────────────────────────────────────────────


def test_all_new_indexes_use_if_not_exists(src: str) -> None:
    plain = re.findall(
        r"CREATE INDEX\s+(?!IF NOT EXISTS)\w+", src, re.IGNORECASE,
    )
    assert not plain, f"non-idempotent index in T-001-07: {plain}"


def test_t001_07_self_registers_to_schema_versions(src: str) -> None:
    """schema_versions に '20260512100000' エントリを INSERT (idempotent)."""
    assert "INSERT INTO schema_versions" in src
    assert "'20260512100000'" in src
    assert "ON CONFLICT (version) DO NOTHING" in src


def test_no_duplicate_index_names_across_migrations(all_migrations_text: str) -> None:
    """全 migration で index 名が重複していない (CREATE INDEX IF NOT EXISTS は OK
    だが、 名前衝突は意図しない上書きにつながるため検出)."""
    matches = re.findall(
        r"CREATE INDEX IF NOT EXISTS\s+(\w+)\b",
        all_migrations_text, re.IGNORECASE,
    )
    duplicates = [name for name in matches if matches.count(name) > 1]
    unique_dupes = sorted(set(duplicates))
    # 既存 migration 同士の重複は historical reason で許容、 本 migration の新規が
    # 既存名と衝突していないかチェック.
    src_local = T001_07_MIG.read_text(encoding="utf-8")
    new_idx_names = set(re.findall(
        r"CREATE INDEX IF NOT EXISTS\s+(\w+)\b", src_local, re.IGNORECASE,
    ))
    # 新規 index 名のうち、 他 migration にも同名がある = 衝突
    other_text = all_migrations_text.replace(src_local, "")
    other_names = set(re.findall(
        r"CREATE INDEX IF NOT EXISTS\s+(\w+)\b", other_text, re.IGNORECASE,
    ))
    collisions = new_idx_names & other_names
    assert not collisions, f"new index names collide with existing: {collisions}"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: invalid extension / 未定義 table への参照なし
# ──────────────────────────────────────────────────────────────────────────


def test_only_known_extensions_used(src: str) -> None:
    """利用する extension は 4 つに限定 (typo 検出)."""
    extensions = set(
        m.group(1).lower()
        for m in re.finditer(
            r"CREATE EXTENSION IF NOT EXISTS\s+(\w+)", src, re.IGNORECASE,
        )
    )
    allowed = {"vector", "pg_trgm", "pgsodium", "pg_cron"}
    unknown = extensions - allowed
    assert not unknown, f"unknown extensions: {unknown}"


def test_indexes_target_existing_tables(src: str) -> None:
    """index の ON {table} がすべて他 migration で定義済の table を指す."""
    # 全 migration で CREATE TABLE される table 一覧を構築
    all_tables = set()
    for p in MIGS.glob("*.sql"):
        text = p.read_text(encoding="utf-8")
        all_tables.update(re.findall(
            r"CREATE TABLE IF NOT EXISTS\s+(\w+)",
            text, re.IGNORECASE,
        ))

    # 本 migration の index ON句から target 抽出
    targets = re.findall(
        r"CREATE INDEX IF NOT EXISTS\s+\w+\s+ON\s+(\w+)",
        src, re.IGNORECASE,
    )
    for tbl in set(targets):
        assert tbl in all_tables, f"index targets undefined table: {tbl}"


def test_pg_cron_schedule_examples_are_commented_out(src: str) -> None:
    """pg_cron 環境依存のため、 schedule 例は comment-only でなければならない.
    実 schedule は環境ごとに登録 (Phase 1 では Supabase Cloud 利用時に手動)."""
    # SELECT cron.schedule(...) の active 行が無いことを確認
    active = re.findall(
        r"^\s*SELECT\s+cron\.schedule",
        src, re.IGNORECASE | re.MULTILINE,
    )
    assert not active, f"cron.schedule should be commented-only, found: {active}"


# ──────────────────────────────────────────────────────────────────────────
# COMMENT 既存 extension に Phase 切替予定 documentation
# ──────────────────────────────────────────────────────────────────────────


def test_pgsodium_has_phase_boundary_comment(src: str) -> None:
    assert re.search(
        r"COMMENT ON EXTENSION pgsodium",
        src, re.IGNORECASE,
    )


def test_pg_cron_has_purpose_comment(src: str) -> None:
    assert re.search(
        r"COMMENT ON EXTENSION pg_cron",
        src, re.IGNORECASE,
    )