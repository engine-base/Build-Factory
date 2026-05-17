/**
 * T-V3-C-55 / S-046: Hook driving the forbidden_403 page.
 *
 * Responsibilities:
 *  - Issue GET /api/me via the typed client and surface 4xx errors
 *    as a non-technical toast / state for the page (AC-F1 / AC-F2).
 *  - Expose a mutation that POSTs the "request access" CTA payload.
 *  - Detect 401 responses and bubble an `unauthenticated` flag so the page
 *    can redirect to /login (S-001) (AC-F1).
 *
 * EARS AC mapping (T-V3-C-55):
 *   functional.AC-F1: UNWANTED unauthenticated -> redirect to /login (S-001).
 *   functional.AC-F2: STATE-DRIVEN — `isLoading` boundary swaps skeleton.
 */

"use client";

import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  ForbiddenApiError,
  ME_ENDPOINT,
  type MeResponse,
  type RoleKey,
  type RoleRequestPayload,
  type RoleRequestResponse,
  fetchMe,
  postRoleRequest,
} from "@/lib/api/forbidden-403";

export interface UseForbidden403Options {
  /** Required role label rendered on the explanation card (mock 逐語). */
  requiredRole?: RoleKey;
}

export interface UseForbidden403Result {
  /** Current actor (role / workspace_id). */
  data?: MeResponse;
  /** True while GET /api/me is in flight. AC-F2 skeleton boundary. */
  isLoading: boolean;
  /** Any error from GET /api/me. */
  isError: boolean;
  error: unknown;
  /** Convenience flag set by the hook when GET /api/me returns 401. */
  unauthenticated: boolean;
  /** Trigger the "request access" CTA. */
  requestAccess: (payload?: Partial<RoleRequestPayload>) => Promise<void>;
  /** True while POST /api/workspaces/{id}/role-requests is in flight. */
  isRequestingAccess: boolean;
  /** Whether the request access CTA succeeded (idempotent state for UI). */
  isAccessRequested: boolean;
  /** Backing response from the POST CTA, if any. */
  requestResponse?: RoleRequestResponse;
}

const DEFAULT_REQUIRED_ROLE: RoleKey = "workspace_admin";

export function useForbidden403(
  options: UseForbidden403Options = {},
): UseForbidden403Result {
  const requiredRole = options.requiredRole ?? DEFAULT_REQUIRED_ROLE;

  // GET /api/me — boundary of skeleton / content.
  const query = useQuery<MeResponse, ForbiddenApiError>({
    queryKey: [ME_ENDPOINT],
    queryFn: () => fetchMe(),
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });

  const unauthenticated =
    query.isError &&
    query.error instanceof ForbiddenApiError &&
    query.error.status === 401;

  // POST /api/workspaces/{id}/role-requests — "request access" CTA.
  const [accessRequested, setAccessRequested] = React.useState(false);
  const mutation = useMutation<
    RoleRequestResponse,
    ForbiddenApiError,
    RoleRequestPayload
  >({
    mutationFn: async (payload) => {
      const workspaceId = query.data?.workspace_id;
      if (!workspaceId || workspaceId <= 0) {
        // No active workspace — surface a typed error so the page can render
        // a non-technical toast instead of leaking a stack trace.
        throw new ForbiddenApiError(
          "NO_ACTIVE_WORKSPACE",
          "アクティブな案件が選択されていません。",
          400,
          "client",
        );
      }
      return postRoleRequest(workspaceId, payload);
    },
    onSuccess: () => setAccessRequested(true),
  });

  const requestAccess = React.useCallback(
    async (payloadOverride?: Partial<RoleRequestPayload>) => {
      const payload: RoleRequestPayload = {
        message: payloadOverride?.message ?? null,
        requested_role: payloadOverride?.requested_role ?? requiredRole,
      };
      await mutation.mutateAsync(payload);
    },
    [mutation, requiredRole],
  );

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    unauthenticated,
    requestAccess,
    isRequestingAccess: mutation.isPending,
    isAccessRequested: accessRequested,
    requestResponse: mutation.data,
  };
}
