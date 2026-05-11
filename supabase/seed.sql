-- T-001-10: Build-Factory seed.sql
--
-- 開発・テスト環境向けの idempotent seed.
-- 本番では絶対に実行しない (BF_ENV ガード経由で呼び出し時に弾く).
--
-- 含まれるもの:
--   1. demo account (個人 ENGINE BASE)
--   2. demo workspace + project (Phase 1 dogfood 用)
--   3. demo user_profile (松本)
--   4. 既存 BMAD 10 ペルソナ seed (20260512400000_bmad_personas_seed.sql) との互換確認
--
-- 実行方法:
--   psql ... -f supabase/seed.sql
--   または backend/services/bf_env_guard.py 経由で run_seed() を呼ぶ.
--
-- BF_ENV={dev|test|local} でのみ実行可. prod は backend/services/bf_env_guard で deny.

BEGIN;

-- ──────────────────────────────────────────────────────────────────────
-- 1. demo account (ENGINE BASE 自社)
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO accounts (id, name, owner_user_id, plan, created_at)
VALUES (
    1,
    'ENGINE BASE (自社)',
    'masato',
    'pro',
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    owner_user_id = EXCLUDED.owner_user_id;

-- ──────────────────────────────────────────────────────────────────────
-- 2. demo workspace (Build-Factory 本体)
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO workspaces (id, account_id, name, slug, owner_user_id, status, created_at)
VALUES (
    1,
    1,
    'Build-Factory (dogfood)',
    'build-factory',
    'masato',
    'active',
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    slug = EXCLUDED.slug;

-- ──────────────────────────────────────────────────────────────────────
-- 3. demo project (Phase 1 = 内製 dogfood)
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO bf_projects (id, workspace_id, name, slug, status, phase_no, created_at)
VALUES (
    1,
    1,
    'Phase 1 — 内製 dogfood',
    'phase1-dogfood',
    'in_progress',
    1,
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status;

-- ──────────────────────────────────────────────────────────────────────
-- 4. demo bf_user_profile (松本本人)
-- ──────────────────────────────────────────────────────────────────────
INSERT INTO bf_user_profiles (user_id, display_name, role, clone_opt_in, created_at)
VALUES (
    'masato',
    '高本まさと',
    'owner',
    FALSE,
    NOW()
)
ON CONFLICT (user_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    role = EXCLUDED.role;

COMMIT;

-- 既存 BMAD 10 ペルソナは 20260512400000_bmad_personas_seed.sql で seed 済み.
-- このファイルは "工場側のセルフ dogfood に必要な最小単位" を埋めるだけに留める.
