-- T-012-01: red_lines 5 主要 category seed (idempotent / existing schema 活用)
--
-- 既存テーブル red_lines は supabase/migrations/20260512000000_impl_integration_ops_tables.sql
-- で定義済み (rule_key + pattern + severity + is_enabled + UNIQUE(workspace_id, rule_key)).
-- 本 migration は **テーブル定義は再宣言せず**, 5 default categories の seed のみ追加する.
--
-- backend/services/red_line_detector.py の DEFAULT_CATEGORIES (5 カテゴリ) と 1:1 対応:
--   api_key_leak / db_destructive / force_push / infinite_loop / deploy_decision
--
-- AC マッピング:
--   AC-1 UBIQUITOUS    : 5 default categories の global seed (workspace_id=NULL)
--   AC-2 EVENT-DRIVEN  : audit_logs trigger は既存 (T-018-01 audit_logs framework)
--   AC-3 STATE-DRIVEN  : RLS は既存 (20260510000002_rls_full_enforcement.sql)
--   AC-4 UNWANTED      : severity CHECK は既存 + UNIQUE(workspace_id, rule_key) で重複弾く

-- ──────────────────────────────────────────────────────────────────
-- 5 default categories seed (workspace_id=NULL = グローバル)
-- 冪等: ON CONFLICT (workspace_id, rule_key) DO NOTHING で再実行安全
-- ──────────────────────────────────────────────────────────────────

INSERT INTO red_lines (workspace_id, constitution_id, rule_key, pattern, severity, description, is_enabled)
VALUES
    (NULL, NULL, 'api_key_leak',
        'sk-ant-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,}|sb_(publishable|secret)_[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9_-]{20,}',
        'block',
        'API key / Supabase key / GitHub PAT 等の literal がコード中に出現 (CLAUDE.md §5.4)',
        TRUE),
    (NULL, NULL, 'db_destructive',
        '\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b|DELETE\s+FROM\s+\w+\s*;',
        'block',
        '本番 DB に対する DROP / TRUNCATE / DELETE *; (CLAUDE.md §5.4)',
        TRUE),
    (NULL, NULL, 'force_push',
        'git\s+push\s+(--force|-f|--no-verify)',
        'warn',
        'force push / no-verify (公開後は明示承認時のみ — CLAUDE.md §5.4)',
        TRUE),
    (NULL, NULL, 'infinite_loop',
        '\bwhile\s+True\s*:|for\s*\(\s*;\s*;\s*\)',
        'warn',
        '無限ループ (while True / for(;;)) の混入',
        TRUE),
    (NULL, NULL, 'deploy_decision',
        '\b(deploy|release)\s+(prod|production)\b',
        'warn',
        '本番 deploy / release の判断 (人間承認必須)',
        TRUE)
ON CONFLICT (workspace_id, rule_key) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────
-- 確認: rule_key 5 件が一致して存在する (post-seed invariant)
-- ──────────────────────────────────────────────────────────────────

DO $$
DECLARE
    expected_count INT := 5;
    actual_count INT;
BEGIN
    SELECT COUNT(*) INTO actual_count
    FROM red_lines
    WHERE workspace_id IS NULL
      AND rule_key IN ('api_key_leak', 'db_destructive', 'force_push', 'infinite_loop', 'deploy_decision');
    IF actual_count < expected_count THEN
        RAISE EXCEPTION
            'T-012-01 seed invariant violated: expected % global default categories, got %',
            expected_count, actual_count;
    END IF;
END
$$;
