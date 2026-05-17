/**
 * T-V3-C-63 / F-004 / S-014 — 案件メンバー TanStack Query hook.
 *
 * Wraps {@link listWorkspaceMembers} + {@link updateMemberRole} +
 * {@link removeWorkspaceMember} so the page only deals with `data` /
 * `isLoading` / mutations.
 *
 * AC mapping (docs/audit/2026-05-16_v3/T-V3-C-63.md):
 *   AC-F1: GET /api/workspaces/{id}/members on mount; 2xx renders; 4xx
 *          surfaces via {@link WorkspaceMembersApiError} so the page can show
 *          an inline error toast + empty state.
 *   AC-F2: 401 surfaces via WorkspaceMembersApiError.status === 401 so the
 *          page can redirect to /login (S-001).
 *   AC-F3: updateMemberRole() PUTs /api/workspaces/{id}/members/{user_id}/role
 *          + the backend emits the account_updated audit log.
 *   AC-F4: The OR-policy across role default_permissions and member
 *          custom_permissions is enforced server-side (F-021); the hook
 *          simply surfaces 403 for the page toast.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listWorkspaceMembers,
  removeWorkspaceMember,
  updateMemberRole,
  type ListWorkspaceMembersResponse,
  type RemoveMemberResponse,
  type UpdateMemberRoleRequest,
  type UpdateMemberRoleResponse,
  type WorkspaceMembersApiError,
  type WorkspaceRole,
} from "@/api/workspace-members";

/** TanStack Query key namespace for the workspace-members feature. */
export const WORKSPACE_MEMBERS_QUERY_KEY = ["workspace-members"] as const;

export interface UseWorkspaceMembersParams {
  workspaceId: number | string;
  /** Bearer token used for the authenticated GET / mutations. */
  authToken?: string | null;
  /** When false, the GET query is held off — useful for unauth gating. */
  enabled?: boolean;
}

export interface UseWorkspaceMembersResult {
  data: ListWorkspaceMembersResponse | undefined;
  isLoading: boolean;
  isPending: boolean;
  isError: boolean;
  error: WorkspaceMembersApiError | unknown;
  isSuccess: boolean;
  refetch: () => Promise<unknown>;
  updateRole: (vars: {
    userId: string;
    role: WorkspaceRole;
  }) => Promise<UpdateMemberRoleResponse>;
  removeMember: (vars: { userId: string }) => Promise<RemoveMemberResponse>;
  isUpdatingRole: boolean;
  isRemoving: boolean;
}

/**
 * useWorkspaceMembers — query + mutations for the S-014 案件メンバー screen.
 *
 * Test seam: the hook uses the default fetch (resolved inside
 * @/api/workspace-members), so vitest tests can mock `globalThis.fetch` to
 * simulate 200 / 401 / 403 paths.
 */
export function useWorkspaceMembers(
  params: UseWorkspaceMembersParams,
): UseWorkspaceMembersResult {
  const { workspaceId, authToken, enabled = true } = params;
  const qc = useQueryClient();

  const queryKey = [
    ...WORKSPACE_MEMBERS_QUERY_KEY,
    "workspace",
    String(workspaceId),
  ] as const;

  const query = useQuery<
    ListWorkspaceMembersResponse,
    WorkspaceMembersApiError
  >({
    queryKey,
    enabled,
    queryFn: ({ signal }) =>
      listWorkspaceMembers(workspaceId, { signal, authToken }),
    retry: false,
    staleTime: 30_000,
  });

  const roleMutation = useMutation({
    mutationFn: async (vars: {
      userId: string;
      role: WorkspaceRole;
    }) => {
      const body: UpdateMemberRoleRequest = { role: vars.role };
      return updateMemberRole(workspaceId, vars.userId, body, { authToken });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey });
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (vars: { userId: string }) =>
      removeWorkspaceMember(workspaceId, vars.userId, { authToken }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey });
    },
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isPending: query.isPending,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: () => query.refetch(),
    updateRole: (vars) => roleMutation.mutateAsync(vars),
    removeMember: (vars) => removeMutation.mutateAsync(vars),
    isUpdatingRole: roleMutation.isPending,
    isRemoving: removeMutation.isPending,
  };
}
