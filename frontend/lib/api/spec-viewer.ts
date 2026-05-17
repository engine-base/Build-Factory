/**
 * T-V3-C-48 / S-022 — Ticket-mandated path alias for the spec viewer typed
 * client. The canonical implementation lives at
 *   frontend/src/api/specs.ts
 * (matches the project convention used by `frontend/src/api/phases.ts` etc.).
 *
 * This file is a thin re-export so anyone navigating to the path declared
 * in `tickets-group-c-ui-part2.json::files_changed[3]` finds the real client.
 */

export * from "@/api/specs";
