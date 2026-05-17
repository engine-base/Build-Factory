/**
 * T-V3-C-63 / F-004 / S-014: Ticket-mandated typed client alias for the
 * workspace_members vertical slice (案件メンバー).
 *
 * The canonical typed client lives at
 * `frontend/src/api/workspace-members.ts` because the Build-Factory Next.js 15
 * project uses `src/` as the App Router root (`tsconfig.json` paths
 * `@/* -> ./src/*`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[3]` and
 * `work_package_boundary.editable[3]`; runtime callers should keep using
 * `@/api/workspace-members`.
 *
 * Re-exports the canonical surface so any tooling that navigates here finds
 * the real types and functions.
 */

export * from "../../src/api/workspace-members";
