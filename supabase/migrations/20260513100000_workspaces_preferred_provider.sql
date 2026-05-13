-- T-024-04: workspaces.preferred_provider column 追加 (ADR-012 Decision 5).
--
-- 仕様:
--   AC-1 UBIQUITOUS    : enum(anthropic / openai / gemini / auto), default 'auto',
--                        NOT NULL. idempotent (二重実行可) + 既存 row backfill.
--   AC-2 EVENT-DRIVEN  : <= 100,000 行で 2 秒以内 (PostgreSQL ALTER は一瞬で完了).
--   AC-3 STATE-DRIVEN  : RLS 不変 (workspaces の既存 RLS policy は preferred_provider
--                        を新規 column として継承して読める).
--   AC-4 UNWANTED      : 二重実行で error にならない (IF NOT EXISTS guard) /
--                        enum 外値は CHECK constraint + application 層で reject.
--
-- 関連:
--   alembic: backend/alembic/versions/h5c6d7e8f9a1_workspaces_preferred_provider.py
--   ADR:     docs/decisions/ADR-012-anthropic-memory-tool-adoption.md
--   ticket:  docs/task-decomposition/2026-05-09_v1/tickets.json T-024-04
--   precedence: per-request header > per-session active_route >
--               per-workspace preferred_provider > BYOK > ADR-010 既定 >
--               T-AI-08 circuit-breaker fallback

-- AC-1 + AC-4: enum 型を idempotent に作成
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'preferred_provider_enum') THEN
        CREATE TYPE preferred_provider_enum AS ENUM ('anthropic', 'openai', 'gemini', 'auto');
    END IF;
END$$;

-- AC-1 + AC-4: column を idempotent に追加 (既に存在しなければのみ)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'workspaces'
          AND column_name = 'preferred_provider'
    ) THEN
        -- DEFAULT 'auto' で既存 row backfill 同時実施
        ALTER TABLE workspaces
            ADD COLUMN preferred_provider preferred_provider_enum
            NOT NULL DEFAULT 'auto';
    END IF;
END$$;

-- AC-2 audit: schema migration の事実を audit_logs に記録 (idempotent guard 付き).
-- 既に同 migration_id が記録済みなら skip.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM audit_logs
        WHERE event_type = 'schema.migration_applied'
          AND detail->>'migration_id' = '20260513100000_workspaces_preferred_provider'
    ) THEN
        INSERT INTO audit_logs (event_type, user_id, detail, created_at)
        VALUES (
            'schema.migration_applied',
            'system',
            jsonb_build_object(
                'migration_id', '20260513100000_workspaces_preferred_provider',
                'ticket', 'T-024-04',
                'adr', 'ADR-012',
                'table', 'workspaces',
                'column', 'preferred_provider',
                'enum_values', ARRAY['anthropic', 'openai', 'gemini', 'auto'],
                'default_value', 'auto'
            ),
            now()
        );
    END IF;
EXCEPTION
    WHEN undefined_table THEN
        -- audit_logs が未作成な環境では skip (Phase 1 SQLite 開発時等)
        NULL;
END$$;

-- AC-3 RLS: workspaces の既存 RLS policy は SELECT 列に preferred_provider を
-- 暗黙含む (policy は WHERE のみ評価). 追加の policy 変更は不要.
-- 既存 SELECT policy が SELECT * 互換であることを期待.

-- Note: index は付与しない. preferred_provider は workspace 単位の参照のみで
-- 高頻度の検索 key にならないため.
