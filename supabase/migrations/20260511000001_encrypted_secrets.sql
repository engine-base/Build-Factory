-- T-023-03 / credentials DB 化: encrypted_secrets テーブル + RLS
--
-- 既存の credentials_store.py (Fernet ファイルベース) を DB ベースに移行するための
-- テーブル定義。 backend は encrypted_store.py の `_backend()` 判定で
-- DATABASE_URL が postgres スキームなら本テーブルを使う。
--
-- 暗号化方式 (encrypted_value):
--   Phase 1: backend (Fernet) で暗号化済み bytes を base64 文字列として保存
--   Phase 2: pgsodium.crypto_aead_det_encrypt を column 暗号化として使用
--
-- RLS:
--   - service_role: 全件 R/W (backend からのアクセス)
--   - authenticated: owner_id = auth.uid()::text のみ R/W

CREATE TABLE IF NOT EXISTS encrypted_secrets (
    id              BIGSERIAL PRIMARY KEY,
    scope           TEXT NOT NULL,
    key             TEXT NOT NULL,
    owner_id        TEXT,
    encrypted_value TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (scope, key, owner_id)
);

CREATE INDEX IF NOT EXISTS idx_encrypted_secrets_scope_key
    ON encrypted_secrets(scope, key);
CREATE INDEX IF NOT EXISTS idx_encrypted_secrets_owner
    ON encrypted_secrets(owner_id);

ALTER TABLE encrypted_secrets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS encrypted_secrets_service_role ON encrypted_secrets;
CREATE POLICY encrypted_secrets_service_role ON encrypted_secrets
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS encrypted_secrets_self ON encrypted_secrets;
CREATE POLICY encrypted_secrets_self ON encrypted_secrets
    FOR ALL TO authenticated
    USING (owner_id = auth.uid()::text)
    WITH CHECK (owner_id = auth.uid()::text);
