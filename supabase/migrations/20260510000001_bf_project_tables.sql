-- =============================================================================
-- T-001-04: Build-Factory プロジェクト 11 テーブル DDL + RLS
-- =============================================================================
-- 既存 legacy `projects` / `tasks` (BIGSERIAL, single-user) と区別するため
-- bf_ prefix を採用。Build-Factory が回す各案件の Phase / Feature / Task /
-- EARS AC / Constitution / Mock / Delivery を表現する。
--
-- 11 tables:
--   1.  bf_projects                — 案件 (workspace に 1:N)
--   2.  bf_phases                  — 8 phase per project (hearing → delivery)
--   3.  bf_features                — F-XXX (functional-breakdown 由来)
--   4.  bf_tasks                   — T-XXX (実装単位)
--   5.  bf_task_dependencies       — DAG edges (deps / blocks)
--   6.  bf_acceptance_criteria     — EARS AC (5 形式)
--   7.  bf_constitutions           — masato/owner の判断基準 JSONB
--   8.  bf_constitution_revisions  — 改訂履歴 (audit)
--   9.  bf_mocks                   — UI モック S-XXX
--   10. bf_deliveries              — 納品レコード
--   11. audit_logs                 — workspace 横断の汎用 audit
--
-- 設計方針:
--   - PK: BIGSERIAL (workspaces / accounts と整合 / NEW で UUID 採用は次フェーズ)
--   - workspace_id: BIGINT FK to workspaces(id) ON DELETE CASCADE
--   - user_id: TEXT (workspace_members.user_id TEXT に整合 / auth.uid()::text)
--   - 全 created_at/updated_at: TIMESTAMPTZ DEFAULT NOW()
--   - 全 CREATE TABLE IF NOT EXISTS / DROP POLICY IF EXISTS で idempotent (AC-2)
--   - RLS: workspace_members への参加で許可 + service_role 全権 (AC-3)
--   - EARS type CHECK: AC-5
--   - 自己参照 dependency 防止 CHECK: AC-5
--   - constitution principles 非空 CHECK: AC-4
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. bf_projects — 案件 (workspace 配下)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_projects (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL,
    client_name     TEXT,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'planning'
                        CHECK (status IN ('planning','hearing','requirements','architecture',
                                          'functional','tech','feature','task','mocks',
                                          'implementation','review','delivered','cancelled')),
    deadline        DATE,
    started_at      TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_project_slug UNIQUE (workspace_id, slug)
);
CREATE INDEX IF NOT EXISTS ix_bf_projects_ws ON bf_projects(workspace_id, status);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. bf_phases — 8 phase per project
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_phases (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES bf_projects(id) ON DELETE CASCADE,
    phase_no        INTEGER NOT NULL CHECK (phase_no BETWEEN 1 AND 10),
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','in_progress','completed','blocked','skipped')),
    artifacts_dir   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_phase UNIQUE (project_id, phase_no)
);
CREATE INDEX IF NOT EXISTS ix_bf_phases_proj ON bf_phases(project_id, phase_no);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. bf_features — F-XXX (functional-breakdown 由来)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_features (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES bf_projects(id) ON DELETE CASCADE,
    feature_id      TEXT NOT NULL,                 -- "F-001"
    title           TEXT NOT NULL,
    description     TEXT,
    priority        TEXT DEFAULT 'must' CHECK (priority IN ('must','should','could','wont')),
    spec_link       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_feature UNIQUE (project_id, feature_id)
);
CREATE INDEX IF NOT EXISTS ix_bf_features_proj ON bf_features(project_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. bf_tasks — T-XXX (実装単位)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_tasks (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES bf_projects(id) ON DELETE CASCADE,
    feature_id      BIGINT REFERENCES bf_features(id) ON DELETE SET NULL,
    phase_id        BIGINT REFERENCES bf_phases(id) ON DELETE SET NULL,
    task_id         TEXT NOT NULL,                 -- "T-001-01"
    title           TEXT NOT NULL,
    description     TEXT,
    label           TEXT NOT NULL CHECK (label IN ('REUSE','REFACTOR','NEW','ARCHIVE')),
    sprint          TEXT,                          -- "S0", "S1"...
    layer           TEXT,                          -- "OPS", "DB", "FE", "BE"...
    status          TEXT NOT NULL DEFAULT 'todo'
                        CHECK (status IN ('todo','in_progress','review','done','blocked','cancelled')),
    assigned_to     TEXT,                          -- AI persona slug or user_id
    estimated_hours NUMERIC(5,2),
    actual_hours    NUMERIC(5,2),
    spec_link       TEXT,
    mock_link       TEXT,
    output_file     TEXT,
    created_by      TEXT,                          -- user_id (TEXT 整合)
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_task UNIQUE (project_id, task_id)
);
CREATE INDEX IF NOT EXISTS ix_bf_tasks_proj      ON bf_tasks(project_id, status);
CREATE INDEX IF NOT EXISTS ix_bf_tasks_assignee  ON bf_tasks(assigned_to, status);
CREATE INDEX IF NOT EXISTS ix_bf_tasks_sprint    ON bf_tasks(project_id, sprint);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. bf_task_dependencies — DAG edges
--    AC-5: 自己参照 dependency 防止 (CHECK depends_on_task_id <> task_id)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_task_dependencies (
    id                  BIGSERIAL PRIMARY KEY,
    task_id             BIGINT NOT NULL REFERENCES bf_tasks(id) ON DELETE CASCADE,
    depends_on_task_id  BIGINT NOT NULL REFERENCES bf_tasks(id) ON DELETE CASCADE,
    dep_type            TEXT NOT NULL DEFAULT 'blocks'
                            CHECK (dep_type IN ('blocks','related','informs')),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_dep UNIQUE (task_id, depends_on_task_id),
    CONSTRAINT no_self_dep CHECK (task_id <> depends_on_task_id)
);
CREATE INDEX IF NOT EXISTS ix_bf_deps_task    ON bf_task_dependencies(task_id);
CREATE INDEX IF NOT EXISTS ix_bf_deps_depends ON bf_task_dependencies(depends_on_task_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. bf_acceptance_criteria — EARS AC (5 形式)
--    AC-5: ears_type CHECK
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_acceptance_criteria (
    id              BIGSERIAL PRIMARY KEY,
    task_id         BIGINT NOT NULL REFERENCES bf_tasks(id) ON DELETE CASCADE,
    ears_type       TEXT NOT NULL
                        CHECK (ears_type IN ('UBIQUITOUS','EVENT','STATE','OPTIONAL','UNWANTED')),
    text            TEXT NOT NULL,
    order_index     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_ac UNIQUE (task_id, order_index)
);
CREATE INDEX IF NOT EXISTS ix_bf_ac_task ON bf_acceptance_criteria(task_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. bf_constitutions — masato/owner の判断基準 JSONB
--    AC-4: principles 非空 CHECK
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_constitutions (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES bf_projects(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL DEFAULT 1,
    principles      JSONB NOT NULL,
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    authored_by     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_constitution_version UNIQUE (project_id, version),
    CONSTRAINT principles_non_empty
        CHECK (jsonb_typeof(principles) = 'object' AND principles <> '{}'::jsonb)
);
CREATE INDEX IF NOT EXISTS ix_bf_constitutions_current
    ON bf_constitutions(project_id) WHERE is_current = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 8. bf_constitution_revisions — 改訂履歴 (audit)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_constitution_revisions (
    id              BIGSERIAL PRIMARY KEY,
    constitution_id BIGINT NOT NULL REFERENCES bf_constitutions(id) ON DELETE CASCADE,
    diff            JSONB NOT NULL,                -- JSON Patch RFC6902
    rationale       TEXT,
    revised_by      TEXT,
    revised_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_bf_const_rev_const ON bf_constitution_revisions(constitution_id, revised_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 9. bf_mocks — UI モック S-XXX
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_mocks (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES bf_projects(id) ON DELETE CASCADE,
    feature_id      BIGINT REFERENCES bf_features(id) ON DELETE SET NULL,
    mock_id         TEXT NOT NULL,                  -- "S-001-login"
    title           TEXT NOT NULL,
    html_path       TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_mock UNIQUE (project_id, mock_id, version)
);
CREATE INDEX IF NOT EXISTS ix_bf_mocks_proj ON bf_mocks(project_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 10. bf_deliveries — 納品レコード
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bf_deliveries (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES bf_projects(id) ON DELETE CASCADE,
    delivery_no     INTEGER NOT NULL,
    delivered_at    TIMESTAMPTZ DEFAULT NOW(),
    deliverables    JSONB NOT NULL,                  -- {kind: spec|code|design, items: [...]}
    accepted_at     TIMESTAMPTZ,
    accepted_by     TEXT,
    notes           TEXT,
    CONSTRAINT uq_bf_delivery_no UNIQUE (project_id, delivery_no)
);
CREATE INDEX IF NOT EXISTS ix_bf_deliveries_proj ON bf_deliveries(project_id, delivered_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 11. audit_logs — workspace 横断の汎用 audit
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    actor_user_id   TEXT,
    actor_persona   TEXT,
    action          TEXT NOT NULL,                  -- "task.create" / "constitution.update" など
    resource_type   TEXT,                           -- "bf_task" / "bf_constitution" など
    resource_id     BIGINT,
    payload         JSONB DEFAULT '{}'::jsonb,
    success         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_audit_ws       ON audit_logs(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_action   ON audit_logs(action, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_actor    ON audit_logs(actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_failures ON audit_logs(created_at DESC) WHERE success = FALSE;

-- =============================================================================
-- RLS: workspace 参加 + service_role 全権 (AC-3)
-- =============================================================================

-- 共通 helper: workspace_id へのアクセス権チェック
CREATE OR REPLACE FUNCTION bf_can_access_workspace(ws_id BIGINT)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT EXISTS (
        SELECT 1 FROM workspace_members
        WHERE workspace_id = ws_id
          AND user_id = auth.uid()::text
    );
$$;

-- 1. bf_projects (workspace 直接参照)
ALTER TABLE bf_projects ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_projects_service_role ON bf_projects;
CREATE POLICY bf_projects_service_role ON bf_projects FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_projects_member ON bf_projects;
CREATE POLICY bf_projects_member ON bf_projects FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- 2. bf_phases (project 経由)
ALTER TABLE bf_phases ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_phases_service_role ON bf_phases;
CREATE POLICY bf_phases_service_role ON bf_phases FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_phases_member ON bf_phases;
CREATE POLICY bf_phases_member ON bf_phases FOR ALL TO authenticated
    USING (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)))
    WITH CHECK (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)));

-- 3. bf_features
ALTER TABLE bf_features ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_features_service_role ON bf_features;
CREATE POLICY bf_features_service_role ON bf_features FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_features_member ON bf_features;
CREATE POLICY bf_features_member ON bf_features FOR ALL TO authenticated
    USING (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)))
    WITH CHECK (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)));

-- 4. bf_tasks
ALTER TABLE bf_tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_tasks_service_role ON bf_tasks;
CREATE POLICY bf_tasks_service_role ON bf_tasks FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_tasks_member ON bf_tasks;
CREATE POLICY bf_tasks_member ON bf_tasks FOR ALL TO authenticated
    USING (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)))
    WITH CHECK (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)));

