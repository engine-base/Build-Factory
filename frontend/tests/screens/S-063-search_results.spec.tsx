/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-24 / S-063 — 検索結果 (Search Results) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness (same convention
 *       as S-011 / T-V3-C-11).
 *
 * Covers (mapped to T-V3-C-24 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-063"
 *   functional.AC-F1  -> "renders non-technical error toast referencing endpoint on 4xx/5xx"
 *   functional.AC-F2  -> "calls GET /api/search?q=<query> via typed client and preserves backend hit order"
 *   functional.AC-F3  -> "renders only hits returned by (RLS-aware) backend payload"
 *   extra             -> "facet checkbox narrows to a single ?category= param"
 *   extra             -> "empty state shown when backend returns zero hits"
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

vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import SearchResultsPage from "@/app/(app)/search/results/page";
import { toast } from "sonner";

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const HITS_FIXTURE = [
  {
    id: "T-V3-AUTH-01",
    kind: "task",
    title: "POST /api/auth/login の実装",
    snippet: "JWT + refresh_token cookie / 401 generic / rate limit.",
    score: 0.97,
    url: "/tasks/T-V3-AUTH-01",
  },
  {
    id: "M-1",
    kind: "spec",
    title: "M-1: 認証 (Auth)",
    snippet: "email + password で signup / login。MFA / OAuth サポート。",
    score: 0.88,
  },
  {
    id: "T-V3-AUTH-02",
    kind: "task",
    title: "POST /api/auth/signup 実装",
    snippet: "User + Account + AccountMember を 1 transaction で作成。",
    score: 0.82,
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

describe("T-V3-C-24 S-063 Search Results", () => {
  it("AC-S1: renders root with data-screen-id='S-063'", () => {
    renderWithQueryClient(<SearchResultsPage />);
    const root = document.querySelector("[data-screen-id='S-063']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-024");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-24");
  });

  it("AC-F2: calls GET /api/search?q=<query> via typed client and preserves backend hit order", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        hits: HITS_FIXTURE,
        total: HITS_FIXTURE.length,
        query: "auth implementation",
      }),
    );
    renderWithQueryClient(<SearchResultsPage />);

    const input = screen.getByTestId(
      "search-results-input",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "auth implementation" } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/api/search");
    expect(url).toContain("q=auth+implementation");

    // task T-V3-AUTH-01 (0.97) must render before T-V3-AUTH-02 (0.82).
    await waitFor(() => {
      expect(
        screen.getByTestId("search-result-task-T-V3-AUTH-01"),
      ).toBeTruthy();
    });
    const cards = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid^='search-result-']"),
    );
    const order = cards.map((c) => c.getAttribute("data-testid"));
    expect(order.indexOf("search-result-task-T-V3-AUTH-01")).toBeLessThan(
      order.indexOf("search-result-task-T-V3-AUTH-02"),
    );
  });

  it("AC-F1: surfaces a non-technical error toast referencing /api/search on 5xx without leaking stack traces", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: "internal_server_error",
            message: "Traceback (most recent call last) ...",
          },
        },
        { status: 500 },
      ),
    );
    renderWithQueryClient(<SearchResultsPage />);

    fireEvent.change(screen.getByTestId("search-results-input"), {
      target: { value: "boom" },
    });

    await waitFor(() => {
      expect(
        (toast.error as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(0);
    });
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(msg).toContain("/api/search");
    expect(msg.toLowerCase()).not.toContain("traceback");
    expect(msg.toLowerCase()).not.toContain("internal_server_error");

    // Inline error region also rendered (parity with toast for assistive tech).
    expect(screen.getByTestId("search-results-error")).toBeTruthy();
  });

  it("AC-F3: renders only the hits returned by the (RLS-filtered) backend payload", async () => {
    // Backend already filtered: only the spec hit is visible to this caller.
    fetchMock.mockResolvedValue(
      jsonResponse({
        hits: [HITS_FIXTURE[1]],
        total: 1,
        query: "auth",
      }),
    );
    renderWithQueryClient(<SearchResultsPage />);

    fireEvent.change(screen.getByTestId("search-results-input"), {
      target: { value: "auth" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("search-result-spec-M-1")).toBeTruthy();
    });
    expect(screen.queryByTestId("search-result-task-T-V3-AUTH-01")).toBeNull();
    expect(screen.queryByTestId("search-result-task-T-V3-AUTH-02")).toBeNull();
  });

  it("facet checkbox narrowing to a single category forwards ?category= to the backend", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        hits: HITS_FIXTURE,
        total: HITS_FIXTURE.length,
        query: "auth",
      }),
    );
    renderWithQueryClient(<SearchResultsPage />);

    // Default selection is {tasks, knowledge, artifacts}.
    // Untick knowledge + artifacts -> only "tasks" remains -> ?category=tasks.
    fireEvent.click(
      screen
        .getByTestId("facet-category-knowledge")
        .querySelector("input[type='checkbox']") as HTMLInputElement,
    );
    fireEvent.click(
      screen
        .getByTestId("facet-category-artifacts")
        .querySelector("input[type='checkbox']") as HTMLInputElement,
    );
    fireEvent.change(screen.getByTestId("search-results-input"), {
      target: { value: "auth" },
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls.at(-1)?.[0]);
    expect(url).toContain("q=auth");
    expect(url).toContain("category=tasks");
  });

  it("renders an empty-state hint when the backend returns zero hits", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ hits: [], total: 0, query: "zzz" }),
    );
    renderWithQueryClient(<SearchResultsPage />);

    fireEvent.change(screen.getByTestId("search-results-input"), {
      target: { value: "zzz" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("search-results-empty")).toBeTruthy();
    });
  });

  it("explicit submit (button) skips the debounce and triggers an immediate fetch", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ hits: HITS_FIXTURE, total: 3, query: "auth" }),
    );
    renderWithQueryClient(<SearchResultsPage />);

    const input = screen.getByTestId(
      "search-results-input",
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "auth" } });
    fireEvent.click(screen.getByTestId("search-results-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("q=auth");
  });
});
