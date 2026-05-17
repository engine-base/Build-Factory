/**
 * T-V3-C-55 / S-046 — Ticket-mandated path alias for the forbidden_403
 * typed API client. The canonical implementation lives at
 * `frontend/src/lib/api/forbidden-403.ts`. This file is a thin re-export to
 * satisfy `tickets-group-c-ui-part2.json::files_changed[3]` and the editable
 * boundary; it must not contain any business logic.
 */

export {
  ForbiddenApiError,
  ME_ENDPOINT,
  ROLE_REQUEST_ENDPOINT_PREFIX,
  fetchMe,
  postRoleRequest,
  type MeResponse,
  type RoleKey,
  type RoleRequestPayload,
  type RoleRequestResponse,
} from "../../src/lib/api/forbidden-403";
