/**
 * T-V3-C-51 / S-025 — Screen Flow Map hook.
 *
 * Lightweight wrapper around {@link getScreenFlow} and {@link getMockHtml}.
 * The dependency-graph page (S-017) prefers ad-hoc React state for ergonomic
 * 401 detection; this hook follows the same pattern so the page can stay
 * provider-independent (no QueryClientProvider required at the (app) layout
 * for the test harness).
 *
 * AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-51.md):
 *   AC-F1 (S-025) — getScreenFlow GET on mount; 4xx → page renders toast + empty.
 *   AC-F2 (S-025) — 401 surfaced via {@link ScreenFlowApiError.status} === 401 so
 *                   the page can router.replace("/login") before any
 *                   workspace-scoped UI is committed.
 *   AC-F3 (S-025) — getMockHtml provides the latest mock html when the user
 *                   clicks a node (drawer preview).
 */

"use client";

import * as React from "react";

import {
  getMockHtml,
  getScreenFlow,
  ScreenFlowApiError,
  type MockHtmlResponse,
  type ScreenFlowResponse,
} from "@/api/screen-flow";

export interface UseScreenFlowMapResult {
  data: ScreenFlowResponse | null;
  loading: boolean;
  error: ScreenFlowApiError | null;
  /** Refetch GET /screen-flow. */
  reload: () => Promise<void>;
  /** AC-F3: fetch the latest html for a screen, surfaces ScreenFlowApiError. */
  fetchMockHtml: (screenId: string) => Promise<MockHtmlResponse>;
}

/**
 * useScreenFlowMap — single GET /screen-flow on mount + on workspace change.
 *
 * Test seam: the hook routes all network calls through the @/api/screen-flow
 * helpers, which themselves rely on `globalThis.fetch` by default. Vitest can
 * therefore mock `globalThis.fetch` to drive the 200 / 401 / 4xx branches.
 */
export function useScreenFlowMap(
  workspaceId: string | number,
): UseScreenFlowMapResult {
  const [data, setData] = React.useState<ScreenFlowResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<ScreenFlowApiError | null>(null);

  const reload = React.useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const payload = await getScreenFlow(workspaceId);
      setData(payload);
    } catch (err) {
      if (err instanceof ScreenFlowApiError) {
        setError(err);
        setData(null);
      } else {
        throw err;
      }
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const fetchMockHtml = React.useCallback(
    (screenId: string): Promise<MockHtmlResponse> => {
      return getMockHtml(workspaceId, screenId);
    },
    [workspaceId],
  );

  return { data, loading, error, reload, fetchMockHtml };
}
