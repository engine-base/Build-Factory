-- =============================================================================
-- Build-Factory: Initial Schema (Supabase Postgres 17)
-- =============================================================================
-- 既存 SQLite スキーマからの統合移行。等価な Postgres スキーマを構築する。
--
-- 対応する alembic revision (依存順):
--   d83319c25a4f  add_ai_employee_tables           (task_schedule, approval_queue,
--                                                   execution_log, communication_log,
--                                                   ai_employee_config)
--   fa5e1c5eaac0  extend_knowledge_base_and_seed   (knowledge_base 拡張)
--   c1a2b3d4e5f6  add_browser_task_queue           (browser_task_queue)
--   e9f0a1b2c3d4  user_profile                     (user_profile)
--   f1a2b3c4d5e6  conversation_slots               (conversation_slots)
--   a7b8c9d0e1f2  artifacts                        (artifacts, artifact_events)
--   b1c2d3e4f5a6  workspaces                       (accounts, account_members,
--                                                   workspaces, workspace_members,
--                                                   workspace_invitations)
--   c1d2e3f4g5h6  dev_tables                       (repos, pull_requests, reviews)
--   d7e8f9a0b1c2  staff_hierarchy_personas         (ai_employee_config 拡張,
--                                                   knowledge_transfer_log)
--
-- これに加えて、alembic 外で SQL 直 CREATE されていた company-dashboard 由来
-- のレガシーテーブル (invoices/pipeline/projects/tasks/conversation_log/threads
-- /knowledge_base 等) も含む。
--
-- 変換ルール:
--   sa.Integer() autoincrement PK → BIGSERIAL PRIMARY KEY
--   sa.Text() で日付保存 (created_at 等) → TIMESTAMPTZ DEFAULT NOW()
--   sa.Text() で JSON 保存 → JSONB
--   sa.Text() 通常 → TEXT
--   sa.Boolean() / INTEGER 0/1 フラグ → BOOLEAN
--   sa.func.current_timestamp() → DEFAULT NOW()
--   server_default '[]' / '{}' → DEFAULT '[]'::jsonb / '{}'::jsonb
--   暗黙 FK は明示化 (REFERENCES ... ON DELETE)
--
-- 破壊的処理は含まない (CREATE TABLE IF NOT EXISTS のみ)。
-- =============================================================================

-- =============================================================================
-- 1. レガシー company-dashboard テーブル (alembic 管理外、SQL 直作成)
-- =============================================================================

