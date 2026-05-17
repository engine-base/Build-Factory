-- =============================================================================
-- T-V3-D-14: AuditLog 二重実装 統合 (E-037 + E-055 → audit_logs + source 列)
-- =============================================================================
--
-- 二重実装解消:
--   - 汎用 `audit_logs`     (E-037, workspace 横断, BIGSERIAL, action/payload)
--   - 専用 `auth_audit_log` (E-055, user_scoped UUID, event_type/metadata)
--
-- v3 では「監査 trail は単一 table 単一意味論」とし source 列 (TEXT CHECK enum)
-- で auth/system/workspace/cost/red_line/generic を区別する。
--
-- 戦略:
--   1. audit_logs.source 列を追加 (idempotent: ADD COLUMN IF NOT EXISTS,
--      CHECK constraint も DROP IF EXISTS → ADD で安全に上書き).
--   2. auth_audit_log の既存 row を audit_logs に INSERT INTO ... SELECT で
--      移行。dedupe は payload->>'legacy_auth_audit_log_id' を natural key
--      とし NOT EXISTS で重複排除。created_at は保全 (AC-F2).
--   3. auth_audit_log は DROP しない。 backward-compat VIEW (AC-F4) として
--      置換する。view は audit_logs WHERE source='auth' を auth_audit_log
--      互換 column shape に reshape し SELECT 専用 (INSERT/UPDATE は不可).
--      これにより 1 release cycle (Phase 1) は legacy SELECT も生存する。
--   4. canonical RLS policies (`audit_logs_service_role_all` /
--      `audit_logs_account_member_select`) を追加 (T-V3-D-14
--      access_policies_required 準拠). 既存の `audit_service_role` /
--      `audit_member_read` policy は backward-compat で温存し OR 結合で
--      cumulative.
--
-- AC mapping:
--   AC-F1 UBIQUITOUS  : audit_logs.source enum(6) + auth_audit_log 全 row 移行
--   AC-F2 EVENT       : auth_audit_log → audit_logs with source='auth' +
--                       original timestamps preserved
--   AC-F3 EVENT       : audit_logs.source は CHECK 制約で強制
--   AC-F4 UNWANTED    : legacy auth_audit_log への query は VIEW 経由で
--                       audit_logs に routing (1 release cycle 互換)
--
-- 関連 ADR: docs/decisions/ADR-018-audit-log-unification.md
-- 関連 audit: docs/audit/2026-05-16_v3/T-V3-D-14.md
-- 関連 spec: docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md
--
-- 重要:
--   - 本 migration は idempotent. 二度実行されても data migrate は INSERT
--     ... WHERE NOT EXISTS で 0 row, view は CREATE OR REPLACE, policy は
--     DROP IF EXISTS で safe.
--   - 実 DROP は data-migration が確実に成功した後に限り将来 migration で
--     実施する (本 migration では DROP しない / DROP は Phase 2 候補).
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. audit_logs.source 列追加 (idempotent)
-- ─────────────────────────────────────────────────────────────────────────────
-- AC-F1: enum('generic'|'auth'|'workspace'|'system'|'cost'|'red_line')
-- DEFAULT 'generic' で既存 row を全て 'generic' source に分類する.
ALTER TABLE audit_logs
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'generic';

-- CHECK constraint は DROP IF EXISTS → ADD で idempotent. enum 拡張時にも
-- 同じ pattern で更新可能.
ALTER TABLE audit_logs
    DROP CONSTRAINT IF EXISTS audit_logs_source_check;

ALTER TABLE audit_logs
    ADD CONSTRAINT audit_logs_source_check
    CHECK (source IN ('generic', 'auth', 'workspace', 'system', 'cost', 'red_line'));

CREATE INDEX IF NOT EXISTS ix_audit_logs_source
    ON audit_logs(source, created_at DESC);

COMMENT ON COLUMN audit_logs.source IS
    'T-V3-D-14: audit event 分類. generic=旧 audit_logs / auth=旧 auth_audit_log / '
    'workspace=workspace 操作 / system=system event / cost=cost tracking / '
    'red_line=red line violation. ADR-018 参照.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. auth_audit_log → audit_logs 移行 (idempotent / 既存環境のみ)
