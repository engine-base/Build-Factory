/**
 * T-V3-C-54 / S-045 — useServerError500 hook.
 *
 * Wraps {@link getServerErrorContext} with TanStack Query so the page only
 * deals with `data` / `isLoading` / `refetch`.
 *
 * AC mapping (T-V3-C-54):
 *   AC-F1 (UNWANTED 401 → redirect to /login) — surfaced via
 *     {@link ServerError500ApiError.status}.
 *   AC-F2 (STATE-DRIVEN skeleton)              — the page reads
 *     {@link UseServerError500Result.isLoading}.
 */

"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getServerErrorContext,
  type ServerErrorContextRequest,
  type ServerErrorContextResponse,
} from "@/api/server-error-500";

/** TanStack Query key namespace for the server-error-500 feature. */
export const SERVER_ERROR_500_QUERY_KEY = ["server-error-500", "context"] as const;

export interface UseServerError500Options {
  /** Optional error_id surfaced by the React error boundary. */
  errorId?: string | null;
  /** Disable the underlying query (e.g. when no error_id is known). */
  enabled?: boolean;
}

export interface UseServerError500Result {
  data: ServerErrorContextResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
}

/**
 * useServerError500 — query the optional `/api/system/error-context` endpoint
 * to enrich the static 500 page with the originating error_id, timestamp,
 * and path (mock fields).
 */
export function useServerError500(
  options: UseServerError500Options = {},
): UseServerError500Result {
  const { errorId = null, enabled = true } = options;

  const query = useQuery({
    queryKey: [...SERVER_ERROR_500_QUERY_KEY, errorId] as const,
    queryFn: ({ signal }) => {
      const req: ServerErrorContextRequest = errorId
        ? { errorId }
        : {};
      return getServerErrorContext(req, { signal });
    },
    enabled,
    retry: false,
    staleTime: 0,
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: () => query.refetch(),
  };
}
