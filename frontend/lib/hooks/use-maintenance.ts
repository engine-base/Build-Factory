/**
 * T-V3-C-56 / S-047 — Ticket-mandated path alias for the maintenance
 * TanStack Query hook. The canonical implementation lives at
 * `frontend/src/lib/hooks/use-maintenance.ts` (which co-locates with the
 * other `src/lib/hooks/*` hooks). This module re-exports the public surface
 * to satisfy the work_package_boundary path in
 * `tickets-group-c-ui-part2.json::files_changed[2]`.
 *
 * Precedent: `frontend/lib/hooks/use-welcome-first-login.ts` (T-V3-C-39)
 *            and `frontend/lib/hooks/use-audit-log-viewer.ts` (T-V3-C-43).
 */

export {
  MAINTENANCE_QUERY_KEY,
  useMaintenance,
  type UseMaintenanceOptions,
  type UseMaintenanceResult,
} from "../../src/lib/hooks/use-maintenance";