-- 5. bf_task_dependencies
ALTER TABLE bf_task_dependencies ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_deps_service_role ON bf_task_dependencies;
CREATE POLICY bf_deps_service_role ON bf_task_dependencies FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_deps_member ON bf_task_dependencies;
CREATE POLICY bf_deps_member ON bf_task_dependencies FOR ALL TO authenticated
    USING (task_id IN (SELECT bt.id FROM bf_tasks bt JOIN bf_projects bp ON bt.project_id = bp.id WHERE bf_can_access_workspace(bp.workspace_id)))
    WITH CHECK (task_id IN (SELECT bt.id FROM bf_tasks bt JOIN bf_projects bp ON bt.project_id = bp.id WHERE bf_can_access_workspace(bp.workspace_id)));

-- 6. bf_acceptance_criteria
ALTER TABLE bf_acceptance_criteria ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_ac_service_role ON bf_acceptance_criteria;
CREATE POLICY bf_ac_service_role ON bf_acceptance_criteria FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_ac_member ON bf_acceptance_criteria;
CREATE POLICY bf_ac_member ON bf_acceptance_criteria FOR ALL TO authenticated
    USING (task_id IN (SELECT bt.id FROM bf_tasks bt JOIN bf_projects bp ON bt.project_id = bp.id WHERE bf_can_access_workspace(bp.workspace_id)))
    WITH CHECK (task_id IN (SELECT bt.id FROM bf_tasks bt JOIN bf_projects bp ON bt.project_id = bp.id WHERE bf_can_access_workspace(bp.workspace_id)));

