-- =============================================================================
-- T-001-05: 実装・連携・運用 20 テーブル DDL + Template
-- =============================================================================
-- spec: docs/architecture/2026-05-09_v1/architecture-v1.md §4 entities
--
-- 既に他 migration で実装済み (重複作成しない):
--   sessions / session_logs / cost_logs / chat_threads / chat_messages
--     → 20260510000003_runner_session_tables.sql
--   audit_logs / workspaces / bf_projects / bf_tasks / bf_constitutions
--     → 20260510000001_bf_project_tables.sql
--
-- 本 migration で追加するもの (17 テーブル):
--   実装・レビュー (5):
--     1. session_artifacts        — session が生成した成果物 (PR 候補ファイル等)
--     2. prs                       — GitHub PR mirror
--     3. pr_reviews                — PR review コメント履歴
--     4. red_lines                 — Constitution の赤線抽出
--     5. red_line_violations      — 抵触ログ
--   連携・運用 (10):
--     6. llm_providers             — 利用可能 LLM provider 一覧
--     7. api_keys                  — API キー metadata (実値は encrypted_secrets)
--     8. slack_webhooks            — workspace ↔ Slack channel webhook
--     9. github_repos              — workspace ↔ GitHub repo
--    10. obsidian_vaults           — workspace ↔ Obsidian vault path (M-28)
--    11. notifications             — in-app 通知 inbox
--    12. token_limits              — workspace 別 LLM token 上限
--    13. backups                   — DB backup metadata
--    14. user_settings             — user 個別設定 (UI / theme / locale)
--   補助 (2):
--    15. workspace_settings        — workspace 別 feature flags / overrides
--    16. schema_versions           — migration 版数履歴
--   Template (1):
--    17. templates                — タスク / PR / mock テンプレート
--
-- AC マッピング:
--   AC-1 UBIQUITOUS: 17 テーブル + ChatThread/ChatMessage/Template を spec 通り
--   AC-3 STATE:     RLS 全テーブル + workspace_id/account_id 経由 + audit_logs 連携
--   AC-4 UNWANTED:  CHECK 制約 + FK / NOT NULL で persist 拒否
--
-- 全テーブルに共通設計:
--   - id BIGSERIAL PRIMARY KEY
--   - created_at TIMESTAMPTZ DEFAULT NOW()
--   - workspace_id FK (workspace scope) で RLS チェック
--   - DROP POLICY IF EXISTS + CREATE POLICY で idempotent
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. session_artifacts — session が生成した artifact (PR ファイル等)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_artifacts (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    artifact_type   TEXT NOT NULL CHECK (artifact_type IN
        ('file_diff','test_report','build_log','design_html','docs_md','other')),
    file_path       TEXT,
    storage_url     TEXT,
    size_bytes      BIGINT DEFAULT 0,
    sha256          TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_session_artifacts_session ON session_artifacts(session_id);
CREATE INDEX IF NOT EXISTS ix_session_artifacts_ws      ON session_artifacts(workspace_id, created_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. prs — GitHub PR mirror
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prs (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    bf_task_id      BIGINT REFERENCES bf_tasks(id) ON DELETE SET NULL,
    session_id      BIGINT REFERENCES sessions(id) ON DELETE SET NULL,
    github_pr_number INTEGER NOT NULL,
    github_repo     TEXT NOT NULL,
    title           TEXT NOT NULL,
    branch_name     TEXT,
    status          TEXT NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open','draft','merged','closed','review')),
    author          TEXT,
    head_sha        TEXT,
    base_branch     TEXT DEFAULT 'main',
    additions       INTEGER DEFAULT 0,
    deletions       INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_pr_workspace_repo_number UNIQUE (workspace_id, github_repo, github_pr_number)
);
CREATE INDEX IF NOT EXISTS ix_prs_ws        ON prs(workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_prs_task      ON prs(bf_task_id);
CREATE INDEX IF NOT EXISTS ix_prs_session   ON prs(session_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. pr_reviews — PR review コメント履歴
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pr_reviews (
    id              BIGSERIAL PRIMARY KEY,
    pr_id           BIGINT NOT NULL REFERENCES prs(id) ON DELETE CASCADE,
    reviewer        TEXT NOT NULL,                              -- ai_employee_id or user_id
    reviewer_type   TEXT NOT NULL DEFAULT 'human'
                       CHECK (reviewer_type IN ('human','ai_employee')),
    verdict         TEXT NOT NULL DEFAULT 'comment'
                       CHECK (verdict IN ('approved','changes_requested','comment','dismissed')),
    body            TEXT,
    inline_comments JSONB DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_pr_reviews_pr ON pr_reviews(pr_id, created_at);


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. red_lines — Constitution の赤線抽出 (絶対禁止事項)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS red_lines (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    constitution_id BIGINT REFERENCES bf_constitutions(id) ON DELETE CASCADE,
    rule_key        TEXT NOT NULL,                              -- "no_drop_table" / "no_force_push" 等
    pattern         TEXT NOT NULL,                              -- regex / glob
    severity        TEXT NOT NULL DEFAULT 'block'
                       CHECK (severity IN ('block','warn','log')),
    description     TEXT,
    is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_red_line UNIQUE (workspace_id, rule_key)
);
CREATE INDEX IF NOT EXISTS ix_red_lines_ws ON red_lines(workspace_id) WHERE is_enabled = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. red_line_violations — 抵触ログ
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS red_line_violations (
    id              BIGSERIAL PRIMARY KEY,
    red_line_id     BIGINT NOT NULL REFERENCES red_lines(id) ON DELETE CASCADE,
    session_id      BIGINT REFERENCES sessions(id) ON DELETE SET NULL,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    matched_text    TEXT,
    action_taken    TEXT NOT NULL DEFAULT 'blocked'
                       CHECK (action_taken IN ('blocked','warned','logged')),
    detail          JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_red_line_violations_ws  ON red_line_violations(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_red_line_violations_rl  ON red_line_violations(red_line_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. llm_providers — 利用可能 LLM provider 一覧
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_providers (
    id              BIGSERIAL PRIMARY KEY,
    provider_key    TEXT NOT NULL UNIQUE,                         -- "anthropic" / "openai" / "gemini" / "litellm"
    display_name    TEXT NOT NULL,
    is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    auth_method     TEXT NOT NULL DEFAULT 'api_key'
                       CHECK (auth_method IN ('api_key','oauth','byok')),
    base_url        TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_llm_providers_primary ON llm_providers(is_primary) WHERE is_primary = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. api_keys — API キー metadata (実値は encrypted_secrets を参照)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    owner_user_id   TEXT,
    provider_key    TEXT NOT NULL,                                -- "anthropic" 等
    label           TEXT,
    secret_scope    TEXT NOT NULL DEFAULT 'oauth',                -- encrypted_secrets.scope
    secret_key      TEXT NOT NULL,                                -- encrypted_secrets.key
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_api_keys_ws    ON api_keys(workspace_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS ix_api_keys_owner ON api_keys(owner_user_id) WHERE is_active = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 8. slack_webhooks — workspace ↔ Slack channel webhook
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS slack_webhooks (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    channel_id      TEXT NOT NULL,                                -- C0XXXXXXX
    channel_name    TEXT,
    webhook_scope   TEXT NOT NULL DEFAULT 'oauth',
    webhook_key     TEXT NOT NULL,                                -- encrypted_secrets.key for URL
    event_filter    JSONB DEFAULT '[]'::jsonb,                   -- 通知する event 種別
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_slack_ws_channel UNIQUE (workspace_id, channel_id)
);
CREATE INDEX IF NOT EXISTS ix_slack_webhooks_ws ON slack_webhooks(workspace_id) WHERE is_active = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 9. github_repos — workspace ↔ GitHub repo 紐付け
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS github_repos (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    owner           TEXT NOT NULL,                                -- engine-base
    repo            TEXT NOT NULL,                                -- Build-Factory
    default_branch  TEXT DEFAULT 'main',
    install_id      BIGINT,                                       -- GitHub App installation ID
    is_primary      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_github_ws_repo UNIQUE (workspace_id, owner, repo)
);
CREATE INDEX IF NOT EXISTS ix_github_repos_ws ON github_repos(workspace_id) WHERE is_primary = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 10. obsidian_vaults — workspace ↔ Obsidian vault (M-28 long-term memory)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS obsidian_vaults (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         TEXT,
    vault_path      TEXT NOT NULL,                                -- ~/Documents/会社運営DB/obsidian/
    sync_mode       TEXT NOT NULL DEFAULT 'opt_in'
                       CHECK (sync_mode IN ('opt_in','disabled','bidirectional')),
    last_synced_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_obsidian_vaults_ws   ON obsidian_vaults(workspace_id);
CREATE INDEX IF NOT EXISTS ix_obsidian_vaults_user ON obsidian_vaults(user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 11. notifications — in-app 通知 inbox
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    recipient_user_id TEXT NOT NULL,
    event_type      TEXT NOT NULL,                                -- "pr.merged" / "task.assigned" 等
    title           TEXT NOT NULL,
    body            TEXT,
    link_url        TEXT,
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    priority        TEXT NOT NULL DEFAULT 'normal'
                       CHECK (priority IN ('low','normal','high','urgent')),
    detail          JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    read_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_notifications_recipient ON notifications(recipient_user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_notifications_ws        ON notifications(workspace_id, created_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- 12. token_limits — workspace 別 LLM token 上限
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS token_limits (
    id                BIGSERIAL PRIMARY KEY,
    workspace_id      BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider_key      TEXT NOT NULL DEFAULT 'anthropic',
    daily_token_limit  BIGINT,
    monthly_token_limit BIGINT,
    daily_cost_usd_limit NUMERIC(10,2),
    monthly_cost_usd_limit NUMERIC(10,2),
    soft_threshold_ratio REAL DEFAULT 0.8 CHECK (soft_threshold_ratio BETWEEN 0 AND 1),
    is_enforced       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_token_limit_ws_provider UNIQUE (workspace_id, provider_key)
);
CREATE INDEX IF NOT EXISTS ix_token_limits_ws ON token_limits(workspace_id) WHERE is_enforced = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 13. backups — DB backup metadata
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS backups (
    id              BIGSERIAL PRIMARY KEY,
    backup_kind     TEXT NOT NULL CHECK (backup_kind IN ('db','storage','obsidian','full')),
    storage_url     TEXT NOT NULL,
    size_bytes      BIGINT DEFAULT 0,
    sha256          TEXT,
    triggered_by    TEXT NOT NULL DEFAULT 'cron'
                       CHECK (triggered_by IN ('cron','manual','pre_release')),
    status          TEXT NOT NULL DEFAULT 'completed'
                       CHECK (status IN ('completed','failed','in_progress')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    retention_days  INTEGER DEFAULT 90 CHECK (retention_days > 0),
    detail          JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_backups_kind ON backups(backup_kind, started_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- 14. user_settings — user 個別設定 (UI / theme / locale 等)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL UNIQUE,
    theme           TEXT NOT NULL DEFAULT 'system'
                       CHECK (theme IN ('light','dark','system')),
    locale          TEXT NOT NULL DEFAULT 'ja',
    notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notifications_filter JSONB DEFAULT '[]'::jsonb,
    keyboard_shortcuts JSONB DEFAULT '{}'::jsonb,
    pinned_workspaces BIGINT[] DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 15. workspace_settings — workspace 別 feature flags / overrides
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS workspace_settings (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT NOT NULL UNIQUE REFERENCES workspaces(id) ON DELETE CASCADE,
    feature_flags   JSONB NOT NULL DEFAULT '{}'::jsonb,
    redline_overrides JSONB DEFAULT '{}'::jsonb,
    phase_gate_mode TEXT NOT NULL DEFAULT 'strict'
                       CHECK (phase_gate_mode IN ('strict','warn','off')),
    auto_pr_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    auto_merge_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 16. schema_versions — migration 版数履歴
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_versions (
    id              BIGSERIAL PRIMARY KEY,
    version         TEXT NOT NULL UNIQUE,                          -- "20260512000000"
    description     TEXT NOT NULL,
    applied_at      TIMESTAMPTZ DEFAULT NOW(),
    applied_by      TEXT,
    is_rollback     BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260512000000', 'T-001-05: implementation/integration/ops 17 tables + Template', 'system')
ON CONFLICT (version) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- 17. templates — タスク / PR / mock テンプレート
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS templates (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    template_kind   TEXT NOT NULL CHECK (template_kind IN ('task','pr','mock','prompt','constitution')),
    name            TEXT NOT NULL,
    description     TEXT,
    body            TEXT NOT NULL,                                 -- markdown / jinja / json
    body_format     TEXT NOT NULL DEFAULT 'markdown'
                       CHECK (body_format IN ('markdown','jinja','json','plain')),
    is_global       BOOLEAN NOT NULL DEFAULT FALSE,                -- workspace_id NULL でも参照可
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_template_ws_kind_name UNIQUE (workspace_id, template_kind, name)
);
CREATE INDEX IF NOT EXISTS ix_templates_ws    ON templates(workspace_id, template_kind) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS ix_templates_global ON templates(template_kind) WHERE is_global = TRUE;


-- =============================================================================
-- RLS (AC-3 STATE): 全テーブル ENABLE + workspace_members 経由 + service_role 全権
-- =============================================================================

-- session_artifacts (session の RLS と同じ pattern)
ALTER TABLE session_artifacts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS session_artifacts_service_role ON session_artifacts;
CREATE POLICY session_artifacts_service_role ON session_artifacts FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS session_artifacts_member ON session_artifacts;
CREATE POLICY session_artifacts_member ON session_artifacts FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- prs
ALTER TABLE prs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS prs_service_role ON prs;
CREATE POLICY prs_service_role ON prs FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS prs_member ON prs;
CREATE POLICY prs_member ON prs FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- pr_reviews
ALTER TABLE pr_reviews ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pr_reviews_service_role ON pr_reviews;
CREATE POLICY pr_reviews_service_role ON pr_reviews FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS pr_reviews_member ON pr_reviews;
CREATE POLICY pr_reviews_member ON pr_reviews FOR ALL TO authenticated
    USING (pr_id IN (SELECT id FROM prs WHERE bf_can_access_workspace(workspace_id)))
    WITH CHECK (pr_id IN (SELECT id FROM prs WHERE bf_can_access_workspace(workspace_id)));

-- red_lines
ALTER TABLE red_lines ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS red_lines_service_role ON red_lines;
CREATE POLICY red_lines_service_role ON red_lines FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS red_lines_member ON red_lines;
CREATE POLICY red_lines_member ON red_lines FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- red_line_violations
ALTER TABLE red_line_violations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS red_line_violations_service_role ON red_line_violations;
CREATE POLICY red_line_violations_service_role ON red_line_violations FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS red_line_violations_member ON red_line_violations;
CREATE POLICY red_line_violations_member ON red_line_violations FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- llm_providers: グローバル参照可、 admin のみ書込 (service_role)
ALTER TABLE llm_providers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS llm_providers_service_role ON llm_providers;
CREATE POLICY llm_providers_service_role ON llm_providers FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS llm_providers_read ON llm_providers;
CREATE POLICY llm_providers_read ON llm_providers FOR SELECT TO authenticated
    USING (is_enabled = TRUE);

-- api_keys: 本人 + service_role
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS api_keys_service_role ON api_keys;
CREATE POLICY api_keys_service_role ON api_keys FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS api_keys_owner ON api_keys;
CREATE POLICY api_keys_owner ON api_keys FOR ALL TO authenticated
    USING (
        (owner_user_id IS NOT NULL AND owner_user_id = auth.uid()::text)
        OR (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id))
    )
    WITH CHECK (
        (owner_user_id IS NOT NULL AND owner_user_id = auth.uid()::text)
        OR (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id))
    );

-- slack_webhooks
ALTER TABLE slack_webhooks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS slack_webhooks_service_role ON slack_webhooks;
CREATE POLICY slack_webhooks_service_role ON slack_webhooks FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS slack_webhooks_member ON slack_webhooks;
CREATE POLICY slack_webhooks_member ON slack_webhooks FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- github_repos
ALTER TABLE github_repos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS github_repos_service_role ON github_repos;
CREATE POLICY github_repos_service_role ON github_repos FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS github_repos_member ON github_repos;
CREATE POLICY github_repos_member ON github_repos FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- obsidian_vaults: 本人 or workspace_member
ALTER TABLE obsidian_vaults ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS obsidian_vaults_service_role ON obsidian_vaults;
CREATE POLICY obsidian_vaults_service_role ON obsidian_vaults FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS obsidian_vaults_owner ON obsidian_vaults;
CREATE POLICY obsidian_vaults_owner ON obsidian_vaults FOR ALL TO authenticated
    USING (
        (user_id IS NOT NULL AND user_id = auth.uid()::text)
        OR (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id))
    )
    WITH CHECK (
        (user_id IS NOT NULL AND user_id = auth.uid()::text)
        OR (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id))
    );

-- notifications: 受信者本人
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notifications_service_role ON notifications;
CREATE POLICY notifications_service_role ON notifications FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS notifications_recipient ON notifications;
CREATE POLICY notifications_recipient ON notifications FOR ALL TO authenticated
    USING (recipient_user_id = auth.uid()::text)
    WITH CHECK (recipient_user_id = auth.uid()::text);

-- token_limits
ALTER TABLE token_limits ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS token_limits_service_role ON token_limits;
CREATE POLICY token_limits_service_role ON token_limits FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS token_limits_member ON token_limits;
CREATE POLICY token_limits_member ON token_limits FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- backups: service_role のみ書込, authenticated は閲覧不可 (admin endpoint 経由)
ALTER TABLE backups ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS backups_service_role ON backups;
CREATE POLICY backups_service_role ON backups FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- user_settings: 本人のみ
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_settings_service_role ON user_settings;
CREATE POLICY user_settings_service_role ON user_settings FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS user_settings_owner ON user_settings;
CREATE POLICY user_settings_owner ON user_settings FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

-- workspace_settings
ALTER TABLE workspace_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_settings_service_role ON workspace_settings;
CREATE POLICY workspace_settings_service_role ON workspace_settings FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS workspace_settings_member ON workspace_settings;
CREATE POLICY workspace_settings_member ON workspace_settings FOR ALL TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

-- schema_versions: service_role のみ
ALTER TABLE schema_versions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS schema_versions_service_role ON schema_versions;
CREATE POLICY schema_versions_service_role ON schema_versions FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- templates: workspace 内 or global
ALTER TABLE templates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS templates_service_role ON templates;
CREATE POLICY templates_service_role ON templates FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS templates_read ON templates;
CREATE POLICY templates_read ON templates FOR SELECT TO authenticated
    USING (is_global = TRUE OR (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id)));
DROP POLICY IF EXISTS templates_write ON templates;
CREATE POLICY templates_write ON templates FOR ALL TO authenticated
    USING (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id));


-- =============================================================================
-- audit_logs 連携 trigger (T-001-05 AC-3): 主要テーブルへの INSERT/UPDATE/DELETE
-- を audit_logs に自動記録. NOTE: app 層から bf_emit_audit_log を呼ぶ pattern
-- も併存 (重複防止のため trigger は重要 4 テーブルのみ).
-- =============================================================================

-- (trigger function は既存 20260510000001_bf_project_tables.sql で定義済みの想定)
-- ここでは ENABLE 状態を documentation comment のみで明示し、 実装は app 層に委譲.
COMMENT ON TABLE prs                  IS 'audit: app emits audit_logs(action=pr.*)';
COMMENT ON TABLE pr_reviews           IS 'audit: app emits audit_logs(action=pr_review.*)';
COMMENT ON TABLE red_line_violations  IS 'audit: app emits audit_logs(action=redline.violation)';
COMMENT ON TABLE api_keys             IS 'audit: app emits audit_logs(action=api_key.*) — never log secret_key value';
