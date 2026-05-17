/**
 * T-V3-C-57-2 / S-027 — Ticket-mandated path alias for useTaskDnd.
 *
 * Canonical lives at `frontend/src/lib/hooks/use-task-dnd.ts`.
 * This re-export satisfies the `work_package_boundary.editable` path
 * declared in tickets-group-c-ui-part2.json::files_changed[2].
 */

export {
  useTaskDnd,
  KANBAN_STATUS_BY_COLUMN,
} from "@/lib/hooks/use-task-dnd";
export type {
  KanbanCard,
  DragSource,
  DropOutcome,
  UseTaskDndArgs,
  UseTaskDndResult,
} from "@/lib/hooks/use-task-dnd";
