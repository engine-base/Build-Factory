/**
 * T-V3-C-57-1 / S-027 — Ticket-mandated path alias for the kanban-board
 * React hook. The canonical implementation lives at
 * `frontend/src/hooks/use-kanban-board.ts` because the Build-Factory
 * Next.js 15 project uses the `src/` root (see `frontend/tsconfig.json`
 * `paths`: `"@/*": ["./src/*"]`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[2]` and
 * `work_package_boundary.editable[2]`.
 *
 * Re-exports the canonical hook so tooling that imports from this path
 * resolves the same implementation as the page.
 */

export {
  aggregateKanban,
  useKanbanBoard,
  type KanbanColumnTasks,
  type KanbanFeatureSection,
  type UseKanbanBoardResult,
} from "../../src/hooks/use-kanban-board";
