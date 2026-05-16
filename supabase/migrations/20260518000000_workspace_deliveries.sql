-- =============================================================================
-- T-V3-B-21 / F-013: workspace_deliveries table for delivery pack management
-- =============================================================================
--
-- Entity coverage:
--   E-034 Delivery  (workspace-scoped delivery pack: draft / approved / sent / accepted)
--   E-033 PullRequest (linkage via workspace; the PR review surface feeds delivery)
--   E-030 Comment   (handled by client_portal_comments — see 20260517000000)
--
-- Why a dedicated table:
--   bf_deliveries (20260510000001) is keyed on project_id and stores accepted_at,
--   but the F-013 endpoint contract for /api/workspaces/{id}/delivery requires
--   workspace_id + status (draft/approved/sent/accepted) + approved_at + sent_at +
--   artifact_urls[]. To preserve backwards compatibility with bf_deliveries and
--   keep the F-013 surface clean (Delivery schema in openapi.yaml line 16392-16429),
--   we model F-013 as its own workspace_deliveries table.
--
-- Endpoint contract:
--   GET  /api/workspaces/{id}/delivery               -> {delivery: Delivery}
--   POST /api/workspaces/{id}/delivery/approve       -> {approved_at}
--   POST /api/workspaces/{id}/delivery/send-client   -> {sent_at, delivery_token}
--
-- send-client uses services.client_portal_service.issue_token() to mint a public
-- token (workspace_id linkage to client_review_tokens — see 20260517000000).
--
-- Idempotent + RLS-enforced.
-- =============================================================================

CREATE TABLE IF NOT EXISTS workspace_deliveries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved', 'sent', 'accepted')),
    approved_at     TIMESTAMPTZ,
    approved_by     TEXT,
    sent_at         TIMESTAMPTZ,
    sent_by         TEXT,
    accepted_at     TIMESTAMPTZ,
    client_email    TEXT,
    artifact_urls   JSONB NOT NULL DEFAULT '[]'::jsonb,
    delivery_token_id UUID REFERENCES client_review_tokens(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_workspace_deliveries_workspace UNIQUE (workspace_id)
);

CREATE INDEX IF NOT EXISTS ix_workspace_deliveries_workspace
    ON workspace_deliveries(workspace_id);
CREATE INDEX IF NOT EXISTS ix_workspace_deliveries_status
    ON workspace_deliveries(status, updated_at DESC);

-- ─────────────────────────────────────────────────────────────────────────
-- RLS: workspace member RW + service_role full access
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE workspace_deliveries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workspace_deliveries_service_role ON workspace_deliveries;
CREATE POLICY workspace_deliveries_service_role ON workspace_deliveries
    FOR ALL TO postgres, service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS workspace_deliveries_workspace_member_select ON workspace_deliveries;
CREATE POLICY workspace_deliveries_workspace_member_select ON workspace_deliveries
    FOR SELECT TO authenticated
    USING (bf_can_access_workspace(workspace_id));

DROP POLICY IF EXISTS workspace_deliveries_workspace_admin_insert ON workspace_deliveries;
CREATE POLICY workspace_deliveries_workspace_admin_insert ON workspace_deliveries
    FOR INSERT TO authenticated
    WITH CHECK (bf_can_access_workspace(workspace_id));

DROP POLICY IF EXISTS workspace_deliveries_workspace_admin_update ON workspace_deliveries;
CREATE POLICY workspace_deliveries_workspace_admin_update ON workspace_deliveries
    FOR UPDATE TO authenticated
    USING (bf_can_access_workspace(workspace_id))
    WITH CHECK (bf_can_access_workspace(workspace_id));
