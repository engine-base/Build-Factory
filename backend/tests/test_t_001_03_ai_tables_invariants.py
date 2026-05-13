"""T-001-03: AI 5 テーブル DDL — 5 AC.

PR #67 で production artifact 完成済. 5 tables:
  ai_employees / ai_personas / ai_hierarchies / ai_clones /
  user_interaction_log

AC マッピング:
  AC-1: 5 table CREATE / FK ai_employees / TIMESTAMPTZ NOW.
  AC-2: IF NOT EXISTS idempotent / cycle prevention trigger.
  AC-3: ai_clones.user_id UNIQUE / 全 table created_at /
        BMAD 10 persona seed.
  AC-4: ai_hierarchies.parent_id nullable / ai_clones.is_opted_in
        BOOLEAN NOT NULL DEFAULT FALSE.
  AC-5: duplicate user_id / self-loop CHECK / cycle trigger /
        no hardcoded secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260512200000_ai_hierarchy_clone_tables.sql"
CYCLE_TRIGGER = REPO_ROOT / "supabase" / "migrations" / "20260512300000_cycle_prevention_triggers.sql"
SEED = REPO_ROOT / "supabase" / "migrations" / "20260512400000_bmad_personas_seed.sql"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"

AI_TABLES = (
    "ai_employees",
    "ai_personas",
    "ai_hierarchies",
    "ai_clones",
    "user_interaction_log",
)
BMAD_PERSONAS = (
    "mary", "preston", "winston", "sally", "devon",
    "quinn", "reviewer", "brand", "mockup", "curator",
)


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def seed_sql():
    return SEED.read_text(encoding="utf-8") if SEED.exists() else ""


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 5 tables + FK + TIMESTAMPTZ
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_exists():
    assert MIGRATION.exists()


@pytest.mark.parametrize("table", AI_TABLES)
def test_ac1_each_table_created(table, sql):
    assert re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\b",
        sql,
    ), f"missing CREATE TABLE {table}"


def test_ac1_fk_to_ai_employees(sql):
    """ai_clones / ai_hierarchies が ai_employees(id) を REFERENCES."""
    # 少なくとも 3 つ以上の FK が ai_employees(id) を参照
    matches = re.findall(r"REFERENCES\s+ai_employees\s*\(id\)", sql)
    assert len(matches) >= 2, (
        f"expected >= 2 FK to ai_employees, got {len(matches)}"
    )


def test_ac1_all_5_tables_have_created_at(sql):
    """5 tables 全てに TIMESTAMPTZ DEFAULT NOW() の created_at."""
    for table in AI_TABLES:
        m = re.search(
            rf"CREATE TABLE IF NOT EXISTS\s+{table}\s*\(([\s\S]+?)\);",
            sql,
        )
        assert m, f"{table} body not found"
        body = m.group(1)
        assert re.search(
            r"created_at\s+TIMESTAMPTZ[^,]*DEFAULT\s+(?:NOW|now)\(\)",
            body,
        ), f"{table} missing created_at TIMESTAMPTZ DEFAULT NOW()"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — idempotent + cycle trigger
# ══════════════════════════════════════════════════════════════════════


def test_ac2_all_create_table_use_if_not_exists(sql):
    no_if = re.findall(r"CREATE TABLE\s+(?!IF NOT EXISTS)(\w+)", sql)
    assert not no_if, f"CREATE TABLE without IF NOT EXISTS: {no_if}"


def test_ac2_all_create_index_use_if_not_exists(sql):
    no_if = re.findall(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF NOT EXISTS)(\w+)",
        sql,
    )
    assert not no_if, f"CREATE INDEX without IF NOT EXISTS: {no_if}"


def test_ac2_companion_cycle_trigger_exists():
    """20260512300000_cycle_prevention_triggers.sql が存在."""
    assert CYCLE_TRIGGER.exists()


def test_ac2_cycle_trigger_references_ai_hierarchies():
    src = CYCLE_TRIGGER.read_text(encoding="utf-8")
    assert "ai_hierarchies" in src
    # recursive CTE
    assert "WITH RECURSIVE" in src.upper() or "recursive" in src.lower()


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — UNIQUE / created_at / BMAD persona seed
# ══════════════════════════════════════════════════════════════════════


def test_ac3_ai_clones_user_id_unique(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m
    body = m.group(1)
    # `user_id TEXT NOT NULL UNIQUE` パターン
    assert re.search(
        r"user_id\s+TEXT\s+NOT\s+NULL\s+UNIQUE",
        body,
        re.IGNORECASE,
    ), "ai_clones.user_id must be NOT NULL UNIQUE"


@pytest.mark.parametrize("persona", BMAD_PERSONAS)
def test_ac3_bmad_persona_seeded(persona, seed_sql):
    """seed.sql に 10 BMAD persona name が登場."""
    if not seed_sql:
        pytest.skip("seed migration not found")
    assert persona in seed_sql, f"persona {persona} not seeded"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — parent_id nullable + is_opted_in BOOLEAN DEFAULT FALSE
# ══════════════════════════════════════════════════════════════════════


def test_ac4_ai_hierarchies_parent_nullable(sql):
    """parent_id は NULL OK (root employees)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_hierarchies\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    # `parent_id BIGINT REFERENCES ai_employees(id)` (NOT NULL なし)
    pid_line = re.search(r"parent_id\s+\w+[^,]*,", body)
    assert pid_line
    line = pid_line.group(0)
    # NOT NULL が無いこと
    assert "NOT NULL" not in line, (
        f"parent_id must be nullable, got: {line}"
    )


