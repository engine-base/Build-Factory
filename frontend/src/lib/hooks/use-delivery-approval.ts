/**
 * T-V3-C-45 / F-013 / S-035: React hook bundle for the delivery-approval UI.
 *
 * Provides three first-class flows:
 *   - useDeliveryQuery(workspaceId) — GET /api/workspaces/{id}/delivery
 *   - useApproveDelivery()          — POST /api/workspaces/{id}/delivery/approve
 *   - useSendDeliveryToClient()     — POST /api/workspaces/{id}/delivery/send-client
 *
 * Each mutation invalidates the delivery query on success so the page picks up
 * the new status (approved / sent). Errors surface via the standard react-query
 * isError/error path and are translated to a non-technical toast by the page
 * (see frontend/src/app/(app)/review/delivery/[id]/page.tsx).
 *
 * @screen-id S-035
 * @feature-id F-013,F-015
 * @task-ids T-V3-C-45
 * @entities E-018
 * @phase Phase 1
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  approveWorkspaceDelivery,
  DeliveryApprovalApiError,
  getWorkspaceDelivery,
  sendDeliveryToClient,
  type ApproveDeliveryResponse,
  type DeliveryApprovalRequestOptions,
  type SendClientDeliveryRequest,
  type SendClientDeliveryResponse,
  type WorkspaceDeliveryResponse,
} from "@/lib/api/delivery-approval";

export const DELIVERY_QUERY_KEY = (workspaceId: string) =>
  ["delivery-approval", workspaceId] as const;

export interface UseDeliveryQueryOpts extends DeliveryApprovalRequestOptions {
  /** When false, the query is paused (e.g. while workspaceId is empty). */
  enabled?: boolean;
}

export function useDeliveryQuery(
  workspaceId: string,
  opts: UseDeliveryQueryOpts = {},
): UseQueryResult<WorkspaceDeliveryResponse, DeliveryApprovalApiError> {
  const { enabled = !!workspaceId, ...request } = opts;
  return useQuery<WorkspaceDeliveryResponse, DeliveryApprovalApiError>({
    queryKey: DELIVERY_QUERY_KEY(workspaceId),
    enabled: enabled && !!workspaceId,
    queryFn: ({ signal }) =>
      getWorkspaceDelivery(workspaceId, { ...request, signal }),
    retry: false,
    staleTime: 30_000,
  });
}

export function useApproveDelivery(
  workspaceId: string,
  opts: DeliveryApprovalRequestOptions = {},
): UseMutationResult<
  ApproveDeliveryResponse,
  DeliveryApprovalApiError,
  void
> {
  const queryClient = useQueryClient();
  return useMutation<
    ApproveDeliveryResponse,
    DeliveryApprovalApiError,
    void
  >({
    mutationFn: () => approveWorkspaceDelivery(workspaceId, opts),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: DELIVERY_QUERY_KEY(workspaceId),
      });
    },
  });
}

export function useSendDeliveryToClient(
  workspaceId: string,
  opts: DeliveryApprovalRequestOptions = {},
): UseMutationResult<
  SendClientDeliveryResponse,
  DeliveryApprovalApiError,
  SendClientDeliveryRequest | void
> {
  const queryClient = useQueryClient();
  return useMutation<
    SendClientDeliveryResponse,
    DeliveryApprovalApiError,
    SendClientDeliveryRequest | void
  >({
    mutationFn: (body) =>
      sendDeliveryToClient(workspaceId, (body ?? {}) as SendClientDeliveryRequest, opts),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: DELIVERY_QUERY_KEY(workspaceId),
      });
    },
  });
}
