/**
 * T-V3-C-56 / S-047: React hook driving the メンテナンス中 (Maintenance) page.
 *
 * Wraps {@link getMaintenanceStatus} with @tanstack/react-query so the page
 * can:
 *   - call GET /api/system/maintenance on mount (AC-F2 skeleton path)
 *   - expose a typed {@link MaintenanceApiError} for AC-F1 401 redirect
 *
 * The hook does not render anything — it bundles the query state so both
 * the page and the vitest spec can import a single named symbol.
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-56.md):
 *   functional.AC-F1 → `useMaintenance()` surfaces a `MaintenanceApiError`
 *                      with `status === 401` so the page calls
 *                      `router.replace("/login")` without leaking any
 *                      workspace-scoped data.
 *   functional.AC-F2 → `isLoading` drives the skeleton swap; the typed
 *                      result replaces the skeleton atomically once the
 *                      promise resolves.
 *
 * @screen-id S-047
 * @feature-id
 * @task-ids T-V3-C-56
 * @entities
 * @phase Phase 1
 */

"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  MAINTENANCE_STATUS_ENDPOINT,
  MaintenanceApiError,
  getMaintenanceStatus,
  type MaintenanceRequestOptions,
  type MaintenanceStatus,
} from "@/lib/api/maintenance";

/** TanStack Query key for the maintenance status feature. */
export const MAINTENANCE_QUERY_KEY = ["system", "maintenance"] as const;

export interface UseMaintenanceOptions {
  /** Override the typed client (test seam). */
  request?: MaintenanceRequestOptions;
  /** Disable the query (e.g. while waiting for auth). Defaults to true. */
  enabled?: boolean;
}

export interface UseMaintenanceResult
  extends Pick<
    UseQueryResult<MaintenanceStatus, MaintenanceApiError>,
    "data" | "isLoading" | "isError" | "error" | "refetch" | "isFetching"
  > {
  /** Canonical endpoint string the query targets. */
  endpoint: string;
  /** Convenience flag: error is a 401 unauth response. */
  unauthenticated: boolean;
}

/**
 * Drive the S-047 maintenance page.
 *
 * - Retries are disabled because the maintenance status endpoint either
 *   returns 200 (in_progress / scheduled), 401 (sign-in required), or
 *   404 (no active window) — retrying any of these is pointless.
 * - `staleTime` of 30s prevents the page from hammering the API while
 *   the user stares at the ETA progress bar.
 */
export function useMaintenance(
  opts: UseMaintenanceOptions = {},
): UseMaintenanceResult {
  const { request, enabled = true } = opts;

  const result = useQuery<MaintenanceStatus, MaintenanceApiError>({
    queryKey: MAINTENANCE_QUERY_KEY,
    queryFn: ({ signal }) =>
      getMaintenanceStatus({ ...(request ?? {}), signal }),
    enabled,
    retry: false,
    staleTime: 30_000,
  });

  const unauthenticated =
    result.isError &&
    result.error instanceof MaintenanceApiError &&
    result.error.status === 401;

  return {
    data: result.data,
    isLoading: result.isLoading,
    isError: result.isError,
    error: result.error,
    refetch: result.refetch,
    isFetching: result.isFetching,
    endpoint: MAINTENANCE_STATUS_ENDPOINT,
    unauthenticated,
  };
}
