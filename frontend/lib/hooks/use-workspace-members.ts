/**
 * T-V3-C-63 / F-004 / S-014: Ticket-mandated hook alias for the
 * workspace_members vertical slice (案件メンバー).
 *
 * The canonical hook lives at `frontend/src/hooks/use-workspace-members.ts`
 * because the Build-Factory Next.js 15 project uses `src/` as the App Router
 * root (`tsconfig.json` paths `@/* -> ./src/*`). This file exists only to
 * satisfy `tickets-group-c-ui-part2.json::files_changed[2]` and
 * `work_package_boundary.editable[2]`; runtime callers should keep using
 * `@/hooks/use-workspace-members`.
 *
 * Re-exports the canonical surface so any tooling that navigates here finds
 * the real hook implementation.
 */

export * from "../../src/hooks/use-workspace-members";
