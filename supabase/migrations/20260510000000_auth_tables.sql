-- =============================================================================
-- T-001-02: 認証 6 テーブル DDL + RLS
-- =============================================================================
-- Build-Factory の Supabase Auth (GoTrue) 上に、profile / session / 2FA / OAuth /
-- audit を追加する。auth.users への FK で連動。
--
-- 6 tables:
--   1. users                       — profile extension (auth.users への 1:1 拡張)
--   2. auth_sessions               — サーバー側セッション追跡 (24h TTL、device 情報)
--   3. user_2fa_secrets            — TOTP secret (pgsodium で暗号化、plaintext 禁止)
--   4. user_2fa_recovery_codes     — 2FA バックアップコード (使用済みフラグ)
--   5. oauth_connections           — Anthropic / Slack / GitHub OAuth 紐付け
--   6. auth_audit_log              — login / 2FA challenge / OAuth event の監査
--
-- 設計方針:
--   - 全 PK は UUID (auth.users と整合)
--   - 全 created_at/updated_at は TIMESTAMPTZ DEFAULT NOW()
--   - 全テーブル CREATE IF NOT EXISTS で idempotent (AC-2)
--   - 2FA secret は pgsodium で暗号化 (AC-5: plaintext 禁止)
--   - RLS は auth.uid() = user_id で owner-only (AC-3)
--
-- 依存: 20260501220000_initial_schema.sql (auth.users が存在する)
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. users — profile extension to auth.users
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    display_name    TEXT,
    avatar_url      TEXT,
    locale          TEXT DEFAULT 'ja',
    timezone        TEXT DEFAULT 'Asia/Tokyo',
    custom_permissions JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

-- auth.users 作成時に users 行を自動生成 (AC: where auth.users is provisioned)
CREATE OR REPLACE FUNCTION handle_new_auth_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO users (id, email, display_name)
    VALUES (NEW.id, NEW.email, COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1)))
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION handle_new_auth_user();

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. auth_sessions — サーバー側セッション追跡 (24h TTL)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auth_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    device_label    TEXT,                                     -- "MacBook Pro / Chrome 130"
    device_fingerprint TEXT,                                  -- 任意の安定 hash
    ip_address      INET,
    user_agent      TEXT,
    issued_at       TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,                     -- issued_at + 24h
    last_seen_at    TIMESTAMPTZ DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ,                              -- ログアウト時
    revoked_reason  TEXT CHECK (revoked_reason IN ('user_logout', 'admin_revoke', 'expired', 'security'))
);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_user      ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires   ON auth_sessions(expires_at);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_active    ON auth_sessions(user_id) WHERE revoked_at IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. user_2fa_secrets — TOTP (pgsodium 暗号化、plaintext 禁止)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_2fa_secrets (
    user_id         UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    encrypted_secret BYTEA NOT NULL,                          -- pgsodium.crypto_secretbox_open で復号
    enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_at      TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. user_2fa_recovery_codes — バックアップコード (1 user × 8〜10 codes)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_2fa_recovery_codes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    code_hash       TEXT NOT NULL,                            -- SHA-256(code)、plaintext 保存禁止
    used_at         TIMESTAMPTZ,                              -- 使用済みは null 解除
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_recovery_user_code UNIQUE (user_id, code_hash)
);

CREATE INDEX IF NOT EXISTS ix_recovery_user ON user_2fa_recovery_codes(user_id) WHERE used_at IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. oauth_connections — Anthropic / Slack / GitHub
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS oauth_connections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL CHECK (provider IN ('anthropic', 'slack', 'github')),
    provider_user_id TEXT NOT NULL,                            -- 各プロバイダの user identifier
    encrypted_access_token  BYTEA NOT NULL,                    -- pgsodium で暗号化必須
    encrypted_refresh_token BYTEA,
    scopes          TEXT[] DEFAULT ARRAY[]::TEXT[],
    expires_at      TIMESTAMPTZ,
    connected_at    TIMESTAMPTZ DEFAULT NOW(),
    last_refreshed_at TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    CONSTRAINT uq_oauth_user_provider UNIQUE (user_id, provider)
);

CREATE INDEX IF NOT EXISTS ix_oauth_user ON oauth_connections(user_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. auth_audit_log — login / 2FA challenge / OAuth event
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auth_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES auth.users(id) ON DELETE SET NULL,  -- 失敗ログイン時 NULL
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'login_attempt', 'login_success', 'login_failure',
                        '2fa_challenge', '2fa_success', '2fa_failure',
                        'oauth_link', 'oauth_unlink', 'oauth_refresh',
                        'session_revoke', 'password_reset', 'recovery_code_used'
                    )),
    success         BOOLEAN NOT NULL,
    ip_address      INET,
    user_agent      TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,                  -- failure_reason / provider 等
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_auth_audit_user    ON auth_audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_auth_audit_type    ON auth_audit_log(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_auth_audit_failures ON auth_audit_log(created_at DESC) WHERE success = FALSE;


-- =============================================================================
-- RLS: owner-only (auth.uid() = user_id) + service_role 全許可
-- =============================================================================

-- 1. users: 本人と service_role のみ更新可、認証済み全員が他人の display_name を読める
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_service_role_all ON users;
CREATE POLICY users_service_role_all ON users
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS users_self_read ON users;
CREATE POLICY users_self_read ON users
    FOR SELECT TO authenticated
    USING (auth.uid() = id OR true);  -- 全員が公開プロフィールを読める

DROP POLICY IF EXISTS users_self_write ON users;
CREATE POLICY users_self_write ON users
    FOR UPDATE TO authenticated
    USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- 2. auth_sessions: 本人と service_role のみ
ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS auth_sessions_service_role ON auth_sessions;
CREATE POLICY auth_sessions_service_role ON auth_sessions
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS auth_sessions_self ON auth_sessions;
CREATE POLICY auth_sessions_self ON auth_sessions
    FOR ALL TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 3. user_2fa_secrets: 本人と service_role のみ
ALTER TABLE user_2fa_secrets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_2fa_secrets_service_role ON user_2fa_secrets;
CREATE POLICY user_2fa_secrets_service_role ON user_2fa_secrets
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_2fa_secrets_self ON user_2fa_secrets;
CREATE POLICY user_2fa_secrets_self ON user_2fa_secrets
    FOR ALL TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 4. user_2fa_recovery_codes: 本人と service_role のみ
ALTER TABLE user_2fa_recovery_codes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS recovery_codes_service_role ON user_2fa_recovery_codes;
CREATE POLICY recovery_codes_service_role ON user_2fa_recovery_codes
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS recovery_codes_self ON user_2fa_recovery_codes;
CREATE POLICY recovery_codes_self ON user_2fa_recovery_codes
    FOR ALL TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 5. oauth_connections: 本人と service_role のみ
ALTER TABLE oauth_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS oauth_service_role ON oauth_connections;
CREATE POLICY oauth_service_role ON oauth_connections
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS oauth_self ON oauth_connections;
CREATE POLICY oauth_self ON oauth_connections
    FOR ALL TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- 6. auth_audit_log: 本人読み取りのみ + service_role 全権、INSERT は service_role のみ
ALTER TABLE auth_audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_service_role ON auth_audit_log;
CREATE POLICY audit_service_role ON auth_audit_log
    FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS audit_self_read ON auth_audit_log;
CREATE POLICY audit_self_read ON auth_audit_log
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);
