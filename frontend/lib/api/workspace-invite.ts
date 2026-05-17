/**
 * T-V3-C-64 / S-015 — Ticket-mandated path alias for the workspace_invite
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/workspace-invite.ts` (co-located with the other
 * src/api/* clients, resolvable via the `@/api/workspace-invite` TS path
 * alias). This module re-exports the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[3]`.
 */

export {
  ACCOUNT_PLAN_ENDPOINT_PATTERN,
  WORKSPACE_INVITATIONS_ENDPOINT_PATTERN,
  WORKSPACE_INVITATION_REVOKE_ENDPOINT_PATTERN,
  WorkspaceInviteApiError,
  accountPlanEndpoint,
  createWorkspaceInvitation,
  listWorkspaceInvitations,
  revokeWorkspaceInvitation,
  updateAccountPlan,
  workspaceInvitationRevokeEndpoint,
  workspaceInvitationsEndpoint,
  type CreateWorkspaceInvitationRequest,
  type CreateWorkspaceInvitationResponse,
  type ListWorkspaceInvitationsResponse,
  type RevokeWorkspaceInvitationResponse,
  type UpdateAccountPlanRequest,
  type UpdateAccountPlanResponse,
  type WorkspaceInvitation,
  type WorkspaceInviteRequestOptions,
  type WorkspaceInviteRole,
  type WorkspaceInviteStatus,
} from "../../src/api/workspace-invite";
