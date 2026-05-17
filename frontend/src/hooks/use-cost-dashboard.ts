/**
 * T-V3-C-42 / F-017 / S-040: React hook driving the コスト ダッシュボード page.
 *
 * Wraps {@link getCostSummary} with @tanstack/react-query so the page can:
 *   - call GET /api/observability/cost-summary on mount (AC-F1)
 *   - re-fetch when the user changes the date-range filter
 *   - expose a typed `CostDashboardApiError` for the page's toast (AC-F1)
 *
 * The hook intentionally does *not* render anything — it just bundles the
 * query state so the page (and tests) can import a single named symbol.
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-42.md):
 *   functional.AC-F1 → `useCostDashboard()` triggers the GET on mount and
 *                      re-runs whenever `query` changes.
 *   functional.AC-F2 → on 401, react-query surfaces the
 *                      CostDashboardApiError via `error`; the page reads
 *                      `error.toUserMessage()` and renders the empty state.
 *   functional.AC-F3 → the typed `CostSummaryResponse` exposes total_usd +
 *                      by_provider + by_user breakdowns to the page.
 *
 * @screen-id S-040
 * @feature-id F-017
 * @task-ids T-V3-C-42
 * @entities E-027,E-028
 * @phase Phase 1
 */

"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  CostDashboardApiError,
  buildCostSummaryEndpoint,
  getCostSummary,
  type CostDashboardRequestOptions,
  type CostSummaryQuery,
  type CostSummaryResponse,
} from "@/api/cost-dashboard";

export interface UseCostDashboardOptions {
  /** Date range + workspace filter forwarded to the API. */
  query?: CostSummaryQuery;
  /** Override the typed client (mainly a test seam). */
  request?: CostDashboardRequestOptions;
  /** Disable the query (e.g. while waiting for auth). Defaults to true. */
  enabled?: boolean;
}

export interface UseCostDashboardResult
  extends Pick<
    UseQueryResult<CostSummaryResponse, CostDashboardApiError>,
    "data" | "isLoading" | "isError" | "error" | "refetch" | "isFetching"
  > {
  /** Canonical endpoint string the query targets (for toast / debug). */
  endpoint: string;
}

/**
 * Drive the S-040 cost dashboard: fetch summary, expose typed error + endpoint.
 *
 * Default behavior:
 *   - re-keyed by `query` (workspace_id, from, to) so date-range changes
 *     trigger a re-fetch.
 *   - on 401/403 the typed `CostDashboardApiError` is surfaced via `error`.
 *   - the page reads `error.toUserMessage()` for an endpoint-tagged toast
 *     (AC-F1).
 */
export function useCostDashboard(
  opts: UseCostDashboardOptions = {},
): UseCostDashboardResult {
  const { query = {}, request, enabled = true } = opts;
  const endpoint = buildCostSummaryEndpoint(query);

  const result = useQuery<CostSummaryResponse, CostDashboardApiError>({
    queryKey: ["observability", "cost-summary", endpoint],
    queryFn: ({ signal }) =>
      getCostSummary(query, { ...(request ?? {}), signal }),
    enabled,
    retry: (failureCount, error) => {
      // Never retry 4xx — they will not become 2xx on the same input.
      if (
        error instanceof CostDashboardApiError &&
        error.status >= 400 &&
        error.status < 500
      ) {
        return false;
      }
      return failureCount < 2;
    },
    staleTime: 30_000,
  });

  return {
    data: result.data,
    isLoading: result.isLoading,
    isError: result.isError,
    error: result.error,
    refetch: result.refetch,
    isFetching: result.isFetching,
    endpoint,
  };
}
