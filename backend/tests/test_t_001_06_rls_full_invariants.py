"""T-001-06: RLS 全テーブル enforcement — 5 AC.

PR #8 で production artifact 完成済
(supabase/migrations/20260510000002_rls_full_enforcement.sql /
23 ALTER TABLE ENABLE RLS / 40 CREATE POLICY / bf_can_access_workspace
helper / DROP POLICY IF EXISTS idempotent).

AC マッピング:
  AC-1: ≥ 20 ALTER TABLE ENABLE RLS / ≥ 30 CREATE POLICY / helper 参照.
  AC-2: bf_can_access_workspace(workspace_id) で zero-row filter /
        DROP POLICY IF EXISTS idempotent.
  AC-3: no public FOR ALL / no DISABLE ROW LEVEL SECURITY.
  AC-4: account_owner / bf_can_access_workspace 中央化.
  AC-5: no DISABLE RLS / no hardcoded secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RLS_MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260510000002_rls_full_enforcement.sql"
BF_TABLES_MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260510000001_bf_project_tables.sql"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture(scope="module")
def sql():
    return RLS_MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — ≥ 20 ALTER + ≥ 30 CREATE POLICY + helper
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_exists():
    assert RLS_MIGRATION.exists()


def test_ac1_at_least_20_alter_table_enable_rls(sql):
    matches = re.findall(
        r"ALTER TABLE\s+\w+\s+ENABLE ROW LEVEL SECURITY",
        sql,
    )
    assert len(matches) >= 20, (
        f"expected >= 20 ALTER TABLE ENABLE RLS, got {len(matches)}"
    )


def test_ac1_at_least_30_create_policy(sql):
    matches = re.findall(r"CREATE POLICY\b", sql)
    assert len(matches) >= 30, (
        f"expected >= 30 CREATE POLICY, got {len(matches)}"
    )


def test_ac1_bf_can_access_workspace_helper_invoked(sql):
    """RLS policy が bf_can_access_workspace(workspace_id) を invoke."""
    assert "bf_can_access_workspace" in sql
    # USING / WITH CHECK 句で使われる
    assert re.search(
        r"USING\s*\(\s*bf_can_access_workspace",
        sql,
    )


def test_ac1_workspace_members_referenced_in_helper_logic(sql):
    """workspace_members または bf_can_access_workspace helper 経由で membership."""
    # bf_can_access_workspace を経由するか、 直接 workspace_members 参照
    assert (
        "workspace_members" in sql
        or "bf_can_access_workspace" in sql
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — zero-row filter via USING / idempotent policies
# ══════════════════════════════════════════════════════════════════════


def test_ac2_using_workspace_filter_present(sql):
    """USING 句で bf_can_access_workspace(...) を呼ぶ pattern が複数ある.

    bare `USING (bf_can_access_workspace(...))` か compound
    `USING (workspace_id IS NULL OR bf_can_access_workspace(...))` の
    どちらでも OK.
    """
    # USING 句の中 (...) で bf_can_access_workspace を呼ぶ全ケース
    matches = re.findall(
        r"USING\s*\([^)]*bf_can_access_workspace\s*\(",
        sql,
    )
    assert len(matches) >= 3, (
        f"expected >= 3 USING bf_can_access_workspace clauses, got {len(matches)}"
    )


def test_ac2_drop_policy_if_exists_pairs_create(sql):
    """idempotent: DROP POLICY IF EXISTS が CREATE POLICY と pair."""
    drop_count = len(re.findall(r"DROP POLICY IF EXISTS", sql))
    create_count = len(re.findall(r"CREATE POLICY", sql))
    # >= 80% pair
    assert drop_count >= create_count * 0.8, (
        f"DROP POLICY IF EXISTS {drop_count} vs CREATE POLICY {create_count}"
    )


def test_ac2_with_check_clauses_present(sql):
    """INSERT / UPDATE policy に WITH CHECK 句."""
    matches = re.findall(r"WITH CHECK\s*\(", sql)
    assert len(matches) >= 5, (
        f"expected >= 5 WITH CHECK clauses, got {len(matches)}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — no public / no DISABLE RLS
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_blanket_for_all_public(sql):
    bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", sql, re.IGNORECASE)
    assert not bad, f"forbidden FOR ALL TO public: {bad}"


def test_ac3_no_disable_row_level_security(sql):
    """DISABLE ROW LEVEL SECURITY が無い."""
    bad = re.findall(r"DISABLE ROW LEVEL SECURITY", sql, re.IGNORECASE)
    assert not bad, f"forbidden DISABLE RLS: {bad}"


def test_ac3_no_grant_to_anon_or_authenticated_for_all(sql):
    """anon / authenticated に GRANT ALL してない."""
    bad = re.findall(
        r"GRANT\s+ALL\s+ON.*TO\s+(anon|authenticated)\b",
        sql,
        re.IGNORECASE,
    )
    assert not bad, f"forbidden GRANT ALL to anon/authenticated: {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — account_owner cross-workspace + helper centralization
# ══════════════════════════════════════════════════════════════════════


def test_ac4_account_owner_helper_or_check(sql):
    """account 関連の policy が account_owner / bf_is_account_owner 等を扱う."""
    assert (
        "account_owner" in sql
        or "bf_is_account_owner" in sql
        or "account_members" in sql
    )


def test_ac4_bf_can_access_workspace_centralized(sql):
    """workspace 判定が helper 経由で集約 (DRY)."""
    # ≥ 5 箇所で bf_can_access_workspace を invoke
    count = len(re.findall(r"bf_can_access_workspace\s*\(", sql))
    assert count >= 5, (
        f"helper should be reused, found {count} invocations"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — no DISABLE / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_no_disable_rls_in_migration():
    src = RLS_MIGRATION.read_text(encoding="utf-8")
    assert "DISABLE ROW LEVEL SECURITY" not in src


def test_ac5_no_hardcoded_jwt():
    src = RLS_MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", src)


def test_ac5_no_hardcoded_supabase_or_anthropic():
    src = RLS_MIGRATION.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_06_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-06"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_06_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-06"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("20260510000002_rls_full_enforcement.sql" in f for f in files)


def test_tickets_t_001_06_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-06"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "20260510000002_rls_full_enforcement.sql",
        "ENABLE ROW LEVEL SECURITY",
        "CREATE POLICY",
        "bf_can_access_workspace",
        "DROP POLICY IF EXISTS",
        "DISABLE ROW LEVEL SECURITY",
        "USING",
        "service_role",
    ):
        assert sym in full, f"T-001-06 AC missing: {sym}"
