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

export { default } from "../../src/app/not-found";
