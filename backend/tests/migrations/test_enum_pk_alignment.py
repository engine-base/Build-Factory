"""T-V3-D-03: Entity type/enum drift fix — spec ↔ impl alignment 検証.

本 task は **「impl 既稼働を spec 側で受け入れる」alignment** を実施した.
6 entity (E-002 Account / E-003 AccountMember / E-004 Workspace /
E-005 WorkspaceMember / E-020 Artifact / E-025 Session) について
spec (docs/functional-breakdown/2026-05-16_v3/entities.json) を impl
(supabase/migrations/*.sql) に合わせて修正した結果を回帰検証する.

戦略:
  1. spec 側 (entities.json) を読み込み, 6 entity の field 名集合と
     drift status (`resolved`) を確認.
  2. impl 側 (CREATE TABLE 文) を migration から regex 抽出し,
     column 名集合との対応を確認.
  3. 差分を許容範囲 (extra impl-only column = OK, missing impl-side =
     NG) で評価し, alignment が崩れていないことを保証.

これにより以下の AC を満たす:
  - AC-F1: 6 entity の column type/enum alignment (impl-aligned spec)
  - AC-F2: CHECK constraint / pgsql ENUM が impl にあること
  - AC-F3: 既存 row data 違反は migration 不実施で吸収 (本 task は spec only)
  - AC-F4: PK width 変更は Polish-phase に deferred (resolution.deferred_to_polish 確認)

ADR-013 系の方針: backend は raw SQL (aiosqlite + Supabase) を採用し
SQLAlchemy ORM を持たないため, alignment 検証は spec ↔ migration の
machine-readable diff として実装する (ORM 不要).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENTITIES_JSON = REPO_ROOT / "docs/functional-breakdown/2026-05-16_v3/entities.json"
MIGRATIONS_DIR = REPO_ROOT / "supabase/migrations"

# T-V3-D-03 で alignment 完了した 6 entity
TARGET_ENTITY_IDS: tuple[str, ...] = (
    "E-002",  # Account
    "E-003",  # AccountMember
    "E-004",  # Workspace
    "E-005",  # WorkspaceMember
    "E-020",  # Artifact
    "E-025",  # Session
)

# entity → impl table 名 (entities.json の table_name と一致)
TARGET_TABLES: dict[str, str] = {
    "E-002": "accounts",
    "E-003": "account_members",
    "E-004": "workspaces",
    "E-005": "workspace_members",
    "E-020": "artifacts",
    "E-025": "sessions",
}


# ────────────────────────────────────────────────────────────────
# fixtures
# ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def entities_data() -> dict:
    """entities.json を全件 load."""
    assert ENTITIES_JSON.exists(), f"entities.json not found: {ENTITIES_JSON}"
    return json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def target_entities(entities_data: dict) -> dict[str, dict]:
    """6 target entity を id → entity dict で返す."""
    by_id: dict[str, dict] = {e["id"]: e for e in entities_data.get("entities", [])}
    missing = [eid for eid in TARGET_ENTITY_IDS if eid not in by_id]
    assert not missing, f"missing entities in entities.json: {missing}"
    return {eid: by_id[eid] for eid in TARGET_ENTITY_IDS}


@pytest.fixture(scope="module")
def migration_text() -> str:
    """全 migration SQL を連結 (テーブル定義検索用)."""
    parts: list[str] = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _extract_columns(sql: str, table_name: str) -> set[str]:
    """`CREATE TABLE IF NOT EXISTS <table> (...)` + 後続 `ALTER TABLE <table> ADD COLUMN`
    の column 名 set を抽出.

    複数の CREATE TABLE がある場合 (idempotent IF NOT EXISTS) は最初の
    1 件を採用. 列名は先頭トークン (大文字小文字無視) を採用.
    後続 migration で `ALTER TABLE <name> ADD COLUMN <col>` も拾う.
    """
    pattern = re.compile(
        rf"CREATE TABLE IF NOT EXISTS\s+{re.escape(table_name)}\s*\((.*?)\n\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    m = pattern.search(sql)
    columns: set[str] = set()
    if m:
        body = m.group(1)
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line:
                continue
            # CONSTRAINT / PRIMARY KEY / UNIQUE / FOREIGN / CHECK 行は skip
            upper = line.upper()
            if upper.startswith(("CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")):
                continue
            # コメント行は skip
            if line.startswith("--"):
                continue
            # 先頭 token (識別子) を抽出
            tok = re.match(r"([a-z_][a-z0-9_]*)", line, re.IGNORECASE)
            if tok:
                columns.add(tok.group(1).lower())

    # 追加: ALTER TABLE <table> ADD COLUMN [IF NOT EXISTS] <col>
    alter_pat = re.compile(
        rf"ALTER TABLE\s+{re.escape(table_name)}\s+ADD COLUMN(?:\s+IF NOT EXISTS)?\s+([a-z_][a-z0-9_]*)",
        re.IGNORECASE,
    )
    for am in alter_pat.finditer(sql):
        columns.add(am.group(1).lower())

    return columns


# ────────────────────────────────────────────────────────────────
# AC-F1: 6 entity が alignment 完了 (resolved)
# ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("entity_id", TARGET_ENTITY_IDS)
def test_drift_resolved_status(target_entities: dict[str, dict], entity_id: str):
    """各 entity の legacy_drift_notes.diff_severity が 'resolved' に更新済."""
    entity = target_entities[entity_id]
    notes = entity.get("legacy_drift_notes")
    assert notes is not None, f"{entity_id}: legacy_drift_notes missing"
    severity = notes.get("diff_severity")
    assert severity == "resolved", (
        f"{entity_id}: diff_severity expected 'resolved', got {severity!r}"
    )
    # previous_severity が残っていること (audit trail)
    assert "previous_severity" in notes, (
        f"{entity_id}: previous_severity must be kept for audit trail"
    )
    # resolution metadata が T-V3-D-03 を指す
    resolution = notes.get("resolution")
    assert resolution is not None, f"{entity_id}: resolution metadata missing"
    assert resolution.get("task_id") == "T-V3-D-03", (
        f"{entity_id}: resolution.task_id expected 'T-V3-D-03', got {resolution.get('task_id')!r}"
    )
    assert resolution.get("decision") == "impl-as-source-of-truth"


# ────────────────────────────────────────────────────────────────
# AC-F1: spec field set ⊆ impl column set (no spec-only ghost columns)
# ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("entity_id", TARGET_ENTITY_IDS)
def test_spec_fields_exist_in_impl(
    target_entities: dict[str, dict],
    migration_text: str,
    entity_id: str,
):
    """spec の fields[] に書かれた column が impl の CREATE TABLE に必ず存在."""
    entity = target_entities[entity_id]
    table = TARGET_TABLES[entity_id]
    spec_fields = {f["name"].lower() for f in entity.get("fields", [])}
    impl_cols = _extract_columns(migration_text, table)
    assert impl_cols, f"{entity_id}: CREATE TABLE {table} not found in migrations"

    missing_in_impl = spec_fields - impl_cols
    assert not missing_in_impl, (
        f"{entity_id} ({table}): spec fields missing in impl: {sorted(missing_in_impl)}; "
        f"impl columns: {sorted(impl_cols)}"
    )


# ────────────────────────────────────────────────────────────────
# AC-F2: enum / CHECK constraint (impl 側) が spec 記述と一致
# ────────────────────────────────────────────────────────────────


def test_session_status_check_constraint_5_values(migration_text: str):
    """sessions.status の CHECK constraint が 5 値 (running/done/crashed/cancelled/paused) を含む.

    spec 旧版は 7 値 (starting/running/paused/completed/failed/cancelled/crashed) だったが
    T-V3-D-03 で impl の 5 値に合わせて spec を縮小した. impl の CHECK constraint が
    実際に 5 値で運用されていることを確認する.

    sessions table 内の status 列定義に限定するため CREATE TABLE sessions ブロックを
    まず切り出してから CHECK 句を検索する.
    """
    block_pat = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+sessions\s*\((.*?)\n\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    block = block_pat.search(migration_text)
    assert block, "CREATE TABLE sessions not found in migrations"
    body = block.group(1)

    pattern = re.compile(
        r"status\s+TEXT[^,]*CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    m = pattern.search(body)
    assert m, "sessions.status CHECK constraint not found in CREATE TABLE sessions block"
    values_raw = m.group(1)
    values = {v.strip().strip("'") for v in values_raw.split(",")}
    expected = {"running", "done", "crashed", "cancelled", "paused"}
    assert values == expected, (
        f"sessions.status CHECK expected {expected}, got {values}"
    )


def test_workspaces_preferred_provider_enum_present(migration_text: str):
    """workspaces.preferred_provider が preferred_provider_enum (4 値) で実装済 (ADR-012 Decision 5)."""
    assert "preferred_provider_enum" in migration_text, (
        "preferred_provider_enum type not declared in any migration"
    )
    pattern = re.compile(
        r"CREATE TYPE\s+preferred_provider_enum\s+AS\s+ENUM\s*\(([^)]+)\)",
        re.IGNORECASE,
    )
    m = pattern.search(migration_text)
    assert m, "preferred_provider_enum CREATE TYPE not found"
    values = {v.strip().strip("'") for v in m.group(1).split(",")}
    expected = {"anthropic", "openai", "gemini", "auto"}
    assert values == expected, (
        f"preferred_provider_enum expected {expected}, got {values}"
    )


# ────────────────────────────────────────────────────────────────
# AC-F4: PK width 変更は Polish-phase deferred (destructive rewrite 回避)
# ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entity_id",
    ["E-002", "E-003", "E-004", "E-005", "E-025"],  # PK width 系のみ (E-020 は TEXT PK 既存)
)
def test_pk_width_change_deferred_to_polish(
    target_entities: dict[str, dict],
    entity_id: str,
):
    """BIGSERIAL → uuid v7 への PK width 変更は破壊的なため Polish-phase に deferred."""
    notes = target_entities[entity_id]["legacy_drift_notes"]
    deferred = notes.get("resolution", {}).get("deferred_to_polish", [])
    assert "uuid_v7_pk_migration" in deferred, (
        f"{entity_id}: 'uuid_v7_pk_migration' must be in deferred_to_polish to honor AC-F4 "
        f"(found: {deferred})"
    )


def test_no_new_destructive_migration_created():
    """本 task は spec-only alignment なので破壊的 migration は新規追加しない (AC-F4 守護)."""
    # T-V3-D-03 用 migration 名候補が存在しないことを確認
    forbidden = MIGRATIONS_DIR / "20260516130000_enum_pk_alignment.sql"
    assert not forbidden.exists(), (
        f"T-V3-D-03 must NOT create destructive migration {forbidden.name} "
        "(impl is source of truth; PK width 変更は Polish-phase deferred per AC-F4)"
    )


# ────────────────────────────────────────────────────────────────
# AC-F3: spec の constraint 違反が起きた場合の安全網
# ────────────────────────────────────────────────────────────────


def test_account_plan_values_documented(target_entities: dict[str, dict]):
    """accounts.plan の取りうる値が spec field descriptor に記述されていること.

    impl では TEXT (no pg ENUM) なので, runtime check は app 層で行う.
    spec の descriptor 文字列に 'free/pro/business/enterprise' が含まれることを保証.
    """
    entity = target_entities["E-002"]
    plan_field = next(f for f in entity["fields"] if f["name"] == "plan")
    desc = plan_field.get("raw_v1_descriptor", "")
    for v in ("free", "pro", "business", "enterprise"):
        assert v in desc, f"E-002 plan descriptor missing value {v!r}: {desc!r}"


def test_account_member_role_documented(target_entities: dict[str, dict]):
    """account_members.role の取りうる値が spec descriptor に含まれること."""
    entity = target_entities["E-003"]
    role_field = next(f for f in entity["fields"] if f["name"] == "role")
    desc = role_field.get("raw_v1_descriptor", "")
    assert "owner" in desc.lower(), f"E-003 role descriptor missing 'owner': {desc!r}"


def test_workspace_member_role_5_values(target_entities: dict[str, dict]):
    """workspace_members.role の 5 値 (workspace_admin/contributor/viewer/client/monitor) が記述."""
    entity = target_entities["E-005"]
    role_field = next(f for f in entity["fields"] if f["name"] == "role")
    desc = role_field.get("raw_v1_descriptor", "")
    for v in ("workspace_admin", "contributor", "viewer", "client", "monitor"):
        assert v in desc, f"E-005 role descriptor missing {v!r}: {desc!r}"


# ────────────────────────────────────────────────────────────────
# integration smoke: artifact_events / session metadata の整合
# ────────────────────────────────────────────────────────────────


def test_artifact_id_is_text_pk(migration_text: str):
    """artifacts.id は TEXT PRIMARY KEY (impl の uuid stored as TEXT パターン)."""
    pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+artifacts\s*\(\s*id\s+TEXT\s+PRIMARY KEY",
        re.IGNORECASE,
    )
    assert pattern.search(migration_text), (
        "artifacts.id must be 'TEXT PRIMARY KEY' (uuid stored as TEXT per impl)"
    )


def test_sessions_pk_is_bigserial(migration_text: str):
    """sessions.id は BIGSERIAL PRIMARY KEY (uuid v7 化は Polish-phase)."""
    pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+sessions\s*\(\s*id\s+BIGSERIAL\s+PRIMARY KEY",
        re.IGNORECASE,
    )
    assert pattern.search(migration_text), (
        "sessions.id must be 'BIGSERIAL PRIMARY KEY' per impl (Polish-phase: uuid v7)"
    )
