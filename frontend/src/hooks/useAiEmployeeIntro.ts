/**
 * T-V3-C-41 / S-050 / F-027: Data-fetching hook for the AI 社員紹介 onboarding
 * page. Mediates the typed onboarding client behind a `view` machine so the
 * page can satisfy the STATE-DRIVEN AC (AC-F2 skeleton swap) and the UNWANTED
 * AC (AC-F1 401 -> redirect to /login) without leaking workspace data.
 *
 * The hook is intentionally network-light: S-050 is informational and the
 * persona catalog is static. We call GET /api/me/onboarding only to verify
 * the session is still alive (401 -> redirect /login).
 *
 * EARS AC mapping (逐語):
 *   functional.AC-F1: UNWANTED unauthenticated -> `view === "unauthorized"`
 *     (consumer redirects to /login and renders zero workspace data).
 *   functional.AC-F2: STATE-DRIVEN — view starts "loading" with skeleton
 *     metadata, then atomically flips to "loaded" once data arrives.
 *
 * The hook does not own redirection (DI-friendly for tests); the page wires
 * `useEffect(() => { if (view === "unauthorized") router.replace("/login") })`.
 */

import * as React from "react";

import {
  ONBOARDING_GET_ENDPOINT,
  OnboardingApiError,
  type OnboardingStateResponse,
  getOnboardingState,
} from "@/api/onboarding";

export type AiEmployeeIntroView =
  | "loading"
  | "loaded"
  | "unauthorized"
  | "error";

export interface UseAiEmployeeIntroResult {
  view: AiEmployeeIntroView;
  state: OnboardingStateResponse | null;
  /** Friendly, non-technical error message for AC-F1 (toast/banner). */
  errorMessage: string | null;
  /** Imperative refetch — used by error-recovery buttons. */
  refetch: () => Promise<void>;
}

export interface UseAiEmployeeIntroOptions {
  /** Test seam — overrides global fetch via the typed client. */
  fetchImpl?: typeof fetch;
  /** Bearer token override (defaults: localStorage `bf.access_token`). */
  authToken?: string | null;
}

/** localStorage key the Build-Factory auth flow uses for the access token. */
const STORAGE_AUTH_TOKEN_KEY = "bf.access_token";

function readAuthTokenFromStorage(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Drives the S-050 view state machine.
 *
 * - On mount: GET /api/me/onboarding (token discovery: explicit > localStorage)
 * - 200/204 -> view="loaded"
 * - 401      -> view="unauthorized" (consumer redirects to /login)
 * - other    -> view="error" with non-technical errorMessage
 */
export function useAiEmployeeIntro(
  options: UseAiEmployeeIntroOptions = {},
): UseAiEmployeeIntroResult {
  const { fetchImpl, authToken: authTokenOverride } = options;
  const [view, setView] = React.useState<AiEmployeeIntroView>("loading");
  const [state, setState] = React.useState<OnboardingStateResponse | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  // Stable token computation across renders so refetch() does not capture
  // stale closures. `authTokenOverride === undefined` means "use storage".
  const resolvedAuthToken = React.useMemo<string | null>(() => {
    if (authTokenOverride !== undefined) return authTokenOverride;
    return readAuthTokenFromStorage();
  }, [authTokenOverride]);

  const fetchOnce = React.useCallback(
    async (signal?: AbortSignal): Promise<void> => {
      try {
        const res = await getOnboardingState({
          signal,
          authToken: resolvedAuthToken,
          fetchImpl,
        });
        setState(res ?? {});
        setErrorMessage(null);
        setView("loaded");
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        if (err instanceof OnboardingApiError) {
          if (err.status === 401) {
            // AC-F1 (UNWANTED): unauthenticated visitor — bubble the state up
            // to the page so it can redirect to /login WITHOUT rendering any
            // workspace-scoped data first.
            setState(null);
            setErrorMessage(err.toUserMessage());
            setView("unauthorized");
            return;
          }
          setErrorMessage(err.toUserMessage());
        } else {
          setErrorMessage(`通信に失敗しました (${ONBOARDING_GET_ENDPOINT})`);
        }
        setState(null);
        setView("error");
      }
    },
    [fetchImpl, resolvedAuthToken],
  );

  React.useEffect(() => {
    const ctrl = new AbortController();
    let alive = true;
    (async () => {
      if (!alive) return;
      await fetchOnce(ctrl.signal);
    })();
    return () => {
      alive = false;
      ctrl.abort();
    };
  }, [fetchOnce]);

  const refetch = React.useCallback(async (): Promise<void> => {
    setView("loading");
    setErrorMessage(null);
    await fetchOnce();
  }, [fetchOnce]);

  return { view, state, errorMessage, refetch };
}
