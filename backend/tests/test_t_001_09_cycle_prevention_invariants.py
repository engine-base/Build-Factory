"""T-001-09: 循環依存防止 trigger 2 種 — 5 AC.

production artifact:
  supabase/migrations/20260512300000_cycle_prevention_triggers.sql
  - bf_prevent_task_dep_cycle()      ON bf_task_dependencies
  - bf_prevent_ai_hierarchy_cycle()  ON ai_hierarchies

AC マッピング:
  AC-1: 2 function + 2 trigger / WITH RECURSIVE / cycle_detected EXCEPTION.
  AC-2: BEFORE INSERT/UPDATE / DROP TRIGGER IF EXISTS idempotent /
        check_violation errcode.
  AC-3: LANGUAGE plpgsql / no SECURITY DEFINER / IF EXISTS guards.
  AC-4: self-loop early-exit / bounded CTE depth.
  AC-5: cyclic INSERT で EXCEPTION / no SECURITY DEFINER / no secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260512300000_cycle_prevention_triggers.sql"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture(scope="module")
def sql():
    return MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 2 functions + 2 triggers + recursive CTE
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_exists():
    assert MIGRATION.exists()


def test_ac1_task_dep_cycle_function_defined(sql):
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_task_dep_cycle\s*\(\)\s+RETURNS\s+TRIGGER",
        sql,
    )


def test_ac1_ai_hierarchy_cycle_function_defined(sql):
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_ai_hierarchy_cycle\s*\(\)\s+RETURNS\s+TRIGGER",
        sql,
    )


def test_ac1_task_dep_trigger_attached(sql):
    assert re.search(
        r"CREATE TRIGGER\s+trg_prevent_task_dep_cycle[\s\S]+?ON\s+bf_task_dependencies",
        sql,
    )


def test_ac1_ai_hierarchy_trigger_attached(sql):
    assert re.search(
        r"CREATE TRIGGER\s+trg_prevent_ai_hierarchy_cycle[\s\S]+?ON\s+ai_hierarchies",
        sql,
    )


def test_ac1_both_functions_use_with_recursive(sql):
    matches = re.findall(r"WITH\s+RECURSIVE\b", sql, re.IGNORECASE)
    assert len(matches) >= 2, (
        f"expected WITH RECURSIVE in both functions, got {len(matches)}"
    )


def test_ac1_cycle_detected_exception_message(sql):
    """EXCEPTION message が cycle_detected: で始まる."""
    matches = re.findall(r"'cycle_detected:", sql)
    assert len(matches) >= 2, (
        f"expected cycle_detected: in both functions, got {len(matches)}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — BEFORE INSERT/UPDATE + idempotent + check_violation
# ══════════════════════════════════════════════════════════════════════


def test_ac2_task_dep_trigger_is_before(sql):
    """BEFORE INSERT (or UPDATE) on bf_task_dependencies."""
    m = re.search(
        r"CREATE TRIGGER\s+trg_prevent_task_dep_cycle\s+BEFORE\s+(INSERT|UPDATE)",
        sql,
    )
    assert m


def test_ac2_ai_hierarchy_trigger_is_before(sql):
    m = re.search(
        r"CREATE TRIGGER\s+trg_prevent_ai_hierarchy_cycle\s+BEFORE\s+(INSERT|UPDATE)",
        sql,
    )
    assert m


def test_ac2_drop_trigger_if_exists_before_create(sql):
    """両 trigger に DROP IF EXISTS が CREATE の前."""
    for trg in ("trg_prevent_task_dep_cycle", "trg_prevent_ai_hierarchy_cycle"):
        drop_pos = sql.find(f"DROP TRIGGER IF EXISTS {trg}")
        create_pos = sql.find(f"CREATE TRIGGER {trg}")
        assert drop_pos > 0 and create_pos > 0
        assert drop_pos < create_pos, f"{trg}: DROP must precede CREATE"


def test_ac2_check_violation_errcode_used(sql):
    """ERRCODE = 'check_violation' で raise."""
    assert "check_violation" in sql


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — plpgsql / no SECURITY DEFINER / IF EXISTS
# ══════════════════════════════════════════════════════════════════════


def test_ac3_functions_are_plpgsql(sql):
    """両 function が LANGUAGE plpgsql."""
    matches = re.findall(r"LANGUAGE\s+plpgsql", sql, re.IGNORECASE)
    assert len(matches) >= 2


def test_ac3_no_security_definer(sql):
    """trigger function に SECURITY DEFINER なし."""
    assert "SECURITY DEFINER" not in sql


def test_ac3_drop_trigger_uses_if_exists(sql):
    """DROP TRIGGER は IF EXISTS で idempotent."""
    bare_drops = re.findall(
        r"DROP TRIGGER\s+(?!IF EXISTS)(\w+)",
        sql,
    )
    assert not bare_drops, f"bare DROP TRIGGER: {bare_drops}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — self-loop early-exit + bounded CTE
# ══════════════════════════════════════════════════════════════════════


def test_ac4_self_loop_early_exit_task_dep(sql):
    """task_id = depends_on_task_id の early-exit check.

    function body は $$ ... $$; で囲まれる. 開始 $$ から終了 $$ までを
    capture して内部の self-loop check を探す.
    """
    # CREATE OR REPLACE FUNCTION ... AS $$ <body> $$;
    func_block = re.search(
        r"FUNCTION\s+bf_prevent_task_dep_cycle\s*\(\s*\)[\s\S]+?AS\s+\$\$([\s\S]+?)\$\$\s*;",
        sql,
    )
    assert func_block, "task_dep function body not found"
    body = func_block.group(1)
    assert re.search(
        r"NEW\.(task_id|depends_on_task_id)\s*=\s*NEW\.(depends_on_task_id|task_id)",
        body,
    )


def test_ac4_self_loop_early_exit_ai_hierarchy(sql):
    func_block = re.search(
        r"FUNCTION\s+bf_prevent_ai_hierarchy_cycle\s*\(\s*\)[\s\S]+?AS\s+\$\$([\s\S]+?)\$\$\s*;",
        sql,
    )
    assert func_block, "ai_hierarchy function body not found"
    body = func_block.group(1)
    assert re.search(
        r"NEW\.(parent_id|child_id)\s*=\s*NEW\.(child_id|parent_id)",
        body,
    )


def test_ac4_recursive_cte_uses_reachable_pattern(sql):
    """WITH RECURSIVE reachable AS (...) pattern."""
    assert re.search(
        r"WITH\s+RECURSIVE\s+reachable\s+AS",
        sql,
        re.IGNORECASE,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — EXCEPTION / no SECURITY DEFINER / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_both_functions_raise_exception(sql):
    """両 function に RAISE EXCEPTION が 2 つ以上 (self-loop + cycle)."""
    matches = re.findall(r"RAISE EXCEPTION", sql)
    assert len(matches) >= 4, (
        f"expected >= 4 RAISE EXCEPTION (2 per function), got {len(matches)}"
    )


def test_ac5_no_security_definer_overall(sql):
    assert "SECURITY DEFINER" not in sql


def test_ac5_no_hardcoded_jwt():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", src)


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    src = MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_09_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-09"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_09_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-09"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("20260512300000_cycle_prevention_triggers.sql" in f for f in files)


def test_tickets_t_001_09_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-09"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "20260512300000_cycle_prevention_triggers.sql",
        "bf_prevent_task_dep_cycle",
        "bf_prevent_ai_hierarchy_cycle",
        "trg_prevent_task_dep_cycle",
        "trg_prevent_ai_hierarchy_cycle",
        "WITH RECURSIVE",
        "cycle_detected",
        "check_violation",
        "SECURITY DEFINER",
    ):
        assert sym in full, f"T-001-09 AC missing: {sym}"
