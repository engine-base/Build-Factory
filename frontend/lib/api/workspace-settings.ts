/**
 * T-V3-C-62 / S-013 — Ticket-mandated path alias for the workspace_settings
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/workspace-settings.ts` (co-located with the other
 * src/api/* clients, resolvable via the `@/api/workspace-settings` TS path
 * alias). This module re-exports the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[3]`.
 */

export {
  WORKSPACE_ENDPOINT_PATTERN,
  WorkspaceSettingsApiError,
  deleteWorkspace,
  getWorkspace,
  updateWorkspace,
  workspaceEndpoint,
  type DeleteWorkspaceResponse,
  type GetWorkspaceResponse,
  type UpdateWorkspaceRequest,
  type UpdateWorkspaceResponse,
  type Workspace,
  type WorkspaceIntegrationLink,
  type WorkspaceProjectType,
  type WorkspaceSettingsRequestOptions,
} from "../../src/api/workspace-settings";
