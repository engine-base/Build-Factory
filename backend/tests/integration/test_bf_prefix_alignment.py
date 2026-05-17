"""T-V3-D-02 integration test: bf_ prefix entity spec vs impl alignment.

ADR-014 (2026-05-17) で「E-014 Task / E-015 TaskDependency / E-016
AcceptanceCriterion / E-017 Constitution の 4 entity は bf_ prefix を canonical
とする」と決定された. 本 test は以下を検証する:

1. entities.json の 4 entity で `table_name` == `spec_table_name` == `bf_*`
2. 4 entity の `legacy_drift_notes.diff_severity` が `resolved_by_adr_014`
3. 4 entity の `legacy_drift_notes.adr_ref` が `ADR-014`
4. supabase migration (20260510000001_bf_project_tables.sql) に `bf_tasks` /
   `bf_task_dependencies` / `bf_acceptance_criteria` / `bf_constitutions`
   の CREATE TABLE 文がある
5. ADR-014 ファイル本体が存在し Status: Accepted

Run:
    pytest backend/tests/integration/test_bf_prefix_alignment.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENTITIES_PATH = REPO_ROOT / "docs/functional-breakdown/2026-05-16_v3/entities.json"
ADR014_PATH = REPO_ROOT / "docs/decisions/ADR-014-bf-prefix-decision.md"
MIGRATION_PATH = (
    REPO_ROOT
    / "supabase/migrations/20260510000001_bf_project_tables.sql"
)

ADR014_ALLOW = {
    "E-014": ("Task", "bf_tasks"),
    "E-015": ("TaskDependency", "bf_task_dependencies"),
    "E-016": ("AcceptanceCriterion", "bf_acceptance_criteria"),
    "E-017": ("Constitution", "bf_constitutions"),
}


@pytest.fixture(scope="module")
def entities() -> list[dict]:
    assert ENTITIES_PATH.exists(), f"{ENTITIES_PATH} not found"
    data = json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))
    items = data.get("entities", data) if isinstance(data, dict) else data
    assert isinstance(items, list), "entities.json must contain a list"
    return items


@pytest.fixture(scope="module")
def by_id(entities: list[dict]) -> dict[str, dict]:
    return {e["id"]: e for e in entities if "id" in e}


# ════════════════════════════════════════════════════════════════════
# AC-F1 (UBIQUITOUS) — ADR-014 が canonical decision として存在する
# ════════════════════════════════════════════════════════════════════


def test_adr014_file_exists_and_accepted() -> None:
    """AC-F1: ADR-014 ファイルが存在し Status: Accepted."""
    assert ADR014_PATH.exists(), f"{ADR014_PATH} not found"
    body = ADR014_PATH.read_text(encoding="utf-8")
    assert "**Status**: Accepted" in body, "ADR-014 must be Accepted"
    assert "bf_" in body, "ADR-014 must reference bf_ prefix"
    # 4 entity が ADR 本体で明示されている
    for eid in ADR014_ALLOW:
        assert eid in body, f"ADR-014 must reference {eid}"


# ════════════════════════════════════════════════════════════════════
# AC-F2 (EVENT-DRIVEN) — entities.json で spec_table_name が impl と一致
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("eid,name,canonical", [
    ("E-014", "Task", "bf_tasks"),
    ("E-015", "TaskDependency", "bf_task_dependencies"),
    ("E-016", "AcceptanceCriterion", "bf_acceptance_criteria"),
    ("E-017", "Constitution", "bf_constitutions"),
])
def test_entity_spec_matches_impl_for_bf_prefix(
    by_id: dict[str, dict], eid: str, name: str, canonical: str
) -> None:
    """AC-F2: 各 bf_ entity で table_name == spec_table_name == bf_<canonical>."""
    e = by_id.get(eid)
    assert e is not None, f"{eid} not found in entities.json"
    assert e.get("name") == name, f"{eid} name drift: expected {name}, got {e.get('name')}"
    assert e.get("table_name") == canonical, (
        f"{eid} table_name drift: expected {canonical}, got {e.get('table_name')}"
    )
    assert e.get("spec_table_name") == canonical, (
        f"{eid} spec_table_name drift: expected {canonical}, "
        f"got {e.get('spec_table_name')} — ADR-014 違反"
    )


@pytest.mark.parametrize("eid", list(ADR014_ALLOW.keys()))
def test_legacy_drift_notes_marked_resolved_by_adr014(
    by_id: dict[str, dict], eid: str
) -> None:
    """AC-F2: legacy_drift_notes.diff_severity = resolved_by_adr_014 + adr_ref."""
    e = by_id.get(eid)
    assert e is not None
    notes = e.get("legacy_drift_notes")
    assert notes is not None, f"{eid} missing legacy_drift_notes"
    assert notes.get("diff_severity") == "resolved_by_adr_014", (
        f"{eid} diff_severity must be 'resolved_by_adr_014' after ADR-014, "
        f"got {notes.get('diff_severity')}"
    )
    assert notes.get("adr_ref") == "ADR-014", (
        f"{eid} adr_ref must be 'ADR-014', got {notes.get('adr_ref')}"
    )
    assert notes.get("task_id") == "T-V3-D-02", (
        f"{eid} task_id must reference T-V3-D-02, got {notes.get('task_id')}"
    )
    # spec_table と impl_table も bf_* で揃っている
    canonical = ADR014_ALLOW[eid][1]
    assert notes.get("spec_table") == canonical
    assert notes.get("impl_table") == canonical


# ════════════════════════════════════════════════════════════════════
# AC-F2 (cont.) — DB rename を行わなかったことを migration 側で確認
# ════════════════════════════════════════════════════════════════════


def test_migration_still_has_bf_prefix_tables() -> None:
    """AC-F2 後半: DB rename しない (= migration 内の CREATE TABLE が bf_* のまま)."""
    assert MIGRATION_PATH.exists(), f"{MIGRATION_PATH} not found"
    src = MIGRATION_PATH.read_text(encoding="utf-8")
    for _eid, (_name, table) in ADR014_ALLOW.items():
        assert f"CREATE TABLE IF NOT EXISTS {table}" in src, (
            f"migration must keep CREATE TABLE for {table} (DB rename 禁止 — ADR-014 Decision 4)"
        )


# ════════════════════════════════════════════════════════════════════
# AC-F4 (UNWANTED) — lint rule #19 allow-list が ADR と同期している
# ════════════════════════════════════════════════════════════════════


def test_lint_rule19_allowlist_matches_adr014() -> None:
    """AC-F4: scripts/lint-mock.sh の ADR014_ALLOW dict が ADR と一致."""
    lint_path = REPO_ROOT / "scripts/lint-mock.sh"
    assert lint_path.exists()
    src = lint_path.read_text(encoding="utf-8")
    # 4 entity が allow-list に列挙されている
    for eid, (_name, table) in ADR014_ALLOW.items():
        assert f'"{eid}": "{table}"' in src, (
            f'lint-mock.sh ADR014_ALLOW must contain `"{eid}": "{table}"`'
        )
    # rule #19 dispatcher が wired
    assert "--entity-table-naming" in src
    assert "check_entity_table_naming" in src


# ════════════════════════════════════════════════════════════════════
# AC-F3 (OPTIONAL) — strip bf_ prefix は本 task スコープ外 (rename 未実施)
# ════════════════════════════════════════════════════════════════════


def test_no_rename_migration_introduced_by_this_task() -> None:
    """AC-F3: 本 task は migration を新規追加していない (DB rename を行わなかった)."""
    migrations_dir = REPO_ROOT / "supabase/migrations"
    assert migrations_dir.exists()
    # 「bf_ prefix を strip する rename migration」が本 task で導入されていない
    for f in migrations_dir.glob("*.sql"):
        body = f.read_text(encoding="utf-8")
        # ALTER TABLE bf_tasks RENAME TO tasks 系を検出 → 本 task ではあってはならない
        for _eid, (_name, table) in ADR014_ALLOW.items():
            stripped = table.removeprefix("bf_")
            forbidden = f"ALTER TABLE {table} RENAME TO {stripped}"
            assert forbidden not in body, (
                f"{f.name} contains a bf_ strip rename ({forbidden}) — "
                "ADR-014 Decision 4 (DB rename 禁止) 違反"
            )
