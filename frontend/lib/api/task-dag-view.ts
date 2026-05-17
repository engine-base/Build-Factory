/**
 * T-V3-C-59 / S-029 — Ticket-mandated path alias for the task-dag-view
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/task-dag.ts` because the Build-Factory Next.js 16
 * project uses the `src/` root (see `frontend/tsconfig.json` `paths`:
 * `"@/*": ["./src/*"]`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[3]` and
 * `work_package_boundary.editable[3]`.
 *
 * Re-exports the canonical typed client so tooling that imports from this
 * path resolves the same module as the hook + page.
 */

export {
  createTaskDependency,
  dependencyCreateEndpoint,
  getTaskDag,
  getTasksByFeature,
  impactAnalysisEndpoint,
  runImpactAnalysis,
  taskDagEndpoint,
  tasksByFeatureEndpoint,
  TaskDagApiError,
  type DependencyCreatePayload,
  type DependencyCreateResponse,
  type ImpactAnalysisAffectedTask,
  type ImpactAnalysisPayload,
  type ImpactAnalysisResponse,
  type TaskDagClientOptions,
  type TaskDagEdge,
  type TaskDagNode,
  type TaskDagResponse,
  type TasksByFeatureGroup,
  type TasksByFeatureResponse,
} from "../../src/api/task-dag";
