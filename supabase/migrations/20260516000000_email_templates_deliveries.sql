-- T-V3-B-30 / F-028: Email backend tables (templates + deliveries)
--
-- Creates:
--   1. email_templates  (E-043) — workspace-scoped versioned outbound email templates
--   2. email_deliveries (E-044) — delivery tracking (queued / sent / bounced / failed)
--   3. RLS enabled on both with service_role + workspace_member policies
--
-- AC マッピング:
--   AC-F1 / AC-F8 UNWANTED  : POST /api/email/test-send 10/hour/workspace 超過 → 429
--                              (rate limit は backend/services/email.py で in-memory token-bucket)
--   AC-F2          EVENT    : GET /api/email/templates → workspace 範囲の active template 一覧
--   AC-F5          EVENT    : POST /api/email/test-send → email_deliveries に row INSERT
--   AC-policy               : workspace_member_select (RLS)
--   AC-RLS                  : email_templates / email_deliveries 共に
--                              ALTER TABLE ... ENABLE ROW LEVEL SECURITY (verify-rls-coverage.py)

-- ──────────────────────────────────────────────────────────────────
-- 1. email_templates (E-043)
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS email_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,                              -- "signup_verify" / "password_reset" / ...
    locale          TEXT NOT NULL DEFAULT 'ja',
    subject         TEXT NOT NULL,
    body_html       TEXT,
    body_text       TEXT,
    body_md         TEXT,
    variables       JSONB NOT NULL DEFAULT '[]'::jsonb,
    version         INT NOT NULL DEFAULT 1,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_email_template_ws_name_locale UNIQUE (workspace_id, name, locale)
);
CREATE INDEX IF NOT EXISTS ix_email_templates_ws ON email_templates(workspace_id) WHERE is_active = TRUE;

-- ──────────────────────────────────────────────────────────────────
-- 2. email_deliveries (E-044)
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS email_deliveries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    template_id     UUID REFERENCES email_templates(id) ON DELETE SET NULL,
    recipient       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued'
                       CHECK (status IN ('queued','sent','bounced','failed','unsubscribed')),
    provider        TEXT,                                       -- "resend" / "ses" / "smtp"
    provider_msg_id TEXT,
    retry_count     INT NOT NULL DEFAULT 0,
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at         TIMESTAMPTZ,
    last_error      TEXT,
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_email_deliveries_ws_status
    ON email_deliveries(workspace_id, status, queued_at DESC);
CREATE INDEX IF NOT EXISTS ix_email_deliveries_template
    ON email_deliveries(template_id, queued_at DESC);

-- ──────────────────────────────────────────────────────────────────
-- 3. RLS (workspace_member_select policy)
-- ──────────────────────────────────────────────────────────────────
ALTER TABLE email_templates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS email_templates_service_role ON email_templates;
CREATE POLICY email_templates_service_role ON email_templates
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS email_templates_workspace_member ON email_templates;
CREATE POLICY email_templates_workspace_member ON email_templates FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

ALTER TABLE email_deliveries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS email_deliveries_service_role ON email_deliveries;
CREATE POLICY email_deliveries_service_role ON email_deliveries
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS email_deliveries_workspace_member ON email_deliveries;
CREATE POLICY email_deliveries_workspace_member ON email_deliveries FOR SELECT TO authenticated
    USING (workspace_id IS NULL OR bf_can_access_workspace(workspace_id));

-- ──────────────────────────────────────────────────────────────────
-- 4. Default template seed (global / workspace_id=NULL, idempotent)
--    5 standard templates: signup_verify / password_reset / invitation /
--                          task_notification / weekly_summary
-- ──────────────────────────────────────────────────────────────────
INSERT INTO email_templates (workspace_id, name, locale, subject, body_text, variables)
VALUES
    (NULL, 'signup_verify', 'ja',
        'Build-Factory にようこそ — メール認証',
        E'{{name}} 様\n\n以下のリンクからメール認証を完了してください:\n{{verify_url}}\n\n— Build-Factory',
        '["name","verify_url"]'::jsonb),
    (NULL, 'password_reset', 'ja',
        'Build-Factory パスワード再設定',
        E'{{name}} 様\n\nパスワード再設定リンク (60 分有効):\n{{reset_url}}\n\n— Build-Factory',
        '["name","reset_url"]'::jsonb),
    (NULL, 'invitation', 'ja',
        '{{inviter_name}} さんから Build-Factory ワークスペース招待',
        E'{{inviter_name}} さんから "{{workspace_name}}" への参加招待が届いています:\n{{accept_url}}',
        '["inviter_name","workspace_name","accept_url"]'::jsonb),
    (NULL, 'task_notification', 'ja',
        '[Build-Factory] {{task_title}} に動きがあります',
        E'タスク {{task_title}} の状態が "{{status}}" に変わりました.\n{{task_url}}',
        '["task_title","status","task_url"]'::jsonb),
    (NULL, 'weekly_summary', 'ja',
        '[Build-Factory] 今週のサマリー ({{week_range}})',
        E'今週の進捗:\n- 完了タスク: {{done_count}}\n- 進行中: {{wip_count}}\n- ブロック: {{blocked_count}}\n\n詳細: {{dashboard_url}}',
        '["week_range","done_count","wip_count","blocked_count","dashboard_url"]'::jsonb)
ON CONFLICT (workspace_id, name, locale) DO NOTHING;
