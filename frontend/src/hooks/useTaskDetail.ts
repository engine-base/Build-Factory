/**
 * T-V3-C-60 / S-030 — タスク詳細 TanStack Query hook.
 *
 * Wraps {@link getTaskDetail} + {@link playTask} / {@link postTaskComment} /
 * {@link putTask} so the page only deals with `data` / `isLoading` / mutations.
 *
 * AC mapping (docs/audit/2026-05-16_v3/T-V3-C-60.md):
 *   AC-F1: GET /api/tasks/{id} on mount; 2xx → render, 4xx → typed error
 *          (surfaced via {@link TaskDetailApiError}).
 *   AC-F2: 401 → page redirect to /login (surfaced via TaskDetailApiError.status).
 *   AC-F5: PUT /api/tasks/{id} pre-validates EARS via @/api/task-detail.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getTaskDetail,
  playTask,
  postTaskComment,
  putTask,
  type PlayTaskRequest,
  type PlayTaskResponse,
  type PostTaskCommentRequest,
  type PostTaskCommentResponse,
  type PutTaskRequest,
  type PutTaskResponse,
  type TaskDetailApiError,
  type TaskDetailResponse,
} from "@/api/task-detail";

/** TanStack Query key namespace for the task-detail feature. */
export const TASK_DETAIL_QUERY_KEY = ["task-detail"] as const;

export interface UseTaskDetailParams {
  taskId: number | string;
  /** When false, the GET query is held off — useful for unauth gating. */
  enabled?: boolean;
}

export interface UseTaskDetailResult {
  data: TaskDetailResponse | undefined;
  isLoading: boolean;
  isPending: boolean;
  isError: boolean;
  error: TaskDetailApiError | unknown;
  isSuccess: boolean;
  refetch: () => Promise<unknown>;
  play: (body?: PlayTaskRequest) => Promise<PlayTaskResponse>;
  comment: (body: PostTaskCommentRequest) => Promise<PostTaskCommentResponse>;
  update: (body: PutTaskRequest) => Promise<PutTaskResponse>;
  isPlaying: boolean;
  isCommenting: boolean;
  isUpdating: boolean;
}

/**
 * useTaskDetail — query + mutations for the S-030 タスク詳細 screen.
 *
 * Test seam: the hook uses the default fetch (resolved inside @/api/task-detail),
 * so vitest tests can mock `globalThis.fetch` to simulate 200 / 401 / 403 paths.
 */
export function useTaskDetail(params: UseTaskDetailParams): UseTaskDetailResult {
  const { taskId, enabled = true } = params;
  const qc = useQueryClient();

  const queryKey = [
    ...TASK_DETAIL_QUERY_KEY,
    "task",
    String(taskId),
  ] as const;

  const query = useQuery<TaskDetailResponse, TaskDetailApiError>({
    queryKey,
    enabled,
    queryFn: ({ signal }) => getTaskDetail(taskId, { signal }),
    retry: false,
    staleTime: 30_000,
  });

  const playMutation = useMutation({
    mutationFn: (body: PlayTaskRequest = {}) => playTask(taskId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const commentMutation = useMutation({
    mutationFn: (body: PostTaskCommentRequest) =>
      postTaskComment(taskId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const updateMutation = useMutation({
    mutationFn: (body: PutTaskRequest) => putTask(taskId, body),
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
    play: (body) => playMutation.mutateAsync(body ?? {}),
    comment: (body) => commentMutation.mutateAsync(body),
    update: (body) => updateMutation.mutateAsync(body),
    isPlaying: playMutation.isPending,
    isCommenting: commentMutation.isPending,
    isUpdating: updateMutation.isPending,
  };
}
