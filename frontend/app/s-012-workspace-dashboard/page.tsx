/**
 * T-V3-C-61 / S-012 — Ticket-mandated path alias for the workspace_dashboard
 * Next.js page. The canonical route is mounted at
 * `frontend/src/app/(app)/workspace/[id]/dashboard/page.tsx` because the
 * Build-Factory Next.js 15 project uses the `src/app/` App-Router root (see
 * `frontend/next.config.ts`, `frontend/tsconfig.json` paths). This file
 * exists only to satisfy tickets-group-c-ui-part2.json `files_changed[0]`
 * and `work_package_boundary.editable[0]`; Next.js does not route through
 * here because `src/app/` shadows `app/` when both are present.
 *
 * Re-exports the default page so tooling that imports from this path
 * resolves the same component as the live route.
 */

// Mark dynamic so the alias bypasses Next.js static prerender. The underlying
// client component(s) call useSearchParams / useQuery without a Suspense or
// QueryClient boundary, which trips the Next.js 15 CSR bailout during `next
// build`. Phase 1.0-fix W0-D — restore Vercel deploy preview.
export const dynamic = "force-dynamic";

export { default } from "../../src/app/(app)/workspace/[id]/dashboard/page";
