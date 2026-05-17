/**
 * T-V3-C-43 / S-041 — Ticket-mandated path alias for the audit_log_viewer page.
 *
 * The canonical implementation lives at
 * `frontend/src/app/(app)/ops/audit-logs/page.tsx`, mounted on the
 * `/ops/audit-logs` route by the App Router's `src/app/(app)` route group.
 * This file is a thin pointer so anyone navigating to the path declared in
 * `tickets-group-c-ui-part2.json::files_changed[0]` finds the real component.
 *
 * Precedent: `frontend/app/s-048-welcome-first-login/page.tsx` (T-V3-C-39).
 */

export { default } from "@/app/(app)/ops/audit-logs/page";
