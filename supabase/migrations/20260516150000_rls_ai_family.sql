-- =============================================================================
-- T-V3-D-05: RLS policy 補完 batch 1 — AI hierarchy / clone family
-- =============================================================================
-- Target tables (E-044 / E-045 / E-046):
--   1. ai_clones        (M-22 個人クローン、user_scoped tenant isolation)
--   2. ai_hierarchies   (parent/child link of ai_employees, account_scoped via
--                        ai_employees.workspace_id → workspaces.account_id)
--   3. ai_personas      (BMAD persona seed table, globally readable but
--                        write-restricted to service_role)
--
-- Background (drift summary):
--   既存 migration `20260512200000_ai_hierarchy_clone_tables.sql` で
--     - ai_clones        : service_role + owner (user_id = auth.uid())
--     - ai_hierarchies   : service_role + member (bf_can_access_workspace)
--     - ai_personas      : service_role + read (global SELECT)
--   までは設定済み. 本 migration は v3 drift summary の access_policies_required
--   (`ai_clones:ai_clones_account_member_select` ほか) に従い、 account_members
--   経由の SELECT policy を **追加** する (account_owner が複数 workspace を
--   横断して所属 ai_clones / ai_hierarchies を可視化する経路を確立).
--
-- 既存 policy は drop せず、 同名の追加 policy を idempotent に CREATE する.
-- Postgres の RLS は policy が複数あるとき OR で結合するため、 既存 owner /
-- member policy と新規 account_member_select policy は accumulative.
--
-- AC マッピング (T-V3-D-05):
--   AC-F1 UBIQUITOUS : 各 table に >= 2 policy (service_role_all + account_member_select)
--   AC-F2 EVENT      : auth user が非所属 account の ai_clones を query → 0 row
--   AC-F3 EVENT      : service_role が ai_clones を query → 全 row
--   AC-F4 UNWANTED   : verify-rls-coverage.py で 3 table の policy_count < 2 なら fail
--
-- 詳細: docs/audit/2026-05-16_v3/T-V3-D-05.md
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- helper: account_members 経由で current user の account_id 集合を返す
-- (RLS policy の WHERE 句で IN (subquery) と組み合わせて使う)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bf_current_user_account_ids()
RETURNS SETOF BIGINT LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT account_id
      FROM account_members
     WHERE user_id = auth.uid()::text
$$;

COMMENT ON FUNCTION bf_current_user_account_ids() IS
    'T-V3-D-05: current authenticated user が所属する account_id の集合.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. ai_clones — account_member_select 追加
-- ai_clones は user_id 直接保有 (user_scoped) かつ workspace_id を持つので
-- account_member_select は workspace_id → workspaces.account_id 経由で判定.
-- (workspace_id が NULL の row は account 紐付けが無いため対象外)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE ai_clones ENABLE ROW LEVEL SECURITY;

-- service_role policy: 念のため再宣言 (idempotent)
DROP POLICY IF EXISTS ai_clones_service_role_all ON ai_clones;
CREATE POLICY ai_clones_service_role_all ON ai_clones
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

-- account_member_select: account_members に紐付く user が所属 workspace の
-- clone を SELECT 可能 (FOR ALL ではなく FOR SELECT のみ; 書き込みは既存 owner
-- policy を利用)
DROP POLICY IF EXISTS ai_clones_account_member_select ON ai_clones;
CREATE POLICY ai_clones_account_member_select ON ai_clones
    FOR SELECT TO authenticated
    USING (
        workspace_id IS NOT NULL
        AND workspace_id IN (
            SELECT id FROM workspaces
             WHERE account_id IN (SELECT bf_current_user_account_ids())
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. ai_hierarchies — account_member_select 追加
-- ai_hierarchies は workspace_id を直接保有 (account_scoped via workspaces)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE ai_hierarchies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ai_hierarchies_service_role_all ON ai_hierarchies;
CREATE POLICY ai_hierarchies_service_role_all ON ai_hierarchies
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS ai_hierarchies_account_member_select ON ai_hierarchies;
CREATE POLICY ai_hierarchies_account_member_select ON ai_hierarchies
    FOR SELECT TO authenticated
    USING (
        workspace_id IS NOT NULL
        AND workspace_id IN (
            SELECT id FROM workspaces
             WHERE account_id IN (SELECT bf_current_user_account_ids())
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. ai_personas — account_member_select 追加
-- ai_personas は global seed table (account / workspace 列なし)
-- account_member_select は「いずれかの account に属する user は read 可」と
-- 解釈する (実質、 認証済み + account_members に 1 件以上ある user に限定).
-- これにより未 onboard user (招待保留中など) を排除する.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE ai_personas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ai_personas_service_role_all ON ai_personas;
CREATE POLICY ai_personas_service_role_all ON ai_personas
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS ai_personas_account_member_select ON ai_personas;
CREATE POLICY ai_personas_account_member_select ON ai_personas
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM account_members
             WHERE user_id = auth.uid()::text
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260516150000', 'T-V3-D-05: RLS policy 補完 batch 1 (ai_clones / ai_hierarchies / ai_personas account_member_select)', 'system')
ON CONFLICT (version) DO NOTHING;


COMMENT ON POLICY ai_clones_account_member_select ON ai_clones IS
    'T-V3-D-05: account_members 経由で同 account 配下 workspace の clone を SELECT 可';
COMMENT ON POLICY ai_hierarchies_account_member_select ON ai_hierarchies IS
    'T-V3-D-05: account_members 経由で同 account 配下 workspace の hierarchy を SELECT 可';
COMMENT ON POLICY ai_personas_account_member_select ON ai_personas IS
    'T-V3-D-05: 何らかの account_members レコードを持つ authenticated user に persona seed を開示';
