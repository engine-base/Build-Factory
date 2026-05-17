/**
 * T-V3-C-54 / S-045 — Ticket-mandated path alias for the server_error_500
 * TanStack Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useServerError500.ts` (which co-locates with the other
 * src/hooks/* hooks), so this module re-exports the public surface to satisfy
 * the work_package_boundary path in
 * tickets-group-c-ui-part2.json::files_changed[2].
 */

export {
  SERVER_ERROR_500_QUERY_KEY,
  useServerError500,
  type UseServerError500Options,
  type UseServerError500Result,
} from "../../src/hooks/useServerError500";
