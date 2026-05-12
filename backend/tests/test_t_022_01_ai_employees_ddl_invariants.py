"""T-022-01: ai_employees DDL 拡張確認 — 5 AC.

Production artifact 完成済
(supabase/migrations/20260512200000_ai_hierarchy_clone_tables.sql +
20260512400000_bmad_personas_seed.sql).
本 module は **spec contract layer** (静的 SQL 解析).

AC マッピング:
  AC-1 UBIQUITOUS    : 5 CREATE TABLE IF NOT EXISTS + role_level
                       CHECK + UNIQUE + relation_type CHECK +
                       opt_in_timestamp_consistent + interaction_type
                       CHECK + embedding_status CHECK.
  AC-2 EVENT-DRIVEN  : seed file inserts 10 BMAD persona keys + ON
                       CONFLICT DO NOTHING + schema_versions INSERT.
  AC-3 STATE-DRIVEN  : persona_id FK late-bind via DO $$ + partial
                       index ix_ai_employees_ws WHERE is_active=TRUE.
  AC-4 OPTIONAL      : workspace_id IS NULL の RLS bypass / trigger
                       trg_enforce_clone_opt_in.
  AC-5 UNWANTED      : bf_enforce_clone_opt_in RAISE EXCEPTION
                       check_violation / RLS ENABLED on all 5 tables /
                       no hardcoded secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DDL = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260512200000_ai_hierarchy_clone_tables.sql"
)
SEED = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260512400000_bmad_personas_seed.sql"
)
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


def _strip_sql_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"--[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 5 CREATE TABLE + CHECK / UNIQUE constraints
# ══════════════════════════════════════════════════════════════════════


def test_ac1_ddl_file_exists():
    assert DDL.exists()


def test_ac1_seed_file_exists():
    assert SEED.exists()


def test_ac1_five_tables_idempotent_create():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    for tbl in (
        "ai_employees", "ai_personas", "ai_hierarchies",
        "ai_clones", "user_interaction_log",
    ):
        assert re.search(rf"CREATE TABLE IF NOT EXISTS {tbl}\b", src), (
            f"missing CREATE TABLE IF NOT EXISTS {tbl}"
        )


def test_ac1_ai_employees_role_level_check():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    # CHECK (role_level IN ('secretary','leader','member'))
    assert re.search(
        r"CHECK\s*\(\s*role_level\s+IN\s*\(\s*'secretary'\s*,\s*'leader'\s*,\s*'member'\s*\)\s*\)",
        src,
    )


def test_ac1_ai_employees_unique_workspace_key():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    assert "uq_ai_employee_ws_key" in src
    assert re.search(
        r"UNIQUE\s*\(\s*workspace_id\s*,\s*employee_key\s*\)",
        src,
    )


def test_ac1_ai_hierarchies_relation_type_check_and_no_self_parent():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    assert re.search(
        r"relation_type\s+IN[\s\S]*?'reports_to'",
        src,
    )
    assert "no_self_parent" in src
    assert re.search(
        r"parent_id\s+IS\s+NULL\s+OR\s+parent_id\s*<>\s*child_id",
        src,
        re.IGNORECASE,
    )


def test_ac1_ai_clones_opt_in_timestamp_consistent():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    assert "opt_in_timestamp_consistent" in src
    assert re.search(
        r"NOT\s+is_opted_in\s+OR\s+opted_in_at\s+IS\s+NOT\s+NULL",
        src,
        re.IGNORECASE,
    )


def test_ac1_user_interaction_log_interaction_type_check():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    assert re.search(
        r"interaction_type\s+IN[\s\S]*?'decision'",
        src,
    )
    # embedding_status CHECK
    assert re.search(
        r"embedding_status\s+IN[\s\S]*?'pending'",
        src,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — 10 BMAD persona seed + ON CONFLICT DO NOTHING
# ══════════════════════════════════════════════════════════════════════


def test_ac2_seed_ten_bmad_personas():
    src = SEED.read_text(encoding="utf-8")
    for key in (
        "mary", "preston", "winston", "sally", "devon",
        "quinn", "reviewer", "brand", "mockup", "logan",
    ):
        assert re.search(rf"\('{key}'\s*,", src), f"persona seed missing {key}"


def test_ac2_seed_on_conflict_do_nothing():
    src = SEED.read_text(encoding="utf-8")
    assert re.search(r"ON\s+CONFLICT[\s\S]+?DO\s+NOTHING", src, re.IGNORECASE)


def test_ac2_seed_registers_schema_version():
    src = _strip_sql_comments(SEED.read_text(encoding="utf-8"))
    assert re.search(
        r"INSERT\s+INTO\s+schema_versions\s*\(",
        src,
        re.IGNORECASE,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — persona_id FK late-bind + partial index
# ══════════════════════════════════════════════════════════════════════


def test_ac3_persona_fk_late_bind_via_do_block():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    # DO $$ BEGIN ... pg_constraint WHERE conname = 'fk_ai_employees_persona' ...
    assert "fk_ai_employees_persona" in src
    assert re.search(r"DO\s+\$\$", src)
    assert re.search(
        r"FROM\s+pg_constraint\s+WHERE\s+conname\s*=\s*'fk_ai_employees_persona'",
        src,
        re.IGNORECASE,
    )
    assert re.search(
        r"FOREIGN\s+KEY\s*\(\s*persona_id\s*\)\s+REFERENCES\s+ai_personas\s*\(\s*id\s*\)\s+ON\s+DELETE\s+SET\s+NULL",
        src,
        re.IGNORECASE,
    )


def test_ac3_partial_index_is_active_true():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    # CREATE INDEX IF NOT EXISTS ix_ai_employees_ws ON ai_employees(workspace_id) WHERE is_active = TRUE
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+ix_ai_employees_ws\s+ON\s+ai_employees\([^)]+\)\s+WHERE\s+is_active\s*=\s*TRUE",
        src,
        re.IGNORECASE,
    )


def test_ac3_partial_index_retired_at_not_null():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    assert re.search(
        r"ix_ai_employees_retired[\s\S]+?WHERE\s+retired_at\s+IS\s+NOT\s+NULL",
        src,
        re.IGNORECASE,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — workspace_id NULL bypass + clone opt-in trigger
# ══════════════════════════════════════════════════════════════════════


def test_ac4_rls_workspace_null_bypass():
    """workspace_id IS NULL OR bf_can_access_workspace(workspace_id)."""
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    assert re.search(
        r"USING\s*\(\s*workspace_id\s+IS\s+NULL\s+OR\s+bf_can_access_workspace\(\s*workspace_id\s*\)\s*\)",
        src,
        re.IGNORECASE,
    )


def test_ac4_clone_opt_in_trigger_declared():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    assert "trg_enforce_clone_opt_in" in src
    # BEFORE INSERT ON user_interaction_log
    assert re.search(
        r"CREATE\s+TRIGGER\s+trg_enforce_clone_opt_in[\s\S]+?BEFORE\s+INSERT\s+ON\s+user_interaction_log[\s\S]+?EXECUTE\s+FUNCTION\s+bf_enforce_clone_opt_in",
        src,
        re.IGNORECASE,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — RAISE EXCEPTION / RLS ENABLED on all 5 / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_trigger_raises_exception_with_errcode():
    src = DDL.read_text(encoding="utf-8")
    # function body is wrapped in $$ ... $$; capture the inner body
    m = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+bf_enforce_clone_opt_in[\s\S]+?AS\s+\$\$([\s\S]+?)\$\$\s*;",
        src,
        re.IGNORECASE,
    )
    assert m
    body = m.group(1)
    assert "RAISE EXCEPTION" in body
    assert "clone_opt_in_required" in body
    assert "ERRCODE" in body
    assert "check_violation" in body


def test_ac5_rls_enabled_on_all_five_tables():
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    for tbl in (
        "ai_employees", "ai_personas", "ai_hierarchies",
        "ai_clones", "user_interaction_log",
    ):
        assert re.search(
            rf"ALTER\s+TABLE\s+{tbl}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            src,
            re.IGNORECASE,
        ), f"{tbl} missing ENABLE ROW LEVEL SECURITY"


def test_ac5_ai_clones_user_id_auth_uid():
    """ai_clones owner policy: user_id = auth.uid()::text."""
    src = _strip_sql_comments(DDL.read_text(encoding="utf-8"))
    # 2 occurrences: ai_clones + user_interaction_log
    count = len(re.findall(
        r"user_id\s*=\s*auth\.uid\(\)::text",
        src,
    ))
    assert count >= 2, f"expected >= 2 user_id=auth.uid()::text policies, got {count}"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (DDL, SEED):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_022_01_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-022-01"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_022_01_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-022-01"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "TBD: specify in BA review" not in files, "TBD must be replaced"
    assert any("ai_hierarchy_clone_tables.sql" in f for f in files)
    assert any("bmad_personas_seed.sql" in f for f in files)


def test_tickets_t_022_01_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-022-01"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "ai_employees",
        "ai_personas",
        "ai_hierarchies",
        "ai_clones",
        "user_interaction_log",
        "role_level",
        "uq_ai_employee_ws_key",
        "fk_ai_employees_persona",
        "trg_enforce_clone_opt_in",
        "bf_enforce_clone_opt_in",
        "BMAD",
        "schema_versions",
        "bf_can_access_workspace",
    ):
        assert sym in full, f"T-022-01 AC missing: {sym}"
