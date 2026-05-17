/**
 * T-V3-C-62 / S-013 — Ticket-mandated path alias for the workspace_settings
 * TanStack Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useWorkspaceSettings.ts` (co-located with the other
 * src/hooks/* hooks, resolvable via the `@/hooks/useWorkspaceSettings` TS
 * path alias). This module re-exports the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[2]`.
 */

export {
  WORKSPACE_SETTINGS_QUERY_KEY,
  useWorkspaceSettings,
  type UseWorkspaceSettingsParams,
  type UseWorkspaceSettingsResult,
} from "../../src/hooks/useWorkspaceSettings";
