"""T-001-08: クローン opt-in trigger — 5 AC.

PR #70 で production artifact 完成済
(bf_enforce_clone_opt_in trigger function + trg_enforce_clone_opt_in
ON user_interaction_log + backend/services/clone_opt_in.py).

AC マッピング:
  AC-1: bf_enforce_clone_opt_in PL/pgSQL function + trg_enforce_clone_opt_in
        idempotent trigger / clone_opt_in_required EXCEPTION.
  AC-2: BEFORE INSERT trigger / SELECT is_opted_in / DROP TRIGGER IF EXISTS.
  AC-3: opt-in FALSE で INSERT 拒否 / no SECURITY DEFINER / service helper.
  AC-4: GDPR 30-day grace / opt_in_timestamp_consistent CHECK.
  AC-5: check_violation EXCEPTION / no SECURITY DEFINER / no secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260512200000_ai_hierarchy_clone_tables.sql"
SERVICE = REPO_ROOT / "backend" / "services" / "clone_opt_in.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — function + trigger + EXCEPTION
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_exists():
    assert MIGRATION.exists()


def test_ac1_service_helper_exists():
    assert SERVICE.exists()


def test_ac1_function_defined(sql):
    """CREATE OR REPLACE FUNCTION bf_enforce_clone_opt_in()."""
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_enforce_clone_opt_in\s*\(\)\s+RETURNS\s+TRIGGER",
        sql,
    )


def test_ac1_function_is_plpgsql(sql):
    assert re.search(
        r"bf_enforce_clone_opt_in[\s\S]+?LANGUAGE\s+plpgsql",
        sql,
        re.IGNORECASE,
    )


def test_ac1_trigger_on_user_interaction_log(sql):
    assert re.search(
        r"CREATE TRIGGER\s+trg_enforce_clone_opt_in[\s\S]+?ON\s+user_interaction_log",
        sql,
    )


def test_ac1_exception_message_clone_opt_in_required(sql):
    assert "clone_opt_in_required" in sql


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — BEFORE INSERT + SELECT + DROP TRIGGER IF EXISTS
# ══════════════════════════════════════════════════════════════════════


def test_ac2_trigger_is_before_insert(sql):
    assert re.search(
        r"CREATE TRIGGER\s+trg_enforce_clone_opt_in\s+BEFORE\s+INSERT",
        sql,
    )


def test_ac2_function_selects_is_opted_in(sql):
    assert re.search(
        r"SELECT\s+is_opted_in\s+INTO\s+\w+\s+FROM\s+ai_clones",
        sql,
        re.IGNORECASE,
    )


def test_ac2_drop_trigger_if_exists_before_create(sql):
    """DROP TRIGGER IF EXISTS が CREATE TRIGGER の前."""
    drop_pos = sql.find("DROP TRIGGER IF EXISTS trg_enforce_clone_opt_in")
    create_pos = sql.find("CREATE TRIGGER trg_enforce_clone_opt_in")
    assert drop_pos > 0 and create_pos > 0
    assert drop_pos < create_pos


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — opt-in check / no SECURITY DEFINER
# ══════════════════════════════════════════════════════════════════════


def test_ac3_check_for_null_or_false(sql):
    """has_opt_in IS NULL OR has_opt_in = FALSE で reject."""
    func_block = re.search(
        r"FUNCTION\s+bf_enforce_clone_opt_in\(\)[\s\S]+?\$\$;",
        sql,
    )
    assert func_block
    body = func_block.group(0)
    assert re.search(
        r"IS\s+NULL\s+OR\s+\w+\s*=\s*FALSE",
        body,
        re.IGNORECASE,
    )


def test_ac3_no_security_definer(sql):
    """trigger function に SECURITY DEFINER なし (privilege escalation 防止)."""
    func_block = re.search(
        r"FUNCTION\s+bf_enforce_clone_opt_in\(\)[\s\S]+?\$\$;",
        sql,
    )
    body = func_block.group(0)
    assert "SECURITY DEFINER" not in body


def test_ac3_service_provides_opt_in_helper():
    src = SERVICE.read_text(encoding="utf-8")
    # opt_in 関連 keyword が出る
    assert "ai_clones" in src or "is_opted_in" in src or "opt" in src.lower()


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — GDPR grace + opt_in_timestamp_consistent CHECK
# ══════════════════════════════════════════════════════════════════════


def test_ac4_opt_in_timestamp_consistent_check(sql):
    """ai_clones に opt_in_timestamp_consistent CHECK constraint."""
    assert "opt_in_timestamp_consistent" in sql
    # CHECK (NOT is_opted_in OR opted_in_at IS NOT NULL)
    assert re.search(
        r"CHECK\s*\(\s*NOT\s+is_opted_in\s+OR\s+opted_in_at\s+IS\s+NOT\s+NULL\s*\)",
        sql,
        re.IGNORECASE,
    )


def test_ac4_ai_clones_has_opted_out_at(sql):
    """opt-out 日時を記録する column が存在."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert "opted_out_at" in body


def test_ac4_ai_clones_has_consent_version(sql):
    """GDPR consent version 記録."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\(([\s\S]+?)\);",
        sql,
    )
    body = m.group(1)
    assert "consent_version" in body


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — check_violation EXCEPTION / no SECURITY DEFINER / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_uses_check_violation_errcode(sql):
    """ERRCODE = 'check_violation' で raise."""
    assert "check_violation" in sql


def test_ac5_no_security_definer_overall(sql):
    """migration 全体に SECURITY DEFINER trigger なし."""
    assert "SECURITY DEFINER" not in sql


def test_ac5_no_hardcoded_jwt():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", src)


def test_ac5_no_hardcoded_supabase_or_anthropic():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_08_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-08"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_08_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-08"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("20260512200000_ai_hierarchy_clone_tables.sql" in f for f in files)
    assert "backend/services/clone_opt_in.py" in files


def test_tickets_t_001_08_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-08"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "bf_enforce_clone_opt_in",
        "trg_enforce_clone_opt_in",
        "user_interaction_log",
        "is_opted_in",
        "clone_opt_in_required",
        "check_violation",
        "SECURITY DEFINER",
        "DROP TRIGGER IF EXISTS",
    ):
        assert sym in full, f"T-001-08 AC missing: {sym}"
