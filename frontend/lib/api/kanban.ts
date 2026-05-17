/**
 * T-V3-C-57-1 / S-027 — Ticket-mandated path alias for the kanban typed
 * API client. The canonical implementation lives at
 * `frontend/src/api/kanban.ts` because the Build-Factory Next.js 15 project
 * uses the `src/` root (see `frontend/tsconfig.json` `paths`:
 * `"@/*": ["./src/*"]`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[3]` and
 * `work_package_boundary.editable[3]`.
 *
 * Re-exports the canonical typed client so tooling that imports from this
 * path resolves the same module as the hook + page.
 */

export {
  KanbanApiError,
  getKanbanTasks,
  kanbanTasksEndpoint,
  normaliseKanbanStatus,
  type KanbanClientOptions,
  type KanbanColumn,
  type KanbanTask,
  type KanbanTaskGroup,
  type KanbanTasksResponse,
} from "../../src/api/kanban";
