/**
 * T-V3-C-56 / S-047 — Ticket-mandated path alias for the maintenance typed
 * API client. The canonical implementation lives at
 * `frontend/src/lib/api/maintenance.ts` (which co-locates with the other
 * `src/lib/api/*` clients). This module re-exports the public surface to
 * satisfy the work_package_boundary path in
 * `tickets-group-c-ui-part2.json::files_changed[3]`.
 *
 * Precedent: `frontend/lib/api/welcome-first-login.ts` (T-V3-C-39)
 *            and `frontend/lib/api/audit-log-viewer.ts` (T-V3-C-43).
 */

export {
  MAINTENANCE_STATUS_ENDPOINT,
  MaintenanceApiError,
  getMaintenanceStatus,
  type MaintenanceItem,
  type MaintenanceRequestOptions,
  type MaintenanceStatus,
} from "../../src/lib/api/maintenance";
