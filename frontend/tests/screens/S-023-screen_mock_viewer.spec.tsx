// @ts-nocheck
/**
 * T-V3-C-49 / S-023 — 画面モックビューア screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are runtime-only devDeps for the screen test harness (same convention
 *       as T-V3-C-37 / C-38 / C-48).
 *
 * Covers (mapped to T-V3-C-49 acceptance_criteria — see docs/audit/2026-05-16_v3/T-V3-C-49.md):
 *   structural.AC-S1  -> "h1 reads '画面モックビューア' inside data-screen-id='S-023' root"
 *   structural.AC-S2  -> "no emoji glyphs — Lucide icons only"
 *   functional.AC-F1  -> "GET /api/workspaces/{id}/mocks on mount; 4xx -> inline error + empty state"
 *   functional.AC-F2  -> "unauthenticated visitor -> /login redirect; no workspace data rendered"
 *   functional.AC-F3  -> "GET /api/workspaces/{id}/mocks/{screen_id}/html on selection -> iframe srcDoc"
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

// next/navigation: mock useParams to inject the route workspace id.
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "ws_8f3a2c" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => "/spec/mocks/ws_8f3a2c",
}));

vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import ScreenMockViewerPage from "@/app/(app)/spec/mocks/[id]/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const WORKSPACE_ID = "ws_8f3a2c";
const TOKEN = "test-bearer-token";

const MOCKS_URL = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/mocks`;
const HTML_URL_006 = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/mocks/S-006/html`;
const HTML_URL_012 = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/mocks/S-012/html`;

const MOCKS_FIXTURE = {
  mocks: [
    {
      screen_id: "S-006",
      name: "Account Dashboard",
      category: "Account",
      version: 3,
      updated_at: "2026-05-15T01:00:00Z",
    },
    {
      screen_id: "S-012",
      name: "Workspace Dashboard",
      category: "Workspace",
      version: 1,
      updated_at: "2026-05-15T01:00:00Z",
    },
  ],
  total: 2,
};

const MOCK_HTML_006 = "<!DOCTYPE html><html><body><h1>S-006 mock</h1></body></html>";
const MOCK_HTML_012 = "<!DOCTYPE html><html><body><h1>S-012 mock</h1></body></html>";

function defaultFetchImpl(url: string, init?: RequestInit): Promise<Response> {
  const method = init?.method ?? "GET";
  if (typeof url === "string" && method === "GET") {
    if (url === MOCKS_URL) return Promise.resolve(jsonResponse(200, MOCKS_FIXTURE));
    if (url === HTML_URL_006)
      return Promise.resolve(jsonResponse(200, { html: MOCK_HTML_006 }));
    if (url === HTML_URL_012)
      return Promise.resolve(jsonResponse(200, { html: MOCK_HTML_012 }));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

function primeAuth() {
  window.localStorage.setItem("bf.auth.token", TOKEN);
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

describe("S-023 画面モックビューア page (T-V3-C-49)", () => {
  it("AC-S1: renders root with data-screen-id='S-023' and h1 '画面モックビューア'", async () => {
    primeAuth();
    const { container } = render(<ScreenMockViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-023"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-005b");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-49");
    expect(root?.getAttribute("data-entities")).toContain("E-022");
    expect(root?.getAttribute("data-entities")).toContain("E-023");
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("画面モックビューア");
  });

  it("AC-S2: uses Lucide icons exclusively (no emoji glyphs)", async () => {
    primeAuth();
    const { container } = render(<ScreenMockViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const text = container.textContent ?? "";
    // 絵文字禁止 (design-tokens.md §8). Match emoji ranges defensively.
    const emojiPattern =
      /[\u{1F300}-\u{1FAFF}\u{1F600}-\u{1F64F}\u{1F900}-\u{1F9FF}\u{2600}-\u{27BF}]/u;
    expect(emojiPattern.test(text)).toBe(false);
    // Sanity: at least one Lucide-rendered svg should be present.
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThan(0);
  });

  it("AC-F1: GET /api/workspaces/{id}/mocks on mount via typed client and renders the 2xx body", async () => {
    primeAuth();
    render(<ScreenMockViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const listCall = fetchMock.mock.calls.find(
      ([url]) => String(url) === MOCKS_URL,
    );
    expect(listCall).toBeTruthy();
    const init = (listCall ?? [])[1] ?? {};
    expect((init.method ?? "GET")).toBe("GET");
    expect(String(init.headers?.Authorization ?? "")).toContain(TOKEN);
    await waitFor(() =>
      expect(screen.queryByTestId("mocks-row-S-006")).not.toBeNull(),
    );
    expect(screen.getByTestId("mocks-row-S-012")).not.toBeNull();
  });

  it("AC-F1 (UNWANTED): 4xx renders an inline error banner and an empty state, with no workspace rows", async () => {
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
    render(<ScreenMockViewerPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("mocks-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("mocks-error");
    expect(banner.textContent).toContain(
      `/api/workspaces/${WORKSPACE_ID}/mocks`,
    );
    // AC-F1: server stack-trace text must not leak into the toast.
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(screen.queryByTestId("mocks-empty")).not.toBeNull();
    expect(screen.queryByTestId("mocks-row-S-006")).toBeNull();
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
      const { container } = render(<ScreenMockViewerPage />);
      await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
      // No fetch happened — the page must not surface workspace rows / iframe.
      expect(fetchMock).not.toHaveBeenCalled();
      expect(container.querySelector("iframe")).toBeNull();
      expect(screen.queryByTestId("mocks-row-S-006")).toBeNull();
    } finally {
      Object.defineProperty(window.location, "replace", {
        configurable: true,
        value: originalReplace,
      });
    }
  });

  it("AC-F3: selecting a screen triggers GET /api/workspaces/{id}/mocks/{screen_id}/html and renders iframe srcDoc", async () => {
    primeAuth();
    const { container } = render(<ScreenMockViewerPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("mocks-row-S-006")).not.toBeNull(),
    );

    // Default selection should be the first mock (S-006) — verify GET html.
    await waitFor(() => {
      const htmlCalls = fetchMock.mock.calls.filter(
        ([url]) => String(url) === HTML_URL_006,
      );
      expect(htmlCalls.length).toBeGreaterThan(0);
    });
    await waitFor(() =>
      expect(container.querySelector("iframe")).not.toBeNull(),
    );
    const iframe = container.querySelector("iframe") as HTMLIFrameElement;
    expect(iframe.getAttribute("srcdoc")).toContain("S-006 mock");

    // Now select S-012 — separate GET html call is issued and srcDoc updates.
    fireEvent.click(screen.getByTestId("mocks-row-S-012"));
    await waitFor(() => {
      const htmlCalls12 = fetchMock.mock.calls.filter(
        ([url]) => String(url) === HTML_URL_012,
      );
      expect(htmlCalls12.length).toBeGreaterThan(0);
    });
    await waitFor(() => {
      const iframe2 = container.querySelector("iframe") as HTMLIFrameElement;
      expect(iframe2.getAttribute("srcdoc")).toContain("S-012 mock");
    });
  });

  it("AC-F1 supplemental: search filter narrows the rendered list", async () => {
    primeAuth();
    render(<ScreenMockViewerPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("mocks-row-S-006")).not.toBeNull(),
    );
    expect(screen.queryByTestId("mocks-row-S-012")).not.toBeNull();
    fireEvent.change(screen.getByTestId("mocks-filter"), {
      target: { value: "S-006" },
    });
    await waitFor(() =>
      expect(screen.queryByTestId("mocks-row-S-012")).toBeNull(),
    );
    expect(screen.getByTestId("mocks-row-S-006")).not.toBeNull();
  });
});
