/**
 * T-V3-C-64 / S-015 — メンバー招待 TanStack Query hook.
 *
 * Wraps the typed client in @/api/workspace-invite so the page only deals with
 * `data` / `isLoading` / mutations.
 *
 * AC mapping (docs/audit/2026-05-16_v3/T-V3-C-64.md):
 *   AC-F1: createWorkspaceInvitation mutation surfaces 2xx into the pending
 *          list and 4xx as WorkspaceInviteApiError for the toast/empty state.
 *   AC-F2: 401 → WorkspaceInviteApiError.status === 401, the page redirects.
 *   AC-F3: updateAccountPlan mutation handles owner plan upgrades.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createWorkspaceInvitation,
  listWorkspaceInvitations,
  revokeWorkspaceInvitation,
  updateAccountPlan,
  type CreateWorkspaceInvitationRequest,
  type CreateWorkspaceInvitationResponse,
  type ListWorkspaceInvitationsResponse,
  type RevokeWorkspaceInvitationResponse,
  type UpdateAccountPlanRequest,
  type UpdateAccountPlanResponse,
  type WorkspaceInvitation,
  type WorkspaceInviteApiError,
} from "@/api/workspace-invite";

/** TanStack Query key namespace for the workspace-invite feature. */
export const WORKSPACE_INVITE_QUERY_KEY = ["workspace-invite"] as const;

export interface UseWorkspaceInviteParams {
  workspaceId: number | string;
  accountId?: number | string;
  /** When false, the list GET is held off — useful for unauth gating. */
  enabled?: boolean;
}

export interface UseWorkspaceInviteResult {
  invitations: WorkspaceInvitation[];
  data: ListWorkspaceInvitationsResponse | undefined;
  isLoading: boolean;
  isPending: boolean;
  isError: boolean;
  error: WorkspaceInviteApiError | unknown;
  isSuccess: boolean;
  refetch: () => Promise<unknown>;
  createInvitation: (
    body: CreateWorkspaceInvitationRequest,
  ) => Promise<CreateWorkspaceInvitationResponse>;
  isCreating: boolean;
  createError: WorkspaceInviteApiError | unknown;
  revokeInvitation: (
    token: string,
  ) => Promise<RevokeWorkspaceInvitationResponse>;
  isRevoking: boolean;
  revokeError: WorkspaceInviteApiError | unknown;
  updatePlan: (
    body: UpdateAccountPlanRequest,
  ) => Promise<UpdateAccountPlanResponse>;
  isUpdatingPlan: boolean;
  updatePlanError: WorkspaceInviteApiError | unknown;
}

/**
 * useWorkspaceInvite — query + mutations for the S-015 メンバー招待 screen.
 *
 * Test seam: the hook uses the default fetch (resolved inside
 * @/api/workspace-invite), so vitest tests can mock `globalThis.fetch` to
 * simulate 200 / 401 / 403 paths.
 */
export function useWorkspaceInvite(
  params: UseWorkspaceInviteParams,
): UseWorkspaceInviteResult {
  const { workspaceId, accountId, enabled = true } = params;
  const qc = useQueryClient();

  const queryKey = [
    ...WORKSPACE_INVITE_QUERY_KEY,
    "workspace",
    String(workspaceId),
  ] as const;

  const query = useQuery<ListWorkspaceInvitationsResponse, WorkspaceInviteApiError>({
    queryKey,
    enabled,
    queryFn: ({ signal }) =>
      listWorkspaceInvitations(workspaceId, { signal }),
    retry: false,
    staleTime: 10_000,
  });

  const createMutation = useMutation<
    CreateWorkspaceInvitationResponse,
    WorkspaceInviteApiError,
    CreateWorkspaceInvitationRequest
  >({
    mutationFn: (body) => createWorkspaceInvitation(workspaceId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const revokeMutation = useMutation<
    RevokeWorkspaceInvitationResponse,
    WorkspaceInviteApiError,
    string
  >({
    mutationFn: (token) => revokeWorkspaceInvitation(workspaceId, token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const updatePlanMutation = useMutation<
    UpdateAccountPlanResponse,
    WorkspaceInviteApiError,
    UpdateAccountPlanRequest
  >({
    mutationFn: (body) => {
      if (accountId === undefined || accountId === null || accountId === "") {
        return Promise.reject(
          new Error("accountId is required to update the plan"),
        );
      }
      return updateAccountPlan(accountId, body);
    },
  });

  return {
    invitations: query.data?.invitations ?? [],
    data: query.data,
    isLoading: query.isLoading,
    isPending: query.isPending,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    createInvitation: (body) => createMutation.mutateAsync(body),
    isCreating: createMutation.isPending,
    createError: createMutation.error,
    revokeInvitation: (token) => revokeMutation.mutateAsync(token),
    isRevoking: revokeMutation.isPending,
    revokeError: revokeMutation.error,
    updatePlan: (body) => updatePlanMutation.mutateAsync(body),
    isUpdatingPlan: updatePlanMutation.isPending,
    updatePlanError: updatePlanMutation.error,
  };
}
