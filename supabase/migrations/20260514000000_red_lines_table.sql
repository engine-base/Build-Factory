-- T-012-01: red_lines DDL + 5 主要 category seed (idempotent)
--
-- F-012 (赤線リスト + 自動停止) の根幹テーブル.
-- backend/services/red_line_detector.py の DEFAULT_CATEGORIES (5 カテゴリ) と 1:1 対応.
--
-- AC マッピング:
--   AC-1 UBIQUITOUS    : red_lines テーブル CREATE + 5 default categories seed
--   AC-2 EVENT-DRIVEN  : INSERT/UPDATE/DELETE で audit_logs に記録 (trigger は別ファイル)
--   AC-3 STATE-DRIVEN  : RLS enable + workspace_members 経由 access control
--   AC-4 UNWANTED      : invalid category (NOT IN allow-list) を CHECK で拒否
--
-- 仕様:
--   - workspace_id NULL = グローバル red_line (全 workspace 適用)
--   - workspace_id 値 = workspace 専用 red_line (override)
--   - severity: 'block' / 'warn' / 'log' (red_line_detector.py 仕様準拠)
--   - is_active: false で論理削除 (履歴保持)
--   - 冪等: CREATE/POLICY/INDEX 全て IF NOT EXISTS / DROP IF EXISTS

-- ──────────────────────────────────────────────────────────────────
-- TABLE
-- ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS red_lines (
    id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT REFERENCES workspaces(id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL,
    pattern TEXT NOT NULL,
    severity VARCHAR(8) NOT NULL DEFAULT 'block',
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- T-012-01 AC-4 UNWANTED: invalid category を弾く
    CONSTRAINT red_lines_category_allowed CHECK (
        category IN (
            'api_key_leak',
            'db_destructive',
            'force_push',
            'infinite_loop',
            'deploy_decision'
        )
    ),
    -- severity も enum 化 (red_line_detector.py 3 種準拠)
    CONSTRAINT red_lines_severity_allowed CHECK (
        severity IN ('block', 'warn', 'log')
    )
);

-- 検索用 index
CREATE INDEX IF NOT EXISTS idx_red_lines_workspace_category
    ON red_lines (workspace_id, category, is_active);
CREATE INDEX IF NOT EXISTS idx_red_lines_active
    ON red_lines (is_active) WHERE is_active = TRUE;

-- ──────────────────────────────────────────────────────────────────
-- 5 主要 category seed (workspace_id=NULL = グローバル)
-- backend/services/red_line_detector.py:50-62 の DEFAULT_CATEGORIES と 1:1
-- ──────────────────────────────────────────────────────────────────

-- 既存 seed があれば skip (冪等)
INSERT INTO red_lines (workspace_id, category, pattern, severity, description)
SELECT NULL, 'api_key_leak',
    'sk-ant-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|sb_(publishable|secret)_[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_-]{20,}',
    'block',
    'API key / Supabase key / GitHub PAT 等の literal がコード中に出現'
WHERE NOT EXISTS (SELECT 1 FROM red_lines WHERE category='api_key_leak' AND workspace_id IS NULL);

INSERT INTO red_lines (workspace_id, category, pattern, severity, description)
SELECT NULL, 'db_destructive',
    '\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b|DELETE\s+FROM\s+\w+\s*;',
    'block',
    '本番 DB に対する DROP / TRUNCATE / DELETE *; (CLAUDE.md §5.4)'
WHERE NOT EXISTS (SELECT 1 FROM red_lines WHERE category='db_destructive' AND workspace_id IS NULL);

INSERT INTO red_lines (workspace_id, category, pattern, severity, description)
SELECT NULL, 'force_push',
    'git\s+push\s+(--force|-f|--no-verify)',
    'warn',
    'force push / no-verify (公開後は明示承認時のみ)'
WHERE NOT EXISTS (SELECT 1 FROM red_lines WHERE category='force_push' AND workspace_id IS NULL);

INSERT INTO red_lines (workspace_id, category, pattern, severity, description)
SELECT NULL, 'infinite_loop',
    '\bwhile\s+True\s*:|for\s*\(\s*;\s*;\s*\)',
    'warn',
    '無限ループ (while True / for(;;)) の混入'
WHERE NOT EXISTS (SELECT 1 FROM red_lines WHERE category='infinite_loop' AND workspace_id IS NULL);

INSERT INTO red_lines (workspace_id, category, pattern, severity, description)
SELECT NULL, 'deploy_decision',
    '\b(deploy|release)\s+(prod|production)\b',
    'warn',
    '本番 deploy / release の判断 (人間承認必須)'
WHERE NOT EXISTS (SELECT 1 FROM red_lines WHERE category='deploy_decision' AND workspace_id IS NULL);

-- ──────────────────────────────────────────────────────────────────
-- RLS (T-012-01 AC-3 STATE-DRIVEN)
-- ──────────────────────────────────────────────────────────────────

ALTER TABLE red_lines ENABLE ROW LEVEL SECURITY;

-- read: グローバル (workspace_id NULL) は全員 read 可 / workspace 専用は member のみ
DROP POLICY IF EXISTS red_lines_read ON red_lines;
CREATE POLICY red_lines_read ON red_lines
    FOR SELECT
    TO authenticated
    USING (
        workspace_id IS NULL
        OR EXISTS (
            SELECT 1 FROM workspace_members wm
            WHERE wm.workspace_id = red_lines.workspace_id
              AND wm.user_id = auth.uid()
        )
    );

-- write: workspace owner / admin / service_role のみ (グローバル は service_role のみ)
DROP POLICY IF EXISTS red_lines_write ON red_lines;
CREATE POLICY red_lines_write ON red_lines
    FOR ALL
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM workspace_members wm
            WHERE wm.workspace_id = red_lines.workspace_id
              AND wm.user_id = auth.uid()
              AND wm.role IN ('owner', 'admin')
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM workspace_members wm
            WHERE wm.workspace_id = red_lines.workspace_id
              AND wm.user_id = auth.uid()
              AND wm.role IN ('owner', 'admin')
        )
    );

-- service_role 全件 access (admin / migration / グローバル seed 用)
DROP POLICY IF EXISTS red_lines_service_role ON red_lines;
CREATE POLICY red_lines_service_role ON red_lines
    FOR ALL
    TO service_role
    USING (TRUE)
    WITH CHECK (TRUE);

-- ──────────────────────────────────────────────────────────────────
-- updated_at trigger
-- ──────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION trg_red_lines_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS red_lines_updated_at ON red_lines;
CREATE TRIGGER red_lines_updated_at
    BEFORE UPDATE ON red_lines
    FOR EACH ROW
    EXECUTE FUNCTION trg_red_lines_set_updated_at();
