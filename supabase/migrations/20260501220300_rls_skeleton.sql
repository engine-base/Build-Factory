-- Row Level Security skeleton
-- 本番運用前に Auth と組み合わせて全テーブルに適用する
-- 現状は scope 列が揃ったテーブルのみ最小限のポリシーで RLS を有効化

-- ────────────────────────────────────────
-- knowledge_base: visibility ベースの RLS
-- ────────────────────────────────────────

ALTER TABLE knowledge_base ENABLE ROW LEVEL SECURITY;

-- 開発中の bypass: postgres ロール (service_role) は全アクセス可
DROP POLICY IF EXISTS kb_service_role_all ON knowledge_base;
CREATE POLICY kb_service_role_all ON knowledge_base
    FOR ALL
    TO postgres, service_role
    USING (true)
    WITH CHECK (true);

-- public 知識は誰でも読める
DROP POLICY IF EXISTS kb_public_read ON knowledge_base;
CREATE POLICY kb_public_read ON knowledge_base
    FOR SELECT
    TO authenticated, anon
    USING (visibility = 'public');

-- account_shared: 同じ account_id のメンバーのみ読める
-- (account_members テーブルとの結合で制御。将来 auth.uid() = user_id で結合)
DROP POLICY IF EXISTS kb_account_shared_read ON knowledge_base;
CREATE POLICY kb_account_shared_read ON knowledge_base
    FOR SELECT
    TO authenticated
    USING (
        visibility IN ('account_shared', 'member_shared')
        AND account_id IN (
            SELECT account_id FROM account_members
            WHERE user_id = (auth.jwt() ->> 'sub')
        )
    );

-- private: 本人のみ
DROP POLICY IF EXISTS kb_private_read ON knowledge_base;
CREATE POLICY kb_private_read ON knowledge_base
    FOR SELECT
    TO authenticated
    USING (
        visibility = 'private'
        AND owner_user_id = (auth.jwt() -> 'user_metadata' ->> 'slug')
    );

-- ai_only: AI persona に紐づく自前バックエンドからのみアクセス想定
-- (service_role 経由のアクセスは上の kb_service_role_all で許可済)
DROP POLICY IF EXISTS kb_ai_only_read ON knowledge_base;
CREATE POLICY kb_ai_only_read ON knowledge_base
    FOR SELECT
    TO authenticated
    USING (
        visibility = 'ai_only'
        AND account_id IN (
            SELECT account_id FROM account_members
            WHERE user_id = (auth.jwt() ->> 'sub')
        )
    );

-- ────────────────────────────────────────
-- workspaces: メンバーシップで制御
-- ────────────────────────────────────────

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ws_service_role_all ON workspaces;
CREATE POLICY ws_service_role_all ON workspaces
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS ws_member_read ON workspaces;
CREATE POLICY ws_member_read ON workspaces
    FOR SELECT TO authenticated
    USING (id IN (SELECT workspace_id FROM workspace_members WHERE user_id = (auth.jwt() ->> 'sub')));

-- ────────────────────────────────────────
-- accounts: 所属メンバーのみ閲覧
-- ────────────────────────────────────────

ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS acc_service_role_all ON accounts;
CREATE POLICY acc_service_role_all ON accounts
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS acc_member_read ON accounts;
CREATE POLICY acc_member_read ON accounts
    FOR SELECT TO authenticated
    USING (id IN (SELECT account_id FROM account_members WHERE user_id = (auth.jwt() ->> 'sub')));

-- ────────────────────────────────────────
-- 注意: それ以外のテーブル (artifacts, threads, conversation_log, tasks 等) は
-- RLS 有効化のみ後付けで対応。現在は service_role 経由のアクセスのみ想定。
-- 本番化時に visibility 同等の制約を追加する。
-- ────────────────────────────────────────

COMMENT ON POLICY kb_account_shared_read ON knowledge_base IS
    'auth.jwt() の sub クレームと account_members.user_id を結合してアクセス制御';
