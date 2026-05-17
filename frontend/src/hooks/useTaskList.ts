/**
 * T-V3-C-58 / S-028 — タスクリスト TanStack Query hook.
 *
 * Wraps {@link getWorkspaceTasks} + {@link bulkPlayTasks} / {@link bulkArchiveTasks}
 * so the page only deals with `data` / `isLoading` / mutations.
 *
 * AC mapping (docs/audit/2026-05-16_v3/T-V3-C-58.md):
 *   AC-F1: GET /api/workspaces/{id}/tasks on mount; 2xx → render, 4xx → error
 *          surfaced via {@link TaskListApiError}.
 *   AC-F2: 401 → page redirect to /login (surfaced via TaskListApiError.status).
 *   AC-F3: GET /api/workspaces/{id}/tasks?group_by=feature returns accordion-friendly
 *          `groups` metadata.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bulkArchiveTasks,
  bulkPlayTasks,
  getWorkspaceTasks,
  type BulkArchiveRequest,
  type BulkArchiveResponse,
  type BulkPlayRequest,
  type BulkPlayResponse,
  type GetWorkspaceTasksParams,
  type TaskListApiError,
  type WorkspaceTasksResponse,
} from "@/api/task-list";

/** TanStack Query key namespace for the task-list feature. */
export const TASK_LIST_QUERY_KEY = ["task-list"] as const;

export interface UseTaskListParams {
  workspaceId: number | string;
  /** When set, requests `?group_by=<value>` for AC-F3 accordion mode. */
  groupBy?: GetWorkspaceTasksParams["group_by"];
  filter?: string;
  /** When false, the GET query is held off — useful for unauth gating. */
  enabled?: boolean;
}

export interface UseTaskListResult {
  data: WorkspaceTasksResponse | undefined;
  isLoading: boolean;
  isPending: boolean;
  isError: boolean;
  error: TaskListApiError | unknown;
  isSuccess: boolean;
  refetch: () => Promise<unknown>;
  bulkPlay: (body: BulkPlayRequest) => Promise<BulkPlayResponse>;
  bulkArchive: (body: BulkArchiveRequest) => Promise<BulkArchiveResponse>;
  isBulkPlaying: boolean;
  isBulkArchiving: boolean;
}

/**
 * useTaskList — query + mutations for the S-028 タスクリスト screen.
 *
 * Test seam: the hook uses the default fetch (resolved inside @/api/task-list),
 * so vitest tests can mock `globalThis.fetch` to simulate 200 / 401 / 403 paths.
 */
export function useTaskList(params: UseTaskListParams): UseTaskListResult {
  const { workspaceId, groupBy, filter, enabled = true } = params;
  const qc = useQueryClient();

  const queryKey = [
    ...TASK_LIST_QUERY_KEY,
    "workspace",
    String(workspaceId),
    "group_by",
    groupBy ?? null,
    "filter",
    filter ?? null,
  ] as const;

  const query = useQuery<WorkspaceTasksResponse, TaskListApiError>({
    queryKey,
    enabled,
    queryFn: ({ signal }) =>
      getWorkspaceTasks(
        workspaceId,
        { group_by: groupBy, filter },
        { signal },
      ),
    retry: false,
    staleTime: 10_000,
  });

  const bulkPlayMutation = useMutation({
    mutationFn: (body: BulkPlayRequest) => bulkPlayTasks(workspaceId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASK_LIST_QUERY_KEY });
    },
  });

  const bulkArchiveMutation = useMutation({
    mutationFn: (body: BulkArchiveRequest) =>
      bulkArchiveTasks(workspaceId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASK_LIST_QUERY_KEY });
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
    bulkPlay: (body) => bulkPlayMutation.mutateAsync(body),
    bulkArchive: (body) => bulkArchiveMutation.mutateAsync(body),
    isBulkPlaying: bulkPlayMutation.isPending,
    isBulkArchiving: bulkArchiveMutation.isPending,
  };
}
