"""T-009-01: task_dependencies CRUD — F-009 spec verification (REUSE audit).

REUSE タスク: DDL は T-001-04 で adopted, cycle 防止 trigger は T-001-09 で
adopted, service / router は T-S0 段階で adopted. 本 file は **F-009
(依存グラフ + 基本伝搬) の 1:1 spec rigor** を機械検証する.

## DDL / Trigger / RLS location (改変禁止 / REUSE)

  bf_task_dependencies table DDL:   supabase/migrations/20260510000001_bf_project_tables.sql:129-141
  RLS (member + service_role):       supabase/migrations/20260510000002_rls_full_enforcement.sql:294-308
  Cycle prevention trigger:          supabase/migrations/20260512300000_cycle_prevention_triggers.sql:26-67

## Service / Router (改変禁止 / REUSE)

  Service: backend/services/task_dependency_service.py
  Router:  backend/routers/task_dependencies.py
  Router mount: backend/main.py:66,228

## AC マッピング (tickets.json T-009-01)

  AC-1 UBIQUITOUS: F-009 を満たす CRUD 実装が存在する.
  AC-2 EVENT-DRIVEN: service / router 経由で呼ぶと 2 sec 内に structured response.
  AC-3 STATE-DRIVEN: 既存 test/integration が回帰しない (T-001-09 trigger / T-001-04 invariant).
  AC-4 UNWANTED: self-loop / cycle / duplicate / dep_type 列外 → 4xx envelope.

## Spec 源泉 (F-009)

  features.json F-009:
    happy_path: タスク追加時に依存選択 → DAG 可視化 → 編集時に AI が影響範囲ハイライト
    error_paths: 循環依存 → trigger で block / 大規模 DAG → 階層折りたたみ
    related_entities: task_dependencies
    related_screens: S-017, S-029

audit doc: docs/audit/2026-05-13_v2/T-009-01.md
"""
from __future__ import annotations

import asyncio
import importlib
import json
import re
import time
from pathlib import Path
from typing import Optional

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BF_TABLES_MIG = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260510000001_bf_project_tables.sql"
)
RLS_MIG = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260510000002_rls_full_enforcement.sql"
)
CYCLE_TRIG_MIG = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260512300000_cycle_prevention_triggers.sql"
)
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
FEATURES = REPO_ROOT / "docs" / "functional-breakdown" / "2026-05-09_v1" / "features.json"
AUDIT_DOC = REPO_ROOT / "docs" / "audit" / "2026-05-13_v2" / "T-009-01.md"
ROUTER_PATH = REPO_ROOT / "backend" / "routers" / "task_dependencies.py"
SERVICE_PATH = REPO_ROOT / "backend" / "services" / "task_dependency_service.py"
MAIN_PATH = REPO_ROOT / "backend" / "main.py"


