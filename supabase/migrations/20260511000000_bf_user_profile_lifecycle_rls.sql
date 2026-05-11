-- Build-Factory user_profile / user_lifecycle テーブル (Supabase 用) + RLS
--
-- 対応タスク:
--   T-023-01: プロフィール編集 UI    → user_profiles
--   T-023-05: クローン opt-in + GDPR 削除権 → user_clone_optin / user_deletion_requests
--
-- 背景:
--   alembic 側 (sqlite, Phase 1 開発用) では既に c7d8e9f0a1b2 / a4b5c6d7e8f9
--   migration で 3 テーブルが定義されている。 Supabase Postgres 移行 (T-001-01) 後は
--   この migration で同等スキーマと RLS を確立する。
--
-- ポリシー設計:
--   user_profiles            : 本人のみ R/W、 service_role は全件 R/W
--   user_clone_optin         : 本人のみ R/W、 service_role は全件 R/W
--   user_deletion_requests   : 本人のみ R (W は service_role 経由)
--
-- 注: encrypted_credentials / oauth_connections は現状ファイル管理 (credentials_store.py)
-- のため、 本 migration では対象外。 DB 化は別タスク (Phase 2 想定) で。

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. user_profiles (Build-Factory 拡張プロフィール)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id       TEXT PRIMARY KEY,
    display_name  TEXT,
    role_text     TEXT,
    bio           TEXT,
    theme         TEXT NOT NULL DEFAULT 'light'
                    CHECK (theme IN ('light','dark','system')),
    avatar_url    TEXT,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_profiles_service_role ON user_profiles;
CREATE POLICY user_profiles_service_role ON user_profiles
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_profiles_self_select ON user_profiles;
CREATE POLICY user_profiles_self_select ON user_profiles
    FOR SELECT TO authenticated
    USING (user_id = auth.uid()::text);

DROP POLICY IF EXISTS user_profiles_self_update ON user_profiles;
CREATE POLICY user_profiles_self_update ON user_profiles
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

DROP POLICY IF EXISTS user_profiles_self_insert ON user_profiles;
CREATE POLICY user_profiles_self_insert ON user_profiles
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. user_clone_optin (T-023-05: AI 社員クローン opt-in)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_clone_optin (
    id            BIGSERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL UNIQUE,
    opted_in      BOOLEAN NOT NULL DEFAULT false,
    opted_in_at   TIMESTAMPTZ,
    opted_out_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_clone_optin_user ON user_clone_optin(user_id);

ALTER TABLE user_clone_optin ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_clone_optin_service_role ON user_clone_optin;
CREATE POLICY user_clone_optin_service_role ON user_clone_optin
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_clone_optin_self ON user_clone_optin;
CREATE POLICY user_clone_optin_self ON user_clone_optin
    FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. user_deletion_requests (T-023-05: GDPR 削除権, 30 日 grace)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_deletion_requests (
    id             BIGSERIAL PRIMARY KEY,
    user_id        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','cancelled','executed')),
    requested_at   TIMESTAMPTZ DEFAULT NOW(),
    execute_after  TIMESTAMPTZ NOT NULL,
    cancelled_at   TIMESTAMPTZ,
    executed_at    TIMESTAMPTZ,
    reason         TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_deletion_requests_status
    ON user_deletion_requests(status, execute_after);
CREATE INDEX IF NOT EXISTS idx_user_deletion_requests_user
    ON user_deletion_requests(user_id);

ALTER TABLE user_deletion_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_deletion_requests_service_role ON user_deletion_requests;
CREATE POLICY user_deletion_requests_service_role ON user_deletion_requests
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

-- 本人のみ自分の削除リクエストを SELECT 可
DROP POLICY IF EXISTS user_deletion_requests_self_read ON user_deletion_requests;
CREATE POLICY user_deletion_requests_self_read ON user_deletion_requests
    FOR SELECT TO authenticated
    USING (user_id = auth.uid()::text);

-- 本人は自分の削除リクエストの新規作成 (削除申請) と キャンセル (UPDATE) のみ可
DROP POLICY IF EXISTS user_deletion_requests_self_insert ON user_deletion_requests;
CREATE POLICY user_deletion_requests_self_insert ON user_deletion_requests
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid()::text);

DROP POLICY IF EXISTS user_deletion_requests_self_cancel ON user_deletion_requests;
CREATE POLICY user_deletion_requests_self_cancel ON user_deletion_requests
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid()::text AND status = 'pending')
    WITH CHECK (user_id = auth.uid()::text AND status IN ('pending','cancelled'));
