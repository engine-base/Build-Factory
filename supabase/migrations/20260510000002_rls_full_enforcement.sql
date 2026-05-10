-- =============================================================================
-- T-001-06: RLS 全テーブル enforcement + custom_permissions 連動
-- =============================================================================
-- 全 user-data テーブルに RLS を有効化し、scope に応じて authenticated
-- policy を付与する。スコープ列が無い legacy テーブルは service_role 専用に
-- ロックダウン (authenticated は読み書き不可) する。
--
-- 既に RLS 設定済みのテーブル (T-001-02 / T-001-04 / rls_skeleton):
--   knowledge_base, users, auth_sessions, user_2fa_secrets,
--   user_2fa_recovery_codes, oauth_connections, auth_audit_log,
--   bf_projects, bf_phases, bf_features, bf_tasks, bf_task_dependencies,
--   bf_acceptance_criteria, bf_constitutions, bf_constitution_revisions,
--   bf_mocks, bf_deliveries, audit_logs (= 18 tables)
--
-- 本 migration が enable する追加テーブル (= 55):
--   workspace 直接 / 経由スコープ (15): workspace_members, workspace_invitations,
--     accounts, account_members, workspaces, ai_employee_config, ai_employee_skills,
--     threads, conversation_log, conversation_slots, artifacts, artifact_events,
--     repos, reviews, design_frames, design_canvas_state, design_mocks,
--     pull_requests, approval_queue, checkpoints, writes
--   legacy single-user (service_role only) (40+):
--     invoices, pipeline, contacts, contracts, outsource_jobs, brand_assets,
--     seo_reports, kpi_records, network, expenses, sns_posts, pl_records,
--     cf_forecasts, cs_feedback, tools_inventory, portfolio_items,
--     weekly_reviews, monthly_reviews, okr, outreach_log, task_log,
--     task_questions, workflow_runs, workflow_steps, slack_processed_messages,
--     user_profile, browser_task_queue, task_schedule, execution_log,
--     communication_log, knowledge_transfer_log, projects (legacy), tasks (legacy),
--     skill_definitions
--
-- AC-3 STATE: service_role bypass は trusted backend code のみ
-- AC-4 OPTIONAL: account_owner はクロス workspace 読み取り可
-- AC-5 UNWANTED: RLS 未設定 table があれば verify-rls-coverage.py で検出
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- helper: account ownership 判定 (AC-4 OPTIONAL)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bf_is_account_owner(acc_id BIGINT)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT EXISTS (
        SELECT 1 FROM account_members
        WHERE account_id = acc_id
          AND user_id = auth.uid()::text
          AND role = 'owner'
    );
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- workspace 経由スコープ (workspace_members で参加判定)
-- bf_can_access_workspace は T-001-04 で定義済み
-- ─────────────────────────────────────────────────────────────────────────────

-- workspace_members (本人 + service_role)
ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_members_service_role ON workspace_members;
CREATE POLICY workspace_members_service_role ON workspace_members FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS workspace_members_self ON workspace_members;
CREATE POLICY workspace_members_self ON workspace_members FOR SELECT TO authenticated
    USING (user_id = auth.uid()::text OR bf_can_access_workspace(workspace_id));

-- workspace_invitations
ALTER TABLE workspace_invitations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_invitations_service_role ON workspace_invitations;
CREATE POLICY workspace_invitations_service_role ON workspace_invitations FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS workspace_invitations_member ON workspace_invitations;
CREATE POLICY workspace_invitations_member ON workspace_invitations FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));

-- accounts (account_members 経由 + AC-4 owner クロス読み取り)
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS accounts_service_role ON accounts;
CREATE POLICY accounts_service_role ON accounts FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS accounts_member_read ON accounts;
CREATE POLICY accounts_member_read ON accounts FOR SELECT TO authenticated
    USING (
        owner_user_id = auth.uid()::text
        OR id IN (SELECT account_id FROM account_members WHERE user_id = auth.uid()::text)
    );
DROP POLICY IF EXISTS accounts_owner_write ON accounts;
CREATE POLICY accounts_owner_write ON accounts FOR UPDATE TO authenticated
    USING (owner_user_id = auth.uid()::text)
    WITH CHECK (owner_user_id = auth.uid()::text);

-- account_members
ALTER TABLE account_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS account_members_service_role ON account_members;
CREATE POLICY account_members_service_role ON account_members FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS account_members_self ON account_members;
CREATE POLICY account_members_self ON account_members FOR SELECT TO authenticated
    USING (user_id = auth.uid()::text OR bf_is_account_owner(account_id));

-- workspaces (account 配下 + AC-4 owner クロス読み取り)
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspaces_service_role ON workspaces;
CREATE POLICY workspaces_service_role ON workspaces FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS workspaces_member_read ON workspaces;
CREATE POLICY workspaces_member_read ON workspaces FOR SELECT TO authenticated
    USING (
        bf_can_access_workspace(id)
        OR bf_is_account_owner(account_id)             -- AC-4 OPTIONAL
    );

-- ai_employee_config (account 配下)
ALTER TABLE ai_employee_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_employee_config_service_role ON ai_employee_config;
CREATE POLICY ai_employee_config_service_role ON ai_employee_config FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS ai_employee_config_member ON ai_employee_config;
CREATE POLICY ai_employee_config_member ON ai_employee_config FOR SELECT TO authenticated
    USING (account_id IS NULL OR bf_is_account_owner(account_id) OR account_id IN (SELECT account_id FROM account_members WHERE user_id = auth.uid()::text));

