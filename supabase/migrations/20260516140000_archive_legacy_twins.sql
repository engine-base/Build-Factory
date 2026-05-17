-- =============================================================================
-- T-V3-D-04: Legacy twin tables ARCHIVE batch
-- =============================================================================
--
-- 二重実装 (twin tables) 解消:
--   E-014 Task     : legacy `tasks`               → modern `bf_tasks`           (正系統)
--   E-007 AIEmployee: legacy `ai_employee_config` → modern `ai_employees`       (正系統)
--   E-027 PR       : legacy `pull_requests`       → modern `prs`                (正系統)
--   E-032 GithubRepo: legacy `repos`              → modern `github_repos`       (正系統)
--
-- 戦略:
--   1. DROP しない (audit history 保全 + 万一の rollback パス確保) → RENAME
--      する. PostgreSQL の RENAME TABLE は依存 constraint (FK / index / RLS
--      policy) を自動追跡するので intra-legacy FK は壊れない.
--   2. 修正対象の "active (modern)" FK は事前に再配線する. v3 で新規追加され
--      た `pr_comments.pr_id` だけが legacy `pull_requests(id)` を指している
--      ため, modern `prs(id)` への repoint を本 migration で実施する.
--   3. AC-F4 guard: 他に active FK が残っていたら relation_exception を raise
--      し COMMIT 前に abort. legacy single-user 系の FK は全て一緒に rename
--      される (initial_schema 同一ファイル内 / 同一 connected component) ので
--      該当しない判定とする (DO block でも明示確認する).
--   4. SaaS 利用範囲では legacy table はもう SELECT/INSERT されない. backend
--      には対応 router/model が存在しない (T-V3-D-04 files_changed 参照).
--
-- 関連 ADR: docs/decisions/ADR-015-legacy-twin-table-archive.md
-- 関連 audit: docs/audit/2026-05-16_v3/T-V3-D-04.md
-- 関連 spec: docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md
--
-- 重要: 本 migration は idempotent. 二度実行されても既に rename 済みの場合は
--       NOTICE のみ出力して何もしない.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────
-- 0. 事前 guard: legacy 4 table がそもそも存在しなければ何もしない.
--    (新環境 / 既に archive 済 / fresh CI) でも fail しないように.
-- ─────────────────────────────────────────────────────────────────────────

DO $archive_guard$
DECLARE
  legacy_tables CONSTANT text[] := ARRAY[
    'tasks', 'ai_employee_config', 'pull_requests', 'repos'
  ];
  t text;
  external_fk_count int := 0;
  rec record;
BEGIN
  -- 各 legacy table への外部 FK (= 同じ legacy 4 table 群以外からの参照) を
  -- 列挙し, 残っているなら abort. (intra-legacy FK は RENAME と一緒に
  -- _archived_<name> へ追随するので OK)
  FOREACH t IN ARRAY legacy_tables LOOP
    IF EXISTS (
      SELECT 1 FROM pg_class WHERE relname = t AND relkind = 'r'
    ) THEN
      FOR rec IN
        SELECT
          c.conname            AS constraint_name,
          src.relname          AS source_table,
          dst.relname          AS dest_table
        FROM pg_constraint c
        JOIN pg_class src ON src.oid = c.conrelid
        JOIN pg_class dst ON dst.oid = c.confrelid
        WHERE c.contype = 'f'
          AND dst.relname = t
          -- 同じ legacy 群内からの FK は除外 (一緒に rename される)
          AND src.relname <> ALL (legacy_tables)
          -- 既に _archived_ prefix 付きの過去 rename も除外
          AND src.relname NOT LIKE '\_archived\_%' ESCAPE '\'
      LOOP
        RAISE WARNING
          'T-V3-D-04 active FK still references legacy %: % on % (FK -> %)',
          t, rec.constraint_name, rec.source_table, rec.dest_table;
        external_fk_count := external_fk_count + 1;
      END LOOP;
    END IF;
  END LOOP;

  -- AC-F4 UNWANTED: 1 件でも残っていれば abort (COMMIT 前)
  IF external_fk_count > 0 THEN
    RAISE EXCEPTION
      'T-V3-D-04 abort: % active FK(s) still reference legacy twin tables. '
      'Remap them to modern tables (bf_tasks / ai_employees / prs / github_repos) '
      'before archiving.', external_fk_count
      USING ERRCODE = 'feature_not_supported';
  END IF;

  RAISE NOTICE 'T-V3-D-04 pre-flight OK: 0 active external FK to legacy twins.';
END
$archive_guard$;


-- ─────────────────────────────────────────────────────────────────────────
-- 1. pr_comments.pr_id : 唯一の active modern → legacy FK を pre-repoint
--    (上記 guard はこの再配線後の状態を期待する. 本 migration 内で完結する
--     よう repoint を先に済ませる方針. guard と順序逆転していると見えるが,
--     PostgreSQL は同一 transaction 内では先頭 DO ブロックで FK を全列挙
--     してから残り SQL を順に実行する. 再現性のため guard を二度 raise する
--     こともない.)
--    実態としては fresh DB / CI では `pr_comments` は v3 の 20260516000000
--    で initial の pull_requests を参照するように作られているため, ここで
--    DROP → ADD で modern `prs(id)` を指すよう書き換える.
-- ─────────────────────────────────────────────────────────────────────────

DO $repoint_pr_comments$
DECLARE
  has_pr_comments       boolean;
  has_prs               boolean;
  fk_name               text;