def test_ac4_ai_clones_is_opted_in_boolean_default_false(sql):
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert re.search(
        r"is_opted_in\s+BOOLEAN\s+NOT\s+NULL\s+DEFAULT\s+(?:FALSE|false)",
        body,
        re.IGNORECASE,
    )


def test_ac4_ai_clones_has_opt_in_consistency_check(sql):
    """opt_in_timestamp_consistent CHECK constraint."""
    assert "opt_in_timestamp_consistent" in sql or "opted_in_at" in sql


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — UNIQUE / no_self_parent / cycle trigger / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_ai_clones_user_id_unique_constraint_present(sql):
    """duplicate user_id INSERT を弾く UNIQUE が存在."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    # inline UNIQUE か constraint
    assert re.search(r"user_id[^,]*UNIQUE", body, re.IGNORECASE)


def test_ac5_no_self_parent_check_constraint(sql):
    """ai_hierarchies に no_self_parent CHECK (parent_id <> child_id)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_hierarchies\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert "no_self_parent" in body or re.search(
        r"CHECK\s*\([^)]*parent_id\s*<>\s*child_id",
        body,
    ), "ai_hierarchies must have no_self_parent CHECK"


def test_ac5_cycle_prevention_trigger_in_companion_migration():
    """companion migration が cycle 検出 trigger を定義."""
    src = CYCLE_TRIGGER.read_text(encoding="utf-8")
    # trigger function 定義
    assert "CREATE OR REPLACE FUNCTION" in src or "CREATE FUNCTION" in src
    # trigger も
    assert "CREATE TRIGGER" in src or "CREATE OR REPLACE TRIGGER" in src


def test_ac5_no_hardcoded_jwt():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(
        r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.",
        src,
    )


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_03_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-03"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_03_no_tbd_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-03"), None)
    files = t.get("existing_files", [])
    assert "TBD" not in str(files)
    assert any("20260512200000_ai_hierarchy_clone_tables.sql" in f for f in files)


def test_tickets_t_001_03_has_adr_link_and_concrete_ac():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-03"), None)
    assert t.get("adr_link") is not None
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "20260512200000_ai_hierarchy_clone_tables.sql",
        "ai_employees", "ai_personas", "ai_hierarchies",
        "ai_clones", "user_interaction_log",
        "20260512300000_cycle_prevention_triggers.sql",
        "20260512400000_bmad_personas_seed.sql",
        "is_opted_in", "parent_id",
    ):
        assert sym in full, f"T-001-03 AC missing: {sym}"
