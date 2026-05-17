// @ts-nocheck
/**
 * T-V3-C-50 / S-024 — コンポーネントカタログ screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are runtime-only devDeps for the screen test harness (wired by
 *       T-V3-C-TEST-01). Same convention as T-V3-C-37 / C-38 / C-39.
 *
 * Covers (mapped to T-V3-C-50 acceptance_criteria):
 *   structural.AC-S1  -> "h1 reads 'コンポーネントカタログ' inside data-screen-id='S-024' root"
 *   structural.AC-S2  -> "no emoji glyphs — Lucide icons only"
 *   functional.AC-F1  -> "GET /api/workspaces/{id}/components on mount; 4xx -> inline error + empty state"
 *   functional.AC-F2  -> "unauthenticated visitor -> /login redirect; no workspace data rendered"
 *   functional.AC-F3  -> "GET /api/workspaces/{id}/components/{id}/usage on card click; renders screens list"
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
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";

vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import ComponentCatalogPage from "@/app/(app)/spec/components/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const COMPONENTS_FIXTURE = {
  components: [
    {
      id: "cmp_button",
      name: "Button",
      type: "form",
      description: "6 variants · 8 states",
      uses: 42,
    },
    {
      id: "cmp_card",
      name: "Card",
      type: "layout",
      description: "Linear flat",
      uses: 35,
    },
    {
      id: "cmp_badge",
      name: "Badge",
      type: "data-display",
      description: "6 status / brand variants",
      uses: 38,
    },
  ],
};

const USAGE_FIXTURE_BUTTON = {
  usages: [
    {
      screen_id: "S-012",
      screen_name: "workspace_dashboard",
      instance_count: 4,
    },
    {
      screen_id: "S-027",
      screen_name: "kanban",
      instance_count: 7,
    },
  ],
};

const WORKSPACE_ID = "ws_8f3a2c";
const TOKEN = "test-bearer-token";

const COMPONENTS_URL = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/components`;
const USAGE_URL_BUTTON = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/components/cmp_button/usage`;

function defaultFetchImpl(url: string, init?: RequestInit): Promise<Response> {
  const method = init?.method ?? "GET";
  if (typeof url === "string" && method === "GET" && url === COMPONENTS_URL) {
    return Promise.resolve(jsonResponse(200, COMPONENTS_FIXTURE));
  }
  if (typeof url === "string" && method === "GET" && url === USAGE_URL_BUTTON) {
    return Promise.resolve(jsonResponse(200, USAGE_FIXTURE_BUTTON));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

function primeAuth(workspaceId: string | null = WORKSPACE_ID) {
  window.localStorage.setItem("bf.auth.token", TOKEN);
  if (workspaceId) {
    window.localStorage.setItem("bf.workspace.id", workspaceId);
  }
}

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
  try {
    window.localStorage.clear();
  } catch {
    /* jsdom localStorage may be unavailable in some envs */
  }
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-024 コンポーネントカタログ page (T-V3-C-50)", () => {
  it("AC-S1: renders root with data-screen-id='S-024' and h1 'コンポーネントカタログ'", async () => {
    primeAuth();
    const { container } = renderWithProviders(<ComponentCatalogPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-024"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-005b");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-50");
    expect(root?.getAttribute("data-entities")).toContain("E-023");
    expect(root?.getAttribute("data-entities")).toContain("E-024");
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("コンポーネントカタログ");
  });

  it("AC-S2: uses Lucide icons exclusively (no emoji glyphs)", async () => {
    primeAuth();
    const { container } = renderWithProviders(<ComponentCatalogPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const text = container.textContent ?? "";
    // 絵文字禁止 (design-tokens.md §8). Match emoji ranges defensively.
    const emojiPattern =
      /[\u{1F300}-\u{1FAFF}\u{1F600}-\u{1F64F}\u{1F900}-\u{1F9FF}\u{2600}-\u{27BF}]/u;
    expect(emojiPattern.test(text)).toBe(false);
  });

  it("AC-F1: GET /api/workspaces/{id}/components on mount and renders the 2xx body", async () => {
    primeAuth();
    renderWithProviders(<ComponentCatalogPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toBe(COMPONENTS_URL);
    expect((init ?? {}).method ?? "GET").toBe("GET");
    expect(String((init ?? {}).headers?.Authorization ?? "")).toContain(TOKEN);
    await waitFor(() =>
      expect(screen.queryByTestId("component-card-cmp_button")).not.toBeNull(),
    );
    expect(screen.getByTestId("component-card-cmp_card")).not.toBeNull();
    expect(screen.getByTestId("component-card-cmp_badge")).not.toBeNull();
  });

  it("AC-F1 (UNWANTED): 4xx renders an inline error banner and an empty state", async () => {
    primeAuth();
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(403, {
          detail: {
            code: "FORBIDDEN",
            message:
              "Traceback (most recent call last): File '/srv/app.py' line 1",
          },
        }),
      ),
    );
    renderWithProviders(<ComponentCatalogPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("components-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("components-error");
    expect(banner.textContent).toContain(
      `/api/workspaces/${WORKSPACE_ID}/components`,
    );
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(screen.queryByTestId("components-empty")).not.toBeNull();
    expect(screen.queryByTestId("component-card-cmp_button")).toBeNull();
  });

  it("AC-F2 (UNWANTED): unauthenticated visitor redirects to /login and renders no workspace-scoped data", async () => {
    // No primeAuth() — localStorage clear means no token.
    const replaceMock = vi.fn();
    const originalReplace = window.location.replace;
    Object.defineProperty(window.location, "replace", {
      configurable: true,
      value: replaceMock,
    });
    try {
      const { container } = renderWithProviders(<ComponentCatalogPage />);
      await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
      // No fetch happened — the page must not surface workspace rows or KPIs.
      expect(fetchMock).not.toHaveBeenCalled();
      expect(container.textContent ?? "").not.toContain("DESIGN.md 準拠");
    } finally {
      Object.defineProperty(window.location, "replace", {
        configurable: true,
        value: originalReplace,
      });
    }
  });

  it("AC-F3: clicking a card fires GET /components/{id}/usage and renders the screens list", async () => {
    primeAuth();
    renderWithProviders(<ComponentCatalogPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("component-card-cmp_button")).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId("component-card-cmp_button"));

    await waitFor(() => {
      const usageCalls = fetchMock.mock.calls.filter(
        ([url]) =>
          typeof url === "string" && url === USAGE_URL_BUTTON,
      );
      expect(usageCalls.length).toBeGreaterThanOrEqual(1);
    });
    await waitFor(() =>
      expect(screen.queryByTestId("component-usage-list")).not.toBeNull(),
    );
    expect(screen.getByTestId("component-usage-list").textContent).toContain(
      "S-012",
    );
    expect(screen.getByTestId("component-usage-list").textContent).toContain(
      "S-027",
    );
  });

  it("AC-R: search and type filter narrow the visible card grid", async () => {
    primeAuth();
    renderWithProviders(<ComponentCatalogPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("component-card-cmp_button")).not.toBeNull(),
    );

    // Search: only "Card" matches.
    fireEvent.change(screen.getByTestId("components-search"), {
      target: { value: "Card" },
    });
    await waitFor(() =>
      expect(screen.queryByTestId("component-card-cmp_button")).toBeNull(),
    );
    expect(screen.getByTestId("component-card-cmp_card")).not.toBeNull();

    // Clear search; filter by type "layout".
    fireEvent.change(screen.getByTestId("components-search"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByTestId("components-type-filter"), {
      target: { value: "layout" },
    });
    await waitFor(() =>
      expect(screen.queryByTestId("component-card-cmp_badge")).toBeNull(),
    );
    expect(screen.getByTestId("component-card-cmp_card")).not.toBeNull();
  });
});
