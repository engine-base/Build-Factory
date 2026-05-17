/**
 * T-V3-C-50 / S-024 — Component Catalog hook.
 *
 * Wraps {@link getComponents} / {@link getComponentUsage} with TanStack Query
 * so the page only reads `data` / `isLoading` / `selectedUsage`.
 *
 * AC mapping (3-tier):
 *   AC-F1 (EVENT-DRIVEN): on mount the hook fires GET
 *     /api/workspaces/{id}/components; 4xx → page reads `isError` and surfaces
 *     a toast + empty state.
 *   AC-F2 (UNWANTED): when no auth token is available, the query is disabled
 *     (the page is responsible for the /login redirect). The hook never
 *     fetches workspace-scoped data for anon visitors.
 *   AC-F3 (EVENT-DRIVEN): {@link selectComponent} fires GET
 *     /api/workspaces/{id}/components/{id}/usage on demand.
 */

"use client";

import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type Component,
  type ComponentUsage,
  type GetComponentUsageResponse,
  type GetComponentsResponse,
  getComponentUsage,
  getComponents,
} from "@/api/components";

/** TanStack Query key namespace for the components feature. */
export const COMPONENTS_QUERY_KEY = ["components"] as const;
export const COMPONENT_USAGE_QUERY_KEY = ["components", "usage"] as const;

export interface UseComponentCatalogArgs {
  workspaceId: string | null;
  authToken: string | null;
}

export interface UseComponentCatalogResult {
  components: Component[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
  /** Selected component id (null until the user clicks a card). */
  selectedComponentId: string | null;
  selectComponent: (componentId: string | null) => void;
  usage: ComponentUsage[];
  isUsageLoading: boolean;
  isUsageError: boolean;
  usageError: unknown;
}

/**
 * useComponentCatalog — query for S-024 component grid + lazy usage lookup.
 *
 * Test seam: the underlying `@/api/components` module uses the global fetch,
 * so vitest tests can mock `globalThis.fetch` to simulate 401 / 200 paths.
 */
export function useComponentCatalog(
  args: UseComponentCatalogArgs,
): UseComponentCatalogResult {
  const { workspaceId, authToken } = args;
  const qc = useQueryClient();
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(
    null,
  );

  const enabled = !!workspaceId && !!authToken;

  const listQuery = useQuery<GetComponentsResponse>({
    queryKey: [...COMPONENTS_QUERY_KEY, workspaceId ?? "__none__"],
    queryFn: ({ signal }) =>
      getComponents(workspaceId as string, {
        authToken,
        signal,
      }),
    enabled,
    retry: false,
    staleTime: 30_000,
  });

  const usageQuery = useQuery<GetComponentUsageResponse>({
    queryKey: [
      ...COMPONENT_USAGE_QUERY_KEY,
      workspaceId ?? "__none__",
      selectedComponentId ?? "__none__",
    ],
    queryFn: ({ signal }) =>
      getComponentUsage(workspaceId as string, selectedComponentId as string, {
        authToken,
        signal,
      }),
    enabled: enabled && !!selectedComponentId,
    retry: false,
    staleTime: 30_000,
  });

  const refetch = useCallback(async () => {
    if (!enabled) return;
    await qc.invalidateQueries({ queryKey: COMPONENTS_QUERY_KEY });
    if (selectedComponentId) {
      await qc.invalidateQueries({ queryKey: COMPONENT_USAGE_QUERY_KEY });
    }
  }, [enabled, qc, selectedComponentId]);

  const selectComponent = useCallback((componentId: string | null) => {
    setSelectedComponentId(componentId);
  }, []);

  const components = useMemo<Component[]>(
    () => listQuery.data?.components ?? [],
    [listQuery.data],
  );
  const usage = useMemo<ComponentUsage[]>(
    () => usageQuery.data?.usages ?? [],
    [usageQuery.data],
  );

  return {
    components,
    isLoading: listQuery.isLoading,
    isError: listQuery.isError,
    error: listQuery.error,
    refetch,
    selectedComponentId,
    selectComponent,
    usage,
    isUsageLoading: usageQuery.isLoading,
    isUsageError: usageQuery.isError,
    usageError: usageQuery.error,
  };
}
