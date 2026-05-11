-- T-018-01: audit_logs trigger (主要テーブルに変更検出)
-- =============================================================================
-- 主要テーブルの INSERT / UPDATE / DELETE を自動で audit_logs に emit する
-- generic trigger.
--
-- AC マッピング:
--   AC-1 UBIQUITOUS: 主要 5 テーブル (workspaces / bf_projects / bf_tasks /
--                    skill_definitions / ai_employees) に trigger 設置
--   AC-2 EVENT:     INSERT/UPDATE/DELETE 操作で audit_logs に 1 行 INSERT
--   AC-3 STATE:     audit_logs.action は "<table>.{insert|update|delete}",
--                   resource_type=<table>, resource_id=NEW.id / OLD.id,
--                   payload に diff (changed_cols) を含む
--   AC-4 UNWANTED:  audit_logs 自身への trigger は設置しない (再帰防止)
-- =============================================================================

-- ── 共通 trigger function ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bf_audit_row_change() RETURNS TRIGGER AS $$
DECLARE
  v_action    TEXT;
  v_payload   JSONB := '{}'::jsonb;
  v_changed   JSONB;
  v_resid     BIGINT;
  v_table     TEXT := TG_TABLE_NAME;
  v_actor     TEXT := COALESCE(current_setting('bf.actor_user_id', true), NULL);
  v_workspace BIGINT := NULLIF(current_setting('bf.workspace_id', true), '')::BIGINT;
BEGIN
  IF (TG_OP = 'INSERT') THEN
    v_action := v_table || '.insert';
    v_resid := (to_jsonb(NEW) ->> 'id')::BIGINT;
    v_payload := jsonb_build_object('after', to_jsonb(NEW));
  ELSIF (TG_OP = 'UPDATE') THEN
    v_action := v_table || '.update';
    v_resid := (to_jsonb(NEW) ->> 'id')::BIGINT;
    -- changed columns のみ diff として残す
    SELECT jsonb_object_agg(key, value) INTO v_changed
      FROM jsonb_each(to_jsonb(NEW))
     WHERE value IS DISTINCT FROM (to_jsonb(OLD) -> key);
    v_payload := jsonb_build_object(
      'changed', COALESCE(v_changed, '{}'::jsonb),
      'before_id', (to_jsonb(OLD) ->> 'id')::BIGINT
    );
  ELSIF (TG_OP = 'DELETE') THEN
    v_action := v_table || '.delete';
    v_resid := (to_jsonb(OLD) ->> 'id')::BIGINT;
    v_payload := jsonb_build_object('before', to_jsonb(OLD));
  END IF;

  INSERT INTO audit_logs
    (workspace_id, actor_user_id, action, resource_type, resource_id, payload, success)
  VALUES (
    v_workspace, v_actor, v_action, v_table, v_resid, v_payload, TRUE
  );

  IF (TG_OP = 'DELETE') THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ── trigger 設置: 主要 5 テーブル (audit_logs 自身は除外) ────────────────
DO $$
DECLARE
  t TEXT;
  target_tables TEXT[] := ARRAY[
    'workspaces',
    'bf_projects',
    'bf_tasks',
    'skill_definitions',
    'ai_employees'
  ];
BEGIN
  FOREACH t IN ARRAY target_tables LOOP
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = t) THEN
      EXECUTE format('DROP TRIGGER IF EXISTS trg_audit_%I ON %I', t, t);
      EXECUTE format(
        'CREATE TRIGGER trg_audit_%I '
        'AFTER INSERT OR UPDATE OR DELETE ON %I '
        'FOR EACH ROW EXECUTE FUNCTION bf_audit_row_change()',
        t, t
      );
    END IF;
  END LOOP;
END$$;


-- audit_logs 自身には設置しない (無限再帰防止). コメントで明記.
COMMENT ON FUNCTION bf_audit_row_change() IS
  'T-018-01: 主要テーブルの行変更を audit_logs に emit. audit_logs 自身には設置禁止 (再帰).';
