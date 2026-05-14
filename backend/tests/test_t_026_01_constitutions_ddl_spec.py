"""T-026-01: constitutions DDL 確認 — F-026 spec verification (REUSE audit).

REUSE タスク: DDL は T-001-04 (PR #194) で adopted, service は T-AI-04 (PR #240)
で adopted 済. 本 file は **F-026 (Constitution / プロジェクト不変原則) の
1:1 spec rigor** を機械検証する.

## DDL location (改変禁止 / REUSE)

  bf_constitutions:               supabase/migrations/20260510000001_bf_project_tables.sql:162-175
  bf_constitution_revisions:      supabase/migrations/20260510000001_bf_project_tables.sql:180-188
  RLS:                            supabase/migrations/20260510000001_bf_project_tables.sql:312-327
  red_lines.constitution_id FK:   supabase/migrations/20260512000000_impl_integration_ops_tables.sql:120
  GIN / current index 補助:       supabase/migrations/20260512100000_extensions_pgsodium_pgcron_indexes.sql:50,119

## AC マッピング (tickets.json T-026-01)

  AC-1 UBIQUITOUS: F-026 を満たす実装が DB に存在する.
  AC-2 EVENT-DRIVEN: service 経由で呼ぶと 2 sec 内に structured response.
  AC-3 STATE-DRIVEN: 既存 test/integration が回帰しない.
  AC-4 UNWANTED: 不正入力 (空 principles / version 重複) は CHECK / UNIQUE で reject.

## Edge cases (audit doc §4.1)

  - principles = {} → DDL CHECK で reject (静的検証)
  - principles 文字列が JSON parse 失敗 → CorruptConstitution raise
  - principles oversized (10KB+) → loader は load 可能 (warn は上位 caller の責務)
  - principles unicode (日本語) → round-trip preserve
  - version 二重採番 → DDL UNIQUE で reject (静的検証)
  - red_lines.constitution_id cascade

audit doc: docs/audit/2026-05-13_v2/T-026-01.md
"""
from __future__ import annotations

import asyncio
import importlib
import json
import re
import time
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BF_TABLES_MIG = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260510000001_bf_project_tables.sql"
)
IMPL_TABLES_MIG = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260512000000_impl_integration_ops_tables.sql"
)
EXT_INDEX_MIG = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260512100000_extensions_pgsodium_pgcron_indexes.sql"
)
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
AUDIT_DOC = REPO_ROOT / "docs" / "audit" / "2026-05-13_v2" / "T-026-01.md"


# ══════════════════════════════════════════════════════════════════════
# Fixtures (静的 SQL load)
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def bf_sql() -> str:
    return BF_TABLES_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def impl_sql() -> str:
    return IMPL_TABLES_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ext_sql() -> str:
    return EXT_INDEX_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def t026_01_ticket() -> dict:
    data = json.loads(TICKETS.read_text(encoding="utf-8"))
    return next(t for t in data["tickets"] if t["id"] == "T-026-01")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — F-026 を満たす DDL 実装が存在
# ══════════════════════════════════════════════════════════════════════


def test_ac1_table_exists(bf_sql: str) -> None:
    """bf_constitutions が CREATE TABLE IF NOT EXISTS で定義されている."""
    assert re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitutions\b", bf_sql,
    ), "bf_constitutions table missing"


def test_ac1_columns_complete(bf_sql: str) -> None:
    """F-026 が要求する全 column が存在.

    columns: id / project_id / version / principles / is_current /
             authored_by / created_at
    """
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitutions\s*\(([\s\S]+?)\);",
        bf_sql,
    )
    assert m, "bf_constitutions DDL block not found"
    body = m.group(1)
    required_cols = (
        ("id", r"\bid\b\s+BIGSERIAL\s+PRIMARY\s+KEY"),
        ("project_id", r"\bproject_id\b\s+BIGINT\s+NOT NULL"),
        ("version", r"\bversion\b\s+INTEGER\s+NOT NULL\s+DEFAULT\s+1"),
        ("principles", r"\bprinciples\b\s+JSONB\s+NOT NULL"),
        ("is_current", r"\bis_current\b\s+BOOLEAN\s+NOT NULL\s+DEFAULT\s+TRUE"),
        ("authored_by", r"\bauthored_by\b\s+TEXT"),
        ("created_at", r"\bcreated_at\b\s+TIMESTAMPTZ\s+DEFAULT\s+NOW\s*\(\s*\)"),
    )
    for name, pat in required_cols:
        assert re.search(pat, body, re.IGNORECASE), (
            f"bf_constitutions column '{name}' missing or wrong type"
        )


