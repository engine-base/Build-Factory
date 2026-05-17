/**
 * T-V3-C-57-2 / S-027 — Ticket-mandated path alias for kanban-move API client.
 *
 * Canonical lives at `frontend/src/lib/api/kanban-move.ts`.
 * This re-export satisfies the `work_package_boundary.editable` path
 * declared in tickets-group-c-ui-part2.json::files_changed[3].
 */

export {
  moveTask,
  playTask,
  KanbanMoveError,
  KANBAN_STATUS_BY_COLUMN,
} from "@/lib/api/kanban-move";
export type {
  KanbanColumn,
  MoveTaskRequest,
  MoveTaskResponse,
} from "@/lib/api/kanban-move";
