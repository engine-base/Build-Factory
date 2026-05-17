/**
 * T-V3-C-58 / S-028 — Ticket-mandated path alias for the task_list typed API
 * client. The canonical implementation lives at
 * `frontend/src/api/task-list.ts` (co-located with the other src/api/* clients,
 * resolvable via the `@/api/task-list` TS path alias). This module re-exports
 * the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[3]`.
 */

export {
  TASK_BULK_ARCHIVE_ENDPOINT_PATTERN,
  TASK_BULK_PLAY_ENDPOINT_PATTERN,
  TASK_LIST_ENDPOINT_PATTERN,
  TaskListApiError,
  bulkArchiveTasks,
  bulkPlayTasks,
  getWorkspaceTasks,
  workspaceBulkArchiveEndpoint,
  workspaceBulkPlayEndpoint,
  workspaceTasksEndpoint,
  type BulkArchiveRequest,
  type BulkArchiveResponse,
  type BulkPlayRequest,
  type BulkPlayResponse,
  type GetWorkspaceTasksParams,
  type TaskGroup,
  type TaskGroupBy,
  type TaskListItem,
  type TaskListRequestOptions,
  type WorkspaceTasksResponse,
} from "../../src/api/task-list";