-- ─────────────────────────────────────────────────────────────────────────────
-- AC-F2: created_at preserved + source='auth'.
-- 既存環境 (auth_audit_log がまだ table として存在) でのみ実行.
-- dedupe key: payload->>'legacy_auth_audit_log_id' (UUID text). 二度実行で
-- 同じ row が二度 INSERT されないことを保証.
DO $migrate_auth_audit$
DECLARE
  is_table boolean := false;
  migrated_count int := 0;
BEGIN
  -- auth_audit_log が「table」として現存しているか確認
  -- (本 migration の step 3 で view 化された後は SELECT のみ可で INSERT 不要)
  SELECT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relname = 'auth_audit_log'
      AND c.relkind = 'r'  -- 'r' = ordinary table (view='v')
      AND n.nspname = 'public'
  ) INTO is_table;

  IF NOT is_table THEN
    RAISE NOTICE 'T-V3-D-14 skip data-migrate: auth_audit_log is not a table (already view or absent).';
    RETURN;
  END IF;

  -- INSERT INTO ... SELECT (NOT EXISTS dedupe による idempotent 化)
  -- auth_audit_log の field mapping:
  --   id           -> payload->>'legacy_auth_audit_log_id'  (natural key)
  --   user_id      -> actor_user_id (UUID → TEXT cast)
  --   event_type   -> action
  --   success      -> success
  --   metadata     -> payload (merge with legacy_id)
  --   ip_address   -> payload->>'ip_address'
  --   user_agent   -> payload->>'user_agent'
  --   created_at   -> created_at (preserved)
  WITH inserted AS (
    INSERT INTO audit_logs (
        workspace_id,
        actor_user_id,
        actor_persona,
        action,
        resource_type,
        resource_id,
        payload,
        success,
        source,
        created_at
    )
    SELECT
        NULL                                                  AS workspace_id,
        a.user_id::text                                       AS actor_user_id,
        NULL                                                  AS actor_persona,
        a.event_type                                          AS action,
        'auth'                                                AS resource_type,
        NULL                                                  AS resource_id,
        COALESCE(a.metadata, '{}'::jsonb)
            || jsonb_build_object(
                'legacy_auth_audit_log_id', a.id::text,
                'ip_address', host(a.ip_address),
                'user_agent', a.user_agent
            )                                                 AS payload,
        a.success                                             AS success,
        'auth'                                                AS source,
        a.created_at                                          AS created_at
    FROM auth_audit_log a
    WHERE NOT EXISTS (
        SELECT 1 FROM audit_logs al
        WHERE al.source = 'auth'
          AND al.payload->>'legacy_auth_audit_log_id' = a.id::text
    )
    RETURNING 1
  )
  SELECT count(*) INTO migrated_count FROM inserted;

  RAISE NOTICE 'T-V3-D-14 data-migrate: % auth_audit_log rows merged into audit_logs (source=auth).',
    migrated_count;
END
$migrate_auth_audit$;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. auth_audit_log を backward-compat VIEW に置換 (AC-F4)
-- ─────────────────────────────────────────────────────────────────────────────
-- 既存 table を rename (history 保全) して同名 VIEW を被せる. SELECT は
-- audit_logs WHERE source='auth' に routing. INSERT/UPDATE は VIEW 経由不可.
-- 二度実行されても idempotent:
--   - auth_audit_log がまだ「table」なら RENAME → 旧 RLS policy 群が
--     _archived_auth_audit_log に追随。
--   - 既に VIEW (= step 3 を通過済) なら何もしない。
DO $replace_with_view$
DECLARE
  is_table boolean := false;
  is_view  boolean := false;
