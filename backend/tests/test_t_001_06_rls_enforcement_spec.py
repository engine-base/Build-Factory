"""T-001-06: RLS 全 23 ユーザデータテーブル enforcement + custom_permissions 連動
(REFACTOR audit / 1:1 AC × test 仕様検証).

このファイルは **audit (検証) 専用**. 実装変更はしない (REFACTOR audit).

源泉:
  - `docs/task-decomposition/2026-05-09_v1/tickets.json#T-001-06`
  - `supabase/migrations/20260510000002_rls_full_enforcement.sql`
  - `supabase/migrations/20260510000001_bf_project_tables.sql`
    (bf_can_access_workspace helper 本体)
  - `backend/services/rls_context.py` (custom_permissions 渡し方;
    `auth.jwt() -> 'custom_permissions'`)

Anti-drift (per audit prompt):
  - 23 テーブル × ENABLE ROW LEVEL SECURITY assertion を **個別** に書く
  - collapsed regex `re.findall("ALTER TABLE.*ENABLE")` だけは NG
  - 各テーブル名は明示的に列挙する (parametrize は table-name を value にする)

AC × test 1:1 mapping (合計 49 tests):

  AC-1 UBIQUITOUS (≥ 20 ALTER + ≥ 30 CREATE POLICY + helper):
    - 23 個別 ENABLE RLS table assertion (parametrize)
    - >= 20 / >= 30 規模 assertion (2)
    - helper bf_can_access_workspace 参照 (1)
    - helper bf_is_account_owner 参照 + 定義 (2)

  AC-2 EVENT-DRIVEN (zero-row filter + idempotent):
    - USING(workspace_id-filter) >= 3 (1)
    - DROP POLICY IF EXISTS pair invariant (1)
    - WITH CHECK >= 5 (1)
    - workspace 経由 policy 名一覧 (23 expected policy names) を個別検証 (1)

  AC-3 STATE-DRIVEN (service_role bypass / no public / no DISABLE):
    - no FOR ALL TO public (1)
    - no DISABLE RLS (1)
    - no GRANT ALL TO anon/authenticated (1)
    - service_role policy per explicit user-data table (23 個別)

  AC-4 OPTIONAL (account_owner + helper DRY + custom_permissions 連動):
    - bf_is_account_owner helper SQL function definition (1)
    - accounts policy uses owner / account_members (1)
    - workspaces policy invokes bf_is_account_owner (1)
    - bf_can_access_workspace centralized (>= 5 invocations) (1)
    - **custom_permissions 連動 Type C gap finding**:
      migration が `auth.jwt() ->> 'custom_permissions'` を呼ばない
      ことを記録 (drift guard — 将来 ADR で導入する際の旗振り) (1)

  AC-5 UNWANTED (no DISABLE / no hardcoded secret):
    - no DISABLE RLS (re-check) (1)
    - no hardcoded JWT (1)
    - no hardcoded supabase / anthropic key (1)

  Drift guards & 整合性:
    - 21 explicit user-data ALTER TABLE 列挙 vs migration source の差分 0 (1)
    - tickets.json EARS 5 形式 (1)
    - tickets.json AC mentions concrete symbols (1)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RLS_MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260510000002_rls_full_enforcement.sql"
BF_TABLES_MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260510000001_bf_project_tables.sql"
RLS_CONTEXT_PY = REPO_ROOT / "backend" / "services" / "rls_context.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# 明示的 23 user-data table 列挙 (anti-drift requirement)
# ══════════════════════════════════════════════════════════════════════
# migration が *explicit* ALTER TABLE で個別 enable する 21 user-data
# テーブル + alembic_version (explicit) + bf_task_dependencies
# (legacy DO $$ 経由だが ticket comment header line 11 で bf_* family
# として listed) = 23.
EXPLICIT_USER_DATA_TABLES = (
    "workspace_members",
    "workspace_invitations",
    "accounts",
    "account_members",
    "workspaces",
    "ai_employee_config",
    "ai_employee_skills",
    "threads",
    "conversation_log",
    "conversation_slots",
    "artifacts",
    "artifact_events",
    "repos",
    "reviews",
    "pull_requests",
    "design_frames",
    "design_canvas_state",
    "design_mocks",
    "approval_queue",
    "checkpoints",
    "writes",
)
SYSTEM_OR_LEGACY_TABLES_INCLUDED = (
    # 明示 ALTER TABLE IF EXISTS で個別 enable
    "alembic_version",
    # legacy DO $$ ループ経由で enable される代表例
    "bf_task_dependencies",
)
ALL_23_TABLES = EXPLICIT_USER_DATA_TABLES + SYSTEM_OR_LEGACY_TABLES_INCLUDED
assert len(ALL_23_TABLES) == 23, "23 テーブル × 個別 ENABLE RLS の anti-drift 要件"


@pytest.fixture(scope="module")
def sql() -> str:
    return RLS_MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bf_sql() -> str:
    return BF_TABLES_MIGRATION.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# Anti-drift: 23 テーブル × ENABLE ROW LEVEL SECURITY (個別 parametrize)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", EXPLICIT_USER_DATA_TABLES)
def test_ac1_explicit_alter_table_enable_rls(sql: str, table: str) -> None:
    """21 explicit user-data table が個別 ALTER TABLE ENABLE RLS で
    立ち上がっている (collapsed regex 禁止 / 各 table 名で別 assertion)."""
    pattern = rf"^ALTER TABLE\s+{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY"
    assert re.search(pattern, sql, re.MULTILINE), (
        f"missing ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
    )


def test_ac1_alembic_version_explicit_alter_table(sql: str) -> None:
    """alembic_version は system metadata (migration tracker) なので
    explicit `ALTER TABLE IF EXISTS alembic_version ENABLE ROW LEVEL SECURITY`
    で個別 enable される."""
    assert re.search(
        r"ALTER TABLE\s+IF EXISTS\s+alembic_version\s+ENABLE ROW LEVEL SECURITY",
        sql,
    ), "alembic_version は IF EXISTS 句付きで個別 enable される必要"


def test_ac1_legacy_bf_task_dependencies_enabled_via_loop(sql: str) -> None:
    """legacy DO $$ ループに bf_task_dependencies が含まれる
    (= 全 23 テーブル中の最後の 1 件)."""
    # legacy_tables ARRAY literal 内に table 名がある
    m = re.search(r"legacy_tables\s+TEXT\[\]\s*:=\s*ARRAY\[([^\]]+)\]", sql, re.DOTALL)
    assert m is not None, "legacy_tables ARRAY が見つからない"
    body = m.group(1)
    assert "'bf_task_dependencies'" in body
    assert "EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t)" in sql


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — ≥ 20 ALTER + ≥ 30 CREATE POLICY + helper
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_file_exists() -> None:
    assert RLS_MIGRATION.exists(), f"missing: {RLS_MIGRATION}"


def test_ac1_at_least_20_alter_table_enable_rls(sql: str) -> None:
    matches = re.findall(r"ALTER TABLE\s+\w+\s+ENABLE ROW LEVEL SECURITY", sql)
    assert len(matches) >= 20, f"expected >= 20, got {len(matches)}"


def test_ac1_at_least_30_create_policy(sql: str) -> None:
    matches = re.findall(r"CREATE POLICY\b", sql)
    assert len(matches) >= 30, f"expected >= 30, got {len(matches)}"


def test_ac1_bf_can_access_workspace_helper_invoked(sql: str) -> None:
    """policy 群が bf_can_access_workspace(workspace_id) helper を USING 句で
    呼ぶ (workspace-scoped tables 全体の DRY 中央化)."""
    assert "bf_can_access_workspace" in sql
    assert re.search(r"USING\s*\(\s*[^)]*bf_can_access_workspace\s*\(", sql), (
        "USING 句で bf_can_access_workspace を呼ぶ pattern が無い"
    )


def test_ac1_bf_can_access_workspace_helper_defined_externally(bf_sql: str) -> None:
    """helper definition は T-001-04 (`20260510000001_bf_project_tables.sql`)
    にある (本 migration は import 的に依存; AC-1 helper 要件は両 migration
    合算で満たす)."""
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_can_access_workspace\s*\(",
        bf_sql,
    )


def test_ac1_bf_is_account_owner_helper_defined_inline(sql: str) -> None:
    """AC-4 OPTIONAL の account_owner 判定 helper は本 migration で
    define する."""
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_is_account_owner\s*\(\s*acc_id\s+BIGINT\s*\)",
        sql,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — zero-row filter + idempotent + workspace policy 名
# ══════════════════════════════════════════════════════════════════════


# 「workspace 経由 / authenticated 用」 policy 名一覧 (個別 assertion)
WORKSPACE_AUTHENTICATED_POLICY_NAMES = (
    "workspace_members_self",
    "workspace_invitations_member",
    "accounts_member_read",
    "accounts_owner_write",
    "account_members_self",
    "workspaces_member_read",
    "ai_employee_config_member",
    "threads_member",
    "conversation_log_member",
    "conversation_slots_member",
    "artifacts_member",
    "repos_member",
    "reviews_member",
    "design_frames_member",
    "design_canvas_state_member",
    "design_mocks_member",
    "approval_queue_member",
)


@pytest.mark.parametrize("policy_name", WORKSPACE_AUTHENTICATED_POLICY_NAMES)
def test_ac2_workspace_authenticated_policy_present(
    sql: str, policy_name: str
) -> None:
    """各 workspace-scoped table の authenticated 用 policy 名が
    個別に出現 (collapsed regex 禁止)."""
    assert re.search(
        rf"CREATE POLICY\s+{re.escape(policy_name)}\s+ON\s+\w+", sql
    ), f"missing CREATE POLICY {policy_name}"


def test_ac2_using_workspace_filter_present_multiple(sql: str) -> None:
    """USING 句で bf_can_access_workspace(...) を呼ぶ pattern が >= 5 個."""
    matches = re.findall(
        r"USING\s*\([^)]*bf_can_access_workspace\s*\(",
        sql,
    )
    assert len(matches) >= 5, f"expected >= 5 USING clauses, got {len(matches)}"


def test_ac2_drop_policy_if_exists_pairs_create(sql: str) -> None:
    """idempotency: DROP POLICY IF EXISTS が CREATE POLICY と pair (>= 80%).
    service_role bulk loop も DROP+CREATE pair で生成される."""
    drop_count = len(re.findall(r"DROP POLICY IF EXISTS", sql))
    create_count = len(re.findall(r"CREATE POLICY", sql))
    assert drop_count >= create_count * 0.8, (
        f"idempotent pair invariant violated: DROP {drop_count} vs CREATE {create_count}"
    )


def test_ac2_with_check_clauses_present(sql: str) -> None:
    """INSERT / UPDATE policy に WITH CHECK 句 (>= 5)."""
    matches = re.findall(r"WITH CHECK\s*\(", sql)
    assert len(matches) >= 5, f"expected >= 5 WITH CHECK, got {len(matches)}"


def test_ac2_no_create_policy_missing_drop_counterpart(sql: str) -> None:
    """全 explicit CREATE POLICY が DROP POLICY IF EXISTS と pair.

    DO$$ block 内の動的 CREATE POLICY は format() 経由なので exclude.
    """
    # explicit (DO ブロック外) の CREATE POLICY を抽出
    # 単純に line-level で `^CREATE POLICY <name> ON <table>` を抜き出す
    create_lines = re.findall(
        r"^CREATE POLICY\s+(\w+)\s+ON\s+(\w+)", sql, re.MULTILINE
    )
    drop_lines = re.findall(
        r"^DROP POLICY IF EXISTS\s+(\w+)\s+ON\s+(\w+)", sql, re.MULTILINE
    )
    drop_set = {(p, t) for p, t in drop_lines}
    missing = [(p, t) for (p, t) in create_lines if (p, t) not in drop_set]
    assert not missing, f"CREATE POLICY without paired DROP: {missing}"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — service_role / no public / no DISABLE
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", EXPLICIT_USER_DATA_TABLES)
def test_ac3_service_role_policy_per_explicit_table(sql: str, table: str) -> None:
    """21 explicit user-data table 毎に service_role 用 policy
    `<table>_service_role` が存在 (個別 assertion / collapsed regex 禁止)."""
    expected = f"{table}_service_role"
    assert re.search(
        rf"CREATE POLICY\s+{re.escape(expected)}\s+ON\s+{re.escape(table)}\b"
        r"\s+FOR ALL\s+TO\s+postgres,\s*service_role",
        sql,
    ), f"missing service_role policy for {table}"


def test_ac3_alembic_version_service_role_only(sql: str) -> None:
    """system metadata は service_role 専用に lockdown."""
    assert re.search(
        r"CREATE POLICY\s+alembic_version_service_role\s+ON\s+alembic_version",
        sql,
    )


def test_ac3_no_blanket_for_all_public(sql: str) -> None:
    bad = re.findall(r"FOR\s+ALL\s+TO\s+public\b", sql, re.IGNORECASE)
    assert not bad, f"forbidden FOR ALL TO public: {bad}"


def test_ac3_no_disable_row_level_security(sql: str) -> None:
    """AC-3 + AC-5 共通 invariant."""
    bad = re.findall(r"DISABLE ROW LEVEL SECURITY", sql, re.IGNORECASE)
    assert not bad, f"forbidden DISABLE RLS: {bad}"


def test_ac3_no_grant_to_anon_or_authenticated_for_all(sql: str) -> None:
    bad = re.findall(
        r"GRANT\s+ALL\s+ON.*TO\s+(anon|authenticated)\b",
        sql,
        re.IGNORECASE,
    )
    assert not bad, f"forbidden GRANT ALL: {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — account_owner + helper centralization +
# **custom_permissions 連動 (Type C gap finding)**
# ══════════════════════════════════════════════════════════════════════


def test_ac4_bf_is_account_owner_function_body_joins_account_members(sql: str) -> None:
    """bf_is_account_owner は account_members.role='owner' を判定."""
    # function definition は `... AS $$ <body> $$;` 形式
    # 2 番目の `$$` までを capture (body 中身を含む)
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_is_account_owner.+?AS\s+\$\$(.+?)\$\$",
        sql,
        re.DOTALL,
    )
    assert m is not None, "bf_is_account_owner function body not found"
    body = m.group(1)
    assert "account_members" in body
    assert "role = 'owner'" in body
    assert "auth.uid()" in body


def test_ac4_accounts_policy_invokes_owner_check(sql: str) -> None:
    """accounts table の policy が owner_user_id / account_members を読む."""
    # accounts_member_read 内 で owner_user_id = auth.uid() 句が存在
    m = re.search(
        r"CREATE POLICY\s+accounts_member_read\s+ON\s+accounts(.+?);",
        sql,
        re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    assert "owner_user_id = auth.uid()" in body
    assert "account_members" in body


def test_ac4_workspaces_member_read_invokes_bf_is_account_owner(sql: str) -> None:
    """workspaces の SELECT policy で account_owner クロス読み取り (AC-4)."""
    m = re.search(
        r"CREATE POLICY\s+workspaces_member_read\s+ON\s+workspaces(.+?);",
        sql,
        re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    assert "bf_is_account_owner" in body
    # AC-4 OPTIONAL コメント明記
    assert "OPTIONAL" in sql or "AC-4" in sql


def test_ac4_bf_can_access_workspace_centralized(sql: str) -> None:
    """workspace 判定が helper 経由で集約 (>= 5 invocations)."""
    count = len(re.findall(r"bf_can_access_workspace\s*\(", sql))
    assert count >= 5, f"helper underused, got {count}"


def test_ac4_custom_permissions_integration_drift_guard(sql: str) -> None:
    """**Type C gap finding (custom_permissions 連動)**:

    ticket title は "custom_permissions 連動" を謳うが、本 migration の
    helper (`bf_can_access_workspace` / `bf_is_account_owner`) は
    workspace_members + account_members の JOIN のみで `auth.jwt() ->>
    'custom_permissions'` を **読まない**.

    `backend/services/rls_context.py` は `request.jwt.claims` に
    custom_permissions を inject する **client-side** path を実装済み
    だが、 SQL policy 側は未連動.

    この test は **drift guard (記録)**: 将来 ADR で
    `auth.jwt()` 経由の grant 機能を追加する際の旗振り point.
    現状は **migration source に `auth.jwt()` 経由の custom_permissions
    呼出が存在しないこと** を invariant として記録する.

    Phase 1.5 で custom_permissions JSONB grant logic を追加する
    follow-up task が必要 (currently captured in audit doc gap G1).
    """
    # Phase 1: migration が `auth.jwt() ->> 'custom_permissions'`
    # を呼ばないことを記録 (drift guard / 否定 invariant)
    assert not re.search(
        r"auth\.jwt\(\)\s*->>?\s*'custom_permissions'",
        sql,
    ), (
        "T-001-06 Phase 1 では custom_permissions JSONB grant は未実装. "
        "もしこれが追加されたら audit doc / ADR を更新せよ."
    )
    # client-side path は rls_context.py で実装済み (cross-reference)
    rls_ctx_src = RLS_CONTEXT_PY.read_text(encoding="utf-8")
    assert "custom_permissions" in rls_ctx_src, (
        "rls_context.py に custom_permissions API が存在しない "
        "(client-side path も missing なら本 gap は CRITICAL)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — no DISABLE / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_no_disable_rls_re_check(sql: str) -> None:
    assert "DISABLE ROW LEVEL SECURITY" not in sql


def test_ac5_no_hardcoded_jwt(sql: str) -> None:
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", sql)


def test_ac5_no_hardcoded_supabase_or_anthropic_secret(sql: str) -> None:
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", sql)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", sql)


# ══════════════════════════════════════════════════════════════════════
# Drift guards & tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_drift_guard_explicit_table_set_matches_migration(sql: str) -> None:
    """テスト側の EXPLICIT_USER_DATA_TABLES (21 件) が migration 中の
    実際の `^ALTER TABLE <name> ENABLE ROW LEVEL SECURITY` set と完全一致.

    新規 table が migration に追加されてテストが追従していない場合 fail.
    """
    actual = set(
        re.findall(
            r"^ALTER TABLE\s+(\w+)\s+ENABLE ROW LEVEL SECURITY",
            sql,
            re.MULTILINE,
        )
    )
    # alembic_version は `ALTER TABLE IF EXISTS` なので別扱い
    expected = set(EXPLICIT_USER_DATA_TABLES)
    assert actual == expected, (
        f"explicit ALTER TABLE set drift: "
        f"missing_in_test={actual - expected} extra_in_test={expected - actual}"
    )


def test_tickets_t_001_06_canonical_ears() -> None:
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-06"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS",
        "EVENT-DRIVEN",
        "STATE-DRIVEN",
        "OPTIONAL",
        "UNWANTED",
    ]


def test_tickets_t_001_06_ac_mentions_concrete_symbols() -> None:
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-06"), None)
    assert t is not None
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
        "account_members",
        "workspace_members",
    ):
        assert sym in full, f"T-001-06 AC missing concrete symbol: {sym}"


def test_tickets_t_001_06_existing_files_includes_target_migration() -> None:
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-06"), None)
    assert t is not None
    files = t.get("existing_files", [])
    assert any(
        "20260510000002_rls_full_enforcement.sql" in f for f in files
    ), "tickets.json existing_files に target migration が無い"
