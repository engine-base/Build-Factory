/**
 * T-V3-C-54 / S-045 — Ticket-mandated path alias for the server_error_500
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/server-error-500.ts` (which co-locates with the other
 * src/api/ clients), so this module simply re-exports the public surface to
 * satisfy the work_package_boundary path in
 * tickets-group-c-ui-part2.json::files_changed[3].
 */

export {
  SERVER_ERROR_500_CONTEXT_ENDPOINT,
  ServerError500ApiError,
  getServerErrorContext,
  type ServerError500RequestOptions,
  type ServerErrorContextRequest,
  type ServerErrorContextResponse,
} from "../../src/api/server-error-500";