def test_ac1_revisions_table_exists(bf_sql: str) -> None:
    """bf_constitution_revisions (audit 履歴) が存在 + FK + index."""
    assert re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitution_revisions\b", bf_sql,
    ), "bf_constitution_revisions table missing"

    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitution_revisions\s*\(([\s\S]+?)\);",
        bf_sql,
    )
    assert m, "bf_constitution_revisions DDL block not found"
    body = m.group(1)
    # FK to bf_constitutions
    assert re.search(
        r"constitution_id\s+BIGINT\s+NOT NULL\s+REFERENCES\s+bf_constitutions\s*\(\s*id\s*\)\s+ON\s+DELETE\s+CASCADE",
        body, re.IGNORECASE,
    ), "bf_constitution_revisions.constitution_id FK CASCADE missing"
    # diff JSONB (RFC6902)
    assert re.search(r"\bdiff\b\s+JSONB\s+NOT NULL", body, re.IGNORECASE), (
        "bf_constitution_revisions.diff JSONB NOT NULL missing"
    )
    # index for time-desc lookup
    assert re.search(
        r"CREATE INDEX IF NOT EXISTS\s+ix_bf_const_rev_const\s+ON\s+bf_constitution_revisions\s*\(\s*constitution_id\s*,\s*revised_at\s+DESC\s*\)",
        bf_sql, re.IGNORECASE,
    ), "ix_bf_const_rev_const index missing"


def test_ac1_partial_index_on_current_version(bf_sql: str) -> None:
    """is_current=TRUE の現行行を高速参照する partial index.

    constitution_engine.get_active_constitution は
    'WHERE is_current = TRUE' を投げるので必須.
    """
    assert re.search(
        r"CREATE INDEX IF NOT EXISTS\s+ix_bf_constitutions_current\s+ON\s+bf_constitutions\s*\(\s*project_id\s*\)\s+WHERE\s+is_current\s*=\s*TRUE",
        bf_sql, re.IGNORECASE,
    ), "ix_bf_constitutions_current partial index missing"


def test_ac1_red_lines_constitution_fk_cascade_present(impl_sql: str) -> None:
    """red_lines.constitution_id が bf_constitutions FK + CASCADE.

    F-026 happy path: constitution 削除で red_lines も削除されないと
    orphan red_line が残るので CASCADE 必須.
    """
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+red_lines\s*\(([\s\S]+?)\);",
        impl_sql,
    )
    assert m, "red_lines table missing"
    body = m.group(1)
    assert re.search(
        r"constitution_id\s+BIGINT\s+REFERENCES\s+bf_constitutions\s*\(\s*id\s*\)\s+ON\s+DELETE\s+CASCADE",
        body, re.IGNORECASE,
    ), "red_lines.constitution_id FK CASCADE missing"


def test_ac1_supplementary_indexes_present(ext_sql: str) -> None:
    """Phase 2 の検索性向上 index (GIN + current view) が後段 PR で追加済.

    - ix_bf_constitutions_principles_gin: principles JSONB 検索
    - ix_bf_constitutions_workspace_current: project_id, version DESC
    """
    assert re.search(
        r"CREATE INDEX IF NOT EXISTS\s+ix_bf_constitutions_principles_gin\s+ON\s+bf_constitutions\s+USING\s+gin\s*\(\s*principles\s+jsonb_path_ops\s*\)",
        ext_sql, re.IGNORECASE,
    ), "ix_bf_constitutions_principles_gin (GIN) missing"
    assert re.search(
        r"CREATE INDEX IF NOT EXISTS\s+ix_bf_constitutions_workspace_current\s+ON\s+bf_constitutions\s*\(\s*project_id\s*,\s*version\s+DESC",
        ext_sql, re.IGNORECASE,
    ), "ix_bf_constitutions_workspace_current missing"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — service round-trip < 2 sec (mock DB)
# ══════════════════════════════════════════════════════════════════════


