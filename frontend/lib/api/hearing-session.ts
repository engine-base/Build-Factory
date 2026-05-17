/**
 * T-V3-C-46 / S-020 — Ticket-mandated path alias for the hearing_session
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/hearing-session.ts` (which co-locates with the other
 * src/api/* clients), so this module simply re-exports the public surface
 * to satisfy the work_package_boundary path in
 * tickets-group-c-ui-part2.json.
 */

export {
  HearingSessionApiError,
  buildHearingWsUrl,
  hearingSaveEndpoint,
  hearingWsEndpoint,
  parseHearingStreamEvent,
  saveHearing,
  type HearingChatMessage,
  type HearingSaveRequest,
  type HearingSaveResponse,
  type HearingSessionRequestOptions,
  type HearingSlotState,
  type HearingStreamEvent,
  type HearingWsOptions,
} from "../../src/api/hearing-session";
