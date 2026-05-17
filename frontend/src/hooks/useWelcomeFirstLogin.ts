/**
 * T-V3-C-39 / S-048 — Welcome First Login hook.
 *
 * Wraps {@link getOnboardingState} / {@link advanceOnboarding} / {@link skipOnboarding}
 * with TanStack Query so the page only deals with `data` / `isLoading` / mutations.
 *
 * AC mapping:
 *   AC-F1 (UNWANTED 401 → redirect to /login) — surfaced via {@link OnboardingApiError.status}
 *   AC-F2 (STATE-DRIVEN loading skeleton)     — page reads {@link UseWelcomeFirstLoginResult.isLoading}
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  advanceOnboarding,
  getOnboardingState,
  skipOnboarding,
  type AdvanceRequest,
  type AdvanceResponse,
  type OnboardingStateResponse,
  type SkipRequest,
  type SkipResponse,
} from "@/api/onboarding";

/** TanStack Query key namespace for the onboarding feature. */
export const ONBOARDING_QUERY_KEY = ["onboarding", "state"] as const;

export interface UseWelcomeFirstLoginResult {
  data: OnboardingStateResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
  advance: (body: AdvanceRequest) => Promise<AdvanceResponse>;
  skip: (body?: SkipRequest) => Promise<SkipResponse>;
  isAdvancing: boolean;
  isSkipping: boolean;
}

/**
 * useWelcomeFirstLogin — query + mutations for the S-048 onboarding screen.
 *
 * Test seam: the hook uses the default fetch (resolved inside @/api/onboarding),
 * so vitest tests can mock `globalThis.fetch` to simulate 401 / 200 paths.
 */
export function useWelcomeFirstLogin(): UseWelcomeFirstLoginResult {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ONBOARDING_QUERY_KEY,
    queryFn: ({ signal }) => getOnboardingState({ signal }),
    retry: false,
    staleTime: 30_000,
  });

  const advanceMutation = useMutation({
    mutationFn: (body: AdvanceRequest) => advanceOnboarding(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ONBOARDING_QUERY_KEY });
    },
  });

  const skipMutation = useMutation({
    mutationFn: (body: SkipRequest = {}) => skipOnboarding(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ONBOARDING_QUERY_KEY });
    },
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: () => query.refetch(),
    advance: (body) => advanceMutation.mutateAsync(body),
    skip: (body) => skipMutation.mutateAsync(body ?? {}),
    isAdvancing: advanceMutation.isPending,
    isSkipping: skipMutation.isPending,
  };
}
