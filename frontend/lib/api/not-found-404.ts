/**
 * T-V3-C-53 / S-044 — Ticket-mandated path alias for the not_found_404
 * typed API client. The canonical implementation lives at
 * `frontend/src/lib/api/not-found-404.ts` (which co-locates with the rest of
 * the `src/lib/api/*` clients), so this module simply re-exports the public
 * surface to satisfy the work_package_boundary path in
 * `tickets-group-c-ui-part2.json`.
 */

export {
  NOT_FOUND_KNOWN_ROUTES,
  NotFoundApiError,
  getKnownRoutes,
  type KnownRoute,
} from "../../src/lib/api/not-found-404";
