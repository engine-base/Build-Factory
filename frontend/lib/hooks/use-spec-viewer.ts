/**
 * T-V3-C-48 / S-022 — Ticket-mandated path alias for the spec viewer hook.
 * The canonical implementation lives at
 *   frontend/src/hooks/useSpecViewer.ts
 * (matches the project convention used by `useSwarmSessionStream` etc.).
 *
 * This file is a thin re-export so anyone navigating to the path declared
 * in `tickets-group-c-ui-part2.json::files_changed[2]` finds the real hook.
 */

export * from "@/hooks/useSpecViewer";
export { useSpecViewer as useSpecViewerHook } from "@/hooks/useSpecViewer";
