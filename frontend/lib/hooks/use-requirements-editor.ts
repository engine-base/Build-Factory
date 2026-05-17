/**
 * T-V3-C-47 / S-021 — Ticket-mandated path alias for the requirements_editor
 * TanStack Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useRequirementsEditor.ts` (which co-locates with the other
 * src/hooks/* hooks), so this module re-exports the public surface to satisfy
 * the work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  REQUIREMENTS_QUERY_KEY,
  useRequirementsEditor,
  type UseRequirementsEditorResult,
} from "../../src/hooks/useRequirementsEditor";
