/**
 * T-V3-C-40 / S-049 — useWorkspaceSetupWizard hook.
 *
 * Encapsulates the wizard's data-fetch state-machine so the page component
 * (frontend/src/app/(onboarding)/project-setup/page.tsx) stays presentational.
 *
 * State machine matches screens.json[S-049].states: loading | loaded | error.
 *
 * AC mapping:
 *   - functional.AC-F2 (skeleton loader while data is being fetched)
 *       → returns `view: "loading"` until GET /api/me/onboarding resolves.
 *       The page renders <SkeletonLoader role="status" aria-live="polite" />.
 *   - functional.AC-F1 (redirect unauthenticated visitors to /login)
 *       → on 401 from GET /api/me/onboarding, exposes
 *         `requiresAuth: true` so the page can router.push(LOGIN_REDIRECT_PATH).
 *       Pre-fetch, the hook checks hasAccessToken() and short-circuits
 *       directly into the redirect state.
 */

import * as React from "react";

import {
  type OnboardingState,
  type OnboardingAdvanceResponse,
  type WorkspaceSetupWizardPayload,
  OnboardingApiError,
  advanceOnboarding,
  getOnboardingState,
  hasAccessToken,
  skipOnboarding,
} from "@/api/onboarding";

export type WizardView = "loading" | "loaded" | "error";

/** The wizard always advances out of the project_setup step (Step 2 / 3). */
const WIZARD_STEP_KEY = "project_setup" as const;

export interface UseWorkspaceSetupWizardResult {
  /** State-machine view; mirrors screens.json[S-049].states. */
  view: WizardView;
  /** Server state once loaded. */
  state: OnboardingState | null;
  /** Error captured during the initial fetch (for the error pane). */
  error: OnboardingApiError | null;
  /** `true` when the user must be redirected to /login (AC-F1). */
  requiresAuth: boolean;
  /** Whether the advance mutation is in-flight (disables the submit button). */
  isAdvancing: boolean;
  /** Latest error from the advance mutation (for inline toast). */
  advanceError: OnboardingApiError | null;
  /** Last successful advance response (e.g. for telemetry / dev panel). */
  lastAdvance: OnboardingAdvanceResponse | null;
  /** Submit handler for the wizard form. */
  submit: (
    payload: WorkspaceSetupWizardPayload,
  ) => Promise<OnboardingAdvanceResponse>;
  /** Manual refetch (used by the error pane retry button). */
  refetch: () => void;
}

export function useWorkspaceSetupWizard(): UseWorkspaceSetupWizardResult {
  const [view, setView] = React.useState<WizardView>("loading");
  const [state, setState] = React.useState<OnboardingState | null>(null);
  const [error, setError] = React.useState<OnboardingApiError | null>(null);
  const [requiresAuth, setRequiresAuth] = React.useState<boolean>(false);
  const [isAdvancing, setIsAdvancing] = React.useState<boolean>(false);
  const [advanceError, setAdvanceError] =
    React.useState<OnboardingApiError | null>(null);
  const [lastAdvance, setLastAdvance] =
    React.useState<OnboardingAdvanceResponse | null>(null);
  const [fetchToken, setFetchToken] = React.useState<number>(0);

  React.useEffect(() => {
    let cancelled = false;

    // Client-side auth pre-check (AC-F1, UNWANTED): bail early before hitting
    // the network if we already know there is no token.
    if (typeof window !== "undefined" && !hasAccessToken()) {
      setRequiresAuth(true);
      // Keep view = "loading" so the page renders nothing workspace-scoped
      // until the parent redirects.
      return () => {
        cancelled = true;
      };
    }

    setView("loading");
    setError(null);

    (async () => {
      try {
        const next = await getOnboardingState();
        if (cancelled) return;
        setState(next);
        setView("loaded");
      } catch (err) {
        if (cancelled) return;
        if (err instanceof OnboardingApiError) {
          if (err.status === 401) {
            setRequiresAuth(true);
            return;
          }
          setError(err);
        } else {
          setError(
            new OnboardingApiError(
              "NETWORK_ERROR",
              "fetch failed",
              0,
              "/api/me/onboarding",
            ),
          );
        }
        setView("error");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [fetchToken]);

  const submit = React.useCallback(
    async (payload: WorkspaceSetupWizardPayload) => {
      setIsAdvancing(true);
      setAdvanceError(null);
      try {
        const resp = await advanceOnboarding({
          step: WIZARD_STEP_KEY,
          payload: payload as unknown as Record<string, unknown>,
        });
        setLastAdvance(resp);
        return resp;
      } catch (err) {
        if (err instanceof OnboardingApiError) {
          if (err.status === 401) {
            setRequiresAuth(true);
          }
          setAdvanceError(err);
        } else {
          setAdvanceError(
            new OnboardingApiError(
              "NETWORK_ERROR",
              "fetch failed",
              0,
              "/api/me/onboarding/advance",
            ),
          );
        }
        throw err;
      } finally {
        setIsAdvancing(false);
      }
    },
    [],
  );

  const refetch = React.useCallback(() => {
    setFetchToken((n) => n + 1);
  }, []);

  return {
    view,
    state,
    error,
    requiresAuth,
    isAdvancing,
    advanceError,
    lastAdvance,
    submit,
    refetch,
  };
}

// Re-export skip helper for the wizard's "後で" affordance.
export { skipOnboarding };
