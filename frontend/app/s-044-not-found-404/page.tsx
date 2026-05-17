/**
 * T-V3-C-53 / S-044 — Ticket-mandated path alias for the not_found_404
 * Next.js page. The canonical route is mounted at
 * `frontend/src/app/not-found.tsx` because that is Next.js 15's built-in
 * convention for the global 404 segment (the file is also wired up as the
 * fallback for any `notFound()` call). The Build-Factory project uses the
 * `src/app/` App-Router root (see `frontend/tsconfig.json` paths), so this
 * file exists only to satisfy
 * `tickets-group-c-ui-part2.json#T-V3-C-53.files_changed[0]` /
 * `work_package_boundary.editable[0]`. Next.js never routes through here
 * because `src/app/` shadows `app/` when both are present.
 *
 * Re-exports the default page so tooling that imports from this path
 * resolves the same component as the live route.
 */

// Mark dynamic so the alias bypasses Next.js static prerender. The underlying
// client component(s) call useSearchParams / useQuery without a Suspense or
// QueryClient boundary, which trips the Next.js 15 CSR bailout during `next
// build`. Phase 1.0-fix W0-D — restore Vercel deploy preview.
export const dynamic = "force-dynamic";

export { default } from "../../src/app/not-found";
