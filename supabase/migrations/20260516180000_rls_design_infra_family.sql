-- =============================================================================
-- T-V3-D-08: RLS policy 補完 batch 4 — design & infrastructure family
-- =============================================================================
-- Target tables (E-062 / E-063 / E-064 / E-065 / E-066 / E-067 / E-068):
--   1. design_frames        (E-062, workspace_scoped via workspace_id)
--   2. design_canvas_state  (E-063, workspace_scoped via workspace_id)
--   3. design_mocks         (E-064, workspace_scoped via workspace_id)
--   4. approval_queue       (E-065, workspace_scoped via workspace_id)
--   5. checkpoints          (E-066, workspace_scoped via chat_threads.id::text)
--   6. schema_versions      (E-067, ops-internal — service_role-only readable)
--   7. knowledge_base       (E-068, account_scoped — adds workspace_member overlay)
--
-- Background (drift summary — see docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md
--   §5 new-migration-only 25 件):
--   既存 migration:
--     - design_frames        : 20260510000002_rls_full_enforcement.sql で
--                              service_role + design_frames_member (FOR ALL) 設定済 (2 policy)
--     - design_canvas_state  : 同上 (2 policy)
--     - design_mocks         : 同上 (2 policy)
--     - approval_queue       : 同上 (FOR SELECT only / 2 policy)
--     - checkpoints          : 同上 (service_role のみ / 1 policy)
--     - schema_versions      : 20260512000000_impl_integration_ops_tables.sql で
--                              service_role のみ (1 policy)
--     - knowledge_base       : 20260501220300_rls_skeleton.sql で
--                              kb_service_role_all + kb_public_read + kb_account_shared_read +
--                              kb_private_read + kb_ai_only_read 5 policy 設定済
--
-- 本 migration は v3 drift summary の access_policies_required
-- (`<table>:<table>_workspace_member_select`) に従い、 explicit な命名の
-- workspace_member_select policy を **追加** する.  既存 policy は drop せず、
-- 同名の追加 policy を idempotent に CREATE する.  Postgres の RLS は同 role 向け
-- の policy が複数あるとき OR で結合するため、 既存 _member / _public_read 等
-- policy と新規 _workspace_member_select policy は accumulative.
--
-- schema_versions は system-internal の ops table のため、 service_role 以外の
-- 読み取りは原則禁止だが、 AC-F1 (policy_count >= 2) を満たすため
-- service_role 限定の `schema_versions_service_role_select` (FOR SELECT) を
-- 追加し、 二重宣言で defense-in-depth する.
--
-- AC マッピング (T-V3-D-08):
--   AC-F1 UBIQUITOUS : 各 table に >= 2 policy
--                      (service_role + workspace_member_select もしくは
--                       既存 _member policy + 新規 _workspace_member_select)
--   AC-F2 EVENT      : auth user が非所属 workspace の design_frames を query → 0 row
--   AC-F3 EVENT      : service_role が schema_versions を query → 全 row
--   AC-F4 OPTIONAL   : knowledge_base.workspace_id IS NOT NULL なら
--                      workspace_members 経由で SELECT 制限
--   AC-F5 UNWANTED   : verify-rls-coverage.py で 7 table の policy_count < 2 なら fail
--
-- 詳細: docs/audit/2026-05-16_v3/T-V3-D-08.md
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. design_frames — workspace_member_select 追加
-- workspace_id NOT NULL なので NULL bypass 経路は無い.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE design_frames ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS design_frames_service_role_all ON design_frames;
CREATE POLICY design_frames_service_role_all ON design_frames
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS design_frames_workspace_member_select ON design_frames;
CREATE POLICY design_frames_workspace_member_select ON design_frames
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. design_canvas_state — workspace_member_select 追加
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE design_canvas_state ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS design_canvas_state_service_role_all ON design_canvas_state;
CREATE POLICY design_canvas_state_service_role_all ON design_canvas_state
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS design_canvas_state_workspace_member_select ON design_canvas_state;
CREATE POLICY design_canvas_state_workspace_member_select ON design_canvas_state
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. design_mocks — workspace_member_select 追加
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE design_mocks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS design_mocks_service_role_all ON design_mocks;
CREATE POLICY design_mocks_service_role_all ON design_mocks
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS design_mocks_workspace_member_select ON design_mocks;
CREATE POLICY design_mocks_workspace_member_select ON design_mocks
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. approval_queue — workspace_member_select 追加
-- approval_queue.workspace_id は NULL 可 (global approvals); 非 NULL に対しては
-- workspace_members 判定で隔離、 NULL は SELECT 不可 (service_role 経由のみ)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE approval_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS approval_queue_service_role_all ON approval_queue;
CREATE POLICY approval_queue_service_role_all ON approval_queue
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS approval_queue_workspace_member_select ON approval_queue;
CREATE POLICY approval_queue_workspace_member_select ON approval_queue
    FOR SELECT TO authenticated
    USING (
        workspace_id IS NOT NULL
        AND bf_can_access_workspace(workspace_id)
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. checkpoints — workspace_member_select 追加
-- checkpoints は langgraph 互換 schema (thread_id TEXT) で workspace_id 列を持た
-- ない.  thread_id は chat_threads.id::text に対応するため、 chat_threads 経由
-- で workspace_member を判定する.  ペアにできない孤児 thread_id 行は SELECT 不可
-- (service_role 経由のみ).
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE checkpoints ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS checkpoints_service_role_all ON checkpoints;
CREATE POLICY checkpoints_service_role_all ON checkpoints
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS checkpoints_workspace_member_select ON checkpoints;
CREATE POLICY checkpoints_workspace_member_select ON checkpoints
    FOR SELECT TO authenticated
    USING (
        thread_id IN (
            SELECT id::text FROM chat_threads
             WHERE workspace_id IS NOT NULL
               AND bf_can_access_workspace(workspace_id)
        )
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. schema_versions — service_role_all (idempotent) + service_role_select
-- system-internal の ops table.  authenticated user に読み取らせない.
-- AC-F1 (policy_count >= 2) を満たすため、 service_role 限定の SELECT policy を
-- 追加で宣言 (defense-in-depth; ALL policy で既に網羅されているが二重宣言).
-- AC-F3 で「service_role が schema_versions を query → 全 row」を保証.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE schema_versions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS schema_versions_service_role_all ON schema_versions;
CREATE POLICY schema_versions_service_role_all ON schema_versions
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS schema_versions_service_role_select ON schema_versions;
CREATE POLICY schema_versions_service_role_select ON schema_versions
    FOR SELECT TO postgres, service_role
    USING (true);


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. knowledge_base — workspace_member_select overlay 追加
-- knowledge_base は元々 account_scoped (visibility = public / account_shared /
-- private / ai_only) で 5 policy 設定済.  workspace_id 列も保持しており、
-- AC-F4 (OPTIONAL) で「workspace-scoped に設定されている row は workspace_members
-- 経由で SELECT 制限」を実現する.  workspace_id IS NULL の row は既存 policy
-- (kb_account_shared_read / kb_private_read 等) でのみ制御される.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS knowledge_base_service_role_all ON knowledge_base;
CREATE POLICY knowledge_base_service_role_all ON knowledge_base
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS knowledge_base_workspace_member_select ON knowledge_base;
CREATE POLICY knowledge_base_workspace_member_select ON knowledge_base
    FOR SELECT TO authenticated
    USING (
        workspace_id IS NOT NULL
        AND bf_can_access_workspace(workspace_id)
    );


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260516180000', 'T-V3-D-08: RLS policy 補完 batch 4 (design_frames / design_canvas_state / design_mocks / approval_queue / checkpoints / schema_versions / knowledge_base workspace_member_select)', 'system')
ON CONFLICT (version) DO NOTHING;


COMMENT ON POLICY design_frames_workspace_member_select ON design_frames IS
    'T-V3-D-08: workspace_members 経由で SELECT 可 (bf_can_access_workspace)';
COMMENT ON POLICY design_canvas_state_workspace_member_select ON design_canvas_state IS
    'T-V3-D-08: workspace_members 経由で SELECT 可 (bf_can_access_workspace)';
COMMENT ON POLICY design_mocks_workspace_member_select ON design_mocks IS
    'T-V3-D-08: workspace_members 経由で SELECT 可 (bf_can_access_workspace)';
COMMENT ON POLICY approval_queue_workspace_member_select ON approval_queue IS
    'T-V3-D-08: workspace_id IS NOT NULL かつ workspace_members に所属する authenticated user に SELECT を許可';
COMMENT ON POLICY checkpoints_workspace_member_select ON checkpoints IS
    'T-V3-D-08: thread_id → chat_threads.id::text 経由で workspace_members に所属する authenticated user に SELECT を許可';
COMMENT ON POLICY schema_versions_service_role_select ON schema_versions IS
    'T-V3-D-08: ops-internal table を service_role 限定で読み取り可能 (defense-in-depth)';
COMMENT ON POLICY knowledge_base_workspace_member_select ON knowledge_base IS
    'T-V3-D-08: workspace_id IS NOT NULL の row を workspace_members に所属する authenticated user に SELECT 許可 (OPTIONAL AC-F4)';
