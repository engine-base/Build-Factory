"""T-V3-D-01: Entity table_name rename + spec alignment.

Static validation of supabase/migrations/20260516120000_entity_rename_alignment.sql
and docs/functional-breakdown/2026-05-16_v3/entities.json alignment for the
3 high-drift rename entities:

    E-008 Skill           : skills            -> skill_definitions
    E-021 ArtifactVersion : artifact_versions -> artifact_events
    E-012 Phase           : phases            -> bf_phases

We do not stand up a real Postgres here -- the migration uses standard
ALTER TABLE ... RENAME TO inside an explicit DO block, which is reviewed
elsewhere (test_supabase_migrations.py + test_t_001_04_bf_ddl_spec.py
verify CREATE TABLE / RLS structure for the canonical names). Here we
verify:

  1. The migration file exists at the path declared in the audit MD.
  2. The migration contains exactly 3 RENAME pairs for the declared entities.
  3. The migration is idempotent (each rename guarded by IF legacy_exists
     AND NOT canonical_exists pattern) -- AC-F3.
  4. The migration asserts the 3 canonical tables exist post-condition --
     AC-F2.
  5. entities.json `spec_table_name` is aligned with `table_name` for the
     3 affected entities -- AC-F1.
  6. The canonical 3 tables remain RLS-covered (no regression on AC-F5).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MIGS = ROOT / "supabase" / "migrations"
ENTITIES_JSON = ROOT / "docs" / "functional-breakdown" / "2026-05-16_v3" / "entities.json"
MIGRATION_PATH = MIGS / "20260516120000_entity_rename_alignment.sql"

# (entity_id, legacy_name, canonical_name) tuples
RENAME_PAIRS: list[tuple[str, str, str]] = [
    ("E-008", "skills", "skill_definitions"),
    ("E-021", "artifact_versions", "artifact_events"),
    ("E-012", "phases", "bf_phases"),
]


def _migration_src() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────
# AC-F1: spec_table_name aligned to canonical table_name in entities.json
# ─────────────────────────────────────────────────────────
def test_migration_file_exists() -> None:
    """The migration file must exist at the path declared in the audit MD."""
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"


def test_entities_json_spec_table_aligned() -> None:
    """AC-F1 UBIQUITOUS: entities.json spec_table_name == canonical table_name
    for E-008 / E-021 / E-012.
    """
    data = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))
    entities = {e["id"]: e for e in data["entities"]}

    for entity_id, _legacy, canonical in RENAME_PAIRS:
        e = entities.get(entity_id)
        assert e is not None, f"entity {entity_id} missing from entities.json"
        assert e["table_name"] == canonical, (
            f"{entity_id}: table_name={e['table_name']!r} expected {canonical!r}"
        )
        assert e["spec_table_name"] == canonical, (
            f"{entity_id}: spec_table_name={e['spec_table_name']!r} "
            f"expected {canonical!r} (aligned to canonical impl)"
        )


# ─────────────────────────────────────────────────────────
# AC-F3: each rename guarded by `legacy AND NOT canonical` (idempotent)
# ─────────────────────────────────────────────────────────
def test_migration_contains_3_rename_pairs() -> None:
    src = _migration_src()
    for _entity_id, legacy, canonical in RENAME_PAIRS:
        # Each rename must reference both legacy and canonical name in a
        # RENAME TO statement.
        rename_pattern = rf"ALTER TABLE\s+{legacy}\s+RENAME TO\s+{canonical}"
        assert re.search(rename_pattern, src, re.IGNORECASE), (
            f"missing ALTER TABLE {legacy} RENAME TO {canonical}"
        )


def test_migration_is_idempotent_via_existence_guards() -> None:
    """AC-F3 EVENT-DRIVEN: the rename block must only execute when legacy
    exists and canonical does not — so re-applying is a no-op.
    """
    src = _migration_src()

    # We expect 3 DO blocks, one per rename pair. Each block must SELECT
    # against information_schema.tables for both names.
    for _entity_id, legacy, canonical in RENAME_PAIRS:
        # legacy_exists check
        assert re.search(
            rf"table_name\s*=\s*'{legacy}'", src
        ), f"missing legacy_exists check for {legacy}"
        # canonical_exists check
        assert re.search(
            rf"table_name\s*=\s*'{canonical}'", src
        ), f"missing canonical_exists check for {canonical}"

    # The guard pattern: "IF legacy_exists AND NOT canonical_exists THEN"
    # We allow flexible whitespace and capitalisation.
    guard_pattern = r"IF\s+legacy_exists\s+AND\s+NOT\s+canonical_exists\s+THEN"
    matches = re.findall(guard_pattern, src, re.IGNORECASE)
    assert len(matches) == 3, (
        f"expected 3 guarded rename branches, found {len(matches)}"
    )


# ─────────────────────────────────────────────────────────
# AC-F2: post-condition asserts canonical tables exist after migration
# ─────────────────────────────────────────────────────────
def test_migration_asserts_canonical_tables_exist() -> None:
    """AC-F2 EVENT-DRIVEN: after the migration runs, all 3 canonical tables
    must be present. The migration enforces this with a post-condition DO
    block that RAISE EXCEPTIONs if any are missing.
    """
    src = _migration_src()
    assert "post-condition failed" in src, (
        "migration must include explicit post-condition RAISE EXCEPTION"
    )
    for _entity_id, _legacy, canonical in RENAME_PAIRS:
        # canonical name must appear in the post-condition ARRAY[...]
        # (we check it appears at least twice: once in its rename block,
        # once in the canonical assertion array)
        occurrences = src.count(f"'{canonical}'")
        assert occurrences >= 2, (
            f"canonical {canonical!r} expected in rename block + assertion "
            f"array, found {occurrences} occurrences"
        )


# ─────────────────────────────────────────────────────────
# AC-F4: same-name FK reference would naturally error after rename — covered
#         by the design of ALTER TABLE RENAME (Postgres semantics).
# Sanity test: ensure migration does NOT use DROP TABLE / TRUNCATE.
# ─────────────────────────────────────────────────────────
def test_migration_is_non_destructive() -> None:
    """AC-F3 follow-up: rename, not DROP+CREATE. Data must be preserved.

    SQL line comments (`-- ...`) are stripped before checking so that the
    operator-facing exception messages referencing "DROP TABLE" don't trip
    the destructive-op detector.
    """
    src = _migration_src()
    # strip SQL line comments
    sql_only_lines: list[str] = []
    for line in src.splitlines():
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        sql_only_lines.append(line)
    sql_only = "\n".join(sql_only_lines).upper()

    forbidden = ["DROP TABLE", "TRUNCATE", "DELETE FROM"]
    for kw in forbidden:
        # Allow inside RAISE EXCEPTION string literals (operator guidance only)
        # by checking that no DML/DDL statement actually executes it.
        # Practical heuristic: the kw must not appear as a real statement
        # (followed by a table name token then ';').
        # We use a tighter regex: kw at start of token, followed by identifier
        # and a semicolon within the same statement.
        assert not re.search(
            rf"\b{kw}\b\s+[A-Z_][A-Z0-9_]*\s*;",
            sql_only,
        ), f"migration must not contain destructive op: {kw}"


# ─────────────────────────────────────────────────────────
# AC-F5: RLS coverage regression — canonical tables already covered by
#         upstream migrations (see verify-rls-coverage.py).
# ─────────────────────────────────────────────────────────
def test_canonical_tables_have_rls_coverage() -> None:
    """AC-F5 UNWANTED: the 3 canonical tables must remain RLS-enabled.
    Static check: at least one ENABLE ROW LEVEL SECURITY (or membership in
    a legacy_tables ARRAY[...] for DO-block dynamic enable) must reference
    each canonical name across all migrations.
    """
    canonical_tables = {pair[2] for pair in RENAME_PAIRS}
    rls_enabled: set[str] = set()

    for sql_path in sorted(MIGS.glob("*.sql")):
        text = sql_path.read_text(encoding="utf-8")
        # 1. plain ALTER TABLE ... ENABLE ROW LEVEL SECURITY
        for m in re.finditer(
            r"ALTER TABLE\s+(?:IF EXISTS\s+)?([a-z_][a-z0-9_]*)\s+ENABLE ROW LEVEL SECURITY",
            text,
            re.IGNORECASE,
        ):
            rls_enabled.add(m.group(1))
        # 2. DO block dynamic enable via legacy_tables ARRAY[...]
        for arr in re.finditer(
            r"legacy_tables\s+TEXT\[\]\s*:=\s*ARRAY\[(.*?)\]\s*;",
            text,
            re.DOTALL | re.IGNORECASE,
        ):
            for s in re.finditer(r"'([a-z_][a-z0-9_]*)'", arr.group(1)):
                rls_enabled.add(s.group(1))

    missing = canonical_tables - rls_enabled
    assert not missing, (
        f"canonical tables missing RLS coverage: {sorted(missing)}"
    )


# ─────────────────────────────────────────────────────────
# AC-F1 sanity: legacy_drift_notes still reflects the rename so the
#               historical drift is auditable post-fix.
# ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("entity_id,legacy,canonical", RENAME_PAIRS)
def test_legacy_drift_notes_reflects_rename(
    entity_id: str, legacy: str, canonical: str
) -> None:
    """Each renamed entity must keep `legacy_drift_notes.spec_table = legacy`
    and `legacy_drift_notes.impl_table = canonical` so the audit trail is
    preserved even after `spec_table_name` is aligned to canonical.
    """
    data = json.loads(ENTITIES_JSON.read_text(encoding="utf-8"))
    entities = {e["id"]: e for e in data["entities"]}
    e = entities[entity_id]
    notes = e.get("legacy_drift_notes")
    assert notes is not None, f"{entity_id}: missing legacy_drift_notes"
    assert notes["spec_table"] == legacy, (
        f"{entity_id}: legacy_drift_notes.spec_table must record the historical "
        f"legacy name {legacy!r}, got {notes['spec_table']!r}"
    )
    assert notes["impl_table"] == canonical, (
        f"{entity_id}: legacy_drift_notes.impl_table must record the canonical "
        f"impl name {canonical!r}, got {notes['impl_table']!r}"
    )
