-- =============================================================================
-- T-V3-D-06: RLS policy 補完 batch 2 — auth & profile family (E-047〜E-055)
-- =============================================================================
-- Target tables (9 entities):
--   1. user_clone_optin          (E-047, user_scoped, user_id TEXT)
--   2. user_deletion_requests    (E-048, user_scoped, user_id TEXT)
--   3. user_profiles             (E-049, user_scoped, user_id TEXT)
--   4. encrypted_secrets         (E-050, polymorphic owner, owner_id TEXT)
--   5. auth_sessions             (E-051, user_scoped, user_id UUID)
--   6. oauth_connections         (E-052, user_scoped, user_id UUID)
--   7. user_2fa_secrets          (E-053, user_scoped, user_id UUID, SECURITY CRITICAL)
--   8. user_2fa_recovery_codes   (E-054, user_scoped, user_id UUID, SECURITY CRITICAL)
--   9. auth_audit_log            (E-055, user_scoped, user_id UUID)
--
-- Background (drift summary):
--   既存 migration (20260510000000_auth_tables.sql /
--   20260511000000_bf_user_profile_lifecycle_rls.sql /
--   20260511000001_encrypted_secrets.sql) は各テーブルに 2-4 policy を既に
--   設定済み。 ただし v3 entities.json (E-047〜E-055) の access_control_policies
--   が要求する canonical 命名 (`<table>_service_role_all` + `<table>_owner_only`
--   など) と差異がある。
--
--   本 migration は v3 drift summary §6「新規 entity の RLS 整備」と
--   tickets-group-d-drift.json#T-V3-D-06 `access_policies_required` に従い、
--   各 table に canonical 命名の policy を idempotent に追加する。
--
--   既存 policy は drop せず、 同名の追加 policy を idempotent に CREATE する。
--   Postgres の RLS は policy が複数あるとき OR で結合するため、 既存 owner /
--   service_role policy と新規 canonical policy は accumulative (cumulative).
--
-- AC マッピング (T-V3-D-06):
--   AC-F1 UBIQUITOUS : 各 table に >= 2 policy (service_role_all + owner_scoped)
--   AC-F2 EVENT      : auth user が user_id != auth.uid() の user_profiles を query → 0 row
--   AC-F3 EVENT      : auth user が他人の auth_audit_log event を query → 0 row
--   AC-F4 UNWANTED   : verify-rls-coverage.py で 9 table の policy_count < 2 なら fail
--   AC-F5 UNWANTED   : encrypted_secrets.secret_value (encrypted_value) が
--                      non-service_role に直接公開されない (owner_id scoped)
--
-- セキュリティ注意 (risk_flags: security_critical):
--   user_2fa_secrets / user_2fa_recovery_codes は TOTP secret/backup を含む。
--   本 migration では owner_only access のみ許可し、 cross-user access path を
--   一切作らない。
--
-- 詳細: docs/audit/2026-05-16_v3/T-V3-D-06.md
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. user_clone_optin (E-047) — service_role_all + owner_only
-- user_id TEXT, RLS は user_id = auth.uid()::text
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE user_clone_optin ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_clone_optin_service_role_all ON user_clone_optin;
CREATE POLICY user_clone_optin_service_role_all ON user_clone_optin
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_clone_optin_owner_only ON user_clone_optin;
CREATE POLICY user_clone_optin_owner_only ON user_clone_optin
    FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. user_deletion_requests (E-048) — service_role_all + owner_only
-- user_id TEXT, RLS は user_id = auth.uid()::text
-- 既存の self_read / self_insert / self_cancel policy はそのまま残し、
-- canonical owner_only policy を OR で結合 (cumulative).
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE user_deletion_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_deletion_requests_service_role_all ON user_deletion_requests;
CREATE POLICY user_deletion_requests_service_role_all ON user_deletion_requests
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_deletion_requests_owner_only ON user_deletion_requests;
CREATE POLICY user_deletion_requests_owner_only ON user_deletion_requests
    FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. user_profiles (E-049) — service_role_all + owner_only
-- user_id TEXT, RLS は user_id = auth.uid()::text
-- 既存の self_select / self_update / self_insert policy はそのまま残す.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_profiles_service_role_all ON user_profiles;
CREATE POLICY user_profiles_service_role_all ON user_profiles
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_profiles_owner_only ON user_profiles;
CREATE POLICY user_profiles_owner_only ON user_profiles
    FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. encrypted_secrets (E-050) — service_role_all のみ canonical 化
-- owner_id は polymorphic (user / workspace / account) のため authenticated 直接
-- アクセス policy は既存の owner_id = auth.uid()::text (encrypted_secrets_self)
-- を維持する. 本 migration は service_role_all canonical 名を追加するのみ.
-- secret_value (encrypted_value) は polymorphic owner check により非所有者には
-- 露出しない (AC-F5).
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE encrypted_secrets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS encrypted_secrets_service_role_all ON encrypted_secrets;
CREATE POLICY encrypted_secrets_service_role_all ON encrypted_secrets
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

