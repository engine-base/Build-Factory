/**
 * T-V3-C-57-1 / S-027 — Ticket-mandated path alias for the Column
 * component. The canonical implementation lives at
 * `frontend/src/components/kanban/Column.tsx` because the Build-Factory
 * Next.js 15 project uses the `src/` root (see `frontend/tsconfig.json`
 * `paths`: `"@/*": ["./src/*"]`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[5]` and
 * `work_package_boundary.editable[5]`.
 *
 * Re-exports the canonical component so tooling that imports from this path
 * resolves the same implementation as the AccordionBoard.
 */

export {
  Column,
  COLUMN_LABELS,
  type KanbanColumnViewProps,
} from "../../src/components/kanban/Column";
