/**
 * T-V3-C-58 / S-028 — Ticket-mandated path alias for the task_list TanStack
 * Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useTaskList.ts` (co-located with the other src/hooks/*
 * hooks, resolvable via the `@/hooks/useTaskList` TS path alias). This module
 * re-exports the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[2]`.
 */

export {
  TASK_LIST_QUERY_KEY,
  useTaskList,
  type UseTaskListParams,
  type UseTaskListResult,
} from "../../src/hooks/useTaskList";
