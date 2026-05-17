/**
 * T-V3-C-39 / S-048 — Ticket-mandated path alias for the welcome_first_login
 * TanStack Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useWelcomeFirstLogin.ts` (which co-locates with the other
 * src/hooks/* hooks), so this module re-exports the public surface to satisfy
 * the work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  ONBOARDING_QUERY_KEY,
  useWelcomeFirstLogin,
  type UseWelcomeFirstLoginResult,
} from "../../src/hooks/useWelcomeFirstLogin";
