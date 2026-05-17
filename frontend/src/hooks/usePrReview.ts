/**
 * T-V3-C-44 / S-033 — PR レビュー TanStack Query hook.
 *
 * Wraps {@link getWorkspacePr} + {@link approvePr} / {@link postPrComment} /
 * {@link mergePr} so the page only deals with `data` / `isLoading` / mutations.
 *
 * AC mapping (docs/audit/2026-05-16_v3/T-V3-C-44.md):
 *   AC-F1: GET /api/workspaces/{id}/prs/{pr_number} on mount.
 *   AC-F2: 401 → page redirect to /login (surfaced via {@link PrReviewApiError.status}).
 *   AC-F3: POST /api/prs/{id}/merge (workspace_admin) emits pr_merged audit log.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approvePr,
  getWorkspacePr,
  mergePr,
  postPrComment,
  type ApprovePrRequest,
  type ApprovePrResponse,
  type MergePrRequest,
  type MergePrResponse,
  type PostPrCommentRequest,
  type PostPrCommentResponse,
  type PrReviewApiError,
  type WorkspacePrResponse,
} from "@/api/pr-review";

/** TanStack Query key namespace for the PR-review feature. */
export const PR_REVIEW_QUERY_KEY = ["pr-review"] as const;

export interface UsePrReviewParams {
  workspaceId: number | string;
  prNumber: number | string;
  /** When false, the GET query is held off — useful for unauth gating. */
  enabled?: boolean;
}

export interface UsePrReviewResult {
  data: WorkspacePrResponse | undefined;
  isLoading: boolean;
  isPending: boolean;
  isError: boolean;
  error: PrReviewApiError | unknown;
  isSuccess: boolean;
  refetch: () => Promise<unknown>;
  approve: (body?: ApprovePrRequest) => Promise<ApprovePrResponse>;
  comment: (body: PostPrCommentRequest) => Promise<PostPrCommentResponse>;
  merge: (body: MergePrRequest) => Promise<MergePrResponse>;
  isApproving: boolean;
  isCommenting: boolean;
  isMerging: boolean;
}

/**
 * usePrReview — query + mutations for the S-033 PR レビュー screen.
 *
 * Test seam: the hook uses the default fetch (resolved inside @/api/pr-review),
 * so vitest tests can mock `globalThis.fetch` to simulate 200 / 401 / 403 paths.
 */
export function usePrReview(params: UsePrReviewParams): UsePrReviewResult {
  const { workspaceId, prNumber, enabled = true } = params;
  const qc = useQueryClient();

  const queryKey = [
    ...PR_REVIEW_QUERY_KEY,
    "workspace",
    String(workspaceId),
    "pr",
    String(prNumber),
  ] as const;

  const query = useQuery<WorkspacePrResponse, PrReviewApiError>({
    queryKey,
    enabled,
    queryFn: ({ signal }) => getWorkspacePr(workspaceId, prNumber, { signal }),
    retry: false,
    staleTime: 30_000,
  });

  // The PR primary key is the DB id (different from pr_number on GitHub).
  // The backend response carries it on `pr.id`; mutations key off it.
  const prId = query.data?.pr?.id;

  const approveMutation = useMutation({
    mutationFn: (body: ApprovePrRequest = {}) => {
      if (prId === undefined || prId === null) {
        throw new Error("pr id is not yet available");
      }
      return approvePr(prId, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const commentMutation = useMutation({
    mutationFn: (body: PostPrCommentRequest) => {
      if (prId === undefined || prId === null) {
        throw new Error("pr id is not yet available");
      }
      return postPrComment(prId, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const mergeMutation = useMutation({
    mutationFn: (body: MergePrRequest) => {
      if (prId === undefined || prId === null) {
        throw new Error("pr id is not yet available");
      }
      return mergePr(prId, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
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
    approve: (body) => approveMutation.mutateAsync(body ?? {}),
    comment: (body) => commentMutation.mutateAsync(body),
    merge: (body) => mergeMutation.mutateAsync(body),
    isApproving: approveMutation.isPending,
    isCommenting: commentMutation.isPending,
    isMerging: mergeMutation.isPending,
  };
}
