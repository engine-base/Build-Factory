/**
 * T-V3-C-55 / S-046 — Ticket-mandated path alias for the forbidden_403 hook.
 * The canonical implementation lives at
 * `frontend/src/hooks/use-forbidden-403.ts`. This file is a thin re-export
 * to satisfy `tickets-group-c-ui-part2.json::files_changed[2]` and the
 * editable boundary; it must not contain any business logic.
 */

export {
  useForbidden403,
  type UseForbidden403Options,
  type UseForbidden403Result,
} from "../../src/hooks/use-forbidden-403";
