-- =============================================================================
-- T-V3-B-20 / F-013: Client portal tokens + comments tables
-- =============================================================================
--
-- Entity coverage:
--   E-033 PullRequest (delivery linkage via workspace)
--   E-034 Delivery    (token expiry / workspace surface)
--   E-030 Comment     (client_portal_comments — public-token authored)
--
-- Why two new tables:
--   - client_review_tokens: gates the 4 public endpoints
--       GET  /api/client/workspaces/{token}
--       GET  /api/client/workspaces/{token}/spec
--       GET  /api/client/comments/{thread_id}
--       POST /api/client/comments
--     T-V3-B-21 (delivery) will issue tokens via POST .../delivery/send-client.
--     We seed the schema here so T-V3-B-20 can land independently.
--   - client_portal_comments: durable storage of public-token-authored comments
--     so /api/comments/{id}/resolve (member-scope) can mutate state.
--
-- Idempotent + RLS-enforced. workspace_id is denormalised onto each row so RLS
-- predicate is a single index lookup.
-- =============================================================================

CREATE TABLE IF NOT EXISTS client_review_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token           TEXT NOT NULL UNIQUE,
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    issued_by       TEXT,
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    client_email    TEXT,
    spec_html_url   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_client_review_tokens_workspace
    ON client_review_tokens(workspace_id, issued_at DESC);
CREATE INDEX IF NOT EXISTS ix_client_review_tokens_expires
    ON client_review_tokens(expires_at);

CREATE TABLE IF NOT EXISTS client_portal_comments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    thread_id       UUID NOT NULL,
    token_id        UUID REFERENCES client_review_tokens(id) ON DELETE SET NULL,
    author_name     TEXT NOT NULL DEFAULT 'client',
    body            TEXT NOT NULL,
    anchor          TEXT,
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT client_portal_comments_body_nonempty CHECK (length(trim(body)) > 0)
);

CREATE INDEX IF NOT EXISTS ix_client_portal_comments_thread
    ON client_portal_comments(thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_client_portal_comments_workspace
    ON client_portal_comments(workspace_id, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────
-- RLS: workspace member RW + service_role full access
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE client_review_tokens ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS client_review_tokens_service_role ON client_review_tokens;
CREATE POLICY client_review_tokens_service_role ON client_review_tokens
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS client_review_tokens_workspace_member_select ON client_review_tokens;
CREATE POLICY client_review_tokens_workspace_member_select ON client_review_tokens
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));

DROP POLICY IF EXISTS client_review_tokens_workspace_admin_insert ON client_review_tokens;
CREATE POLICY client_review_tokens_workspace_admin_insert ON client_review_tokens
    FOR INSERT TO authenticated
    WITH CHECK (bf_can_access_workspace(workspace_id));

DROP POLICY IF EXISTS client_review_tokens_workspace_admin_update ON client_review_tokens;
CREATE POLICY client_review_tokens_workspace_admin_update ON client_review_tokens
    FOR UPDATE TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));

ALTER TABLE client_portal_comments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS client_portal_comments_service_role ON client_portal_comments;
CREATE POLICY client_portal_comments_service_role ON client_portal_comments
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS client_portal_comments_workspace_member_select ON client_portal_comments;
CREATE POLICY client_portal_comments_workspace_member_select ON client_portal_comments
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));

-- Public insert path goes through service_role (token-gated at app layer);
-- authenticated members may also insert (e.g., when resolving / staff reply).
DROP POLICY IF EXISTS client_portal_comments_workspace_member_insert ON client_portal_comments;
CREATE POLICY client_portal_comments_workspace_member_insert ON client_portal_comments
    FOR INSERT TO authenticated
    WITH CHECK (bf_can_access_workspace(workspace_id));

DROP POLICY IF EXISTS client_portal_comments_workspace_member_update ON client_portal_comments;
CREATE POLICY client_portal_comments_workspace_member_update ON client_portal_comments
    FOR UPDATE TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));
