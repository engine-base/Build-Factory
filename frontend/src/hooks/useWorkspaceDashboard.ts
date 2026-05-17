/**
 * T-V3-C-61 / S-012 / F-006,F-007,F-008,F-026 — React hook backing the
 * 案件ダッシュボード page. Wraps `getWorkspaceDashboard` with React state and
 * surfaces a typed `error` of {@link WorkspaceDashboardApiError} so the page
 * component can render the AC-F1 inline error toast.
 *
 * Auto-refreshes the dashboard payload every `refetchIntervalMs` while the
 * page is mounted (default 30s), matching the swarm-cockpit feel of the
 * S-012 mock. The interval can be disabled with `refetchIntervalMs = 0`.
 */

import * as React from "react";

import {
  WorkspaceDashboardApiError,
  getWorkspaceDashboard,
  type WorkspaceDashboardResponse,
} from "@/api/workspace-dashboard";

export interface UseWorkspaceDashboardParams {
  /** Workspace UUID. When null/empty the hook stays idle. */
  workspaceId: string | null;
  /** Bearer token; null suspends the fetch (caller should redirect to login). */
  authToken: string | null;
  /** Disable the auto-refetch loop entirely (tests). */
  refetchIntervalMs?: number | null;
  /** Test seam — alternate fetch implementation. */
  fetchImpl?: typeof fetch;
}

export interface UseWorkspaceDashboardResult {
  /** Last successful 2xx response body, or null while loading / errored. */
  data: WorkspaceDashboardResponse | null;
  /** Last error encountered. Cleared on a successful refetch. */
  error: WorkspaceDashboardApiError | Error | null;
  /** True until the first fetch attempt (success or failure) completes. */
  isLoading: boolean;
  /** True while a refetch is in flight after the initial load. */
  isRefreshing: boolean;
  /** Manual refresh; returns the new body (or throws). */
  refetch: () => Promise<WorkspaceDashboardResponse | null>;
}

const DEFAULT_REFETCH_INTERVAL_MS = 30_000;

export function useWorkspaceDashboard(
  params: UseWorkspaceDashboardParams,
): UseWorkspaceDashboardResult {
  const { workspaceId, authToken, refetchIntervalMs, fetchImpl } = params;

  const [data, setData] = React.useState<WorkspaceDashboardResponse | null>(
    null,
  );
  const [error, setError] = React.useState<
    WorkspaceDashboardApiError | Error | null
  >(null);
  const [isLoading, setIsLoading] = React.useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = React.useState<boolean>(false);
  const cancelledRef = React.useRef<boolean>(false);
  const fetchedOnceRef = React.useRef<boolean>(false);

  // Stable refs so the timer callback always sees the latest params.
  const workspaceIdRef = React.useRef(workspaceId);
  const authTokenRef = React.useRef(authToken);
  const fetchImplRef = React.useRef(fetchImpl);
  React.useEffect(() => {
    workspaceIdRef.current = workspaceId;
    authTokenRef.current = authToken;
    fetchImplRef.current = fetchImpl;
  }, [workspaceId, authToken, fetchImpl]);

  const runFetch = React.useCallback(
    async (
      withSpinner: boolean,
    ): Promise<WorkspaceDashboardResponse | null> => {
      const wsId = workspaceIdRef.current;
      const token = authTokenRef.current;
      if (!wsId || !token) return null;
      if (withSpinner) {
        if (fetchedOnceRef.current) setIsRefreshing(true);
        else setIsLoading(true);
      }
      try {
        const body = await getWorkspaceDashboard(wsId, {
          authToken: token,
          fetchImpl: fetchImplRef.current,
        });
        if (cancelledRef.current) return body;
        setData(body);
        setError(null);
        return body;
      } catch (err) {
        if (cancelledRef.current) return null;
        if (err instanceof WorkspaceDashboardApiError) {
          setError(err);
        } else if (err instanceof Error) {
          setError(err);
        } else {
          setError(new Error(String(err)));
        }
        return null;
      } finally {
        if (!cancelledRef.current) {
          fetchedOnceRef.current = true;
          setIsLoading(false);
          setIsRefreshing(false);
        }
      }
    },
    [],
  );

  // Reset on workspace / token change.
  React.useEffect(() => {
    if (!workspaceId || !authToken) {
      setData(null);
      setError(null);
      setIsLoading(false);
      return;
    }
    cancelledRef.current = false;
    fetchedOnceRef.current = false;
    setIsLoading(true);
    void runFetch(true);
    return () => {
      cancelledRef.current = true;
    };
  }, [workspaceId, authToken, runFetch]);

  // Auto-refetch loop (paused when interval ≤ 0 or token/workspace missing).
  React.useEffect(() => {
    if (!workspaceId || !authToken) return;
    const interval =
      refetchIntervalMs === null || refetchIntervalMs === undefined
        ? DEFAULT_REFETCH_INTERVAL_MS
        : refetchIntervalMs;
    if (interval <= 0) return;
    if (typeof window === "undefined") return;
    const handle = window.setInterval(() => {
      void runFetch(true);
    }, interval);
    return () => {
      window.clearInterval(handle);
    };
  }, [workspaceId, authToken, refetchIntervalMs, runFetch]);

  return {
    data,
    error,
    isLoading,
    isRefreshing,
    refetch: () => runFetch(true),
  };
}
