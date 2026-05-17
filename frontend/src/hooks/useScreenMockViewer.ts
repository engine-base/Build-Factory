/**
 * T-V3-C-49 / S-023 — `useScreenMockViewer` hook.
 *
 * Encapsulates the data-fetching state machine for the 画面モックビューア page:
 *   1. GET /api/workspaces/{id}/mocks (list)              — on mount (AC-F1)
 *   2. GET /api/workspaces/{id}/mocks/{screen_id}/html    — on selection (AC-F3)
 *
 * The hook is *only* responsible for state; the page owns layout + redirect.
 * Side effects (fetch / redirect) are kept testable by injecting `fetchImpl`.
 */

import * as React from "react";

import {
  MocksApiError,
  getMockHtml,
  getMocks,
  type Mock,
  workspaceMockHtmlEndpoint,
  workspaceMocksEndpoint,
} from "@/api/mocks";

export type ViewerState = "idle" | "loading" | "loaded" | "error";

export interface UseScreenMockViewerOptions {
  workspaceId: string | null;
  authToken: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

export interface UseScreenMockViewerResult {
  /** Top-level list state ("loaded" once the GET /mocks call resolved). */
  state: ViewerState;
  mocks: Mock[];
  total: number;
  /** Currently selected screen id (drives the iframe). */
  selectedScreenId: string | null;
  /** HTML body for the selected screen — null while loading / on error. */
  selectedHtml: string | null;
  /** Inline error message (user-friendly + endpoint-tagged) or null. */
  errorMessage: string | null;
  /** True while the HTML for the selected mock is being fetched. */
  htmlLoading: boolean;
  selectScreen: (screenId: string) => void;
  refresh: () => Promise<void>;
}

/**
 * Read the auth bearer token from localStorage (test harness sets this).
 * Returning null lets the page trigger the AC-F2 redirect.
 */
export function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.auth.token");
  } catch {
    return null;
  }
}

/**
 * Resolve the active workspace id. Order of precedence:
 *   1. `?workspace=<id>` query param (canonical entry point from S-012 sidebar)
 *   2. localStorage `bf.workspace.id` (sticky selection)
 *   3. `null` → caller renders an inline missing-workspace state.
 */
export function readWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const url = new URL(window.location.href);
    const fromQuery = url.searchParams.get("workspace");
    if (fromQuery && fromQuery.length > 0) return fromQuery;
    const fromStorage = window.localStorage.getItem("bf.workspace.id");
    if (fromStorage && fromStorage.length > 0) return fromStorage;
  } catch {
    // localStorage blocked / URL malformed — fall through to null.
  }
  return null;
}

export function useScreenMockViewer(
  options: UseScreenMockViewerOptions,
): UseScreenMockViewerResult {
  const { workspaceId, authToken, fetchImpl } = options;

  const [state, setState] = React.useState<ViewerState>("idle");
  const [mocks, setMocks] = React.useState<Mock[]>([]);
  const [total, setTotal] = React.useState<number>(0);
  const [selectedScreenId, setSelectedScreenId] = React.useState<string | null>(
    null,
  );
  const [selectedHtml, setSelectedHtml] = React.useState<string | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [htmlLoading, setHtmlLoading] = React.useState<boolean>(false);

  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string): string => {
      const userMsg =
        err instanceof MocksApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      setErrorMessage(userMsg);
      return userMsg;
    },
    [],
  );

  // ---- List fetch (AC-F1) -------------------------------------------------
  const refresh = React.useCallback(async () => {
    if (!workspaceId || !authToken) return;
    setState("loading");
    setErrorMessage(null);
    try {
      const body = await getMocks(workspaceId, { authToken, fetchImpl });
      const list = Array.isArray(body.mocks) ? body.mocks : [];
      setMocks(list);
      setTotal(typeof body.total === "number" ? body.total : list.length);
      setState("loaded");
      // Default selection: first mock in the list (if any).
      if (list.length > 0) {
        setSelectedScreenId((prev) => prev ?? list[0].screen_id);
      }
    } catch (err) {
      setMocks([]);
      setTotal(0);
      setState("error");
      surfaceError(err, workspaceMocksEndpoint(workspaceId));
    }
  }, [workspaceId, authToken, fetchImpl, surfaceError]);

  React.useEffect(() => {
    if (!workspaceId || !authToken) return;
    void refresh();
  }, [workspaceId, authToken, refresh]);

  // ---- HTML fetch (AC-F3) -------------------------------------------------
  React.useEffect(() => {
    if (!workspaceId || !authToken || !selectedScreenId) return;
    let cancelled = false;
    setHtmlLoading(true);
    setSelectedHtml(null);
    void (async () => {
      try {
        const body = await getMockHtml(workspaceId, selectedScreenId, {
          authToken,
          fetchImpl,
        });
        if (cancelled) return;
        const html = typeof body.html === "string" ? body.html : "";
        setSelectedHtml(html);
      } catch (err) {
        if (cancelled) return;
        setSelectedHtml(null);
        surfaceError(
          err,
          workspaceMockHtmlEndpoint(workspaceId, selectedScreenId),
        );
      } finally {
        if (!cancelled) setHtmlLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, authToken, selectedScreenId, fetchImpl, surfaceError]);

  const selectScreen = React.useCallback((screenId: string) => {
    setSelectedScreenId(screenId);
  }, []);

  return {
    state,
    mocks,
    total,
    selectedScreenId,
    selectedHtml,
    errorMessage,
    htmlLoading,
    selectScreen,
    refresh,
  };
}