# ══════════════════════════════════════════════════════════════════════
# Fixtures (静的 SQL / Python load)
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def bf_sql() -> str:
    return BF_TABLES_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rls_sql() -> str:
    return RLS_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def trig_sql() -> str:
    return CYCLE_TRIG_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tickets() -> dict:
    return json.loads(TICKETS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def features() -> list:
    """features.json は {meta, items, ...} 構造. items リストを返す."""
    data = json.loads(FEATURES.read_text(encoding="utf-8"))
    return data["items"] if isinstance(data, dict) else data


# ══════════════════════════════════════════════════════════════════════
# Section A — DDL invariant (AC-1 UBIQUITOUS / F-009 happy_path 永続化層)
# ══════════════════════════════════════════════════════════════════════


def test_ddl_bf_task_dependencies_table_exists(bf_sql: str) -> None:
    """spec: F-009 related_entities=['task_dependencies'] → DDL に CREATE TABLE bf_task_dependencies."""
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_task_dependencies\s*\(",
        bf_sql,
        re.IGNORECASE,
    ), "bf_task_dependencies table CREATE 文が DDL に無い"


def test_ddl_columns_task_id_and_depends_on_task_id(bf_sql: str) -> None:
    """spec: DAG edge は task_id (from) と depends_on_task_id (to) の有向ペア."""
    block = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_task_dependencies\s*\((.*?)\);",
        bf_sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert block, "bf_task_dependencies の CREATE TABLE block を取得失敗"
    body = block.group(1)
    assert re.search(r"\btask_id\s+BIGINT\s+NOT\s+NULL", body, re.IGNORECASE), \
        "task_id BIGINT NOT NULL カラム不在"
    assert re.search(
        r"\bdepends_on_task_id\s+BIGINT\s+NOT\s+NULL", body, re.IGNORECASE,
    ), "depends_on_task_id BIGINT NOT NULL カラム不在"


def test_ddl_fk_cascade_on_both_task_refs(bf_sql: str) -> None:
    """spec: task 削除時に edge も削除 (ON DELETE CASCADE) — 大規模 DAG 整合性."""
    # Find the bf_task_dependencies CREATE TABLE block specifically
    block = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_task_dependencies\s*\((.*?)\);",
        bf_sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert block
    body = block.group(1)
    # 両方の FK が ON DELETE CASCADE で bf_tasks を参照しているか
    cascade_count = len(re.findall(
        r"REFERENCES\s+bf_tasks\s*\(\s*id\s*\)\s+ON\s+DELETE\s+CASCADE",
        body,
        re.IGNORECASE,
    ))
    assert cascade_count == 2, (
        f"task_id と depends_on_task_id の両方が ON DELETE CASCADE で "
        f"bf_tasks 参照していること (found={cascade_count})"
    )


def test_ddl_no_self_dep_check_constraint(bf_sql: str) -> None:
    """spec: UNWANTED — 自己参照 (task が自分自身に依存) は CHECK で reject."""
    block = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_task_dependencies\s*\((.*?)\);",
        bf_sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert block
    body = block.group(1)
    assert re.search(
        r"CONSTRAINT\s+no_self_dep\s+CHECK\s*\(\s*task_id\s*<>\s*depends_on_task_id\s*\)",
        body,
        re.IGNORECASE,
    ), "no_self_dep CHECK 制約が DDL に無い (UNWANTED AC: self-loop)"


def test_ddl_unique_constraint_prevents_duplicate_edges(bf_sql: str) -> None:
    """spec: UNWANTED — 同一 (task_id, depends_on_task_id) ペア重複 INSERT は reject."""
    block = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_task_dependencies\s*\((.*?)\);",
        bf_sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert block
    body = block.group(1)
    assert re.search(
        r"CONSTRAINT\s+uq_bf_dep\s+UNIQUE\s*\(\s*task_id\s*,\s*depends_on_task_id\s*\)",
        body,
        re.IGNORECASE,
    ), "uq_bf_dep UNIQUE 制約が DDL に無い"


def test_ddl_dep_type_check_enum_blocks_related_informs(bf_sql: str) -> None:
    """spec: dep_type は 3 enum (blocks / related / informs) — DAG 種別の固定化."""
    block = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_task_dependencies\s*\((.*?)\);",
        bf_sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert block
    body = block.group(1)
    # dep_type CHECK 句に 3 enum すべてが入っていることを確認
    m = re.search(
        r"dep_type\s+TEXT\s+NOT\s+NULL[^,]*CHECK\s*\(\s*dep_type\s+IN\s*\(([^)]+)\)\s*\)",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, "dep_type CHECK 句が見つからない"
    enums = [s.strip().strip("'") for s in m.group(1).split(",")]
    assert set(enums) == {"blocks", "related", "informs"}, (
        f"dep_type enum が想定外: {enums} (期待: blocks/related/informs)"
    )


def test_ddl_indexes_for_dag_traversal(bf_sql: str) -> None:
    """spec: 大規模 DAG 走査の性能担保 — task_id / depends_on_task_id 両方に index."""
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+ix_bf_deps_task\s+ON\s+bf_task_dependencies\s*\(\s*task_id\s*\)",
        bf_sql,
        re.IGNORECASE,
    ), "ix_bf_deps_task index が無い (outgoing edges 走査用)"
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+ix_bf_deps_depends\s+ON\s+bf_task_dependencies\s*\(\s*depends_on_task_id\s*\)",
        bf_sql,
        re.IGNORECASE,
    ), "ix_bf_deps_depends index が無い (incoming edges 走査用)"


# ══════════════════════════════════════════════════════════════════════
# Section B — Cycle prevention trigger (AC-4 UNWANTED / F-009 error_paths)
# ══════════════════════════════════════════════════════════════════════


def test_trigger_cycle_prevention_function_exists(trig_sql: str) -> None:
    """spec: F-009 error_paths『循環依存→trigger で block』を担う関数."""
    assert re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+bf_prevent_task_dep_cycle\b",
        trig_sql,
        re.IGNORECASE,
    ), "bf_prevent_task_dep_cycle 関数 DEFINE が無い"


