-- =============================================================================
-- T-V3-D-12: NEW entity formalization batch 1 — Critical drift entities
-- =============================================================================
-- Target entities (3 critical NEW entities flagged in entity-drift-summary.md
-- §2 "Critical drift" — spec exists in v1/v3 entities.json but impl_table is
-- missing):
--
--   1. skill_executions          (E-009 SkillExecution, workspace_scoped)
--      → /api/skills/{id}/test execution log: cost / tokens / status /
--        langfuse_trace_id per skill run.
--
--   2. phase_gates               (E-013 PhaseGate, workspace_scoped via phase)
--      → Gate condition + status (pending/passed/failed) per bf_phases row;
--        `passed_at` / `passed_by` recorded at transition.
--
--   3. user_knowledge_namespaces (E-010 UserKnowledgeNamespace, user_scoped)
--      → user/namespace pair with scope (private/account/workspace) for
--        Mem0/Obsidian/Constitution namespace isolation.
--
-- Why a new migration:
--   v3 entity-drift-summary.md §2 ("Critical drift, 3 件") marks these as
--   `impl_table: (missing)` with diff_severity = critical/high. Downstream
--   features (T-AI-MEM-01 memory namespace, S-038 skill test surface,
--   S-016/S-039 phase gate dashboards, T-AI-MEM-04 provider-adapter
--   namespace isolation) need physical tables before they can ship.
--
--   This migration creates the 3 tables with idempotent CREATE TABLE IF NOT
--   EXISTS, enables RLS, and installs the canonical access_policies_required
--   set from tickets-group-d-drift.json#T-V3-D-12:
--     - skill_executions:           service_role_all + workspace_member_select
--     - phase_gates:                service_role_all + workspace_member_select
--     - user_knowledge_namespaces:  service_role_all + owner_only
--
-- AC マッピング (T-V3-D-12):
--   AC-F1 UBIQUITOUS : 3 tables with column set matching entities.json E-009 /
--                      E-013 / E-010 fields[].
--   AC-F2 EVENT      : skill execution → row in skill_executions with
--                      workspace_id + skill_id + ai_employee_id + cost + tokens
--                      + status + langfuse_trace_id (column existence enforced
--                      by NOT NULL where applicable + CHECK constraints).
--   AC-F3 EVENT      : phase gate passed → passed_at + passed_by recorded
--                      (columns present + status transition tracked by status
--                      enum + passed_at/passed_by columns).
--   AC-F4 EVENT      : user knowledge namespace insert → UNIQUE
--                      (user_id, namespace_id) constraint + scope enum
--                      (private/account/workspace).
--   AC-F5 UNWANTED   : verify-rls-coverage.py policy_count < 2 → fail.
--                      Each table gets 2 canonical policies.
--
-- Helper:
--   bf_can_access_workspace(ws_id BIGINT) — defined in
--   20260510000001_bf_project_tables.sql (re-used).
--
-- 詳細: docs/audit/2026-05-16_v3/T-V3-D-12.md
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. skill_executions (E-009 SkillExecution) — workspace_scoped
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_executions (
    id                  BIGSERIAL PRIMARY KEY,
    skill_id            BIGINT NOT NULL REFERENCES skill_definitions(id) ON DELETE CASCADE,
    ai_employee_id      BIGINT REFERENCES ai_employees(id) ON DELETE SET NULL,
    user_id             TEXT,
    workspace_id        BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    session_id          BIGINT REFERENCES sessions(id) ON DELETE SET NULL,
    input               JSONB NOT NULL DEFAULT '{}'::jsonb,
    output              JSONB NOT NULL DEFAULT '{}'::jsonb,
    cost                NUMERIC(12, 6) NOT NULL DEFAULT 0,
    tokens              INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'success'
                            CHECK (status IN ('success', 'failed', 'cancelled')),
    langfuse_trace_id   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_skill_executions_workspace
    ON skill_executions(workspace_id);
CREATE INDEX IF NOT EXISTS ix_skill_executions_user
    ON skill_executions(user_id);
CREATE INDEX IF NOT EXISTS ix_skill_executions_skill
    ON skill_executions(skill_id);
CREATE INDEX IF NOT EXISTS ix_skill_executions_session
    ON skill_executions(session_id);
CREATE INDEX IF NOT EXISTS ix_skill_executions_created
    ON skill_executions(created_at DESC);

ALTER TABLE skill_executions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS skill_executions_service_role_all ON skill_executions;
CREATE POLICY skill_executions_service_role_all ON skill_executions
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS skill_executions_workspace_member_select ON skill_executions;
CREATE POLICY skill_executions_workspace_member_select ON skill_executions
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. phase_gates (E-013 PhaseGate) — workspace_scoped via phase_id → bf_phases
-- ─────────────────────────────────────────────────────────────────────────────
-- spec の tenant_isolation は workspace_scoped (workspace_id column) と記載
-- されているが、 PhaseGate の自然な所属は bf_phases (phase_id) であり、
-- workspace は bf_phases → bf_projects → workspace を経由する。
--
-- 本 migration では runtime クエリの簡便さと spec compliance の両立のため、
--   - phase_id (FK to bf_phases.id, NOT NULL, CASCADE)
--   - workspace_id (FK to workspaces, NOT NULL, CASCADE) を非正規化保持
-- し、 RLS は workspace_id 直接参照で評価する (bf_can_access_workspace).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS phase_gates (
    id              BIGSERIAL PRIMARY KEY,
    phase_id        BIGINT NOT NULL REFERENCES bf_phases(id) ON DELETE CASCADE,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         TEXT,
    name            TEXT NOT NULL,
    condition_type  TEXT NOT NULL
                        CHECK (condition_type IN ('task_completion',
                                                  'review_approval',
                                                  'manual')),
    criteria        JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'passed', 'failed')),
    passed_at       TIMESTAMPTZ,
    passed_by       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_phase_gates_phase
    ON phase_gates(phase_id);
