/**
 * T-V3-C-59 / S-029 — Ticket-mandated path alias for the task-dag-view
 * React hook. The canonical implementation lives at
 * `frontend/src/hooks/use-task-dag-view.ts` because the Build-Factory
 * Next.js 16 project uses the `src/` root (see `frontend/tsconfig.json`
 * `paths`: `"@/*": ["./src/*"]`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[2]` and
 * `work_package_boundary.editable[2]`.
 *
 * Re-exports the canonical hook so tooling that imports from this path
 * resolves the same module as the page + typed client.
 */

export {
  useTaskDagView,
  type UseTaskDagViewResult,
} from "../../src/hooks/use-task-dag-view";
