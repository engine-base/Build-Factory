-- =============================================================================
-- T-001-07: 拡張機能 (pgvector/pg_trgm/pgsodium/pg_cron) + 追加 index
-- =============================================================================
-- 既存 (20260501220100_pgvector.sql) で導入済:
--   CREATE EXTENSION vector  -- pgvector (embedding)
--   CREATE EXTENSION pg_trgm  -- 全文検索 trigram
--
-- 本 migration で追加:
--   pgsodium   -- column-level 暗号化 (api keys / oauth tokens 用)
--   pg_cron    -- 定期実行 (audit_logs partition / backup retention)
--
-- + 100+ index 達成のため、 既存 127 index に加えて
--   実装・連携・運用 17 テーブル (20260512000000) 用の補助 index を追加:
--   - GIN (notification.detail / api_keys.metadata JSONB)
--   - BRIN (audit_logs / cost_logs / session_logs 時系列大量データ用)
--   - partial (is_active / is_enabled flags)
--
-- AC マッピング:
--   AC-1 UBIQUITOUS: 4 extension + 補助 index
--   AC-3 STATE:     既存 migration 順序を破壊しない (IF NOT EXISTS)
--   AC-4 UNWANTED:  invalid extension 名 / index 未使用 などはなし
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. 拡張機能 (pgsodium / pg_cron)
-- ─────────────────────────────────────────────────────────────────────────────

-- pgsodium: column-level 暗号化 (T-023-03 encrypted_secrets は app-side Fernet
-- を Phase 1 で使うが、 pgsodium に切り替えやすいよう拡張を有効化).
-- Supabase Cloud では schema 'pgsodium' を提供.
CREATE EXTENSION IF NOT EXISTS pgsodium;

-- pg_cron: 定期実行 (audit_logs partition 作成 / backup retention 等).
-- Supabase Cloud は cron schema を提供.
CREATE EXTENSION IF NOT EXISTS pg_cron;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. GIN index — JSONB / 配列 列の検索高速化
-- ─────────────────────────────────────────────────────────────────────────────

-- notifications.detail (workspace 内 event 検索)
CREATE INDEX IF NOT EXISTS ix_notifications_detail_gin
    ON notifications USING gin (detail jsonb_path_ops);

-- api_keys 関連: encrypted_secrets を介すため metadata JSONB なし → skip

-- bf_constitutions.principles (section_X_* キー検索)
CREATE INDEX IF NOT EXISTS ix_bf_constitutions_principles_gin
    ON bf_constitutions USING gin (principles jsonb_path_ops);

-- audit_logs.payload (event detail 検索)
CREATE INDEX IF NOT EXISTS ix_audit_logs_payload_gin
    ON audit_logs USING gin (payload jsonb_path_ops);

-- cost_logs.metadata (ai_employee_id 検索等)
CREATE INDEX IF NOT EXISTS ix_cost_logs_metadata_gin
    ON cost_logs USING gin (metadata jsonb_path_ops);

-- sessions.metadata
CREATE INDEX IF NOT EXISTS ix_sessions_metadata_gin
    ON sessions USING gin (metadata jsonb_path_ops);

-- user_settings: 配列 column の検索
CREATE INDEX IF NOT EXISTS ix_user_settings_pinned_workspaces_gin
    ON user_settings USING gin (pinned_workspaces);

-- workspace_settings.feature_flags / redline_overrides
CREATE INDEX IF NOT EXISTS ix_workspace_settings_flags_gin
    ON workspace_settings USING gin (feature_flags jsonb_path_ops);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. BRIN index — 時系列大量データ (audit_logs / cost_logs / session_logs)
-- ─────────────────────────────────────────────────────────────────────────────

-- audit_logs: 月次パーティション + BRIN で過去 event の範囲検索を高速化
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at_brin
    ON audit_logs USING brin (created_at);

-- cost_logs: occurred_at で日次集計
CREATE INDEX IF NOT EXISTS ix_cost_logs_occurred_at_brin
    ON cost_logs USING brin (occurred_at);