-- ai_employee_skills
ALTER TABLE ai_employee_skills ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_employee_skills_service_role ON ai_employee_skills;
CREATE POLICY ai_employee_skills_service_role ON ai_employee_skills FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- threads (workspace_id)
ALTER TABLE threads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS threads_service_role ON threads;
CREATE POLICY threads_service_role ON threads FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS threads_member ON threads;
CREATE POLICY threads_member ON threads FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- conversation_log
ALTER TABLE conversation_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversation_log_service_role ON conversation_log;
CREATE POLICY conversation_log_service_role ON conversation_log FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS conversation_log_member ON conversation_log;
CREATE POLICY conversation_log_member ON conversation_log FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- conversation_slots
ALTER TABLE conversation_slots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversation_slots_service_role ON conversation_slots;
CREATE POLICY conversation_slots_service_role ON conversation_slots FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS conversation_slots_member ON conversation_slots;
CREATE POLICY conversation_slots_member ON conversation_slots FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- artifacts
ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS artifacts_service_role ON artifacts;
CREATE POLICY artifacts_service_role ON artifacts FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS artifacts_member ON artifacts;
CREATE POLICY artifacts_member ON artifacts FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- artifact_events
ALTER TABLE artifact_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS artifact_events_service_role ON artifact_events;
CREATE POLICY artifact_events_service_role ON artifact_events FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- repos (workspace_id)
ALTER TABLE repos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS repos_service_role ON repos;
CREATE POLICY repos_service_role ON repos FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS repos_member ON repos;
CREATE POLICY repos_member ON repos FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- reviews
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS reviews_service_role ON reviews;
CREATE POLICY reviews_service_role ON reviews FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS reviews_member ON reviews;
CREATE POLICY reviews_member ON reviews FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- pull_requests
ALTER TABLE pull_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pull_requests_service_role ON pull_requests;
CREATE POLICY pull_requests_service_role ON pull_requests FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- design_frames
ALTER TABLE design_frames ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS design_frames_service_role ON design_frames;
CREATE POLICY design_frames_service_role ON design_frames FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS design_frames_member ON design_frames;
CREATE POLICY design_frames_member ON design_frames FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- design_canvas_state
ALTER TABLE design_canvas_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS design_canvas_state_service_role ON design_canvas_state;
CREATE POLICY design_canvas_state_service_role ON design_canvas_state FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS design_canvas_state_member ON design_canvas_state;
CREATE POLICY design_canvas_state_member ON design_canvas_state FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- design_mocks
ALTER TABLE design_mocks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS design_mocks_service_role ON design_mocks;
CREATE POLICY design_mocks_service_role ON design_mocks FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS design_mocks_member ON design_mocks;
CREATE POLICY design_mocks_member ON design_mocks FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- approval_queue
ALTER TABLE approval_queue ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS approval_queue_service_role ON approval_queue;
CREATE POLICY approval_queue_service_role ON approval_queue FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS approval_queue_member ON approval_queue;
CREATE POLICY approval_queue_member ON approval_queue FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- checkpoints
ALTER TABLE checkpoints ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS checkpoints_service_role ON checkpoints;
CREATE POLICY checkpoints_service_role ON checkpoints FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- writes (legacy, scope unclear)
ALTER TABLE writes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS writes_service_role ON writes;
CREATE POLICY writes_service_role ON writes FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- ─────────────────────────────────────────────────────────────────────────────
-- legacy single-user tables: service_role only (authenticated 不可)
-- これらは元々 masato 単一ユーザ向けで scope 列を持たない。
-- multi-tenant 化は別タスクで段階的に scope 列追加 + policy 強化。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    t TEXT;
    legacy_tables TEXT[] := ARRAY[
        'invoices','pipeline','contacts','contracts','outsource_jobs','brand_assets',
        'seo_reports','kpi_records','network','expenses','sns_posts','pl_records',
        'cf_forecasts','cs_feedback','tools_inventory','portfolio_items',
        'weekly_reviews','monthly_reviews','okr','outreach_log','task_log',
        'task_questions','workflow_runs','workflow_steps','slack_processed_messages',
        'user_profile','browser_task_queue','task_schedule','execution_log',
        'communication_log','knowledge_transfer_log','projects','tasks',
        'skill_definitions','bf_task_dependencies','bf_acceptance_criteria',
        'bf_constitution_revisions'
    ];
BEGIN
    FOREACH t IN ARRAY legacy_tables LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I_service_role ON %I', t, t);
        EXECUTE format(
            'CREATE POLICY %I_service_role ON %I FOR ALL TO postgres, service_role USING (true) WITH CHECK (true)',
            t, t
        );
    END LOOP;
END$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- alembic_version は system metadata (migration tracker) なので RLS 対象外。
-- 念のため明示的に service_role-only ポリシーを付与。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE IF EXISTS alembic_version ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS alembic_version_service_role ON alembic_version;
CREATE POLICY alembic_version_service_role ON alembic_version
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- ─────────────────────────────────────────────────────────────────────────────
-- AC-5 UNWANTED 検証: 「RLS 未設定の table があれば fail」
-- 検証用の SQL function。 verify-rls-coverage.py から呼ぶ。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bf_tables_without_rls()
RETURNS TABLE(table_name TEXT) LANGUAGE sql STABLE AS $$
    SELECT c.relname::TEXT
    FROM pg_class c
    JOIN pg_namespace n ON c.relnamespace = n.oid
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relrowsecurity = false
    ORDER BY c.relname;
$$;