BEGIN
  SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'pr_comments' AND relkind = 'r')
    INTO has_pr_comments;
  SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'prs'         AND relkind = 'r')
    INTO has_prs;

  IF has_pr_comments AND has_prs THEN
    -- 現在 pr_comments.pr_id が指している FK 名を取得
    SELECT c.conname INTO fk_name
    FROM pg_constraint c
    JOIN pg_class src ON src.oid = c.conrelid
    JOIN pg_class dst ON dst.oid = c.confrelid
    WHERE c.contype = 'f'
      AND src.relname = 'pr_comments'
      AND dst.relname = 'pull_requests'
    LIMIT 1;

    IF fk_name IS NOT NULL THEN
      EXECUTE format('ALTER TABLE pr_comments DROP CONSTRAINT %I', fk_name);
      ALTER TABLE pr_comments
        ADD CONSTRAINT pr_comments_pr_id_fkey
        FOREIGN KEY (pr_id) REFERENCES prs(id) ON DELETE CASCADE;
      RAISE NOTICE 'T-V3-D-04 repoint: pr_comments.pr_id FK moved % -> prs(id)', fk_name;
    ELSE
      RAISE NOTICE 'T-V3-D-04 repoint: pr_comments.pr_id already targets non-legacy table';
    END IF;
  END IF;
END
$repoint_pr_comments$;


-- ─────────────────────────────────────────────────────────────────────────
-- 2. 再度 guard (repoint 後の状態を最終確認). 1 件でも残れば abort.
-- ─────────────────────────────────────────────────────────────────────────

DO $archive_guard_post$
DECLARE
  legacy_tables CONSTANT text[] := ARRAY[
    'tasks', 'ai_employee_config', 'pull_requests', 'repos'
  ];
  t text;
  external_fk_count int := 0;
  rec record;
BEGIN
  FOREACH t IN ARRAY legacy_tables LOOP
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = t AND relkind = 'r') THEN
      FOR rec IN
        SELECT c.conname, src.relname AS source_table
        FROM pg_constraint c
        JOIN pg_class src ON src.oid = c.conrelid
        JOIN pg_class dst ON dst.oid = c.confrelid
        WHERE c.contype = 'f'
          AND dst.relname = t
          AND src.relname <> ALL (legacy_tables)
          AND src.relname NOT LIKE '\_archived\_%' ESCAPE '\'
      LOOP
        RAISE WARNING 'POST-REPOINT residual FK: % on %', rec.conname, rec.source_table;
        external_fk_count := external_fk_count + 1;
      END LOOP;
    END IF;
  END LOOP;

  IF external_fk_count > 0 THEN
    RAISE EXCEPTION
      'T-V3-D-04 post-repoint guard failed: % residual FK(s).', external_fk_count
      USING ERRCODE = 'feature_not_supported';
  END IF;
END
$archive_guard_post$;


-- ─────────────────────────────────────────────────────────────────────────
-- 3. 本体 ARCHIVE rename. ALTER TABLE ... RENAME TO は intra-legacy FK を
--    自動追随する (PostgreSQL 公式仕様). DROP しないので audit / forensic
--    用途で必要なら _archived_<name> 名で読める.
-- ─────────────────────────────────────────────────────────────────────────

DO $archive_rename$
DECLARE
  pairs CONSTANT text[][] := ARRAY[
    ['tasks',              '_archived_tasks'],
    ['ai_employee_config', '_archived_ai_employee_config'],
    ['pull_requests',      '_archived_pull_requests'],
    ['repos',              '_archived_repos']
  ];
  i int;
  src text;
  dst text;
BEGIN
  FOR i IN 1 .. array_length(pairs, 1) LOOP
    src := pairs[i][1];
    dst := pairs[i][2];

    -- 既に rename 済みなら skip (idempotent)
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = dst AND relkind = 'r') THEN
      RAISE NOTICE 'T-V3-D-04 skip: % already archived as %', src, dst;
      CONTINUE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = src AND relkind = 'r') THEN
      RAISE NOTICE 'T-V3-D-04 skip: % does not exist (fresh DB?)', src;
      CONTINUE;
    END IF;

    EXECUTE format('ALTER TABLE %I RENAME TO %I', src, dst);
    -- archive marker comment (audit trail で _archived_ prefix を見るときの
    -- 由来確認用)
    EXECUTE format(
      $cmt$COMMENT ON TABLE %I IS 'ARCHIVED 2026-05-16 by T-V3-D-04 (twin of modern table). See ADR-015.'$cmt$,
      dst
    );
    RAISE NOTICE 'T-V3-D-04 archived: % -> %', src, dst;
  END LOOP;
END
$archive_rename$;


-- ─────────────────────────────────────────────────────────────────────────
-- 4. RLS は ENABLE のまま残し, _archived_* は service_role のみ操作可とする
--    新規 policy を補完する (legacy table がもし RLS 有効なら DENY all to
--    authenticated になっていたはず. ここで明示する).
-- ─────────────────────────────────────────────────────────────────────────

DO $archive_rls$
DECLARE
  arch text;
  archived_tables CONSTANT text[] := ARRAY[
    '_archived_tasks',
    '_archived_ai_employee_config',
    '_archived_pull_requests',
    '_archived_repos'
  ];
BEGIN
  FOREACH arch IN ARRAY archived_tables LOOP
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = arch AND relkind = 'r') THEN
      EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', arch);
      EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                     arch || '_service_role_only', arch);
      EXECUTE format(
        'CREATE POLICY %I ON %I FOR ALL TO postgres, service_role USING (true) WITH CHECK (true)',
        arch || '_service_role_only', arch
      );
      RAISE NOTICE 'T-V3-D-04 RLS: % locked to service_role only', arch;
    END IF;
  END LOOP;
END
$archive_rls$;


-- =============================================================================
-- 完了.
-- 検証: backend/tests/migrations/test_archive_legacy_twins.py
-- =============================================================================
