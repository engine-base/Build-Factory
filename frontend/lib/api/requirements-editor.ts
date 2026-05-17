/**
 * T-V3-C-47 / S-021 — Ticket-mandated path alias for the requirements_editor
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/requirements-editor.ts` (which co-locates with the other
 * src/api/* clients), so this module simply re-exports the public surface to
 * satisfy the work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  EARS_FORMS,
  EarsValidationError,
  RequirementsApiError,
  createRequirementsVersion,
  detectEarsForm,
  getRequirements,
  putRequirements,
  requirementsListEndpoint,
  requirementsPutEndpoint,
  requirementsVersionsEndpoint,
  validateRequirementItems,
  type EarsForm,
  type RequirementItem,
  type RequirementsClientOptions,
  type RequirementsListResponse,
  type RequirementsPutPayload,
  type RequirementsPutResponse,
  type RequirementsVersionCreatePayload,
  type RequirementsVersionCreateResponse,
} from "../../src/api/requirements-editor";
