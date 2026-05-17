-- =============================================================================
-- T-V3-D-13: NEW entity formalization batch 2 — Screen-Component pair
--   E-023 Component / E-024 ScreenComponent (new tables)
--   E-022 Screen → merged into E-058 BFMock (ADR-017, entity merger only)
-- =============================================================================
-- Background (drift summary §2 critical / §3 high):
--   v3 entities.json は Screen (E-022) / Component (E-023) / ScreenComponent
--   (E-024) を別 entity として宣言していたが、 impl side では:
--     - E-022 Screen        → impl_table = (missing)。 bf_mocks (E-058) が
--       UI screen S-XXX の sole-source-of-truth として既に運用中。
--     - E-023 Component     → impl_table = (missing)。 design system →
--       frontend component の関係は frontend repo の static 構造で管理。
--     - E-024 ScreenComponent → impl_table = (missing)。 上記 2 entity が
--       無いため必然的に未実装。
--
--   本 migration は drift summary §6「推奨対応 / spec 統合」 に従い:
--     (a) E-022 Screen は新 table を作らず E-058 BFMock に merge する
--         (ADR-017)。 entities.json は E-022 を deprecated 化し
--         pointer (`replaced_by = E-058`) を埋める。
--     (b) E-023 components / E-024 screen_components を新規 table として
--         作成する。 screen_components.screen_id は ADR-017 に従い
--         bf_mocks(id) BIGINT を FK 参照する。
--     (c) tenant isolation は workspace_id 直接保有 (components) +
--         workspace_id 直接保有 (screen_components, denormalized for RLS
--         simplicity + 高速 query) の 2 重で実装。 screen_id FK 経由でも
--         検証可能だが、 RLS predicate を join なしで書ける方が安全。
--
-- Tables (2 new):
--   1. components          (E-023, workspace_scoped, BIGSERIAL PK)
--   2. screen_components   (E-024, workspace_scoped + join screens/components)
--
-- AC マッピング (T-V3-D-13):
--   AC-F1 UBIQUITOUS : components / screen_components 両 table を作成 +
--                      ADR-017 で E-022 → E-058 merge を記録 (本 migration
--                      header + 別 markdown)。
--   AC-F2 EVENT      : components 追加時に (workspace_id, name, version)
--                      の uniqueness を UNIQUE constraint で強制。
--   AC-F3 EVENT      : screen_components 作成時に screen_id (= bf_mocks.id)
--                      + component_id の FK constraint を強制。
--   AC-F4 UNWANTED   : entities.json で E-022 が依然 active なら fail.
--                      別途 entities.json で status=deprecated + replaced_by
--                      = "E-058" を埋め込む (本 migration の範囲外、
--                      entities.json update task で完了)。
--
-- RLS pattern (T-V3-D-06/07/08 と同形):
--   <table>_service_role_all           : FOR ALL TO postgres, service_role
--                                        USING (true) WITH CHECK (true)
--   <table>_workspace_member_select    : FOR SELECT TO authenticated
--                                        USING (bf_can_access_workspace(workspace_id))
--
-- Helper:
--   bf_can_access_workspace(ws_id BIGINT) — 20260510000001 で定義済 (再利用)
--
-- 詳細: docs/audit/2026-05-16_v3/T-V3-D-13.md / ADR-017
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. components (E-023) — design-system component catalog
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS components (
    id                  BIGSERIAL PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    version             TEXT NOT NULL DEFAULT 'v1',
    type                TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (type IN (
                                'button','input','select','card','modal','table',
                                'nav','sidebar','header','footer','form','badge',
                                'tooltip','tabs','accordion','toast','avatar',
                                'chart','editor','unknown'
                            )),
    description         TEXT,
    mock_artifact_id    BIGINT,
    metadata            JSONB DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ,
    CONSTRAINT uq_components_ws_name_version
        UNIQUE (workspace_id, name, version)
);
CREATE INDEX IF NOT EXISTS ix_components_ws ON components(workspace_id);
CREATE INDEX IF NOT EXISTS ix_components_type ON components(type);

ALTER TABLE components ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS components_service_role_all ON components;
CREATE POLICY components_service_role_all ON components
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS components_workspace_member_select ON components;
CREATE POLICY components_workspace_member_select ON components
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. screen_components (E-024) — junction table screens × components
--
--   screen_id は ADR-017 に従い bf_mocks(id) を参照する (Screen entity の
--   実体は bf_mocks)。 workspace_id を denormalize 保存して RLS predicate を
--   join 無しで書けるようにする (read-heavy / simple guard)。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS screen_components (
    id                  BIGSERIAL PRIMARY KEY,
    workspace_id        BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    screen_id           BIGINT NOT NULL REFERENCES bf_mocks(id) ON DELETE CASCADE,
    component_id        BIGINT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    slot                TEXT,
    position            INTEGER NOT NULL DEFAULT 0,
    layout              JSONB DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_screen_components_screen_component_slot
        UNIQUE (screen_id, component_id, slot)
);
CREATE INDEX IF NOT EXISTS ix_screen_components_ws ON screen_components(workspace_id);
CREATE INDEX IF NOT EXISTS ix_screen_components_screen ON screen_components(screen_id);
CREATE INDEX IF NOT EXISTS ix_screen_components_component ON screen_components(component_id);

ALTER TABLE screen_components ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS screen_components_service_role_all ON screen_components;
CREATE POLICY screen_components_service_role_all ON screen_components
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS screen_components_workspace_member_select ON screen_components;
CREATE POLICY screen_components_workspace_member_select ON screen_components
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260516200000', 'T-V3-D-13: components / screen_components tables (E-023/E-024) + ADR-017 E-022 Screen→BFMock merge decision', 'system')
ON CONFLICT (version) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT (運用者向け)
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE components IS
    'T-V3-D-13 / E-023: design-system component catalog. workspace_scoped. UNIQUE (workspace_id, name, version) で同名 component の version 管理可';
COMMENT ON TABLE screen_components IS
    'T-V3-D-13 / E-024: screens (= bf_mocks per ADR-017) × components M:N join. workspace_id denormalized for RLS simplicity. UNIQUE (screen_id, component_id, slot)';
COMMENT ON COLUMN screen_components.screen_id IS
    'T-V3-D-13 / ADR-017: FK to bf_mocks(id). v1 spec Screen entity (E-022) は E-058 BFMock に merge 済 (ADR-017)';
COMMENT ON POLICY components_service_role_all ON components IS
    'T-V3-D-13: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY components_workspace_member_select ON components IS
    'T-V3-D-13: same-workspace member のみ SELECT 可 (bf_can_access_workspace 経由)';
COMMENT ON POLICY screen_components_service_role_all ON screen_components IS
    'T-V3-D-13: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY screen_components_workspace_member_select ON screen_components IS
    'T-V3-D-13: same-workspace member のみ SELECT 可 (bf_can_access_workspace 経由)';
