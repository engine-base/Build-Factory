-- =============================================================================
-- T-V3-D-07: RLS policy 補完 batch 3 — bf_project family
-- =============================================================================
-- Target tables (E-056 / E-057 / E-058 / E-059 / E-060 / E-061):
--   1. bf_projects                (E-056 BFProject)
--   2. bf_features                (E-057 BFFeature)
--   3. bf_mocks                   (E-058 BFMock)
--   4. bf_deliveries              (E-059 BFDelivery)
--   5. bf_constitution_revisions  (E-060 BFConstitutionRevision)
--   6. session_artifacts          (E-061 SessionArtifact)
--
-- Background (drift summary §5):
--   既存 migration `20260510000001_bf_project_tables.sql` および
--   `20260512000000_impl_integration_ops_tables.sql` で各 table に
--     - <table>_service_role           : FOR ALL TO postgres, service_role
--     - <table>_member                 : FOR ALL/SELECT TO authenticated
--                                        (bf_can_access_workspace 経由)
--   までは設定済み. しかし v3 entities.json (E-056〜E-061) に明記された
--   canonical policy 名 `<table>_service_role_all` /
--   `<table>_workspace_member_select` /
--   `<table>_workspace_member_write` と実装名が不一致だったため、
--   下流の access-control verifier (T-V3-D-15) が spec ↔ impl 突合できない
--   状態が継続していた (drift).
--
--   本 migration は v3 drift summary の access_policies_required (T-V3-D-07
--   ticket #access_policies_required[]) に従い、 canonical 名の policy を
--   **追加** する (既存 policy は drop せず保持; Postgres の RLS は同一
--   role に複数 policy がある場合 OR で結合するため、 SELECT 範囲のみ
--   累積拡大し縮小しない — backward compatible).
--
-- AC マッピング (T-V3-D-07):
--   AC-F1 UBIQUITOUS : 各 table に >= 2 policy
--                      (service_role_all + workspace_scoped) を保証.
--                      本 migration では canonical 名 (workspace_member_select)
--                      を追加し、 既存 _member policy と合算で 3 policy/table.
--   AC-F2 EVENT      : auth user が非所属 workspace の bf_projects を query
--                      → 0 row.
--                      workspace_member_select policy は
--                      bf_can_access_workspace(workspace_id) (or 該当 join
--                      経由) を USING 句で参照するため、 非所属 workspace の
--                      行はフィルタされる.
--   AC-F3 EVENT      : service_role が 6 table を query → 全 row.
--                      service_role_all policy は USING (true) WITH CHECK
--                      (true) で行 filter を bypass する.
--   AC-F4 UNWANTED   : verify-rls-coverage.py で 6 table の policy_count < 2
--                      なら fail.  本 migration により全 6 table が >= 2
--                      policy を保持することを保証.
--
-- Helper:
--   bf_can_access_workspace(ws_id BIGINT) — 20260510000001 で定義済 (再利用).
--
-- 詳細: docs/audit/2026-05-16_v3/T-V3-D-07.md
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. bf_projects — service_role_all + workspace_member_select (canonical 名)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE bf_projects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bf_projects_service_role_all ON bf_projects;
CREATE POLICY bf_projects_service_role_all ON bf_projects
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS bf_projects_workspace_member_select ON bf_projects;
CREATE POLICY bf_projects_workspace_member_select ON bf_projects
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. bf_features — project_id 経由で workspace 参照
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE bf_features ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bf_features_service_role_all ON bf_features;
CREATE POLICY bf_features_service_role_all ON bf_features
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS bf_features_workspace_member_select ON bf_features;
CREATE POLICY bf_features_workspace_member_select ON bf_features
    FOR SELECT TO authenticated
    USING (
        project_id IN (
            SELECT id FROM bf_projects
             WHERE bf_can_access_workspace(workspace_id)
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. bf_mocks — project_id 経由で workspace 参照
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE bf_mocks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bf_mocks_service_role_all ON bf_mocks;
CREATE POLICY bf_mocks_service_role_all ON bf_mocks
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS bf_mocks_workspace_member_select ON bf_mocks;
CREATE POLICY bf_mocks_workspace_member_select ON bf_mocks
    FOR SELECT TO authenticated
    USING (
        project_id IN (
            SELECT id FROM bf_projects
             WHERE bf_can_access_workspace(workspace_id)
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. bf_deliveries — project_id 経由で workspace 参照
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE bf_deliveries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bf_deliveries_service_role_all ON bf_deliveries;
CREATE POLICY bf_deliveries_service_role_all ON bf_deliveries
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS bf_deliveries_workspace_member_select ON bf_deliveries;
CREATE POLICY bf_deliveries_workspace_member_select ON bf_deliveries
    FOR SELECT TO authenticated
    USING (
        project_id IN (
            SELECT id FROM bf_projects
             WHERE bf_can_access_workspace(workspace_id)
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. bf_constitution_revisions — constitution_id → constitutions → projects → workspace
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE bf_constitution_revisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bf_constitution_revisions_service_role_all ON bf_constitution_revisions;
CREATE POLICY bf_constitution_revisions_service_role_all ON bf_constitution_revisions
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS bf_constitution_revisions_workspace_member_select ON bf_constitution_revisions;
CREATE POLICY bf_constitution_revisions_workspace_member_select ON bf_constitution_revisions
    FOR SELECT TO authenticated
    USING (
        constitution_id IN (
            SELECT bc.id
              FROM bf_constitutions bc
              JOIN bf_projects bp ON bc.project_id = bp.id
             WHERE bf_can_access_workspace(bp.workspace_id)
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. session_artifacts — workspace_id 直接保有 (NULL 許容)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE session_artifacts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS session_artifacts_service_role_all ON session_artifacts;
CREATE POLICY session_artifacts_service_role_all ON session_artifacts
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS session_artifacts_workspace_member_select ON session_artifacts;
CREATE POLICY session_artifacts_workspace_member_select ON session_artifacts
    FOR SELECT TO authenticated
    USING (
        workspace_id IS NOT NULL
        AND bf_can_access_workspace(workspace_id)
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260516170000', 'T-V3-D-07: RLS policy 補完 batch 3 (bf_project family canonical workspace_member_select)', 'system')
ON CONFLICT (version) DO NOTHING;


COMMENT ON POLICY bf_projects_workspace_member_select ON bf_projects IS
    'T-V3-D-07: workspace_members 経由で同 workspace の bf_projects を SELECT 可 (canonical 名)';
COMMENT ON POLICY bf_features_workspace_member_select ON bf_features IS
    'T-V3-D-07: bf_projects 経由で同 workspace の bf_features を SELECT 可 (canonical 名)';
COMMENT ON POLICY bf_mocks_workspace_member_select ON bf_mocks IS
    'T-V3-D-07: bf_projects 経由で同 workspace の bf_mocks を SELECT 可 (canonical 名)';
COMMENT ON POLICY bf_deliveries_workspace_member_select ON bf_deliveries IS
    'T-V3-D-07: bf_projects 経由で同 workspace の bf_deliveries を SELECT 可 (canonical 名)';
COMMENT ON POLICY bf_constitution_revisions_workspace_member_select ON bf_constitution_revisions IS
    'T-V3-D-07: bf_constitutions → bf_projects 経由で同 workspace の revisions を SELECT 可 (canonical 名)';
COMMENT ON POLICY session_artifacts_workspace_member_select ON session_artifacts IS
    'T-V3-D-07: workspace_members 経由で同 workspace の session_artifacts を SELECT 可 (canonical 名)';