def _build_fake_db(monkeypatch, principles: dict, *, version: int = 1):
    """mock _db() / _db_path() で sqlite なし環境でも service を呼べるように."""
    from services import constitution_engine as ce

    class _Cur:
        def __init__(self, rows): self._rows = rows
        async def fetchall(self): return self._rows

    class _Conn:
        Row = dict

        def __init__(self):
            self.row_factory = None

        async def execute(self, sql, args=()):
            return _Cur([{
                "id": 1,
                "version": version,
                "authored_by": "masato",
                "principles": json.dumps(principles, ensure_ascii=False),
            }])

        async def commit(self): return None
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    fake_mod = types.SimpleNamespace(connect=lambda _p: _Conn(), Row=dict)
    monkeypatch.setattr(ce, "_db", lambda: fake_mod)
    monkeypatch.setattr(ce, "_db_path", lambda: ":memory:")
    ce._cache.clear()
    return ce


def test_ac2_service_round_trip_under_2s(monkeypatch) -> None:
    """service 経由の load → inject が 2 sec 以内に構造化値を返す."""
    principles = {
        "section_1_mission": "Build-Factory mission",
        "section_2_values": ["シンプル", "速く"],
        "section_4_red_lines": ["DROP TABLE 禁止"],
    }
    ce = _build_fake_db(monkeypatch, principles)

    t0 = time.perf_counter()
    text = asyncio.run(ce.inject_for_session(role="default"))
    elapsed = time.perf_counter() - t0

    assert isinstance(text, str), "inject_for_session must return str"
    assert "Constitution v" in text, "version marker missing"
    assert "section_2_values" in text, "Section 2 not injected for default role"
    assert "section_4_red_lines" in text, "Section 4 (red lines) must always inject"
    assert elapsed < 2.0, f"round-trip took {elapsed:.2f}s, exceeds 2s SLO"


def test_ac2_principles_jsonb_round_trip(monkeypatch) -> None:
    """JSONB string → Constitution.principles dict round-trip 整合."""
    principles = {
        "section_1_mission": "mission text",
        "section_2_values": ["v1", "v2"],
        "section_3_methods": ["EARS"],
        "section_4_red_lines": ["no force push"],
        "section_5_examples": ["case A"],
    }
    ce = _build_fake_db(monkeypatch, principles)
    c = asyncio.run(ce.get_active_constitution())
    assert c.principles == principles
    assert c.version == 1
    assert c.authored_by == "masato"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — 既存 test / integration を回帰させない
# ══════════════════════════════════════════════════════════════════════


def test_ac3_t001_04_invariants_unchanged() -> None:
    """T-001-04 の bf_constitutions 関連 invariant が依然として静的に通る.

    REUSE は 'no DDL change' を保証する. T-001-04 が assert している
    重要 invariant の subset を本テストでも再 assert することで, 二重 guard.
    """
    sql = BF_TABLES_MIG.read_text(encoding="utf-8")
    # T-001-04 AC-4: principles NOT NULL
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitutions\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m
    body = m.group(1)
    assert re.search(r"\bprinciples\b\s+JSONB\s+NOT NULL", body, re.IGNORECASE)
    # T-001-04 AC-4: revisions FK to bf_constitutions
    m2 = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitution_revisions\s*\(([\s\S]+?)\);",
        sql,
    )
    assert m2
    assert re.search(r"REFERENCES\s+bf_constitutions\s*\(\s*id\s*\)", m2.group(1))


def test_ac3_t_ai_04_module_imports() -> None:
    """T-AI-04 の constitution_engine module が依然 import 可能.

    REUSE は service 改変なし → import 可能性は不変.
    """
    mod = importlib.import_module("services.constitution_engine")
    # 主要 public symbol が消えていない
    for sym in (
        "Constitution",
        "ConstitutionError",
        "CorruptConstitution",
        "MissingConstitution",
        "SECTION_KEYS",
        "NON_SECRETARY_SECTIONS",
        "get_active_constitution",
        "invalidate_cache",
        "inject_for_session",
        "merge_constitutions",
        "assert_constitution_available",
    ):
        assert hasattr(mod, sym), f"public symbol '{sym}' missing — REUSE broken"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — 不正入力は CHECK / UNIQUE / RLS で reject
# ══════════════════════════════════════════════════════════════════════


