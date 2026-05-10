-- =============================================================================
-- T-S0-08: claude-agent-sdk runner 関連 5 テーブル
-- =============================================================================
-- ADR-010 (AI スタック再設計) に従い、claude-agent-sdk が SDK 内部で扱う
-- session resume / 3-tier compaction / prompt cache を、自前の永続化層で
-- 補完するためのテーブル。
--
-- 5 tables:
--   1. sessions          — 1 タスク実行 = 1 row (status / 4-choice resume)
--   2. session_logs      — stdout/stderr 行単位ストリーム (1 session : N logs)
--   3. cost_logs         — Anthropic Usage API + cache hit rate (AC-4)
--   4. chat_threads      — claude-agent-sdk session に対応する会話スレッド
--   5. chat_messages     — メッセージ + 9-section structured summary (AC-5)
--
-- 設計方針:
--   - PK: BIGSERIAL (workspaces / accounts と整合)
--   - sessions.status = (running / done / crashed / cancelled / paused)
--   - sessions.resume_choice = (from_checkpoint / rerun_full / manual_fix / cancel)
--   - workspace 経由 RLS (T-001-04 / T-001-06 と同じ pattern)
--   - 全 CREATE TABLE IF NOT EXISTS / DROP POLICY IF EXISTS で idempotent
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. sessions — 1 タスク実行 = 1 row
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id              BIGSERIAL PRIMARY KEY,
    sdk_session_id  TEXT NOT NULL UNIQUE,                  -- claude-agent-sdk が発行
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id      BIGINT REFERENCES bf_projects(id) ON DELETE SET NULL,
    bf_task_id      BIGINT REFERENCES bf_tasks(id) ON DELETE SET NULL,
    agent_persona   TEXT,                                  -- "mary" / "devon" / "quinn" など
    skill_name      TEXT,
    prompt          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running','done','crashed','cancelled','paused')),
    resume_choice   TEXT
                        CHECK (resume_choice IN ('from_checkpoint','rerun_full','manual_fix','cancel')),
    crash_reason    TEXT,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_by      TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_ws       ON sessions(workspace_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_sessions_status   ON sessions(status, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_sessions_active   ON sessions(workspace_id) WHERE status = 'running';

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. session_logs — stdout/stderr 行単位ストリーム
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_logs (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    line_no         INTEGER NOT NULL,
    stream          TEXT NOT NULL CHECK (stream IN ('stdout','stderr','system')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_session_line UNIQUE (session_id, line_no)
);
CREATE INDEX IF NOT EXISTS ix_session_logs_session ON session_logs(session_id, line_no);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. cost_logs — Anthropic Usage API + cache hit rate (AC-4)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cost_logs (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          BIGINT REFERENCES sessions(id) ON DELETE CASCADE,
    workspace_id        BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    provider            TEXT NOT NULL DEFAULT 'anthropic'
                            CHECK (provider IN ('anthropic','openai','gemini','litellm','other')),
    model               TEXT NOT NULL,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,        -- prompt cache 読み出し (AC-4)
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,        -- prompt cache 書き込み
    cost_usd            NUMERIC(10,6) NOT NULL DEFAULT 0,
    occurred_at         TIMESTAMPTZ DEFAULT NOW(),
    metadata            JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_cost_session  ON cost_logs(session_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_cost_workspace ON cost_logs(workspace_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_cost_model    ON cost_logs(model, occurred_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. chat_threads — claude-agent-sdk session に対応する会話スレッド
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_threads (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    session_id      BIGINT REFERENCES sessions(id) ON DELETE SET NULL,
    title           TEXT,
    persona         TEXT,
    is_archived     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_chat_threads_ws ON chat_threads(workspace_id, updated_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. chat_messages — メッセージ + 9-section structured summary (AC-5)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id                  BIGSERIAL PRIMARY KEY,
    thread_id           BIGINT NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role                TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
    content             TEXT NOT NULL,
    compressed_summary  JSONB,                                  -- 95% 超過時の 9-section structured summary (AC-5)
    token_count         INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_chat_messages_thread ON chat_messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS ix_chat_messages_summary ON chat_messages(thread_id) WHERE compressed_summary IS NOT NULL;

-- =============================================================================
-- RLS (T-001-04 / T-001-06 と同一 pattern: workspace_members 経由)
-- =============================================================================

-- 1. sessions
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sessions_service_role ON sessions;
CREATE POLICY sessions_service_role ON sessions FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS sessions_member ON sessions;
CREATE POLICY sessions_member ON sessions FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- 2. session_logs
ALTER TABLE session_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS session_logs_service_role ON session_logs;
CREATE POLICY session_logs_service_role ON session_logs FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS session_logs_member ON session_logs;
CREATE POLICY session_logs_member ON session_logs FOR SELECT TO authenticated
    USING (session_id IN (
        SELECT id FROM sessions
        WHERE workspace_id IS NULL OR bf_can_access_workspace(workspace_id)
    ));

-- 3. cost_logs
ALTER TABLE cost_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cost_logs_service_role ON cost_logs;
CREATE POLICY cost_logs_service_role ON cost_logs FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS cost_logs_member ON cost_logs;
CREATE POLICY cost_logs_member ON cost_logs FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- 4. chat_threads
ALTER TABLE chat_threads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS chat_threads_service_role ON chat_threads;
CREATE POLICY chat_threads_service_role ON chat_threads FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS chat_threads_member ON chat_threads;
CREATE POLICY chat_threads_member ON chat_threads FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- 5. chat_messages
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS chat_messages_service_role ON chat_messages;
CREATE POLICY chat_messages_service_role ON chat_messages FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS chat_messages_member ON chat_messages;
CREATE POLICY chat_messages_member ON chat_messages FOR ALL TO authenticated
    USING (thread_id IN (
        SELECT id FROM chat_threads
        WHERE workspace_id IS NULL OR bf_can_access_workspace(workspace_id)
    ))
    WITH CHECK (thread_id IN (
        SELECT id FROM chat_threads
        WHERE workspace_id IS NULL OR bf_can_access_workspace(workspace_id)
    ));