-- owner_only policy: 既存 encrypted_secrets_self と論理的に同一だが
-- canonical 命名で再宣言 (entities.json drift 整合).
DROP POLICY IF EXISTS encrypted_secrets_owner_only ON encrypted_secrets;
CREATE POLICY encrypted_secrets_owner_only ON encrypted_secrets
    FOR ALL TO authenticated
    USING (owner_id = auth.uid()::text)
    WITH CHECK (owner_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. auth_sessions (E-051) — service_role_all + owner_only
-- user_id UUID, RLS は auth.uid() = user_id (UUID 比較)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS auth_sessions_service_role_all ON auth_sessions;
CREATE POLICY auth_sessions_service_role_all ON auth_sessions
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS auth_sessions_owner_only ON auth_sessions;
CREATE POLICY auth_sessions_owner_only ON auth_sessions
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. oauth_connections (E-052) — service_role_all + owner_only
-- user_id UUID, RLS は auth.uid() = user_id (UUID 比較)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE oauth_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS oauth_connections_service_role_all ON oauth_connections;
CREATE POLICY oauth_connections_service_role_all ON oauth_connections
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS oauth_connections_owner_only ON oauth_connections;
CREATE POLICY oauth_connections_owner_only ON oauth_connections
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. user_2fa_secrets (E-053) — service_role_all + owner_only
-- SECURITY CRITICAL: TOTP secret (BYTEA) を含む。 owner_only でのみ
-- authenticated アクセスを許可し、 cross-user access path を一切作らない。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE user_2fa_secrets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_2fa_secrets_service_role_all ON user_2fa_secrets;
CREATE POLICY user_2fa_secrets_service_role_all ON user_2fa_secrets
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_2fa_secrets_owner_only ON user_2fa_secrets;
CREATE POLICY user_2fa_secrets_owner_only ON user_2fa_secrets
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 8. user_2fa_recovery_codes (E-054) — service_role_all + owner_only
-- SECURITY CRITICAL: backup codes hash を含む。 owner_only でのみ
-- authenticated アクセスを許可。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE user_2fa_recovery_codes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_2fa_recovery_codes_service_role_all ON user_2fa_recovery_codes;
CREATE POLICY user_2fa_recovery_codes_service_role_all ON user_2fa_recovery_codes
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_2fa_recovery_codes_owner_only ON user_2fa_recovery_codes;
CREATE POLICY user_2fa_recovery_codes_owner_only ON user_2fa_recovery_codes
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 9. auth_audit_log (E-055) — service_role_all + account_member_select
-- user_id UUID (NULL 許容 = login_failure 時の anonymous attempt)
-- account_member_select: 本人の event のみ SELECT 可 (user_id IS NULL は
-- service_role でのみ可視; admin/SOC 用は service_role 経由とする).
-- INSERT/UPDATE/DELETE は service_role のみ (authenticated には開放しない).
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE auth_audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS auth_audit_log_service_role_all ON auth_audit_log;
CREATE POLICY auth_audit_log_service_role_all ON auth_audit_log
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

-- account_member_select: 本人 (auth.uid() = user_id) の event のみ SELECT 可.
-- 「他人 (account 外) の event」 → user_id != auth.uid() → 0 row return.
-- 名前は ticket `access_policies_required` の
-- `auth_audit_log_account_member_select` に合わせる.
DROP POLICY IF EXISTS auth_audit_log_account_member_select ON auth_audit_log;
CREATE POLICY auth_audit_log_account_member_select ON auth_audit_log
    FOR SELECT TO authenticated
    USING (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260516160000', 'T-V3-D-06: RLS policy 補完 batch 2 (auth & profile family: user_clone_optin / user_deletion_requests / user_profiles / encrypted_secrets / auth_sessions / oauth_connections / user_2fa_secrets / user_2fa_recovery_codes / auth_audit_log)', 'system')
ON CONFLICT (version) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT (運用者向け)
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON POLICY user_clone_optin_service_role_all ON user_clone_optin IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY user_clone_optin_owner_only ON user_clone_optin IS
    'T-V3-D-06: 本人のみ (user_id = auth.uid()::text) ALL operation 許可';
COMMENT ON POLICY user_deletion_requests_service_role_all ON user_deletion_requests IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY user_deletion_requests_owner_only ON user_deletion_requests IS
    'T-V3-D-06: 本人のみ (user_id = auth.uid()::text) ALL operation 許可';
COMMENT ON POLICY user_profiles_service_role_all ON user_profiles IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY user_profiles_owner_only ON user_profiles IS
    'T-V3-D-06: 本人のみ (user_id = auth.uid()::text) ALL operation 許可';
COMMENT ON POLICY encrypted_secrets_service_role_all ON encrypted_secrets IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY encrypted_secrets_owner_only ON encrypted_secrets IS
    'T-V3-D-06: polymorphic owner (owner_id = auth.uid()::text) ALL operation 許可; secret_value 非露出保証 (AC-F5)';
COMMENT ON POLICY auth_sessions_service_role_all ON auth_sessions IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY auth_sessions_owner_only ON auth_sessions IS
    'T-V3-D-06: 本人のみ (auth.uid() = user_id, UUID 比較) ALL operation 許可';
COMMENT ON POLICY oauth_connections_service_role_all ON oauth_connections IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY oauth_connections_owner_only ON oauth_connections IS
    'T-V3-D-06: 本人のみ (auth.uid() = user_id, UUID 比較) ALL operation 許可';
COMMENT ON POLICY user_2fa_secrets_service_role_all ON user_2fa_secrets IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY user_2fa_secrets_owner_only ON user_2fa_secrets IS
    'T-V3-D-06: SECURITY CRITICAL — TOTP secret は本人のみ access 可 (cross-user 一切禁止)';
COMMENT ON POLICY user_2fa_recovery_codes_service_role_all ON user_2fa_recovery_codes IS
    'T-V3-D-06: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY user_2fa_recovery_codes_owner_only ON user_2fa_recovery_codes IS
    'T-V3-D-06: SECURITY CRITICAL — recovery codes は本人のみ access 可';
COMMENT ON POLICY auth_audit_log_service_role_all ON auth_audit_log IS
    'T-V3-D-06: backend service_role による全 record access (audit 書き込み専用 path)';
COMMENT ON POLICY auth_audit_log_account_member_select ON auth_audit_log IS
    'T-V3-D-06: 本人 (auth.uid() = user_id) の event のみ SELECT 可; 他人の event は 0 row';