CREATE TABLE IF NOT EXISTS invoices (
    id           BIGSERIAL PRIMARY KEY,
    invoice_no   TEXT UNIQUE NOT NULL,
    client       TEXT NOT NULL,
    project      TEXT,
    subtotal     INTEGER NOT NULL,
    tax          INTEGER NOT NULL,
    total        INTEGER NOT NULL,
    issued_date  DATE NOT NULL,
    due_date     DATE NOT NULL,
    status       TEXT DEFAULT 'unpaid' CHECK (status IN ('unpaid','paid','overdue','cancelled')),
    paid_date    DATE,
    md_path      TEXT,
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline (
    id                BIGSERIAL PRIMARY KEY,
    client            TEXT NOT NULL,
    project           TEXT NOT NULL,
    stage             TEXT NOT NULL CHECK (stage IN ('lead','contact','proposal','negotiation','won','lost')),
    amount            INTEGER,
    probability       INTEGER,
    last_contact      DATE,
    next_action       TEXT,
    next_action_date  DATE,
    source            TEXT,
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id              BIGSERIAL PRIMARY KEY,
    week_label      TEXT UNIQUE NOT NULL,
    review_date     DATE NOT NULL,
    sales_actual    INTEGER,
    sales_target    INTEGER,
    leads_count     INTEGER,
    meetings_count  INTEGER,
    won_count       INTEGER,
    won_amount      INTEGER,
    web_sessions    INTEGER,
    top3_next       TEXT,
    okr_progress    REAL,
    md_path         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monthly_reviews (
    id              BIGSERIAL PRIMARY KEY,
    month_label     TEXT UNIQUE NOT NULL,
    review_date     DATE NOT NULL,
    sales_actual    INTEGER,
    sales_target    INTEGER,
    expenses_total  INTEGER,
    profit          INTEGER,
    new_clients     INTEGER,
    active_projects INTEGER,
    top3_month      TEXT,
    okr_q_progress  REAL,
    md_path         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okr (
    id          BIGSERIAL PRIMARY KEY,
    year        INTEGER NOT NULL,
    quarter     INTEGER,
    level       TEXT CHECK (level IN ('annual','quarterly')),
    objective   TEXT NOT NULL,
    kr1         TEXT,
    kr1_target  REAL,
    kr1_current REAL,
    kr2         TEXT,
    kr2_target  REAL,
    kr2_current REAL,
    kr3         TEXT,
    kr3_target  REAL,
    kr3_current REAL,
    status      TEXT DEFAULT 'active',
    md_path     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outreach_log (
    id                BIGSERIAL PRIMARY KEY,
    contact_date      DATE NOT NULL,
    company           TEXT,
    contact_name      TEXT,
    channel           TEXT CHECK (channel IN ('email','x-dm','linkedin','line','phone','other')),
    type              TEXT CHECK (type IN ('cold','followup1','followup2','followup3','reply')),
    status            TEXT CHECK (status IN ('sent','opened','replied','meeting','no-reply','rejected')),
    notes             TEXT,
    next_action       TEXT,
    next_action_date  DATE,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_log (
    id              BIGSERIAL PRIMARY KEY,
    task_date       DATE NOT NULL,
    task1           TEXT,
    task1_done      BOOLEAN DEFAULT FALSE,
    task2           TEXT,
    task2_done      BOOLEAN DEFAULT FALSE,
    task3           TEXT,
    task3_done      BOOLEAN DEFAULT FALSE,
    completion_rate REAL,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contacts (
    id           BIGSERIAL PRIMARY KEY,
    company      TEXT,
    name         TEXT NOT NULL,
    role         TEXT,
    email        TEXT,
    phone        TEXT,
    channel      TEXT,
    type         TEXT CHECK (type IN ('client','prospect','partner','expert','other')),
    last_contact DATE,
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contracts (
    id            BIGSERIAL PRIMARY KEY,
    contract_no   TEXT UNIQUE NOT NULL,
    type          TEXT CHECK (type IN ('business','nda','terms','other')),
    counterparty  TEXT NOT NULL,
    project       TEXT,
    status        TEXT DEFAULT 'draft' CHECK (status IN ('draft','reviewing','signed','expired','cancelled')),
    signed_date   DATE,
    expiry_date   DATE,
    auto_renew    BOOLEAN DEFAULT FALSE,
    key_terms     TEXT,
    risk_level    TEXT CHECK (risk_level IN ('low','medium','high')),
    md_path       TEXT,
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outsource_jobs (
    id            BIGSERIAL PRIMARY KEY,
    job_no        TEXT UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    vendor        TEXT,
    category      TEXT,
    budget        INTEGER,
    deadline      DATE,
    status        TEXT DEFAULT 'draft' CHECK (status IN ('draft','posted','in_progress','reviewing','done','cancelled')),
    quality_check BOOLEAN DEFAULT FALSE,
    md_path       TEXT,
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS brand_assets (
    id         BIGSERIAL PRIMARY KEY,
    type       TEXT CHECK (type IN ('brand-voice','company-profile','press-release','other')),
    version    TEXT,
    title      TEXT,
    md_path    TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS seo_reports (
    id               BIGSERIAL PRIMARY KEY,
    report_date      DATE NOT NULL,
    report_type      TEXT CHECK (report_type IN ('weekly','monthly')),
    top_keywords     TEXT,
    organic_sessions INTEGER,
    clicks           INTEGER,
    impressions      INTEGER,
    avg_position     REAL,
    issues_found     INTEGER,
    actions_taken    TEXT,
    md_path          TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kpi_records (
    id               BIGSERIAL PRIMARY KEY,
    record_date      DATE NOT NULL,
    period           TEXT,
    metric_name      TEXT NOT NULL,
    metric_value     REAL,
    target_value     REAL,
    achievement_rate REAL,
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS network (
    id                  BIGSERIAL PRIMARY KEY,
    name                TEXT NOT NULL,
    company             TEXT,
    role                TEXT,
    category            TEXT CHECK (category IN ('expert','partner','referral','peer','mentor','other')),
    specialty           TEXT,
    email               TEXT,
    phone               TEXT,
    last_contact        DATE,
    contact_frequency   TEXT,
    referrals_received  INTEGER DEFAULT 0,
    referrals_given     INTEGER DEFAULT 0,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id                BIGSERIAL PRIMARY KEY,
    expense_date      DATE NOT NULL,
    category          TEXT,
    description       TEXT,
    amount            INTEGER NOT NULL,
    tax_deductible    BOOLEAN DEFAULT TRUE,
    account_category  TEXT,
    receipt_path      TEXT,
    notes             TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sns_posts (
    id              BIGSERIAL PRIMARY KEY,
    post_date       DATE,
    platform        TEXT CHECK (platform IN ('x','instagram','linkedin','facebook','other')),
    content_summary TEXT,
    likes           INTEGER DEFAULT 0,
    reposts         INTEGER DEFAULT 0,
    replies         INTEGER DEFAULT 0,
    impressions     INTEGER DEFAULT 0,
    theme           TEXT,
    md_path         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pl_records (
    id                  BIGSERIAL PRIMARY KEY,
    month               TEXT UNIQUE NOT NULL,
    revenue             INTEGER DEFAULT 0,
    cogs                INTEGER DEFAULT 0,
    gross_profit        INTEGER DEFAULT 0,
    operating_expenses  INTEGER DEFAULT 0,
    operating_profit    INTEGER DEFAULT 0,
    notes               TEXT,
    md_path             TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cf_forecasts (
    id                BIGSERIAL PRIMARY KEY,
    forecast_month    TEXT NOT NULL,
    inflows_fixed     INTEGER DEFAULT 0,
    inflows_variable  INTEGER DEFAULT 0,
    outflows_fixed    INTEGER DEFAULT 0,
    outflows_variable INTEGER DEFAULT 0,
    net_cf            INTEGER DEFAULT 0,
    balance_end       INTEGER DEFAULT 0,
    alert_level       TEXT CHECK (alert_level IN ('safe','warning','danger')),
    md_path           TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cs_feedback (
    id              BIGSERIAL PRIMARY KEY,
    client          TEXT NOT NULL,
    survey_date     DATE NOT NULL,
    nps_score       INTEGER,
    satisfaction    INTEGER,
    feedback_text   TEXT,
    action_taken    TEXT,
    md_path         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tools_inventory (
    id              BIGSERIAL PRIMARY KEY,
    tool_name       TEXT NOT NULL,
    category        TEXT,
    monthly_cost    INTEGER DEFAULT 0,
    billing_cycle   TEXT CHECK (billing_cycle IN ('monthly','annual','one-time')),
    renewal_date    DATE,
    usage_frequency TEXT CHECK (usage_frequency IN ('daily','weekly','monthly','rarely','unused')),
    essential       BOOLEAN DEFAULT TRUE,
    alternative     TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_items (
    id            BIGSERIAL PRIMARY KEY,
    project_name  TEXT NOT NULL,
    client_type   TEXT,
    industry      TEXT,
    deliverables  TEXT,
    outcomes      TEXT,
    technologies  TEXT,
    period        TEXT,
    public_ok     BOOLEAN DEFAULT FALSE,
    md_path       TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 2. AI 社員システム (alembic d83319c25a4f / fa5e1c5eaac0 / d7e8f9a0b1c2)
-- =============================================================================

CREATE TABLE IF NOT EXISTS ai_employee_config (
    id                 BIGSERIAL PRIMARY KEY,
    employee_name      TEXT NOT NULL UNIQUE,
    display_name       TEXT,
    category           TEXT,
    primary_skill      TEXT,
    knowledge_tags     JSONB,
    autonomy_settings  JSONB,
    llm_provider       TEXT DEFAULT 'ollama',
    llm_model          TEXT DEFAULT 'qwen2.5:7b',
    is_active          BOOLEAN DEFAULT TRUE,
    -- staff_hierarchy_personas 拡張
    parent_id          BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    role_level         TEXT DEFAULT 'leader',  -- 'secretary' / 'leader' / 'member'
    persona_name       TEXT,
    personality        TEXT,
    tone_style         TEXT,
    catchphrase        TEXT,
    avatar_emoji       TEXT,
    specialty          TEXT,
    handles            TEXT,
    knowledge_folders  JSONB,
    retired_at         TIMESTAMPTZ,
    retire_reason      TEXT,
    inherited_to       BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    -- workspaces 拡張
    account_id         BIGINT,  -- FK は accounts 作成後に追加 (循環回避)
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ai_employee_parent     ON ai_employee_config(parent_id);
CREATE INDEX IF NOT EXISTS ix_ai_employee_role_level ON ai_employee_config(role_level);
CREATE INDEX IF NOT EXISTS ix_ai_employee_retired_at ON ai_employee_config(retired_at);

CREATE TABLE IF NOT EXISTS skill_definitions (
    id           BIGSERIAL PRIMARY KEY,
    skill_name   TEXT NOT NULL UNIQUE,
    display_name TEXT,
    description  TEXT,
    category     TEXT,
    tags         JSONB,
    md_path      TEXT NOT NULL,
    is_active    BOOLEAN DEFAULT TRUE,
    version      TEXT DEFAULT '1.0',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_skill_def_category ON skill_definitions(category);

CREATE TABLE IF NOT EXISTS ai_employee_skills (
    id          BIGSERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES ai_employee_config(id) ON DELETE CASCADE,
    skill_id    BIGINT NOT NULL REFERENCES skill_definitions(id) ON DELETE CASCADE,
    is_primary  BOOLEAN DEFAULT FALSE,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (employee_id, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_ae_skills_emp ON ai_employee_skills(employee_id);

CREATE TABLE IF NOT EXISTS task_schedule (
    id           BIGSERIAL PRIMARY KEY,
    task_name    TEXT NOT NULL,
    skill_name   TEXT NOT NULL,
    description  TEXT,
    frequency    TEXT NOT NULL,
    day_of_week  TEXT,
    day_of_month INTEGER,
    run_time     TEXT NOT NULL,
    timezone     TEXT DEFAULT 'Asia/Tokyo',
    is_active    BOOLEAN DEFAULT TRUE,
    autonomy     TEXT DEFAULT 'confirm',
    params       JSONB,
    last_run_at  TIMESTAMPTZ,
    next_run_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_task_schedule_active ON task_schedule(is_active, next_run_at);

CREATE TABLE IF NOT EXISTS execution_log (
    id              BIGSERIAL PRIMARY KEY,
    skill_name      TEXT NOT NULL,
    triggered_by    TEXT NOT NULL,
    trigger_id      BIGINT,
    status          TEXT NOT NULL,
    input_context   JSONB,
    result_summary  TEXT,
    result_path     TEXT,
    approval_id     BIGINT,
    error_message   TEXT,
    duration_sec    REAL,
    llm_provider    TEXT,
    llm_model       TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_execution_log_skill  ON execution_log(skill_name, started_at);
CREATE INDEX IF NOT EXISTS idx_execution_log_status ON execution_log(status, started_at);

CREATE TABLE IF NOT EXISTS approval_queue (
    id                  BIGSERIAL PRIMARY KEY,
    action_type         TEXT NOT NULL,
    title               TEXT NOT NULL,
    content             TEXT NOT NULL,
    metadata            JSONB,
    status              TEXT DEFAULT 'pending',
    channel_notified    TEXT,
    slack_ts            TEXT,
    source_skill        TEXT,
    source_execution_id BIGINT REFERENCES execution_log(id) ON DELETE SET NULL,
    revision_memo       TEXT,
    expires_at          TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    workspace_id        BIGINT,  -- FK は workspaces 作成後に追加
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_approval_queue_status ON approval_queue(status, expires_at);

CREATE TABLE IF NOT EXISTS communication_log (
    id             BIGSERIAL PRIMARY KEY,
    channel        TEXT NOT NULL,
    channel_id     TEXT,
    direction      TEXT NOT NULL,
    sender_name    TEXT,
    sender_id      TEXT,
    subject        TEXT,
    body           TEXT,
    body_summary   TEXT,
    importance     TEXT DEFAULT 'low',
    status         TEXT DEFAULT 'unread',
    reply_draft_id BIGINT,
    external_id    TEXT,
    received_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_comm_log_channel ON communication_log(channel, importance, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_comm_log_external ON communication_log(channel, external_id);

-- =============================================================================
-- 3. ナレッジベース (legacy + alembic 拡張)
-- =============================================================================

CREATE TABLE IF NOT EXISTS knowledge_base (
    id                   BIGSERIAL PRIMARY KEY,
    title                TEXT NOT NULL,
    category             TEXT,
    tags                 JSONB,
    summary              TEXT,
    md_path              TEXT,
    last_updated         DATE DEFAULT CURRENT_DATE,
    -- fa5e1c5eaac0 拡張
    knowledge_type       TEXT DEFAULT 'pattern',
    confirmed_by_user    BOOLEAN DEFAULT FALSE,
    use_count            INTEGER DEFAULT 0,
    source_execution_id  BIGINT REFERENCES execution_log(id) ON DELETE SET NULL,
    -- legacy 拡張カラム (SQLite で ALTER TABLE 追加されていた)
    content              TEXT,
    source               TEXT DEFAULT 'manual',
    skill_tags           JSONB,
    confidence           REAL DEFAULT 1.0,
    -- d7e8f9a0b1c2 拡張
    assigned_employee_id BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    -- b1c2d3e4f5a6 拡張
    account_id           BIGINT,  -- FK は accounts 作成後
    workspace_id         BIGINT,  -- FK は workspaces 作成後
    -- 注: embedding は pgvector migration (20260501220100) で追加
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kb_skill_tags          ON knowledge_base(skill_tags);
CREATE INDEX IF NOT EXISTS idx_kb_source              ON knowledge_base(source);
CREATE INDEX IF NOT EXISTS idx_kb_category            ON knowledge_base(category);
CREATE INDEX IF NOT EXISTS ix_knowledge_assigned_emp  ON knowledge_base(assigned_employee_id);

CREATE TABLE IF NOT EXISTS knowledge_transfer_log (
    id              BIGSERIAL PRIMARY KEY,
    knowledge_id    BIGINT NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
    from_employee   BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    to_employee     BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    reason          TEXT,
    triggered_by    TEXT DEFAULT 'staff_management',
    transferred_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_kt_knowledge ON knowledge_transfer_log(knowledge_id);
CREATE INDEX IF NOT EXISTS ix_kt_to        ON knowledge_transfer_log(to_employee);

-- =============================================================================
-- 4. プロジェクト / タスク / ワークフロー (legacy)
-- =============================================================================

CREATE TABLE IF NOT EXISTS projects (
    id            BIGSERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    status        TEXT DEFAULT 'active',
    initiated_by  TEXT DEFAULT 'user',
    goal          TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_proj_status ON projects(status, created_at DESC);

CREATE TABLE IF NOT EXISTS tasks (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT REFERENCES projects(id) ON DELETE CASCADE,
    parent_task_id  BIGINT REFERENCES tasks(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    assigned_to     BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    skill_name      TEXT,
    status          TEXT DEFAULT 'pending',
    result          TEXT,
    depends_on      JSONB,
    level           INTEGER DEFAULT 0,
    order_index     INTEGER DEFAULT 0,
    retry_count     INTEGER DEFAULT 0,
    last_error      TEXT,
    next_retry_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tasks_proj     ON tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent   ON tasks(parent_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assigned_to, status);

CREATE TABLE IF NOT EXISTS task_questions (
    id           BIGSERIAL PRIMARY KEY,
    task_id      BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    asked_by     BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    ask_to       TEXT NOT NULL,
    question     TEXT NOT NULL,
    answer       TEXT,
    status       TEXT DEFAULT 'pending',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    answered_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_questions_status ON task_questions(status, created_at);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id              BIGSERIAL PRIMARY KEY,
    user_request    TEXT NOT NULL,
    plan_json       JSONB,
    status          TEXT DEFAULT 'planning',
    steps_completed INTEGER DEFAULT 0,
    steps_total     INTEGER DEFAULT 0,
    final_output    TEXT,
    approval_id     BIGINT REFERENCES approval_queue(id) ON DELETE SET NULL,
    triggered_by    TEXT DEFAULT 'user',
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_wfr_status ON workflow_runs(status, started_at DESC);

CREATE TABLE IF NOT EXISTS workflow_steps (
    id              BIGSERIAL PRIMARY KEY,
    workflow_run_id BIGINT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    step_number     INTEGER NOT NULL,
    skill_name      TEXT NOT NULL,
    input           JSONB,
    output          JSONB,
    status          TEXT DEFAULT 'pending',
    parallel_group  TEXT,
    depends_on      JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_sec    REAL
);
CREATE INDEX IF NOT EXISTS idx_wfs_run ON workflow_steps(workflow_run_id, step_number);

-- =============================================================================
-- 5. チャット / 会話ログ (legacy + alembic)
-- =============================================================================

CREATE TABLE IF NOT EXISTS threads (
    id             BIGSERIAL PRIMARY KEY,
    title          TEXT NOT NULL DEFAULT '新しいチャット',
    channel        TEXT NOT NULL,
    with_employee  BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    archived       BOOLEAN DEFAULT FALSE,
    workspace_id   BIGINT,  -- FK は workspaces 作成後
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_threads_emp     ON threads(with_employee, last_active_at DESC);
CREATE INDEX IF NOT EXISTS idx_threads_channel ON threads(channel, last_active_at DESC);

CREATE TABLE IF NOT EXISTS conversation_log (
    id             BIGSERIAL PRIMARY KEY,
    channel        TEXT DEFAULT 'web',
    with_employee  BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    role           TEXT,
    message        TEXT NOT NULL,
    task_id        BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
    thread_id      BIGINT REFERENCES threads(id) ON DELETE CASCADE,
    workspace_id   BIGINT,  -- FK は workspaces 作成後
    -- 注: embedding は pgvector migration で追加
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conv_emp_time    ON conversation_log(with_employee, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_thread      ON conversation_log(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conv_log_thread  ON conversation_log(thread_id, created_at DESC);

CREATE TABLE IF NOT EXISTS conversation_slots (
    id              BIGSERIAL PRIMARY KEY,
    thread_id       BIGINT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    goal            TEXT,
    slot_name       TEXT NOT NULL,
    confirmed_value TEXT,
    rejected        JSONB DEFAULT '[]'::jsonb,
    hints           JSONB DEFAULT '[]'::jsonb,
    history         JSONB DEFAULT '[]'::jsonb,
    position        INTEGER DEFAULT 0,
    is_resolved     BOOLEAN DEFAULT FALSE,
    workspace_id    BIGINT,  -- FK は workspaces 作成後
    last_updated    TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_slots_thread_name UNIQUE (thread_id, slot_name)
);
CREATE INDEX IF NOT EXISTS ix_slots_thread ON conversation_slots(thread_id);

CREATE TABLE IF NOT EXISTS slack_processed_messages (
    channel      TEXT NOT NULL,
    ts           TEXT NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (channel, ts)
);
CREATE INDEX IF NOT EXISTS idx_slack_processed_ts ON slack_processed_messages(channel, ts DESC);

-- =============================================================================
-- 6. user_profile (alembic e9f0a1b2c3d4)
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_profile (
    user_key      TEXT PRIMARY KEY,  -- "masato" 固定（将来の拡張用）
    display_name  TEXT,
    aliases       JSONB,
    preferences   JSONB,
    recent_topics JSONB,
    notes         TEXT,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 初期 seed (まさと)
INSERT INTO user_profile (user_key, display_name, aliases, preferences, recent_topics, notes)
VALUES (
    'masato',
    '高本 まさと',
    '["まさと","聖斗","Masato"]'::jsonb,
    '{"language":"ja","tone":"casual"}'::jsonb,
    '[]'::jsonb,
    'ENGINE BASE 代表。AI社員システムのオーナー。'
) ON CONFLICT (user_key) DO NOTHING;

-- =============================================================================
-- 7. browser_task_queue (alembic c1a2b3d4e5f6)
-- =============================================================================

CREATE TABLE IF NOT EXISTS browser_task_queue (
    id                   BIGSERIAL PRIMARY KEY,
    task                 TEXT NOT NULL,
    service              TEXT,
    status               TEXT DEFAULT 'pending',
    priority             INTEGER DEFAULT 3,
    max_steps            INTEGER DEFAULT 20,
    provider             TEXT DEFAULT 'openai',
    model                TEXT DEFAULT 'gpt-4o-mini',
    requested_by         TEXT,
    requested_via_thread BIGINT REFERENCES threads(id) ON DELETE SET NULL,
    result               TEXT,
    error                TEXT,
    screenshot_path      TEXT,
    steps_summary        JSONB,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    started_at           TIMESTAMPTZ,
    finished_at          TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_browser_task_queue_status ON browser_task_queue(status);

-- =============================================================================
-- 8. artifacts (alembic a7b8c9d0e1f2)
-- =============================================================================

CREATE TABLE IF NOT EXISTS artifacts (
    id            TEXT PRIMARY KEY,  -- uuid
    type          TEXT NOT NULL,      -- list/kanban/...
    title         TEXT NOT NULL DEFAULT '',
    data          JSONB DEFAULT '{}'::jsonb,
    category_tags JSONB DEFAULT '[]'::jsonb,
    pinned_by     JSONB DEFAULT '[]'::jsonb,
    thread_id     BIGINT REFERENCES threads(id) ON DELETE SET NULL,
    employee_id   BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    created_by    TEXT DEFAULT 'ai',
    is_archived   BOOLEAN DEFAULT FALSE,
    workspace_id  BIGINT,  -- FK は workspaces 作成後
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_artifacts_thread   ON artifacts(thread_id);
CREATE INDEX IF NOT EXISTS ix_artifacts_type     ON artifacts(type);
CREATE INDEX IF NOT EXISTS ix_artifacts_archived ON artifacts(is_archived);

CREATE TABLE IF NOT EXISTS artifact_events (
    id          BIGSERIAL PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    diff        JSONB DEFAULT '{}'::jsonb,
    note        TEXT DEFAULT '',
    ts          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_events_artifact ON artifact_events(artifact_id);
CREATE INDEX IF NOT EXISTS ix_events_ts       ON artifact_events(ts);

-- =============================================================================
-- 9. アカウント / ワークスペース階層 (alembic b1c2d3e4f5a6)
-- =============================================================================

CREATE TABLE IF NOT EXISTS accounts (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    type          TEXT DEFAULT 'individual',  -- company / individual
    plan          TEXT DEFAULT 'free',         -- free / pro / business / enterprise
    owner_user_id TEXT NOT NULL,
    billing_email TEXT,
    metadata      JSONB DEFAULT '{}'::jsonb,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_accounts_owner ON accounts(owner_user_id);

CREATE TABLE IF NOT EXISTS account_members (
    id          BIGSERIAL PRIMARY KEY,
    account_id  BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    role        TEXT DEFAULT 'owner',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_account_member UNIQUE (account_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_account_members_account ON account_members(account_id);

CREATE TABLE IF NOT EXISTS workspaces (
    id                BIGSERIAL PRIMARY KEY,
    account_id        BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    description       TEXT,
    status            TEXT DEFAULT 'active',
    project_meta      JSONB DEFAULT '{}'::jsonb,
    client_visibility JSONB DEFAULT '[]'::jsonb,
    design_system_ref TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_workspaces_account ON workspaces(account_id);
CREATE INDEX IF NOT EXISTS ix_workspaces_status  ON workspaces(status);

CREATE TABLE IF NOT EXISTS workspace_members (
    id                 BIGSERIAL PRIMARY KEY,
    workspace_id       BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id            TEXT NOT NULL,
    role               TEXT DEFAULT 'contributor',
    custom_permissions JSONB DEFAULT '{}'::jsonb,
    invited_by         TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_workspace_member UNIQUE (workspace_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_workspace_members_workspace ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS ix_workspace_members_user      ON workspace_members(user_id);

CREATE TABLE IF NOT EXISTS workspace_invitations (
    id           BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    email        TEXT NOT NULL,
    role         TEXT DEFAULT 'contributor',
    token        TEXT NOT NULL UNIQUE,
    invited_by   TEXT,
    status       TEXT DEFAULT 'pending',
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_invitations_workspace ON workspace_invitations(workspace_id);
CREATE INDEX IF NOT EXISTS ix_invitations_token     ON workspace_invitations(token);

-- ── 後方 FK: 先行テーブルの workspace_id / account_id へ FK 制約を追加 ──
DO $$ BEGIN
    ALTER TABLE ai_employee_config
        ADD CONSTRAINT fk_ai_employee_config_account
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE knowledge_base
        ADD CONSTRAINT fk_knowledge_base_account
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE knowledge_base
        ADD CONSTRAINT fk_knowledge_base_workspace
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE threads
        ADD CONSTRAINT fk_threads_workspace
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE artifacts
        ADD CONSTRAINT fk_artifacts_workspace
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE conversation_log
        ADD CONSTRAINT fk_conversation_log_workspace
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE conversation_slots
        ADD CONSTRAINT fk_conversation_slots_workspace
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TABLE approval_queue
        ADD CONSTRAINT fk_approval_queue_workspace
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS ix_threads_workspace   ON threads(workspace_id);
CREATE INDEX IF NOT EXISTS ix_artifacts_workspace ON artifacts(workspace_id);

-- =============================================================================
-- 10. 開発フロー (alembic c1d2e3f4g5h6)
-- =============================================================================

CREATE TABLE IF NOT EXISTS repos (
    id               BIGSERIAL PRIMARY KEY,
    workspace_id     BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    github_full_name TEXT,
    local_path       TEXT,
    default_branch   TEXT DEFAULT 'main',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_repos_workspace ON repos(workspace_id);

CREATE TABLE IF NOT EXISTS pull_requests (
    id               BIGSERIAL PRIMARY KEY,
    repo_id          BIGINT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    number           INTEGER NOT NULL,
    title            TEXT NOT NULL,
    author           TEXT,
    status           TEXT,
    head_branch      TEXT,
    base_branch      TEXT,
    url              TEXT,
    ai_review_status TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_pr_repo   ON pull_requests(repo_id);
CREATE INDEX IF NOT EXISTS ix_pr_status ON pull_requests(status);

CREATE TABLE IF NOT EXISTS reviews (
    id                   BIGSERIAL PRIMARY KEY,
    pr_id                BIGINT REFERENCES pull_requests(id) ON DELETE CASCADE,
    task_id              BIGINT REFERENCES tasks(id) ON DELETE SET NULL,
    workspace_id         BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    reviewer_employee_id BIGINT REFERENCES ai_employee_config(id) ON DELETE SET NULL,
    verdict              TEXT,
    summary              TEXT,
    findings_json        JSONB DEFAULT '[]'::jsonb,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_reviews_workspace ON reviews(workspace_id);
CREATE INDEX IF NOT EXISTS ix_reviews_verdict   ON reviews(verdict);

-- =============================================================================
-- 11. LangGraph checkpoint テーブル (legacy: SQLite で AsyncSqliteSaver が作成)
--     PostgresSaver は別スキーマを期待するため、カラム互換のみ用意
-- =============================================================================

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id            TEXT NOT NULL,
    checkpoint_ns        TEXT NOT NULL DEFAULT '',
    checkpoint_id        TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type                 TEXT,
    checkpoint           BYTEA,
    metadata             BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS writes (
    thread_id     TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id       TEXT NOT NULL,
    idx           INTEGER NOT NULL,
    channel       TEXT NOT NULL,
    type          TEXT,
    value         BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- =============================================================================
-- 12. alembic 管理テーブル (移行期間のため残す)
-- =============================================================================

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
