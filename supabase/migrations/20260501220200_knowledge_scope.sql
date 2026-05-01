-- Knowledge base のスコープ拡張
-- ─────────────────────────────────────────────
-- 階層: account > workspace > member > ai_persona > shared
-- visibility:
--   private          : owner_user_id 本人のみ
--   member_shared    : workspace のメンバー全員
--   account_shared   : account 配下の全 workspace メンバー
--   ai_only          : 特定 AI persona の専用知識（人間からは検索しない）
--   public           : account を跨いで全員（テンプレート的な汎用知識）
-- ─────────────────────────────────────────────

ALTER TABLE knowledge_base
    ADD COLUMN IF NOT EXISTS owner_user_id TEXT,
    ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'account_shared',
    ADD COLUMN IF NOT EXISTS scope_path TEXT;
    -- scope_path 例:
    --   "accounts/1/shared/policies/working-style"
    --   "accounts/1/members/masato/private/journal/2026-05-01"
    --   "accounts/1/ai-personas/rin-reviewer/review-rules"
    --   "workspaces/1/shared/onboarding"

-- visibility の制約
ALTER TABLE knowledge_base
    DROP CONSTRAINT IF EXISTS chk_kb_visibility;
ALTER TABLE knowledge_base
    ADD CONSTRAINT chk_kb_visibility
    CHECK (visibility IN ('private', 'member_shared', 'account_shared', 'ai_only', 'public'));

CREATE INDEX IF NOT EXISTS ix_kb_visibility ON knowledge_base(visibility);
CREATE INDEX IF NOT EXISTS ix_kb_owner_user ON knowledge_base(owner_user_id);
CREATE INDEX IF NOT EXISTS ix_kb_scope_path ON knowledge_base(scope_path);

-- 同期用ビュー: AI persona から見える知識（ai_only + 自分の所属 account/workspace のもの）
CREATE OR REPLACE VIEW kb_for_ai AS
SELECT
    kb.id,
    kb.title,
    kb.content,
    kb.summary,
    kb.tags,
    kb.skill_tags,
    kb.embedding,
    kb.visibility,
    kb.scope_path,
    kb.account_id,
    kb.workspace_id,
    kb.assigned_employee_id,
    kb.owner_user_id,
    kb.confidence,
    kb.use_count,
    kb.created_at
FROM knowledge_base kb
WHERE kb.visibility != 'private';

COMMENT ON COLUMN knowledge_base.visibility IS 'private/member_shared/account_shared/ai_only/public';
COMMENT ON COLUMN knowledge_base.owner_user_id IS 'private 知識の所有者 (Supabase Auth user_id 連携想定)';
COMMENT ON COLUMN knowledge_base.scope_path IS 'Obsidian vault 内のディレクトリパス。スコープ判定の元情報';
