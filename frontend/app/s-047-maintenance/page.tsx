/**
 * T-V3-C-56 / S-047 — Ticket-mandated path alias for the maintenance page.
 *
 * The canonical implementation lives at
 * `frontend/src/app/maintenance/page.tsx`, mounted on the `/maintenance`
 * route by the App Router's `src/app/` root (see `frontend/tsconfig.json`
 * paths). This file is a thin pointer so anyone navigating to the path
 * declared in `tickets-group-c-ui-part2.json::files_changed[0]` finds the
 * real component.
 *
 * Precedent: `frontend/app/s-041-audit-log-viewer/page.tsx` (T-V3-C-43)
 *            and `frontend/app/s-048-welcome-first-login/page.tsx` (T-V3-C-39).
 */

export { default } from "@/app/maintenance/page";