-- 7. bf_constitutions
ALTER TABLE bf_constitutions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_const_service_role ON bf_constitutions;
CREATE POLICY bf_const_service_role ON bf_constitutions FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_const_member ON bf_constitutions;
CREATE POLICY bf_const_member ON bf_constitutions FOR ALL TO authenticated
    USING (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)))
    WITH CHECK (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)));

-- 8. bf_constitution_revisions
ALTER TABLE bf_constitution_revisions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_const_rev_service_role ON bf_constitution_revisions;
CREATE POLICY bf_const_rev_service_role ON bf_constitution_revisions FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_const_rev_member ON bf_constitution_revisions;
CREATE POLICY bf_const_rev_member ON bf_constitution_revisions FOR SELECT TO authenticated
    USING (constitution_id IN (SELECT bc.id FROM bf_constitutions bc JOIN bf_projects bp ON bc.project_id = bp.id WHERE bf_can_access_workspace(bp.workspace_id)));

-- 9. bf_mocks
ALTER TABLE bf_mocks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_mocks_service_role ON bf_mocks;
CREATE POLICY bf_mocks_service_role ON bf_mocks FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_mocks_member ON bf_mocks;
CREATE POLICY bf_mocks_member ON bf_mocks FOR ALL TO authenticated
    USING (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)))
    WITH CHECK (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)));

-- 10. bf_deliveries
ALTER TABLE bf_deliveries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_deliveries_service_role ON bf_deliveries;
CREATE POLICY bf_deliveries_service_role ON bf_deliveries FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_deliveries_member ON bf_deliveries;
CREATE POLICY bf_deliveries_member ON bf_deliveries FOR ALL TO authenticated
    USING (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)))
    WITH CHECK (project_id IN (SELECT id FROM bf_projects WHERE bf_can_access_workspace(workspace_id)));

-- 11. audit_logs (workspace 直接参照、書き込みは service_role のみ)
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_service_role ON audit_logs;
CREATE POLICY audit_service_role ON audit_logs FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS audit_member_read ON audit_logs;
CREATE POLICY audit_member_read ON audit_logs FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));
