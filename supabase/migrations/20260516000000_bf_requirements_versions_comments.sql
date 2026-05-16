-- T-V3-B-10 / F-006: Requirements backend (CRUD / versions / task comments)
--
-- Phase 1 v3 Wave 1 で新規作成する 3 table:
--   1. bf_requirements          — workspace 単位の EARS 要件 (CRUD ターゲット)
--   2. bf_requirement_versions  — requirements snapshot (POST /versions が生成)
--   3. bf_task_comments         — bf_tasks への comment (POST /api/tasks/{id}/comments)
--
-- AC マッピング (T-V3-B-10):
--   AC-F1 (EVENT-DRIVEN PUT persist + version+1)         → bf_requirements + version_seq logic
--   AC-F3 (EVENT-DRIVEN POST versions snapshot)          → bf_requirement_versions
--   AC-F13 (EVENT-DRIVEN POST comments returns comment_id) → bf_task_comments
--   AC-R4 (Gate 4 RLS coverage)                          → ENABLE ROW LEVEL SECURITY + service_role/member policies
--
-- F-006 entities (entities.json):
--   E-015 Requirement / E-016 Task (existing bf_tasks) / E-017 TaskDependency / E-019 AcceptanceCriterion
--
-- access_control_policies (workspace_scoped + service_role):
--   - bf_*_service_role_all   : service_role 全権 (RLS bypass 相当)
--   - bf_*_member_select      : workspace_member SELECT
--   - bf_*_member_write       : workspace_member ALL (admin / contributor は contributor 以上で書込)

-- =============================================================================
-- 1. bf_requirements — F-006 workspace-level requirement items
-- =============================================================================
CREATE TABLE IF NOT EXISTS bf_requirements (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    item_index      INTEGER NOT NULL,           -- PUT 時の items 配列の index 順
    ears_type       TEXT NOT NULL
                        CHECK (ears_type IN ('UBIQUITOUS','EVENT-DRIVEN','STATE-DRIVEN','OPTIONAL','UNWANTED')),
    text            TEXT NOT NULL,              -- raw EARS 文 (例: "When ..., the system shall ...")
    title           TEXT,
    category        TEXT,                       -- functional / nonfunctional / legal etc
    version         INTEGER NOT NULL DEFAULT 1, -- 現在 version (PUT のたびに +1)
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_req_ws_index UNIQUE (workspace_id, item_index)
);
CREATE INDEX IF NOT EXISTS ix_bf_requirements_ws ON bf_requirements(workspace_id);
CREATE INDEX IF NOT EXISTS ix_bf_requirements_ws_idx ON bf_requirements(workspace_id, item_index);

-- =============================================================================
-- 2. bf_requirement_versions — 明示的に snapshot された version (POST /versions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS bf_requirement_versions (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    version_number  INTEGER NOT NULL,
    message         TEXT,                       -- snapshot コミットメッセージ (caller 指定)
    snapshot        JSONB NOT NULL,             -- bf_requirements 全件の snapshot
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_bf_req_ver UNIQUE (workspace_id, version_number)
);
CREATE INDEX IF NOT EXISTS ix_bf_req_versions_ws ON bf_requirement_versions(workspace_id, created_at DESC);

-- =============================================================================
-- 3. bf_task_comments — bf_tasks への comment
-- =============================================================================
CREATE TABLE IF NOT EXISTS bf_task_comments (
    id              BIGSERIAL PRIMARY KEY,
    task_id         BIGINT NOT NULL REFERENCES bf_tasks(id) ON DELETE CASCADE,
    body            TEXT NOT NULL,
    author_user_id  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT bf_task_comments_body_nonempty CHECK (length(trim(body)) > 0)
);
CREATE INDEX IF NOT EXISTS ix_bf_task_comments_task
    ON bf_task_comments(task_id, created_at DESC);

-- =============================================================================
-- RLS (workspace_scoped — service_role + workspace_member)
-- =============================================================================

-- 1. bf_requirements
ALTER TABLE bf_requirements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_requirements_service_role_all ON bf_requirements;
CREATE POLICY bf_requirements_service_role_all ON bf_requirements
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_requirements_workspace_member_select ON bf_requirements;
CREATE POLICY bf_requirements_workspace_member_select ON bf_requirements
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));
DROP POLICY IF EXISTS bf_requirements_workspace_member_write ON bf_requirements;
CREATE POLICY bf_requirements_workspace_member_write ON bf_requirements
    FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- 2. bf_requirement_versions
ALTER TABLE bf_requirement_versions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_requirement_versions_service_role_all ON bf_requirement_versions;
CREATE POLICY bf_requirement_versions_service_role_all ON bf_requirement_versions
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_requirement_versions_workspace_member_select ON bf_requirement_versions;
CREATE POLICY bf_requirement_versions_workspace_member_select ON bf_requirement_versions
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));
DROP POLICY IF EXISTS bf_requirement_versions_workspace_member_write ON bf_requirement_versions;
CREATE POLICY bf_requirement_versions_workspace_member_write ON bf_requirement_versions
    FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- 3. bf_task_comments — task の workspace_id を bf_tasks → bf_projects 経由で取得
ALTER TABLE bf_task_comments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS bf_task_comments_service_role_all ON bf_task_comments;
CREATE POLICY bf_task_comments_service_role_all ON bf_task_comments
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bf_task_comments_workspace_member_select ON bf_task_comments;
CREATE POLICY bf_task_comments_workspace_member_select ON bf_task_comments
    FOR SELECT TO authenticated
    USING (task_id IN (
        SELECT bt.id FROM bf_tasks bt
        JOIN bf_projects bp ON bt.project_id = bp.id
        WHERE bf_can_access_workspace(bp.workspace_id)
    ));
DROP POLICY IF EXISTS bf_task_comments_workspace_member_write ON bf_task_comments;
CREATE POLICY bf_task_comments_workspace_member_write ON bf_task_comments
    FOR ALL TO authenticated
    USING (task_id IN (
        SELECT bt.id FROM bf_tasks bt
        JOIN bf_projects bp ON bt.project_id = bp.id
        WHERE bf_can_access_workspace(bp.workspace_id)
    ))
    WITH CHECK (task_id IN (
        SELECT bt.id FROM bf_tasks bt
        JOIN bf_projects bp ON bt.project_id = bp.id
        WHERE bf_can_access_workspace(bp.workspace_id)
    ));