def test_ac4_principles_non_empty_check_present(bf_sql: str) -> None:
    """principles = {} は DDL CHECK で reject される (PG レイヤー gate)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitutions\s*\(([\s\S]+?)\);",
        bf_sql,
    )
    assert m
    body = m.group(1)
    assert re.search(
        r"CONSTRAINT\s+principles_non_empty\s+CHECK\s*\(\s*jsonb_typeof\s*\(\s*principles\s*\)\s*=\s*'object'\s+AND\s+principles\s*<>\s*'\{\}'::jsonb\s*\)",
        body, re.IGNORECASE,
    ), "principles_non_empty CHECK missing — empty/non-object principles can leak in"


def test_ac4_unique_version_per_project_present(bf_sql: str) -> None:
    """同 project_id 内で同 version の二重採番を UNIQUE で reject."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_constitutions\s*\(([\s\S]+?)\);",
        bf_sql,
    )
    assert m
    body = m.group(1)
    assert re.search(
        r"CONSTRAINT\s+uq_bf_constitution_version\s+UNIQUE\s*\(\s*project_id\s*,\s*version\s*\)",
        body, re.IGNORECASE,
    ), "uq_bf_constitution_version UNIQUE missing — version race可能"


def test_ac4_rls_enabled_and_authenticated_only(bf_sql: str) -> None:
    """RLS が有効 + service_role / authenticated workspace_member のみ.

    anon role に直接 read を許可していないことを assert (4xx for unauthorized).
    """
    # ALTER TABLE で RLS 有効化
    assert re.search(
        r"ALTER\s+TABLE\s+bf_constitutions\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        bf_sql, re.IGNORECASE,
    ), "bf_constitutions RLS not ENABLED"
    assert re.search(
        r"ALTER\s+TABLE\s+bf_constitution_revisions\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        bf_sql, re.IGNORECASE,
    ), "bf_constitution_revisions RLS not ENABLED"
    # member POLICY は authenticated role のみ
    assert re.search(
        r"CREATE\s+POLICY\s+bf_const_member\s+ON\s+bf_constitutions\s+FOR\s+ALL\s+TO\s+authenticated",
        bf_sql, re.IGNORECASE,
    ), "bf_const_member must be scoped to 'authenticated' role only"
    # revisions は SELECT のみ (audit 改竄防止)
    assert re.search(
        r"CREATE\s+POLICY\s+bf_const_rev_member\s+ON\s+bf_constitution_revisions\s+FOR\s+SELECT\s+TO\s+authenticated",
        bf_sql, re.IGNORECASE,
    ), "bf_const_rev_member must be FOR SELECT (revisions are append-only audit)"
    # anon role が直接付与されていない (member POLICY が anon を含まない)
    assert not re.search(
        r"CREATE\s+POLICY\s+bf_const(?:_rev)?_member\s+ON\s+bf_constitution[s_revision]+\s+FOR\s+\w+\s+TO\s+anon",
        bf_sql, re.IGNORECASE,
    ), "anon role must NOT be granted on bf_constitutions / revisions"


def test_ac4_corrupt_principles_rejected_in_loader(monkeypatch) -> None:
    """principles が JSON parse 不能 / 空 dict なら loader が CorruptConstitution raise.

    DDL CHECK と二重 gate (defense in depth).
    """
    from services import constitution_engine as ce

    class _CurBad:
        async def fetchall(self):
            # principles が壊れた JSON 文字列
            return [{
                "id": 1, "version": 1, "authored_by": "x",
                "principles": "{not-valid-json",
            }]

    class _ConnBad:
        Row = dict
        def __init__(self): self.row_factory = None
        async def execute(self, sql, args=()): return _CurBad()
        async def commit(self): return None
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    fake_mod = types.SimpleNamespace(connect=lambda _p: _ConnBad(), Row=dict)
    monkeypatch.setattr(ce, "_db", lambda: fake_mod)
    monkeypatch.setattr(ce, "_db_path", lambda: ":memory:")
    ce._cache.clear()

    with pytest.raises(ce.CorruptConstitution):
        asyncio.run(ce.get_active_constitution())


# ══════════════════════════════════════════════════════════════════════
# Edge cases (audit doc §4.1)
# ══════════════════════════════════════════════════════════════════════


