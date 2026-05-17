/**
 * T-V3-C-61 / S-012 — Ticket-mandated path alias for the workspace_dashboard
 * hook. The canonical implementation lives at
 * `frontend/src/hooks/useWorkspaceDashboard.ts` (which co-locates with the
 * other src/hooks/* hooks), so this module re-exports the public surface to
 * satisfy the work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  useWorkspaceDashboard,
  type UseWorkspaceDashboardParams,
  type UseWorkspaceDashboardResult,
} from "../../src/hooks/useWorkspaceDashboard";
