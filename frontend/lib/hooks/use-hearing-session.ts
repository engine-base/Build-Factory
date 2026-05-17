/**
 * T-V3-C-46 / S-020 — Ticket-mandated path alias for the hearing_session
 * hook. The canonical implementation lives at
 * `frontend/src/hooks/useHearingSession.ts` (which co-locates with the other
 * src/hooks/* hooks), so this module re-exports the public surface to
 * satisfy the work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  useHearingSession,
  type HearingReadyState,
  type UseHearingSessionParams,
  type UseHearingSessionResult,
} from "../../src/hooks/useHearingSession";
