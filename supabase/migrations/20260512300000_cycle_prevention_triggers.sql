-- =============================================================================
-- T-001-09: 循環依存防止 trigger (recursive CTE)
-- =============================================================================
-- DAG として閉路 (cycle) 禁止される 2 graph に BEFORE INSERT/UPDATE trigger を
-- 設置し、 recursive CTE で reachability を計算して cycle 検出時に reject.
--
-- 対象 graph:
--   1. bf_task_dependencies (task_id, depends_on_task_id)
--      → タスクの依存関係 (T-001-04 で作成)
--   2. ai_hierarchies       (parent_id, child_id)
--      → AI 社員の階層 (T-001-03 で作成)
--
-- recursive CTE 戦略:
--   新しい edge (a → b) を加える前に、 既存 graph に b → a の path が存在するか
--   検査する. 存在すれば cycle 形成 → ERRCODE 'check_violation' で reject.
--
-- AC マッピング:
--   AC-1 UBIQUITOUS: 2 graph に trigger 設置 + recursive CTE
--   AC-2 EVENT:     INSERT 試行で 2 秒以内に判定 (CTE は depth 制限なし、 実用範囲で速い)
--   AC-3 STATE:     RLS と直交 (trigger は service_role 経由でも発火)
--   AC-4 UNWANTED:  cycle 形成 → reject + {code: 'cycle_detected'} で caller 4xx 化
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. bf_task_dependencies: cycle 防止 trigger
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bf_prevent_task_dep_cycle() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    cycle_found BIGINT;
BEGIN
    -- 自己参照は CREATE TABLE 時の CHECK で防止済だが、 念のため
    IF NEW.task_id = NEW.depends_on_task_id THEN
        RAISE EXCEPTION 'cycle_detected: task cannot depend on itself (task_id=%)', NEW.task_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- depends_on_task_id から出発し、 既存 deps を辿って task_id に到達できるかを
    -- recursive CTE で計算. 到達できる → 新 edge を加えると cycle 形成.
    WITH RECURSIVE reachable AS (
        -- 起点: 新 edge の depends_on_task_id
        SELECT depends_on_task_id AS node
          FROM bf_task_dependencies
         WHERE task_id = NEW.depends_on_task_id
        UNION
        -- 既存 edges を辿る
        SELECT d.depends_on_task_id
          FROM bf_task_dependencies d
          JOIN reachable r ON d.task_id = r.node
    )
    SELECT node INTO cycle_found FROM reachable WHERE node = NEW.task_id LIMIT 1;

    IF cycle_found IS NOT NULL THEN
        RAISE EXCEPTION
            'cycle_detected: adding dep (% -> %) would create cycle',
            NEW.task_id, NEW.depends_on_task_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END$$;

DROP TRIGGER IF EXISTS trg_prevent_task_dep_cycle ON bf_task_dependencies;
CREATE TRIGGER trg_prevent_task_dep_cycle
    BEFORE INSERT OR UPDATE ON bf_task_dependencies
    FOR EACH ROW EXECUTE FUNCTION bf_prevent_task_dep_cycle();


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. ai_hierarchies: cycle 防止 trigger (T-001-03 で作成された table)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bf_prevent_ai_hierarchy_cycle() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE
    cycle_found BIGINT;
BEGIN
    -- parent_id NULL は root → cycle 形成し得ない
    IF NEW.parent_id IS NULL THEN
        RETURN NEW;
    END IF;
    -- 自己参照は CHECK で禁止済 (no_self_parent) だが念のため
    IF NEW.parent_id = NEW.child_id THEN
        RAISE EXCEPTION 'cycle_detected: ai_employee cannot be its own parent (id=%)', NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;

    -- child_id から既存 hierarchy を辿って parent_id に到達するか
    WITH RECURSIVE reachable AS (
        SELECT child_id AS node
          FROM ai_hierarchies
         WHERE parent_id = NEW.child_id
        UNION
        SELECT h.child_id
          FROM ai_hierarchies h
          JOIN reachable r ON h.parent_id = r.node
    )
    SELECT node INTO cycle_found FROM reachable WHERE node = NEW.parent_id LIMIT 1;

    IF cycle_found IS NOT NULL THEN
        RAISE EXCEPTION
            'cycle_detected: adding hierarchy (parent=%, child=%) would create cycle',
            NEW.parent_id, NEW.child_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END$$;

DROP TRIGGER IF EXISTS trg_prevent_ai_hierarchy_cycle ON ai_hierarchies;
CREATE TRIGGER trg_prevent_ai_hierarchy_cycle
    BEFORE INSERT OR UPDATE ON ai_hierarchies
    FOR EACH ROW EXECUTE FUNCTION bf_prevent_ai_hierarchy_cycle();


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260512300000', 'T-001-09: cycle prevention triggers (task_deps + ai_hierarchies)', 'system')
ON CONFLICT (version) DO NOTHING;


COMMENT ON FUNCTION bf_prevent_task_dep_cycle() IS
    'T-001-09: recursive CTE で bf_task_dependencies の cycle を BEFORE INSERT で reject';
COMMENT ON FUNCTION bf_prevent_ai_hierarchy_cycle() IS
    'T-001-09: recursive CTE で ai_hierarchies の cycle を BEFORE INSERT で reject';