def test_trigger_attached_before_insert_or_update(trig_sql: str) -> None:
    """spec: cycle 形成「前」に block するため BEFORE INSERT OR UPDATE で発火."""
    assert re.search(
        r"CREATE\s+TRIGGER\s+trg_prevent_task_dep_cycle\s+"
        r"BEFORE\s+INSERT\s+OR\s+UPDATE\s+ON\s+bf_task_dependencies\s+"
        r"FOR\s+EACH\s+ROW\s+EXECUTE\s+FUNCTION\s+bf_prevent_task_dep_cycle\(\)",
        trig_sql,
        re.IGNORECASE | re.DOTALL,
    ), "trg_prevent_task_dep_cycle が BEFORE INSERT OR UPDATE で attach されていない"


# ══════════════════════════════════════════════════════════════════════
# Section C — RLS invariant (AC-3 STATE / workspace scope T-001-06 継承)
# ══════════════════════════════════════════════════════════════════════


def test_rls_enabled_on_bf_task_dependencies(bf_sql: str, rls_sql: str) -> None:
    """spec: workspace 境界 — RLS ENABLE は必須.

    ENABLE は bf_project_tables.sql で先に行い, policy は rls_full_enforcement.sql
    で定義される (2 段階).
    """
    pattern = r"ALTER\s+TABLE\s+bf_task_dependencies\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY"
    in_bf = re.search(pattern, bf_sql, re.IGNORECASE) is not None
    in_rls = re.search(pattern, rls_sql, re.IGNORECASE) is not None
    assert in_bf or in_rls, (
        "bf_task_dependencies の RLS ENABLE が見つからない "
        "(bf_project_tables.sql または rls_full_enforcement.sql のどちらかに必要)"
    )


def test_rls_policies_member_and_service_role_exist(bf_sql: str, rls_sql: str) -> None:
    """spec: RLS は 2 policy (service_role 全権 + member 限定アクセス).

    Policy 定義は bf_project_tables.sql / rls_full_enforcement.sql どちらに
    あっても OK (両方検索).
    """
    combined = bf_sql + "\n" + rls_sql
    assert re.search(
        r"CREATE\s+POLICY\s+bf_deps_service_role\s+ON\s+bf_task_dependencies",
        combined,
        re.IGNORECASE,
    ), "bf_deps_service_role policy が無い (service_role 全権)"
    assert re.search(
        r"CREATE\s+POLICY\s+bf_deps_member\s+ON\s+bf_task_dependencies",
        combined,
        re.IGNORECASE,
    ), "bf_deps_member policy が無い (member 限定)"


# ══════════════════════════════════════════════════════════════════════
# Section D — Service invariant (AC-4 UNWANTED + exception 階層)
# ══════════════════════════════════════════════════════════════════════


def test_service_valid_dep_types_matches_ddl_enum() -> None:
    """spec: Python の VALID_DEP_TYPES 定数 = DDL CHECK enum と完全一致."""
    from services import task_dependency_service as tds
    assert set(tds.VALID_DEP_TYPES) == {"blocks", "related", "informs"}, (
        f"VALID_DEP_TYPES が DDL CHECK enum と乖離: {tds.VALID_DEP_TYPES}"
    )


def test_service_exceptions_inherit_value_error() -> None:
    """spec: 全 service 例外は ValueError 派生 (caller 側の 4xx 化 handler 統一)."""
    from services.task_dependency_service import (
        InvalidDepInput, DepCycleDetected, DepNotFound,
    )
    assert issubclass(InvalidDepInput, ValueError)
    assert issubclass(DepCycleDetected, ValueError)
    assert issubclass(DepNotFound, ValueError)


def test_service_validate_dep_type_rejects_unknown_with_message() -> None:
    """spec: 未知 dep_type は InvalidDepInput + 列挙メッセージで reject."""
    from services import task_dependency_service as tds
    with pytest.raises(tds.InvalidDepInput, match=r"dep_type must be one of"):
        tds._validate_dep_type("BOGUS_TYPE")


# ══════════════════════════════════════════════════════════════════════
# Section E — Service AC-2 EVENT-DRIVEN: 2 秒以内に structured response
# ══════════════════════════════════════════════════════════════════════


def test_service_self_loop_rejected_fast(monkeypatch) -> None:
    """spec EVENT: 2 秒以内 + UNWANTED self-loop → InvalidDepInput (DB 触らず)."""
    from services import task_dependency_service as tds
    start = time.perf_counter()
    with pytest.raises(tds.InvalidDepInput, match="depend on itself"):
        asyncio.run(tds.create_dependency(
            task_id=42, depends_on_task_id=42, dep_type="blocks",
        ))
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"self-loop 判定が 2 秒以内に終わるべき (elapsed={elapsed:.3f}s)"


