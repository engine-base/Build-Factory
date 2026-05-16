/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-11 / S-011 — Global Search (Cmd+K) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the new screen test harness; they are
 *       installed by the Wave 2 frontend test setup ticket (T-V3-C-TEST-01).
 *       Once installed, tsc strict mode picks them up automatically.
 *
 * Covers (mapped to T-V3-C-11 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-011"
 *   functional.AC-F1  -> "calls GET /api/search?q=...&category=... via typed client"
 *   functional.AC-F2  -> "renders non-technical error toast referencing endpoint"
 *   functional.AC-F3  -> "preserves backend ranking (FTS + vector score order)"
 *   functional.AC-F4  -> "renders only hits returned by RLS-aware backend"
 *   extra             -> "Cmd+K focuses the search input"
 *   extra             -> "category chip switches the search request"
 */

import * as React from "react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Sonner is a side-effect toast — mock so we can assert toast.error fires.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import GlobalSearchPage from "@/app/(app)/search/page";
import { toast } from "sonner";

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const HITS_FIXTURE = [
  {
    id: "t1",
    kind: "task",
    title: "auth backend: POST /api/auth/login",
    snippet: "T-V3-AUTH-01 · running",
    score: 0.97,
    url: "/tasks/t1",
  },
  {
    id: "t2",
    kind: "task",
    title: "auth frontend: /login page",
    snippet: "T-V3-AUTH-08 · todo",
    score: 0.81,
  },
  {
    id: "w1",
    kind: "workspace",
    title: "Build-Factory dogfood",
    snippet: "ws_8f3a2c · Phase 1",
    score: 0.55,
  },
];

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("T-V3-C-11 S-011 Global Search (Cmd+K)", () => {
  it("AC-S1: renders root with data-screen-id='S-011'", () => {
    renderWithQueryClient(<GlobalSearchPage />);
    const root = document.querySelector("[data-screen-id='S-011']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-024");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-11");
  });

  it("AC-F1: calls GET /api/search?q=<query>&category=<cat> via typed client on input", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        hits: HITS_FIXTURE,
        total: HITS_FIXTURE.length,
        query: "auth",
      }),
    );
    renderWithQueryClient(<GlobalSearchPage />);

    const input = screen.getByTestId(
      "global-search-input",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "auth" } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/api/search");
    expect(url).toContain("q=auth");
  });

  it("AC-F3: renders hits in backend-provided order (FTS + vector ranking preserved)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ hits: HITS_FIXTURE, total: 3, query: "auth" }),
    );
    renderWithQueryClient(<GlobalSearchPage />);

    fireEvent.change(screen.getByTestId("global-search-input"), {
      target: { value: "auth" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("search-hit-task-t1")).toBeTruthy();
    });
    // task t1 (0.97) must appear before task t2 (0.81)
    const all = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid^='search-hit-']"),
    );
    const idsInOrder = all.map((el) => el.getAttribute("data-testid"));
    expect(idsInOrder.indexOf("search-hit-task-t1")).toBeLessThan(
      idsInOrder.indexOf("search-hit-task-t2"),
    );
  });

  it("AC-F2: surfaces a non-technical error toast referencing /api/search when backend returns 5xx", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "internal_server_error", message: "search failed" } },
        { status: 500 },
      ),
    );
    renderWithQueryClient(<GlobalSearchPage />);

    fireEvent.change(screen.getByTestId("global-search-input"), {
      target: { value: "boom" },
    });

    await waitFor(() => {
      expect(
        (toast.error as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(0);
    });
    const toastMsg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(toastMsg).toContain("/api/search");
    // Must not leak a server stack trace / internal error code.
    expect(toastMsg.toLowerCase()).not.toContain("traceback");
    expect(toastMsg.toLowerCase()).not.toContain("internal_server_error");
  });

  it("AC-F4: renders only the hits returned by the (RLS-filtered) backend payload", async () => {
    // Backend already filtered: only one workspace hit visible to this caller.
    fetchMock.mockResolvedValue(
      jsonResponse({
        hits: [HITS_FIXTURE[2]],
        total: 1,
        categories: { workspace: 1 },
        query: "build",
      }),
    );
    renderWithQueryClient(<GlobalSearchPage />);

    fireEvent.change(screen.getByTestId("global-search-input"), {
      target: { value: "build" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("search-hit-workspace-w1")).toBeTruthy();
    });
    expect(screen.queryByTestId("search-hit-task-t1")).toBeNull();
    expect(screen.queryByTestId("search-hit-task-t2")).toBeNull();
  });

  it("Cmd+K focuses the global search input (extra: trigger contract)", async () => {
    renderWithQueryClient(<GlobalSearchPage />);

    const input = screen.getByTestId(
      "global-search-input",
    ) as HTMLInputElement;
    input.blur();

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    await waitFor(() => expect(document.activeElement).toBe(input));
  });

  it("category chip selection adds the &category= parameter to /api/search", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ hits: [HITS_FIXTURE[0]], total: 1, query: "auth" }),
    );
    renderWithQueryClient(<GlobalSearchPage />);

    fireEvent.click(screen.getByTestId("category-chip-tasks"));
    fireEvent.change(screen.getByTestId("global-search-input"), {
      target: { value: "auth" },
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls.at(-1)?.[0]);
    expect(url).toContain("q=auth");
    expect(url).toContain("category=tasks");
  });
});
