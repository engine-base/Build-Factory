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

// Mark dynamic so the alias bypasses Next.js static prerender. The underlying
// client component(s) call useSearchParams / useQuery without a Suspense or
// QueryClient boundary, which trips the Next.js 15 CSR bailout during `next
// build`. Phase 1.0-fix W0-D — restore Vercel deploy preview.
export const dynamic = "force-dynamic";

export { default } from "@/app/(app)/spec/viewer/[id]/page";