BEGIN
  SELECT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relname = 'auth_audit_log'
      AND c.relkind = 'r'
      AND n.nspname = 'public'
  ) INTO is_table;

  SELECT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relname = 'auth_audit_log'
      AND c.relkind = 'v'
      AND n.nspname = 'public'
  ) INTO is_view;

  IF is_view THEN
    RAISE NOTICE 'T-V3-D-14 skip rename: auth_audit_log is already a VIEW.';
    RETURN;
  END IF;

  IF is_table THEN
    -- rename old table to _archived_ prefix (history 保全)
    ALTER TABLE auth_audit_log RENAME TO _archived_auth_audit_log;
    RAISE NOTICE 'T-V3-D-14 rename: auth_audit_log -> _archived_auth_audit_log (history preserved).';
  ELSE
    RAISE NOTICE 'T-V3-D-14 skip rename: auth_audit_log table not found (fresh DB).';
  END IF;
END
$replace_with_view$;

-- VIEW は CREATE OR REPLACE で常に最新化. audit_logs WHERE source='auth' に
-- routing し auth_audit_log と同 column shape で reshape する.
-- security_barrier=true で行レベルアクセス制御を audit_logs RLS に委譲する.
CREATE OR REPLACE VIEW auth_audit_log
WITH (security_barrier = true)
AS
SELECT
    -- id は legacy UUID を保持 (payload に格納された値を返す). 後方互換の
    -- ため UUID 型に cast し直す. legacy_id が NULL の row (= 移行後に
    -- new code が誤って source='auth' で書き込んでも legacy_id なし) は
    -- gen_random_uuid() 同等の安定 UUID を id field として返す (BIGINT id
    -- を md5 ハッシュ → UUID).
    COALESCE(
        NULLIF(al.payload->>'legacy_auth_audit_log_id', '')::uuid,
        ('00000000-0000-0000-0000-' || lpad(to_hex(al.id), 12, '0'))::uuid
    )                                                          AS id,
    al.actor_user_id::uuid                                     AS user_id,
    al.action                                                  AS event_type,
    al.success                                                 AS success,
    NULLIF(al.payload->>'ip_address', '')::inet                AS ip_address,
    NULLIF(al.payload->>'user_agent', '')                      AS user_agent,
    al.payload - 'legacy_auth_audit_log_id'
              - 'ip_address'
              - 'user_agent'                                   AS metadata,
    al.created_at                                              AS created_at
FROM audit_logs al
WHERE al.source = 'auth';

COMMENT ON VIEW auth_audit_log IS
    'T-V3-D-14: backward-compat VIEW (audit_logs WHERE source=''auth''). '
    'AC-F4 UNWANTED: 旧 query を 1 release cycle 互換に保つ. '
    'INSERT/UPDATE は service 層から audit_logs に source=''auth'' で書く. '
    'Phase 2 で VIEW を 410 Gone deprecate → 物理削除予定. ADR-018 参照.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. audit_logs canonical RLS policies 追加
-- ─────────────────────────────────────────────────────────────────────────────
-- 既存 policy (`audit_service_role` / `audit_member_read`) は温存し、
-- canonical name (`audit_logs_service_role_all` /
-- `audit_logs_account_member_select`) を追加で CREATE する. RLS は OR 結合
-- なので追加してもアクセス権が緩和されない (同等 USING clause).
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_logs_service_role_all ON audit_logs;
CREATE POLICY audit_logs_service_role_all ON audit_logs
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

-- account_member_select: workspace_id に対する workspace member のみ SELECT.
-- workspace_id IS NULL の system event (auth login 等) は service_role のみ
-- 可視. 既存 `audit_member_read` policy (workspace_id IS NULL も認証済 user
-- に開放) との OR 結合で「authenticated は wsmember または NULL ws を SELECT」
-- 可能. Phase 2 で `audit_member_read` を deprecate し本 policy に統一する.
DROP POLICY IF EXISTS audit_logs_account_member_select ON audit_logs;
CREATE POLICY audit_logs_account_member_select ON audit_logs
    FOR SELECT TO authenticated
    USING (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id));

COMMENT ON POLICY audit_logs_service_role_all ON audit_logs IS
    'T-V3-D-14: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY audit_logs_account_member_select ON audit_logs IS
    'T-V3-D-14: workspace_members 参加者のみ workspace 内の audit を SELECT 可';


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260516210000', 'T-V3-D-14: AuditLog 二重実装統合 (audit_logs.source + auth_audit_log → VIEW migration)', 'system')
ON CONFLICT (version) DO NOTHING;
