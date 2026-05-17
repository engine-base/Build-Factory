/**
 * T-V3-C-60 / S-030 — Ticket-mandated path alias for the task-detail typed API
 * client. The canonical implementation lives at
 * `frontend/src/api/task-detail.ts` (co-located with the other src/api/*
 * clients, resolvable via the `@/api/task-detail` TS path alias). This module
 * re-exports the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[3]`.
 */

export {
  TASK_COMMENTS_ENDPOINT_PATTERN,
  TASK_DETAIL_ENDPOINT_PATTERN,
  TASK_PLAY_ENDPOINT_PATTERN,
  TaskDetailApiError,
  assertAllEarsValid,
  detectEarsForm,
  getTaskDetail,
  playTask,
  postTaskComment,
  putTask,
  taskCommentsEndpoint,
  taskDetailEndpoint,
  taskPlayEndpoint,
  type AcceptanceCriterion,
  type EarsForm,
  type PlayTaskRequest,
  type PlayTaskResponse,
  type PostTaskCommentRequest,
  type PostTaskCommentResponse,
  type PutTaskRequest,
  type PutTaskResponse,
  type SessionSummary,
  type TaskComment,
  type TaskDetailRequestOptions,
  type TaskDetailResponse,
  type TaskView,
} from "../../src/api/task-detail";