def test_service_invalid_dep_type_rejected_before_db_call(monkeypatch) -> None:
    """spec AC-4: dep_type 不正は DB アクセス前に検出 (先回り validation)."""
    from services import task_dependency_service as tds
    # DB を「壊れた sentinel」に差し替え、 触ると例外
    class _BoomDB:
        def connect(self, _p):
            raise AssertionError("DB should not be touched for dep_type 不正")
    monkeypatch.setattr(tds, "aiosqlite", _BoomDB())
    with pytest.raises(tds.InvalidDepInput, match="dep_type must be one of"):
        asyncio.run(tds.create_dependency(
            task_id=1, depends_on_task_id=2, dep_type="UNKNOWN",
        ))


# ══════════════════════════════════════════════════════════════════════
# Section F — Router contract (AC-2 EVENT: {detail: {code, message}})
# ══════════════════════════════════════════════════════════════════════


def test_router_module_exposes_5_endpoints() -> None:
    """spec UBIQUITOUS: F-009 CRUD = 5 endpoint (list-by-task / list-by-project /
    get / create / delete)."""
    src = ROUTER_PATH.read_text(encoding="utf-8")
    expected = [
        ('get', '/api/tasks/{task_id}/dependencies'),
        ('get', '/api/projects/{project_id}/dependencies'),
        ('get', '/api/dependencies/{dep_id}'),
        ('post', '/api/tasks/{task_id}/dependencies'),
        ('delete', '/api/dependencies/{dep_id}'),
    ]
    for method, path in expected:
        pattern = rf'@router\.{method}\("{re.escape(path)}"\)'
        assert re.search(pattern, src), f"router に {method.upper()} {path} が無い"


def test_router_error_envelope_format_is_detail_code_message() -> None:
    """spec EVENT: 4xx は {detail: {code, message}} 形式 (T-001-02 共通契約)."""
    src = ROUTER_PATH.read_text(encoding="utf-8")
    # _err helper が detail={"code": ..., "message": ...} を組むこと
    m = re.search(
        r'def\s+_err\s*\([^)]*\)\s*->\s*HTTPException\s*:.*?'
        r'return\s+HTTPException\s*\(.*?'
        r'detail\s*=\s*\{\s*"code"\s*:\s*code\s*,\s*"message"\s*:\s*message\s*\}',
        src,
        re.DOTALL,
    )
    assert m, "_err helper が {detail: {code, message}} envelope を返していない"


def test_router_mounted_in_main() -> None:
    """spec UBIQUITOUS: router は app に mount 済 (HTTP 経由でアクセス可能)."""
    src = MAIN_PATH.read_text(encoding="utf-8")
    assert "from routers.task_dependencies import router as task_dependencies_router" in src, (
        "main.py に task_dependencies_router の import が無い"
    )
    assert "app.include_router(task_dependencies_router)" in src, (
        "main.py で app.include_router(task_dependencies_router) されていない"
    )


# ══════════════════════════════════════════════════════════════════════
# Section G — Tickets meta / Workflow guard (audit doc + spec source link)
# ══════════════════════════════════════════════════════════════════════


def test_tickets_meta_t_009_01_invariant(tickets: dict) -> None:
    """spec: tickets.json の T-009-01 meta 不変 (label / sprint / deps)."""
    t = next((x for x in tickets["tickets"] if x["id"] == "T-009-01"), None)
    assert t is not None, "tickets.json に T-009-01 が無い"
    assert t["label"] == "REUSE"
    assert t["sprint"] == 4
    assert t["feature"] == "F-009"
    assert t["layer"] == "BE"
    assert "T-001-09" in t["deps"], "T-009-01 は T-001-09 (cycle trigger) に依存"


def test_features_json_f_009_invariant(features: list) -> None:
    """spec 源泉 pin: features.json F-009 の核となる属性が変わらないこと."""
    f = next((x for x in features if x["id"] == "F-009"), None)
    assert f is not None, "features.json に F-009 が無い"
    assert f["name"] == "依存グラフ + 基本伝搬"
    assert "task_dependencies" in f["related_entities"]
    # error_paths に「循環依存」「trigger で block」の語が含まれる
    error_text = " ".join(f["error_paths"])
    assert "循環依存" in error_text and "trigger" in error_text, (
        f"F-009 error_paths から『循環依存→trigger で block』が消えた: {f['error_paths']}"
    )


def test_audit_doc_for_t_009_01_exists() -> None:
    """spec: ADR-011 ワークフロー — 着手前 audit doc は merge 前 commit 済み."""
    assert AUDIT_DOC.exists(), f"audit doc 不在: {AUDIT_DOC}"
    text = AUDIT_DOC.read_text(encoding="utf-8")
    assert "T-009-01" in text
    assert "F-009" in text
    assert "REUSE" in text