def test_edge_corrupt_string_principles_raises(monkeypatch) -> None:
    """別形態の corrupt: principles が空 dict (CHECK は DDL 側 / loader も raise)."""
    from services import constitution_engine as ce

    class _Cur:
        async def fetchall(self):
            return [{
                "id": 1, "version": 1, "authored_by": "x",
                "principles": "{}",  # 空 object
            }]

    class _Conn:
        Row = dict
        def __init__(self): self.row_factory = None
        async def execute(self, sql, args=()): return _Cur()
        async def commit(self): return None
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    fake_mod = types.SimpleNamespace(connect=lambda _p: _Conn(), Row=dict)
    monkeypatch.setattr(ce, "_db", lambda: fake_mod)
    monkeypatch.setattr(ce, "_db_path", lambda: ":memory:")
    ce._cache.clear()

    with pytest.raises(ce.CorruptConstitution):
        asyncio.run(ce.get_active_constitution())


def test_edge_oversized_principles_loads_with_warn_marker(monkeypatch) -> None:
    """F-026 policy: max_size_kb=10 は spec 上 warn のみ (DDL 強制せず).

    loader は load 可能であり, 上位 caller (UI / writer) が KB 計算で warn する責務.
    本テストは「loader は raise しない」という invariant を ACK で固定する
    (skip-with-reason ではなく明示 ACK / DDL 強制を別 ADR に切り出す根拠).
    """
    big = "x" * (12 * 1024)  # 12KB > 10KB threshold
    principles = {
        "section_1_mission": big,
        "section_4_red_lines": ["block: drop table"],
    }
    ce = _build_fake_db(monkeypatch, principles)
    c = asyncio.run(ce.get_active_constitution())
    assert len(c.principles["section_1_mission"]) > 10 * 1024
    # caller responsible: warn marker is computed by upstream (UI/writer)
    # this assertion documents the boundary explicitly:
    measured_kb = len(json.dumps(c.principles, ensure_ascii=False)) / 1024
    assert measured_kb > 10, "oversized fixture must trigger warn boundary"


def test_edge_unicode_round_trip(monkeypatch) -> None:
    """日本語 + 記号 + 改行を含む principles の round-trip 整合."""
    principles = {
        "section_1_mission": "案件並列運用 — 1 人で 10 案件",
        "section_2_values": ["速く・シンプルに・妥協しない", "顧客第一主義\n二行目"],
        "section_4_red_lines": ["本番 DB に DROP / TRUNCATE 禁止"],
    }
    ce = _build_fake_db(monkeypatch, principles)
    c = asyncio.run(ce.get_active_constitution())
    assert c.principles["section_1_mission"] == "案件並列運用 — 1 人で 10 案件"
    assert "二行目" in c.principles["section_2_values"][1]
    text = asyncio.run(ce.inject_for_session(role="secretary"))
    # secretary は全 section 注入
    assert "案件並列運用" in text
    assert "本番 DB" in text


# ══════════════════════════════════════════════════════════════════════
# Audit doc 存在確認 (workflow guard / 事後監査ループ廃止の機械化)
# ══════════════════════════════════════════════════════════════════════


def test_audit_doc_present_for_t026_01() -> None:
    """ADR-011 / 2026-05-13_v2 protocol: 着手前 audit doc が必須."""
    assert AUDIT_DOC.exists(), (
        f"missing audit doc {AUDIT_DOC}; required by 2026-05-13_v2 protocol"
    )
    text = AUDIT_DOC.read_text(encoding="utf-8")
    # 必須 section 存在 (audit-first protocol)
    for required_section in (
        "AC × 実装 × テスト × Status",  # AC table
        "DDL location",                 # location 明示
        "Gap",                           # gap 列挙
        "Edge case",                     # edge case
    ):
        assert required_section in text, (
            f"audit doc missing section '{required_section}'"
        )


def test_t026_01_ticket_meta_intact(t026_01_ticket: dict) -> None:
    """tickets.json の T-026-01 メタが REUSE / DB / F-026 のままであること."""
    assert t026_01_ticket["label"] == "REUSE"
    assert t026_01_ticket["layer"] == "DB"
    assert t026_01_ticket["feature"] == "F-026"
    # AC が EARS 4 形式 (UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / UNWANTED)
    types_ = {ac["type"] for ac in t026_01_ticket["acceptance_criteria"]}
    assert types_ == {"UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"}
