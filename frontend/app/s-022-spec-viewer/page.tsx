/**
 * T-V3-C-48 / S-022 — Ticket-mandated path alias for the spec_viewer page.
 *
 * The canonical implementation lives at
 *   frontend/src/app/(app)/spec/viewer/[id]/page.tsx
 * (Next.js App Router with the `(app)` shell + dynamic [id] segment).
 *
 * This file is a thin re-export so anyone navigating to the path declared
 * in `tickets-group-c-ui-part2.json::files_changed[0]` finds the real page.
 */

export { default } from "@/app/(app)/spec/viewer/[id]/page";
