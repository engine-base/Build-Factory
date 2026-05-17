// @ts-nocheck
/**
 * T-V3-C-51 / S-025 — 画面遷移マップ (screen_flow_map) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen
 *       test harness; they are wired by the Wave 2 frontend test setup
 *       ticket (T-V3-C-TEST-01). Same convention as T-V3-C-38 / C-39 / C-12.
 *
 * Covers (mapped to T-V3-C-51 acceptance_criteria):
 *   structural.AC-S1  -> 'h1 reads "画面遷移マップ"'
 *   structural.AC-S2  -> 'renders root with data-screen-id=S-025'
 *   functional.AC-F1  -> 'GET /api/workspaces/{id}/screen-flow via typed client on mount'
 *   functional.AC-F1  -> '4xx surfaces non-technical toast + empty state'
 *   functional.AC-F2  -> '401 -> redirect /login + no workspace data rendered'
 *   functional.AC-F3  -> 'GET /api/workspaces/{id}/mocks/{screen_id}/html on node click'
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
  waitFor,
  cleanup,
  fireEvent,
} from "@testing-library/react";

import ScreenFlowMapPage from "@/app/(app)/spec/screen-flow/page";

// --------------------------------------------------------------------------
// Next.js router + searchParams mocks
// --------------------------------------------------------------------------

const routerReplace = vi.fn();
const searchParamsGet = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplace,
    push: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => ({
    get: searchParamsGet,
  }),
}));

// --------------------------------------------------------------------------
// fetch mocking
// --------------------------------------------------------------------------

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SCREEN_FLOW_FIXTURE = {
  nodes: [
    { screen_id: "S-001", name: "login", kind: "screen" },
    { screen_id: "S-006", name: "10 案件俯瞰", kind: "screen" },
    { screen_id: "S-012", name: "workspace dash", kind: "screen" },
  ],
  edges: [
    { from_screen_id: "S-001", to_screen_id: "S-006", trigger: "submit_login" },
    {
      from_screen_id: "S-006",
      to_screen_id: "S-012",
      trigger: "select_workspace",
    },
  ],
};

function defaultFetchImpl(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const method = init?.method ?? "GET";
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.includes("/api/workspaces/") &&
    url.endsWith("/screen-flow")
  ) {
    return Promise.resolve(jsonResponse(200, SCREEN_FLOW_FIXTURE));
  }
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.includes("/api/workspaces/") &&
    url.includes("/mocks/") &&
    url.endsWith("/html")
  ) {
    return Promise.resolve(
      jsonResponse(200, {
        html: "<!DOCTYPE html><html><body><h1>S-001 login</h1></body></html>",
      }),
    );
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  routerReplace.mockReset();
  searchParamsGet.mockReset();
  searchParamsGet.mockImplementation((key: string) =>
    key === "workspace_id" ? "ws-test" : null,
  );
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-025 画面遷移マップ page (T-V3-C-51)", () => {
  it("AC-S2: renders root with data-screen-id='S-025'", async () => {
    const { container } = render(<ScreenFlowMapPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-025"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-005b");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-51");
    expect(root?.getAttribute("data-entities")).toContain("E-022");
  });

  it("AC-S1: h1 reads '画面遷移マップ'", async () => {
    render(<ScreenFlowMapPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("画面遷移マップ");
  });

  it("AC-F1: GET /api/workspaces/{id}/screen-flow on mount via typed client", async () => {
    render(<ScreenFlowMapPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain("/api/workspaces/ws-test/screen-flow");
    expect((init ?? {}).method ?? "GET").toBe("GET");
    // Backend body should be rendered into the page (AC-F1 — render 2xx body).
    await waitFor(() =>
      expect(screen.queryByTestId("flow-node-S-001")).not.toBeNull(),
    );
    expect(screen.getByTestId("flow-node-S-006")).not.toBeNull();
    expect(screen.getByTestId("flow-node-S-012")).not.toBeNull();
    // Edge rendered for S-001 -> S-006.
    expect(
      screen.getByTestId("flow-edge-S-001-S-006"),
    ).not.toBeNull();
  });

  it("AC-F1: 4xx surfaces a non-technical toast referencing the endpoint and renders an empty state", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(404, {
          detail: {
            code: "NOT_FOUND",
            message:
              "Traceback (most recent call last): File '/srv/app.py' line 99",
          },
        }),
      ),
    );

    render(<ScreenFlowMapPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("screen-flow-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("screen-flow-error");
    expect(banner.textContent).toContain(
      "/api/workspaces/ws-test/screen-flow",
    );
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(banner.textContent?.toLowerCase()).not.toContain("/srv/app.py");
    // Empty state visible.
    expect(screen.queryByTestId("flow-empty")).not.toBeNull();
    // No node rows rendered.
    expect(screen.queryByTestId("flow-node-S-001")).toBeNull();
  });

  it("AC-F2: 401 from GET screen-flow redirects to /login and does not render workspace-scoped data", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "UNAUTHORIZED", message: "missing token" },
        }),
      ),
    );

    render(<ScreenFlowMapPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    // No node rows or error toast rendered (AC-F2 UNWANTED).
    expect(screen.queryByTestId("flow-node-S-001")).toBeNull();
    expect(screen.queryByTestId("screen-flow-error")).toBeNull();
  });

  it("AC-F3: GET /api/workspaces/{id}/mocks/{screen_id}/html when a node is clicked", async () => {
    render(<ScreenFlowMapPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("flow-node-S-001"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [calledUrl, init] = fetchMock.mock.calls[1];
    expect(String(calledUrl)).toContain(
      "/api/workspaces/ws-test/mocks/S-001/html",
    );
    expect((init ?? {}).method ?? "GET").toBe("GET");

    await waitFor(() =>
      expect(screen.queryByTestId("flow-drawer-html")).not.toBeNull(),
    );
    expect(screen.getByTestId("flow-drawer-html").textContent).toContain(
      "S-001 login",
    );
  });

  it("AC-F3: 404 from GET mocks/html surfaces a drawer-local non-technical error", async () => {
    render(<ScreenFlowMapPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse(404, {
          detail: {
            code: "NOT_FOUND",
            message: "Traceback (most recent call last): db error",
          },
        }),
      ),
    );

    fireEvent.click(screen.getByTestId("flow-node-S-001"));

    await waitFor(() =>
      expect(screen.queryByTestId("flow-drawer-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("flow-drawer-error");
    expect(banner.textContent).toContain(
      "/api/workspaces/ws-test/mocks/S-001/html",
    );
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
  });
});
