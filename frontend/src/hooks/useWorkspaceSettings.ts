/**
 * T-V3-C-62 / S-013 — 案件設定 TanStack Query hook.
 *
 * Wraps {@link getWorkspace} + {@link updateWorkspace} + {@link deleteWorkspace}
 * so the page only deals with `data` / `isLoading` / mutations.
 *
 * AC mapping (docs/audit/2026-05-16_v3/T-V3-C-62.md):
 *   AC-F1: GET /api/workspaces/{id} on mount; 2xx → render, 4xx → error
 *          surfaced via {@link WorkspaceSettingsApiError}.
 *   AC-F2: 401 → page redirect to /login (surfaced via .status).
 *   AC-F3: PUT /api/workspaces/{id} on save; on 2xx the server emits an
 *          account_updated audit log.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteWorkspace,
  getWorkspace,
  updateWorkspace,
  type DeleteWorkspaceResponse,
  type GetWorkspaceResponse,
  type UpdateWorkspaceRequest,
  type UpdateWorkspaceResponse,
  type WorkspaceSettingsApiError,
} from "@/api/workspace-settings";

/** TanStack Query key namespace for the workspace-settings feature. */
export const WORKSPACE_SETTINGS_QUERY_KEY = ["workspace-settings"] as const;

export interface UseWorkspaceSettingsParams {
  workspaceId: number | string;
  /** When false, the GET query is held off — useful for unauth gating. */
  enabled?: boolean;
}

export interface UseWorkspaceSettingsResult {
  data: GetWorkspaceResponse | undefined;
  isLoading: boolean;
  isPending: boolean;
  isError: boolean;
  error: WorkspaceSettingsApiError | unknown;
  isSuccess: boolean;
  refetch: () => Promise<unknown>;
  save: (body: UpdateWorkspaceRequest) => Promise<UpdateWorkspaceResponse>;
  remove: () => Promise<DeleteWorkspaceResponse>;
  isSaving: boolean;
  isDeleting: boolean;
}

/**
 * useWorkspaceSettings — query + mutations for the S-013 案件設定 screen.
 *
 * Test seam: the hook uses the default fetch (resolved inside
 * @/api/workspace-settings), so vitest tests can mock `globalThis.fetch` to
 * simulate 200 / 401 / 403 paths.
 */
export function useWorkspaceSettings(
  params: UseWorkspaceSettingsParams,
): UseWorkspaceSettingsResult {
  const { workspaceId, enabled = true } = params;
  const qc = useQueryClient();

  const queryKey = [
    ...WORKSPACE_SETTINGS_QUERY_KEY,
    "workspace",
    String(workspaceId),
  ] as const;

  const query = useQuery<GetWorkspaceResponse, WorkspaceSettingsApiError>({
    queryKey,
    enabled,
    queryFn: ({ signal }) => getWorkspace(workspaceId, { signal }),
    retry: false,
    staleTime: 10_000,
  });

  const updateMutation = useMutation({
    mutationFn: (body: UpdateWorkspaceRequest) =>
      updateWorkspace(workspaceId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: WORKSPACE_SETTINGS_QUERY_KEY });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteWorkspace(workspaceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: WORKSPACE_SETTINGS_QUERY_KEY });
    },
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isPending: query.isPending,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    save: (body) => updateMutation.mutateAsync(body),
    remove: () => deleteMutation.mutateAsync(),
    isSaving: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  };
}
