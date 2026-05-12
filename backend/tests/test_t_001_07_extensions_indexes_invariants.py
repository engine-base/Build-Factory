"""T-001-07: 拡張機能 4 + 100+ index — 5 AC.

PR #62 で production artifact 完成済 (20260501220100_pgvector.sql で
vector + pg_trgm / 20260512100000_extensions_pgsodium_pgcron_indexes.sql
で pgsodium + pg_cron + 20 GIN/BRIN/partial indexes).

AC マッピング:
  AC-1: 4 extensions + 全 migration 計 >= 150 CREATE INDEX.
  AC-2: 全 EXTENSION/INDEX IF NOT EXISTS / GIN >= 3 / BRIN >= 3 / partial >= 3.
  AC-3: extensions の機能対応 / no DROP EXTENSION.
  AC-4: USING gin / USING brin / WHERE で適切な index type.
  AC-5: no DROP EXTENSION / no hardcoded secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PGVECTOR_MIG = REPO_ROOT / "supabase" / "migrations" / "20260501220100_pgvector.sql"
EXT_INDEX_MIG = REPO_ROOT / "supabase" / "migrations" / "20260512100000_extensions_pgsodium_pgcron_indexes.sql"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture(scope="module")
def pgvector_sql():
    return PGVECTOR_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ext_index_sql():
    return EXT_INDEX_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def all_migrations_text():
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in MIGRATIONS_DIR.glob("*.sql")
    )


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 4 extensions + >= 150 indexes
# ══════════════════════════════════════════════════════════════════════


def test_ac1_pgvector_migration_exists():
    assert PGVECTOR_MIG.exists()


def test_ac1_ext_index_migration_exists():
    assert EXT_INDEX_MIG.exists()


def test_ac1_vector_extension_in_pgvector_migration(pgvector_sql):
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+vector",
        pgvector_sql,
    )


def test_ac1_pg_trgm_in_pgvector_migration(pgvector_sql):
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+pg_trgm",
        pgvector_sql,
    )


def test_ac1_pgsodium_in_ext_index_migration(ext_index_sql):
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+pgsodium",
        ext_index_sql,
    )


def test_ac1_pg_cron_in_ext_index_migration(ext_index_sql):
    assert re.search(
        r"CREATE EXTENSION IF NOT EXISTS\s+pg_cron",
        ext_index_sql,
    )


def test_ac1_total_index_count_at_least_150(all_migrations_text):
    """全 migrations に CREATE INDEX が >= 150."""
    matches = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF NOT EXISTS\s+)?\w+",
        all_migrations_text,
    )
    assert len(matches) >= 150, (
        f"expected >= 150 CREATE INDEX total, got {len(matches)}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — idempotent + GIN/BRIN/partial counts
# ══════════════════════════════════════════════════════════════════════


def _strip_sql_comments(src: str) -> str:
    """SQL の `--` 行コメントを除去 (header docs に CREATE EXTENSION
    が hint として書かれていても誤検出しないように)."""
    out = []
    for line in src.splitlines():
        # `--` 以降を削除 (ただし quote 内は無視 / 簡易)
        if "--" in line:
            line = line.split("--", 1)[0]
        out.append(line)
    return "\n".join(out)


def test_ac2_all_create_extension_idempotent(ext_index_sql, pgvector_sql):
    for src, name in ((ext_index_sql, "ext_index"), (pgvector_sql, "pgvector")):
        code = _strip_sql_comments(src)
        no_if = re.findall(
            r"CREATE EXTENSION\s+(?!IF NOT EXISTS)(\w+)",
            code,
        )
        assert not no_if, f"non-idempotent EXTENSION in {name}: {no_if}"


def test_ac2_all_create_index_idempotent_in_ext_migration(ext_index_sql):
    no_if = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF NOT EXISTS)(\w+)",
        ext_index_sql,
    )
    assert not no_if, f"non-idempotent INDEX: {no_if}"


def test_ac2_at_least_3_gin_indexes(ext_index_sql):
    """USING gin 指定の index が >= 3 (JSONB / text array)."""
    matches = re.findall(r"USING\s+gin\b", ext_index_sql, re.IGNORECASE)
    assert len(matches) >= 3, (
        f"expected >= 3 GIN indexes, got {len(matches)}"
    )


def test_ac2_at_least_3_brin_indexes(ext_index_sql):
    matches = re.findall(r"USING\s+brin\b", ext_index_sql, re.IGNORECASE)
    assert len(matches) >= 3, (
        f"expected >= 3 BRIN indexes, got {len(matches)}"
    )


def test_ac2_at_least_3_partial_indexes(ext_index_sql):
    """CREATE INDEX ... WHERE pattern."""
    matches = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX[^;]+WHERE\s+",
        ext_index_sql,
        re.DOTALL,
    )
    assert len(matches) >= 3, (
        f"expected >= 3 partial indexes, got {len(matches)}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — extensions enable functionality / no DROP EXTENSION
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_drop_extension_in_either_migration(ext_index_sql, pgvector_sql):
    for src in (ext_index_sql, pgvector_sql):
        assert "DROP EXTENSION" not in src


def test_ac3_pgvector_used_for_embedding(all_migrations_text):
    """vector(N) 型を使う column が少なくとも 1 つある."""
    assert re.search(r"\bvector\s*\(\s*\d+\s*\)", all_migrations_text)


def test_ac3_pg_trgm_used_for_similarity(all_migrations_text):
    """gin_trgm_ops or similar pg_trgm 関連 op."""
    assert (
        "gin_trgm_ops" in all_migrations_text
        or "trigram" in all_migrations_text.lower()
        or "% " in all_migrations_text  # trigram similarity %
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — index type appropriate use
# ══════════════════════════════════════════════════════════════════════


def test_ac4_gin_indexes_target_jsonb(ext_index_sql):
    """GIN index は JSONB / array column を対象."""
    # CREATE INDEX ... USING gin (col)
    gin_blocks = re.findall(
        r"CREATE INDEX[^;]+USING\s+gin\s*\([^)]+\)",
        ext_index_sql,
        re.IGNORECASE,
    )
    assert len(gin_blocks) >= 3
    # 少なくとも 1 つに jsonb 関連 column 名がある (e.g. _gin suffix)
    has_jsonb_target = any(
        "principles" in b.lower() or "detail" in b.lower()
        or "metadata" in b.lower() or "payload" in b.lower()
        or "settings" in b.lower() or "flags" in b.lower()
        for b in gin_blocks
    )
    assert has_jsonb_target


def test_ac4_brin_indexes_target_timestamp(ext_index_sql):
    """BRIN index は append-only timestamp column を対象."""
    brin_blocks = re.findall(
        r"CREATE INDEX[^;]+USING\s+brin\s*\([^)]+\)",
        ext_index_sql,
        re.IGNORECASE,
    )
    assert len(brin_blocks) >= 3
    has_ts = any(
        "_at" in b.lower() or "occurred" in b.lower()
        or "created" in b.lower()
        for b in brin_blocks
    )
    assert has_ts


def test_ac4_partial_indexes_use_where(ext_index_sql):
    partial_blocks = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX[^;]+WHERE\s+[^;]+",
        ext_index_sql,
        re.DOTALL,
    )
    assert len(partial_blocks) >= 3


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — no DROP EXTENSION / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_no_create_extension_without_if_not_exists(ext_index_sql, pgvector_sql):
    for src in (ext_index_sql, pgvector_sql):
        code = _strip_sql_comments(src)
        no_if = re.findall(
            r"CREATE EXTENSION\s+(?!IF NOT EXISTS)(\w+)",
            code,
        )
        assert not no_if, f"non-idempotent: {no_if}"


def test_ac5_no_drop_extension():
    for path in (PGVECTOR_MIG, EXT_INDEX_MIG):
        src = path.read_text(encoding="utf-8")
        assert "DROP EXTENSION" not in src


def test_ac5_no_hardcoded_jwt():
    for path in (PGVECTOR_MIG, EXT_INDEX_MIG):
        src = path.read_text(encoding="utf-8")
        assert not re.search(
            r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.",
            src,
        )


def test_ac5_no_hardcoded_supabase_or_anthropic_keys():
    for path in (PGVECTOR_MIG, EXT_INDEX_MIG):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_07_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-07"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_07_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-07"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "supabase/migrations/20260501220100_pgvector.sql" in files
    assert any("20260512100000" in f for f in files)


def test_tickets_t_001_07_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-07"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "20260501220100_pgvector.sql",
        "20260512100000_extensions_pgsodium_pgcron_indexes.sql",
        "vector", "pg_trgm", "pgsodium", "pg_cron",
        "GIN", "BRIN", "partial",
        "DROP EXTENSION",
    ):
        assert sym in full, f"T-001-07 AC missing: {sym}"
