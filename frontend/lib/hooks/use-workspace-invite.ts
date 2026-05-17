/**
 * T-V3-C-64 / S-015 — Ticket-mandated path alias for the workspace_invite
 * TanStack Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useWorkspaceInvite.ts` (co-located with the other
 * src/hooks/* hooks, resolvable via the `@/hooks/useWorkspaceInvite` TS path
 * alias). This module re-exports the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[2]`.
 */

export {
  WORKSPACE_INVITE_QUERY_KEY,
  useWorkspaceInvite,
  type UseWorkspaceInviteParams,
  type UseWorkspaceInviteResult,
} from "../../src/hooks/useWorkspaceInvite";
