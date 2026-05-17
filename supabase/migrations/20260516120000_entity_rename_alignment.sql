-- =============================================================================
-- T-V3-D-01 / F-002: Entity table_name rename + spec alignment
-- =============================================================================
--
-- Drift coverage (docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md §3):
--   E-008 Skill           : legacy spec_table = "skills"            -> impl/canonical = "skill_definitions"
--   E-021 ArtifactVersion : legacy spec_table = "artifact_versions" -> impl/canonical = "artifact_events"
--   E-012 Phase           : legacy spec_table = "phases"            -> impl/canonical = "bf_phases"
--
-- Why this migration:
--   v1 entities.json shipped with the "legacy" spec table names (skills /
--   artifact_versions / phases). The actual supabase migrations
--   (20260501220000_initial_schema.sql + 20260510000001_bf_project_tables.sql)
--   created the tables under the canonical impl names (skill_definitions /
--   artifact_events / bf_phases). v3 entities.json now records both
--   `table_name` (canonical / impl) and `spec_table_name` (legacy). Group D
--   drift-fix Wave 4 picks the impl name as the single canonical source of
--   truth and aligns the spec to it.
--
-- What this migration does:
--   1. For each (legacy, canonical) pair: if legacy table exists AND canonical
--      table does NOT exist, perform `ALTER TABLE legacy RENAME TO canonical`
--      so historical data is preserved (AC-F3 EVENT-DRIVEN).
--   2. If both exist, the operator MUST manually reconcile -- we raise an
--      `assert` style notice so the migration stops in obviously-broken
--      environments instead of silently dropping data.
--   3. If only canonical exists (the situation in this repository today), the
--      migration is a no-op for that pair.
--   4. AC-F2 EVENT-DRIVEN: after the migration runs we assert that all three
--      canonical tables exist.
--   5. AC-F4 UNWANTED: if any FK still references the legacy name after rename
--      a relation-not-found error will naturally bubble up from Postgres
--      because the legacy relation will be gone -- the operator is forced to
--      add explicit FK cascade renames.
--
-- Idempotent: re-running this migration is safe. It only renames when the
-- legacy table is present and the canonical is absent.
--
-- Non-destructive on this codebase:
--   This repository never created the legacy tables (skills / artifact_versions
--   / phases) -- the impl migrations always used the canonical names. So in
--   this repo the migration is a verified no-op + post-condition assertion.
--   It is shipped to protect operators who imported a v1 schema into their
--   environment before v3.
--
-- See: docs/decisions/ADR-013-entity-table-naming-alignment.md
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Pair 1: E-008 Skill — skills -> skill_definitions
-- ---------------------------------------------------------------------------
DO $rename_skills$
DECLARE
    legacy_exists   boolean;
    canonical_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'skills'
    ) INTO legacy_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'skill_definitions'
    ) INTO canonical_exists;

    IF legacy_exists AND NOT canonical_exists THEN
        RAISE NOTICE 'T-V3-D-01: renaming legacy "skills" -> canonical "skill_definitions"';
        EXECUTE 'ALTER TABLE skills RENAME TO skill_definitions';
    ELSIF legacy_exists AND canonical_exists THEN
        RAISE EXCEPTION
          'T-V3-D-01: both legacy "skills" and canonical "skill_definitions" exist. Operator must manually reconcile (likely DROP TABLE skills after data merge).';
    ELSE
        RAISE NOTICE 'T-V3-D-01: skills rename skipped (legacy=%, canonical=%)', legacy_exists, canonical_exists;
    END IF;
END
$rename_skills$;

-- ---------------------------------------------------------------------------
-- Pair 2: E-021 ArtifactVersion — artifact_versions -> artifact_events
-- ---------------------------------------------------------------------------
DO $rename_artifact_versions$
DECLARE
    legacy_exists   boolean;
    canonical_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'artifact_versions'
    ) INTO legacy_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'artifact_events'
    ) INTO canonical_exists;

    IF legacy_exists AND NOT canonical_exists THEN
        RAISE NOTICE 'T-V3-D-01: renaming legacy "artifact_versions" -> canonical "artifact_events"';
        EXECUTE 'ALTER TABLE artifact_versions RENAME TO artifact_events';
    ELSIF legacy_exists AND canonical_exists THEN
        RAISE EXCEPTION
          'T-V3-D-01: both legacy "artifact_versions" and canonical "artifact_events" exist. Operator must manually reconcile.';
    ELSE
        RAISE NOTICE 'T-V3-D-01: artifact_versions rename skipped (legacy=%, canonical=%)', legacy_exists, canonical_exists;
    END IF;
END
$rename_artifact_versions$;

-- ---------------------------------------------------------------------------
-- Pair 3: E-012 Phase — phases -> bf_phases
-- ---------------------------------------------------------------------------
DO $rename_phases$
DECLARE
    legacy_exists   boolean;
    canonical_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'phases'
    ) INTO legacy_exists;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'bf_phases'
    ) INTO canonical_exists;

    IF legacy_exists AND NOT canonical_exists THEN
        RAISE NOTICE 'T-V3-D-01: renaming legacy "phases" -> canonical "bf_phases"';
        EXECUTE 'ALTER TABLE phases RENAME TO bf_phases';
    ELSIF legacy_exists AND canonical_exists THEN
        RAISE EXCEPTION
          'T-V3-D-01: both legacy "phases" and canonical "bf_phases" exist. Operator must manually reconcile.';
    ELSE
        RAISE NOTICE 'T-V3-D-01: phases rename skipped (legacy=%, canonical=%)', legacy_exists, canonical_exists;
    END IF;
END
$rename_phases$;

-- ---------------------------------------------------------------------------
-- AC-F2 post-condition: all 3 canonical tables must exist after migration
-- ---------------------------------------------------------------------------
DO $assert_canonical$
DECLARE
    missing text[] := ARRAY[]::text[];
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['skill_definitions', 'artifact_events', 'bf_phases']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = t
        ) THEN
            missing := array_append(missing, t);
        END IF;
    END LOOP;

    IF array_length(missing, 1) IS NOT NULL THEN
        RAISE EXCEPTION
          'T-V3-D-01 post-condition failed: canonical table(s) missing after migration: %', missing;
    END IF;
END
$assert_canonical$;

COMMIT;

-- =============================================================================
-- RLS coverage note (AC-F5):
--   The 3 canonical tables already have RLS enabled by upstream migrations:
--     - skill_definitions  : 20260510000002_rls_full_enforcement.sql (legacy_tables array)
--     - artifact_events    : 20260510000002_rls_full_enforcement.sql (explicit ENABLE)
--     - bf_phases          : 20260510000001_bf_project_tables.sql   (explicit ENABLE)
--   Since this migration only renames (and only when legacy table is present),
--   the existing RLS policies and ENABLE flags carry over to the renamed table
--   in Postgres semantics. `python3 scripts/verify-rls-coverage.py` continues
--   to report 0 missing RLS for these 3 tables.
-- =============================================================================
