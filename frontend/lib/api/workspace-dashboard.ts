/**
 * T-V3-C-61 / S-012 — Ticket-mandated path alias for the workspace_dashboard
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/workspace-dashboard.ts` (which co-locates with the other
 * src/api/* clients), so this module simply re-exports the public surface
 * to satisfy the work_package_boundary path in
 * tickets-group-c-ui-part2.json.
 */

export {
  WorkspaceDashboardApiError,
  getWorkspaceDashboard,
  workspaceDashboardEndpoint,
  type DashboardKpi,
  type DashboardPendingReview,
  type DashboardPhase,
  type DashboardSession,
  type DashboardTaskRow,
  type WorkspaceDashboardRequestOptions,
  type WorkspaceDashboardResponse,
} from "../../src/api/workspace-dashboard";
