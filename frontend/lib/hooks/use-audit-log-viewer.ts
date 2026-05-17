/**
 * T-V3-C-43 / S-041 — Ticket-mandated path alias for the audit_log_viewer
 * page hook. The canonical implementation lives at
 * `frontend/src/hooks/use-audit-log-viewer.ts` (which co-locates with the
 * other `src/hooks/` modules), so this module simply re-exports the public
 * surface to satisfy the work_package_boundary path declared in
 * `tickets-group-c-ui-part2.json::files_changed[2]`.
 */

export {
  AUDIT_LOG_TIME_RANGES,
  DEFAULT_FILTERS,
  applyFreeTextSearch,
  buildWireFilter,
  useAuditLogViewer,
  type AuditLogTimeRange,
  type AuditLogViewerFilters,
  type UseAuditLogViewerResult,
} from "@/hooks/use-audit-log-viewer";
