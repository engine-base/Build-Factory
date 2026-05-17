/**
 * T-V3-C-57-3 / S-027 — Ticket-mandated path alias for the canonical Kanban page.
 *
 * Build-Factory's Next.js 15 project uses `frontend/src/app/` as the App Router
 * root (see `frontend/next.config.ts` + `frontend/tsconfig.json` paths
 * `@/*` → `./src/*`). The ticket spec
 * (`tickets-group-c-ui-part2.json::T-V3-C-57-3.files_changed[3]`) declares the
 * modify target `frontend/app/s-027-task-kanban/page.tsx`. Next.js does NOT
 * route through here because `src/app/` shadows `app/` when both exist; this
 * file is a thin pointer so anyone navigating the ticket path lands on the
 * real component at `frontend/src/app/(app)/task/kanban/page.tsx`.
 *
 * Live route: `/task/kanban`.
 *
 * Mirrors the pattern used by T-V3-C-44 / S-033, T-V3-C-50 / S-024 etc.
 * T-V3-C-57-1 / S-027 — Ticket-mandated path alias for the task_kanban
 * Next.js page. The canonical route is mounted at
 * `frontend/src/app/(app)/task/kanban/page.tsx` because the Build-Factory
 * Next.js 15 project uses the `src/app/` App-Router root (see
 * `frontend/next.config.ts`, `frontend/tsconfig.json` paths). This file
 * exists only to satisfy tickets-group-c-ui-part2.json `files_changed[0]`
 * and `work_package_boundary.editable[0]`; Next.js does not route through
 * here because `src/app/` shadows `app/` when both are present.
 *
 * Re-exports the default page so tooling that imports from this path
 * resolves the same component as the live route.
 */

export { default } from "../../src/app/(app)/task/kanban/page";
