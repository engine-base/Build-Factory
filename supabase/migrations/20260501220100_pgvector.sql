-- =============================================================================
-- Build-Factory: pgvector + 全文検索拡張
-- =============================================================================
-- 対応: knowledge_base への semantic / lexical 検索インフラ追加
--
-- 前提:
--   - 20260501220000_initial_schema.sql が先に流れていること
--   - knowledge_base テーブル / content カラム / md_path カラムが存在すること
--   - Supabase ローカルでは vector / pg_trgm 拡張が利用可能
--
-- 注: 既存の embedding カラム (SQLite では BLOB) は initial_schema では
--     用意していない。ここで vector(1536) として ADD する。
--     既存データは pgvector マイグレーション時に再生成 (TODO)。
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- knowledge_base に embedding / Obsidian 同期用カラムを追加
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS embedding   vector(1536);
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS source_path TEXT;  -- Obsidian vault 内の相対パス
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS file_hash   TEXT;  -- 同期差分検出用

-- ベクトル類似度検索 (cosine)
CREATE INDEX IF NOT EXISTS ix_knowledge_embedding
    ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Obsidian path 検索
CREATE INDEX IF NOT EXISTS ix_knowledge_source_path
    ON knowledge_base(source_path);

-- 部分一致 (trigram) 全文検索
CREATE INDEX IF NOT EXISTS ix_knowledge_content_trgm
    ON knowledge_base
    USING gin (content gin_trgm_ops);

-- conversation_log にも embedding を追加 (legacy SQLite では BLOB として存在)
ALTER TABLE conversation_log ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS ix_conversation_log_embedding
    ON conversation_log
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
