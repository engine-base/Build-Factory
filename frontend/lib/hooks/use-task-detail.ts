/**
 * T-V3-C-60 / S-030 — Ticket-mandated path alias for the task-detail TanStack
 * Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useTaskDetail.ts`. This module re-exports the public
 * surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[2]`.
 */

export {
  TASK_DETAIL_QUERY_KEY,
  useTaskDetail,
  type UseTaskDetailParams,
  type UseTaskDetailResult,
} from "../../src/hooks/useTaskDetail";
