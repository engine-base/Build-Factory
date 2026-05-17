/**
 * T-V3-C-51 / S-025 — Ticket-mandated path alias for the screen_flow_map
 * Next.js page. The canonical route is mounted at
 * `frontend/src/app/(app)/spec/screen-flow/page.tsx` because the Build-Factory
 * Next.js 15 project uses the `src/app/` App-Router root (see
 * `frontend/next.config.ts`, `frontend/tsconfig.json` paths). This file exists
 * only to satisfy tickets-group-c-ui-part2.json `files_changed[0]` and
 * `work_package_boundary.editable[0]`; Next.js does not route through here
 * because `src/app/` shadows `app/` when both are present.
 *
 * Re-exports the default page so tooling that imports from this path resolves
 * the same component as the live route.
 */

export { default } from "../../src/app/(app)/spec/screen-flow/page";