CREATE INDEX IF NOT EXISTS ix_phase_gates_workspace
    ON phase_gates(workspace_id);
CREATE INDEX IF NOT EXISTS ix_phase_gates_status
    ON phase_gates(status, updated_at DESC);

ALTER TABLE phase_gates ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS phase_gates_service_role_all ON phase_gates;
CREATE POLICY phase_gates_service_role_all ON phase_gates
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS phase_gates_workspace_member_select ON phase_gates;
CREATE POLICY phase_gates_workspace_member_select ON phase_gates
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. user_knowledge_namespaces (E-010 UserKnowledgeNamespace) — user_scoped
-- ─────────────────────────────────────────────────────────────────────────────
-- spec fields: user_id (FK), namespace_id text, scope enum(private/shared).
-- T-V3-D-12 ticket spec extends scope to (private/account/workspace) for
-- Mem0/Obsidian/Constitution namespace isolation (BF-Factory side). The
-- UNIQUE constraint on (user_id, namespace_id) enforces AC-F4.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_knowledge_namespaces (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    namespace_id    TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'private'
                        CHECK (scope IN ('private', 'account', 'workspace')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_knowledge_namespaces_user_namespace
        UNIQUE (user_id, namespace_id)
);

CREATE INDEX IF NOT EXISTS ix_user_knowledge_namespaces_user
    ON user_knowledge_namespaces(user_id);
CREATE INDEX IF NOT EXISTS ix_user_knowledge_namespaces_scope
    ON user_knowledge_namespaces(scope);

ALTER TABLE user_knowledge_namespaces ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_knowledge_namespaces_service_role_all ON user_knowledge_namespaces;
CREATE POLICY user_knowledge_namespaces_service_role_all ON user_knowledge_namespaces
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS user_knowledge_namespaces_owner_only ON user_knowledge_namespaces;
CREATE POLICY user_knowledge_namespaces_owner_only ON user_knowledge_namespaces
    FOR ALL TO authenticated
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_versions に本 migration を記録
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO schema_versions (version, description, applied_by) VALUES
    ('20260516190000', 'T-V3-D-12: NEW entity formalization batch 1 (critical drift: skill_executions / phase_gates / user_knowledge_namespaces) — 3 tables + RLS canonical policies', 'system')
ON CONFLICT (version) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT (運用者向け)
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE skill_executions IS
    'T-V3-D-12 / E-009 SkillExecution: skill 実行 1 回ごとの履歴 (cost / tokens / status / langfuse_trace_id)';
COMMENT ON TABLE phase_gates IS
    'T-V3-D-12 / E-013 PhaseGate: bf_phases の gate 条件と通過状態 (passed_at / passed_by 記録)';
COMMENT ON TABLE user_knowledge_namespaces IS
    'T-V3-D-12 / E-010 UserKnowledgeNamespace: user_id × namespace_id の scope (private/account/workspace)';

COMMENT ON POLICY skill_executions_service_role_all ON skill_executions IS
    'T-V3-D-12: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY skill_executions_workspace_member_select ON skill_executions IS
    'T-V3-D-12: workspace_members 経由で同 workspace の skill_executions を SELECT 可';
COMMENT ON POLICY phase_gates_service_role_all ON phase_gates IS
    'T-V3-D-12: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY phase_gates_workspace_member_select ON phase_gates IS
    'T-V3-D-12: workspace_members 経由で同 workspace の phase_gates を SELECT 可 (workspace_id 非正規化保持)';
COMMENT ON POLICY user_knowledge_namespaces_service_role_all ON user_knowledge_namespaces IS
    'T-V3-D-12: backend service_role による全 record access (RLS bypass 相当)';
COMMENT ON POLICY user_knowledge_namespaces_owner_only ON user_knowledge_namespaces IS
    'T-V3-D-12: 本人のみ (user_id = auth.uid()::text) ALL operation 許可';
