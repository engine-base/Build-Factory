/**
 * T-V3-C-39 / S-048 — Ticket-mandated path alias for the welcome_first_login
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/onboarding.ts` (which co-locates with the other src/api/
 * clients), so this module simply re-exports the public surface to satisfy
 * the work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  ONBOARDING_ADVANCE_ENDPOINT,
  ONBOARDING_ENDPOINT,
  ONBOARDING_SKIP_ENDPOINT,
  OnboardingApiError,
  advanceOnboarding,
  getOnboardingState,
  skipOnboarding,
  type AdvanceRequest,
  type AdvanceResponse,
  type OnboardingRequestOptions,
  type OnboardingStateResponse,
  type SkipRequest,
  type SkipResponse,
} from "../../src/api/onboarding";
