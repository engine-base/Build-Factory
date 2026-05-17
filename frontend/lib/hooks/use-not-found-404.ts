/**
 * T-V3-C-53 / S-044 — Ticket-mandated path alias for the not_found_404 hook.
 * The canonical implementation lives at
 * `frontend/src/lib/hooks/use-not-found-404.ts` (which co-locates with the
 * rest of the `src/lib/hooks/*` hooks), so this module re-exports the public
 * surface to satisfy the work_package_boundary path in
 * `tickets-group-c-ui-part2.json`.
 */

export {
  useNotFound404,
  type UseNotFound404Result,
} from "../../src/lib/hooks/use-not-found-404";
