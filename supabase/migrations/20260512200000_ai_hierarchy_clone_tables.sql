-- =============================================================================
-- T-001-03: AI 5 テーブル DDL (hierarchy + clone) — Supabase 化
-- =============================================================================
-- legacy alembic (d7e8f9a0b1c2_staff_hierarchy_personas.py) で ai_employee_config を
-- 拡張していたが、 Supabase Postgres に移行するため正準 5 テーブル構成で再定義.
--
-- 5 テーブル (architecture-v1 §4 / CLAUDE.md §3 BMAD 10 ペルソナ + M-22 個人クローン):
--
--   1. ai_employees           — AI 社員 master (BMAD 10 ペルソナ + 拡張)
--   2. ai_personas            — 個性 / 性格 / 口調 / 専門分野
--   3. ai_hierarchies         — parent-child 階層 (秘書 → リーダー → メンバー)
--   4. ai_clones              — 個人クローン opt-in (M-22, デフォルト OFF)
--   5. user_interaction_log   — クローン学習データ (opt-in TRUE のみ INSERT 可能)
--
-- AC マッピング:
--   AC-1 UBIQUITOUS: 5 テーブル DDL + RLS + 個人クローン opt-in trigger
--   AC-3 STATE:     既存 ai_employee_config (legacy SQLite) と共存 (新 schema は別名前空間)
--   AC-4 UNWANTED:  opt-in OFF user の interaction log を INSERT しようとすると
--                   trigger で reject (M-22 プライバシー必須要件)
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. ai_employees — AI 社員 master
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_employees (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    employee_key    TEXT NOT NULL,                              -- "mary" / "preston" / etc
    display_name    TEXT NOT NULL,                              -- "Mary (BA)"
    persona_id      BIGINT,                                     -- FK ai_personas.id (後で ADD)
    role_level      TEXT NOT NULL DEFAULT 'leader'
                       CHECK (role_level IN ('secretary','leader','member')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    retired_at      TIMESTAMPTZ,
    retire_reason   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_ai_employee_ws_key UNIQUE (workspace_id, employee_key)
);
CREATE INDEX IF NOT EXISTS ix_ai_employees_ws         ON ai_employees(workspace_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS ix_ai_employees_role_level ON ai_employees(role_level, is_active);
CREATE INDEX IF NOT EXISTS ix_ai_employees_retired    ON ai_employees(retired_at) WHERE retired_at IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. ai_personas — 個性 / 性格 / 口調 / 専門分野
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_personas (
    id              BIGSERIAL PRIMARY KEY,
    persona_key     TEXT NOT NULL UNIQUE,                       -- "ba_analyst" / "developer" etc
    persona_name    TEXT NOT NULL,                              -- "Mary Mansfield"
    personality     TEXT,                                       -- "落ち着いて全体を把握"
    tone_style      TEXT,                                       -- "敬語・短く要点"
    catchphrase     TEXT,
    specialty       TEXT,                                       -- "業務分析 / 要件抽出"
    handles         TEXT,                                       -- "M-1 / M-2 / 顧客対応"
    avatar_lucide   TEXT,                                       -- lucide icon name (規約: emoji 禁止)
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- persona FK を late-bind (ai_employees → ai_personas)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ai_employees_persona'
    ) THEN
        ALTER TABLE ai_employees
            ADD CONSTRAINT fk_ai_employees_persona
            FOREIGN KEY (persona_id) REFERENCES ai_personas(id) ON DELETE SET NULL;
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS ix_ai_personas_specialty ON ai_personas(specialty);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. ai_hierarchies — parent-child 階層
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_hierarchies (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    parent_id       BIGINT REFERENCES ai_employees(id) ON DELETE CASCADE,
    child_id        BIGINT NOT NULL REFERENCES ai_employees(id) ON DELETE CASCADE,
    relation_type   TEXT NOT NULL DEFAULT 'reports_to'
                       CHECK (relation_type IN ('reports_to','collaborates_with','delegates_to','mentors')),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    -- 自分自身を親にすることを禁止
    CONSTRAINT no_self_parent CHECK (parent_id IS NULL OR parent_id <> child_id),
    -- 同じ workspace 内で同じ parent-child 関係を多重登録しない
    CONSTRAINT uq_ai_hierarchy_relation UNIQUE (workspace_id, parent_id, child_id, relation_type)
);
CREATE INDEX IF NOT EXISTS ix_ai_hierarchies_ws_parent ON ai_hierarchies(workspace_id, parent_id);
CREATE INDEX IF NOT EXISTS ix_ai_hierarchies_ws_child  ON ai_hierarchies(workspace_id, child_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. ai_clones — 個人クローン opt-in (M-22, デフォルト OFF)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_clones (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL UNIQUE,                       -- 1 user = 1 clone
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE SET NULL,
    base_employee_id BIGINT REFERENCES ai_employees(id) ON DELETE SET NULL,
    is_opted_in     BOOLEAN NOT NULL DEFAULT FALSE,             -- AC-4: デフォルト OFF (CLAUDE.md §11)
    opted_in_at     TIMESTAMPTZ,
    opted_out_at    TIMESTAMPTZ,
    consent_version TEXT,                                       -- "v1.0" (GDPR 対応)
    training_count  INTEGER NOT NULL DEFAULT 0,
    last_trained_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    -- opt_in 切替時の整合性: TRUE なら opted_in_at 必須
    CONSTRAINT opt_in_timestamp_consistent
        CHECK (NOT is_opted_in OR opted_in_at IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_ai_clones_opted_in ON ai_clones(user_id) WHERE is_opted_in = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. user_interaction_log — クローン学習データ (opt-in TRUE のみ INSERT 可能)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_interaction_log (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    clone_id        BIGINT REFERENCES ai_clones(id) ON DELETE CASCADE,
    interaction_type TEXT NOT NULL CHECK (interaction_type IN
        ('decision','correction','preference','rejection','approval','annotation')),
    context_summary TEXT,
    raw_payload     JSONB DEFAULT '{}'::jsonb,
    embedding_status TEXT NOT NULL DEFAULT 'pending'
                       CHECK (embedding_status IN ('pending','embedded','failed','redacted')),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_user_interaction_user    ON user_interaction_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_user_interaction_clone   ON user_interaction_log(clone_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_user_interaction_pending ON user_interaction_log(user_id)
    WHERE embedding_status = 'pending';


-- ─────────────────────────────────────────────────────────────────────────────
-- AC-4 trigger: opt_in = FALSE の user_interaction_log INSERT を reject
-- (M-22 個人クローン: opt-in OFF user のログ収集を完全に塞ぐ)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bf_enforce_clone_opt_in() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    has_opt_in BOOLEAN;
BEGIN
    -- 該当 user の clone レコードが opt-in TRUE か確認
    SELECT is_opted_in INTO has_opt_in FROM ai_clones WHERE user_id = NEW.user_id;
    IF has_opt_in IS NULL OR has_opt_in = FALSE THEN
        RAISE EXCEPTION 'clone_opt_in_required: user_id=% has not opted in to clone training', NEW.user_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END$$;

DROP TRIGGER IF EXISTS trg_enforce_clone_opt_in ON user_interaction_log;
CREATE TRIGGER trg_enforce_clone_opt_in
    BEFORE INSERT ON user_interaction_log
    FOR EACH ROW EXECUTE FUNCTION bf_enforce_clone_opt_in();


-- ─────────────────────────────────────────────────────────────────────────────
-- RLS: 全 5 テーブル ENABLE + service_role 全権 + workspace_member or owner_user
-- ─────────────────────────────────────────────────────────────────────────────

-- ai_employees: workspace member 経由
ALTER TABLE ai_employees ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_employees_service_role ON ai_employees;
CREATE POLICY ai_employees_service_role ON ai_employees FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS ai_employees_member ON ai_employees;
CREATE POLICY ai_employees_member ON ai_employees FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- ai_personas: グローバル参照可、 admin のみ書き込み
ALTER TABLE ai_personas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_personas_service_role ON ai_personas;
CREATE POLICY ai_personas_service_role ON ai_personas FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS ai_personas_read ON ai_personas;
CREATE POLICY ai_personas_read ON ai_personas FOR SELECT TO authenticated USING (true);

-- ai_hierarchies: workspace 経由
ALTER TABLE ai_hierarchies ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_hierarchies_service_role ON ai_hierarchies;
CREATE POLICY ai_hierarchies_service_role ON ai_hierarchies FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS ai_hierarchies_member ON ai_hierarchies;
CREATE POLICY ai_hierarchies_member ON ai_hierarchies FOR ALL TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id))
    WITH CHECK (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- ai_clones: 本人のみ (user_id == auth.uid()) + service_role
ALTER TABLE ai_clones ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ai_clones_service_role ON ai_clones;
CREATE POLICY ai_clones_service_role ON ai_clones FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS ai_clones_owner ON ai_clones;
CREATE POLICY ai_clones_owner ON ai_clones FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

-- user_interaction_log: 本人のみ
ALTER TABLE user_interaction_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_interaction_log_service_role ON user_interaction_log;
CREATE POLICY user_interaction_log_service_role ON user_interaction_log FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS user_interaction_log_owner ON user_interaction_log;
CREATE POLICY user_interaction_log_owner ON user_interaction_log FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260512200000', 'T-001-03: AI 5 tables (employees/personas/hierarchies/clones/interaction_log)', 'system')
ON CONFLICT (version) DO NOTHING;


COMMENT ON TABLE ai_clones IS 'M-22 個人クローン opt-in: default OFF / consent_version / opt_out anytime';
COMMENT ON TABLE user_interaction_log IS 'M-22 学習データ: trg_enforce_clone_opt_in で opt-in FALSE は INSERT reject';