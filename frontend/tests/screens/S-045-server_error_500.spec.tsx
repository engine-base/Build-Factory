/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-54 / S-045 — サーバーエラー (server_error_500) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen
 *       test harness; tsc strict mode picks them up once the Wave 2 frontend
 *       test ticket (T-V3-C-TEST-01) is installed. Pattern mirrors the
 *       existing S-048 / S-008 specs.
 *
 * Covers (mapped to T-V3-C-54 acceptance_criteria):
 *   structural.AC-S1 -> "h1 == 'サーバーエラー'"
 *   structural.AC-S2 -> "Lucide icons only (no emoji)"
 *   functional.AC-F1 -> "401 redirects to /login (S-001), no workspace data"
 *   functional.AC-F2 -> "skeleton role='status' aria-live='polite' while loading"
 *   regression       -> retry button calls reset / reload
 *                       Sentry captureException is invoked at boundary commit
 *                       typed client GETs /api/system/error-context with error_id
 *                       global-error.tsx exports a default React component
 */

import * as React from "react";
import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// next/navigation: stub router so we can assert push/replace targets (AC-F1).
const pushMock = vi.fn();
const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// Sentry helper — assert captureException is called when an error reaches
// the boundary (regression: Sentry breadcrumb wiring).
const captureExceptionMock = vi.fn();
vi.mock("@/lib/sentry", () => ({
  captureException: (...args: unknown[]) => {
    captureExceptionMock(...args);
    return Promise.resolve("evt_xyz");
  },
}));

import ServerError500Content from "@/components/system/ServerError500Content";
import GlobalError from "@/app/global-error";
import RouteError from "@/app/error";
import {
  SERVER_ERROR_500_CONTEXT_ENDPOINT,
} from "@/api/server-error-500";

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  pushMock.mockReset();
  replaceMock.mockReset();
  captureExceptionMock.mockReset();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-54 S-045 サーバーエラー (server_error_500)", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-045' and exact h1 'サーバーエラー'", async () => {
    // No error_id → useServerError500 stays disabled → no fetch.
    renderWithQueryClient(<ServerError500Content />);

    await waitFor(() => {
      expect(screen.queryByTestId("server-error-500-content")).not.toBeNull();
    });

    const root = document.querySelector("[data-screen-id='S-045']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-system");
    expect(root?.getAttribute("data-screen-name")).toBe("server_error_500");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("サーバーエラー");

    // 500 status badge from mock (逐語).
    expect(
      root?.querySelector("[data-testid='server-error-500-status']")
        ?.textContent,
    ).toBe("500");

    // AC-S2: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F2: while error-context is being fetched the skeleton with role='status' + aria-live='polite' is rendered, then replaced atomically", async () => {
    let resolveFetch: (value: Response) => void;
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((res) => {
          resolveFetch = res;
        }),
    );

    const boundaryError = Object.assign(new Error("boom"), {
      digest: "err_a3f8c29b71",
    });

    renderWithQueryClient(<ServerError500Content error={boundaryError} />);

    const skeleton = await screen.findByTestId("server-error-500-skeleton");
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-live")).toBe("polite");
    expect(screen.queryByTestId("server-error-500-content")).toBeNull();

    resolveFetch!(
      jsonResponse({
        error_id: "err_a3f8c29b71",
        timestamp: "2026-05-17T05:42:11Z",
        path: "POST /api/workspaces/abc/tasks",
        status: 500,
      }),
    );

    await waitFor(() => {
      expect(screen.queryByTestId("server-error-500-content")).not.toBeNull();
    });
    expect(screen.queryByTestId("server-error-500-skeleton")).toBeNull();
    expect(
      screen.getByTestId("server-error-500-error-id").textContent,
    ).toContain("err_a3f8c29b71");
  });

  it("AC-F1: 401 from GET /api/system/error-context redirects to /login (S-001) and renders no workspace-scoped data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "UNAUTHORIZED", message: "missing token" } },
        { status: 401 },
      ),
    );

    const boundaryError = Object.assign(new Error("boom"), {
      digest: "err_a3f8c29b71",
    });

    renderWithQueryClient(<ServerError500Content error={boundaryError} />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledTimes(1);
    });
    expect(replaceMock.mock.calls[0][0]).toBe("/login");

    // AC-F1 second half: no workspace data is rendered (h1 / details absent).
    expect(screen.queryByTestId("server-error-500-content")).toBeNull();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("regression: retry button invokes the boundary's reset() callback", async () => {
    const resetSpy = vi.fn();

    renderWithQueryClient(
      <ServerError500Content
        error={Object.assign(new Error("x"), { digest: "err_x" })}
        reset={resetSpy}
      />,
    );

    // No fetch fired (errorId is present but we mock fetch to a never-resolving
    // promise to keep us in the skeleton state — except we don't need to; we
    // wait for the content to render via fetch resolving to 200).
    fetchMock.mockResolvedValue(
      jsonResponse({
        error_id: "err_x",
        timestamp: "t",
        path: "p",
        status: 500,
      }),
    );

    await waitFor(() =>
      expect(screen.queryByTestId("server-error-500-content")).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId("server-error-500-retry-button"));
    expect(resetSpy).toHaveBeenCalledTimes(1);
  });

  it("regression: captureException is invoked when the boundary delivers an error", async () => {
    const boundaryError = Object.assign(new Error("boom"), {
      digest: "err_a3f8c29b71",
    });

    renderWithQueryClient(<ServerError500Content error={boundaryError} />);

    await waitFor(() => {
      expect(captureExceptionMock).toHaveBeenCalled();
    });
    expect(captureExceptionMock.mock.calls[0][0]).toBe(boundaryError);
  });

  it("regression: typed client GETs /api/system/error-context with error_id query when boundary supplies a digest", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        error_id: "err_dig",
        timestamp: "2026-05-17T00:00:00Z",
        path: "GET /api/x",
        status: 500,
      }),
    );

    renderWithQueryClient(
      <ServerError500Content
        error={Object.assign(new Error("x"), { digest: "err_dig" })}
      />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    const urlStr = String(url);
    expect(urlStr).toContain(SERVER_ERROR_500_CONTEXT_ENDPOINT);
    expect(urlStr).toContain("error_id=err_dig");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("regression: global-error.tsx exports a default React component that renders <html><body>", () => {
    expect(typeof GlobalError).toBe("function");
    const { container } = render(
      <GlobalError
        error={Object.assign(new Error("x"), { digest: "err_x" })}
        reset={() => {}}
      />,
    );
    // global-error renders its own <html>/<body>; JSDOM hoists them, but the
    // root element should carry data-screen-id="S-045" via the body.
    expect(
      container.querySelector("[data-screen-id='S-045']"),
    ).not.toBeNull();
  });

  it("regression: route-level error.tsx exports a default React component", () => {
    expect(typeof RouteError).toBe("function");
    renderWithQueryClient(
      <RouteError
        error={Object.assign(new Error("x"), { digest: "err_y" })}
        reset={() => {}}
      />,
    );
    expect(
      document.querySelector("[data-screen-id='S-045']"),
    ).not.toBeNull();
  });
});
