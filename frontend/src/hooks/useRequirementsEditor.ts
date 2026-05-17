/**
 * T-V3-C-47 / S-021 — Requirements editor (TanStack Query hook).
 *
 * Wraps {@link getRequirements} / {@link putRequirements} /
 * {@link createRequirementsVersion} with TanStack Query so the page only deals
 * with `data` / `isLoading` / `save` / `snapshot` callbacks.
 *
 * AC mapping (T-V3-C-47):
 *   AC-F1 (EVENT-DRIVEN GET on mount + 4xx error toast)     -> {@link useQuery}
 *   AC-F2 (UNWANTED 401 -> redirect to /login)              -> {@link RequirementsApiError.status}
 *   AC-F3 (EVENT-DRIVEN PUT returns version+1)              -> {@link saveMutation}
 *   AC-F4 (UBIQUITOUS EARS validation before PUT)           -> delegated to api/requirements-editor.ts
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createRequirementsVersion,
  getRequirements,
  putRequirements,
  type RequirementsListResponse,
  type RequirementsPutPayload,
  type RequirementsPutResponse,
  type RequirementsVersionCreatePayload,
  type RequirementsVersionCreateResponse,
} from "@/api/requirements-editor";

/** TanStack Query key namespace for the requirements editor feature. */
export const REQUIREMENTS_QUERY_KEY = (workspaceId: string | number) =>
  ["requirements", String(workspaceId)] as const;

export interface UseRequirementsEditorResult {
  data: RequirementsListResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
  save: (payload: RequirementsPutPayload) => Promise<RequirementsPutResponse>;
  snapshot: (
    payload?: RequirementsVersionCreatePayload,
  ) => Promise<RequirementsVersionCreateResponse>;
  isSaving: boolean;
  isSnapshotting: boolean;
}

/**
 * useRequirementsEditor — query + mutations for the S-021 requirements editor.
 *
 * Test seam: callers can mock `globalThis.fetch` to simulate 401 / 200 / 422.
 */
export function useRequirementsEditor(
  workspaceId: string | number,
): UseRequirementsEditorResult {
  const qc = useQueryClient();
  const queryKey = REQUIREMENTS_QUERY_KEY(workspaceId);

  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => getRequirements(workspaceId, { signal }),
    retry: false,
    staleTime: 30_000,
  });

  const saveMutation = useMutation({
    mutationFn: (payload: RequirementsPutPayload) =>
      putRequirements(workspaceId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const snapshotMutation = useMutation({
    mutationFn: (payload: RequirementsVersionCreatePayload = {}) =>
      createRequirementsVersion(workspaceId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: () => query.refetch(),
    save: (payload) => saveMutation.mutateAsync(payload),
    snapshot: (payload) => snapshotMutation.mutateAsync(payload ?? {}),
    isSaving: saveMutation.isPending,
    isSnapshotting: snapshotMutation.isPending,
  };
}
