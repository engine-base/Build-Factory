/**
 * T-V3-C-43 / S-041 — Ticket-mandated path alias for the audit_log_viewer
 * typed API client. The canonical implementation lives at
 * `frontend/src/lib/api/audit-log-viewer.ts` (which co-locates with the
 * other `src/lib/api/` clients such as `cost-dashboard.ts`), so this module
 * simply re-exports the public surface to satisfy the work_package_boundary
 * path declared in `tickets-group-c-ui-part2.json::files_changed[3]`.
 */

export {
  AUDIT_LOGS_ENDPOINT,
  AUDIT_LOGS_EXPORT_CSV_ENDPOINT,
  AUDIT_LOGS_EXPORT_JSON_ENDPOINT,
  AuditLogApiError,
  fetchAuditLogs,
  fetchAuditLogsExportCsv,
  fetchAuditLogsExportJson,
  triggerBlobDownload,
  type AuditLogEntry,
  type AuditLogFilter,
  type AuditLogJsonExportResponse,
  type AuditLogListResponse,
} from "@/lib/api/audit-log-viewer";