-- session_logs: line_no 単位 INSERT が大量、 created_at は時系列
CREATE INDEX IF NOT EXISTS ix_session_logs_created_at_brin
    ON session_logs USING brin (created_at);

-- red_line_violations: 時系列大量 INSERT 想定
CREATE INDEX IF NOT EXISTS ix_red_line_violations_created_at_brin
    ON red_line_violations USING brin (created_at);

-- notifications: created_at で feed 表示
CREATE INDEX IF NOT EXISTS ix_notifications_created_at_brin
    ON notifications USING brin (created_at);


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. partial index — flag 列ベースの fast lookup
-- ─────────────────────────────────────────────────────────────────────────────

-- 未読通知のみ
CREATE INDEX IF NOT EXISTS ix_notifications_unread_only
    ON notifications(recipient_user_id, priority)
    WHERE is_read = FALSE;

-- 有効な API キーのみ
CREATE INDEX IF NOT EXISTS ix_api_keys_active_only
    ON api_keys(workspace_id, provider_key)
    WHERE is_active = TRUE;

-- enforce 中の token_limits のみ
CREATE INDEX IF NOT EXISTS ix_token_limits_enforced_only
    ON token_limits(workspace_id)
    WHERE is_enforced = TRUE;

-- 現在の (is_current) bf_constitutions
CREATE INDEX IF NOT EXISTS ix_bf_constitutions_workspace_current
    ON bf_constitutions(project_id, version DESC)
    WHERE is_current = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. composite index — RLS でよく使われる workspace_id + status 系
-- ─────────────────────────────────────────────────────────────────────────────

-- prs: workspace × status × open のみのリスト
CREATE INDEX IF NOT EXISTS ix_prs_workspace_status_open
    ON prs(workspace_id, created_at DESC)
    WHERE status = 'open';

-- prs: workspace × draft
CREATE INDEX IF NOT EXISTS ix_prs_workspace_status_draft
    ON prs(workspace_id, created_at DESC)
    WHERE status = 'draft';

-- sessions: workspace 内の running セッション
-- (既存 ix_sessions_active は 003 migration にあり、 重複しない名前で作成)
CREATE INDEX IF NOT EXISTS ix_sessions_workspace_running_v2
    ON sessions(workspace_id, started_at DESC)
    WHERE status = 'running';

-- templates: active テンプレート lookup
CREATE INDEX IF NOT EXISTS ix_templates_workspace_kind_active
    ON templates(workspace_id, template_kind, name)
    WHERE is_active = TRUE;


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260512100000', 'T-001-07: extensions (pgsodium/pg_cron) + 100+ index', 'system')
ON CONFLICT (version) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. pg_cron schedule (Supabase Cloud で実行) — Phase 1 では comment-only
-- ─────────────────────────────────────────────────────────────────────────────
-- pg_cron が利用可能な環境では以下の jobs を登録する想定:
--
-- SELECT cron.schedule('audit_logs_partition_monthly', '0 0 1 * *',
--   'SELECT bf_create_audit_partition_next_month()');
--
-- SELECT cron.schedule('backup_retention_cleanup_daily', '0 3 * * *',
--   'DELETE FROM backups WHERE started_at < NOW() - (retention_days || '' days'')::interval AND status = ''completed''');
--
-- SELECT cron.schedule('notifications_old_cleanup_weekly', '0 4 * * 0',
--   'DELETE FROM notifications WHERE is_read = TRUE AND read_at < NOW() - INTERVAL ''90 days''');
--
-- 本 migration では schedule 関数は登録しない (環境依存 / pg_cron 不在環境で
-- migration が壊れないようにするため). 実環境では Supabase dashboard か
-- 別 migration で個別登録する.

COMMENT ON EXTENSION pgsodium IS 'T-001-07: column-level encryption for sensitive data (Phase 2 切替予定)';
COMMENT ON EXTENSION pg_cron IS 'T-001-07: scheduled jobs (audit partition / backup retention)';
