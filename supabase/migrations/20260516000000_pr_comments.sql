-- =============================================================================
-- T-V3-B-19 / F-013: pr_comments table for PR review backend
-- =============================================================================
--
-- Entity coverage:
--   E-030 Comment (PR comment subset, scoped to pull_request)
--
-- Why a dedicated table:
--   pull_requests already exists (20260501220000_initial_schema.sql) but has no
--   per-comment record. F-013 endpoint POST /api/prs/{id}/comments needs a
--   first-class comment row with anchor_file / anchor_line + author audit so
--   that the client review surface (S-033/S-035/S-042/S-043) can re-render.
--
-- Idempotent + RLS-enforced. The workspace_id column is denormalised onto the
-- row (instead of joining through repos -> pull_requests) so that the
-- bf_can_access_workspace(workspace_id) RLS predicate is a single index lookup
-- on a hot path.
-- =============================================================================

CREATE TABLE IF NOT EXISTS pr_comments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pr_id           BIGINT NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    author_user_id  TEXT NOT NULL,
    body            TEXT NOT NULL,
    anchor_file     TEXT,
    anchor_line     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_pr_comments_pr        ON pr_comments(pr_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_pr_comments_workspace ON pr_comments(workspace_id, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────
-- RLS: workspace member RW + service_role full access
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE pr_comments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pr_comments_service_role ON pr_comments;
CREATE POLICY pr_comments_service_role ON pr_comments
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS pr_comments_workspace_member_select ON pr_comments;
CREATE POLICY pr_comments_workspace_member_select ON pr_comments
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));

DROP POLICY IF EXISTS pr_comments_workspace_member_insert ON pr_comments;
CREATE POLICY pr_comments_workspace_member_insert ON pr_comments
    FOR INSERT TO authenticated
    WITH CHECK (
        bf_can_access_workspace(workspace_id)
        AND author_user_id = auth.uid()::text
    );

-- author-only update / delete (defensive: usually pr_comments are append-only,
-- but we allow the author to fix typos for 5 min — enforced at app layer; here
-- the predicate only restricts WHO can ever issue UPDATE/DELETE).
DROP POLICY IF EXISTS pr_comments_workspace_member_write ON pr_comments;
CREATE POLICY pr_comments_workspace_member_write ON pr_comments
    FOR UPDATE TO authenticated
    USING (bf_can_access_workspace(workspace_id) AND author_user_id = auth.uid()::text)
    WITH CHECK (bf_can_access_workspace(workspace_id) AND author_user_id = auth.uid()::text);

DROP POLICY IF EXISTS pr_comments_workspace_member_delete ON pr_comments;
CREATE POLICY pr_comments_workspace_member_delete ON pr_comments
    FOR DELETE TO authenticated
    USING (bf_can_access_workspace(workspace_id) AND author_user_id = auth.uid()::text);
