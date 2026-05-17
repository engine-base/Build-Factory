/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-39 / S-048 — ようこそ (welcome_first_login) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness; tsc strict mode
 *       picks them up once the Wave 2 frontend test ticket (T-V3-C-TEST-01) is
 *       installed. Pattern mirrors S-001 / S-008 specs.
 *
 * Covers (mapped to T-V3-C-39 acceptance_criteria):
 *   structural.AC-S1 -> "h1 == 'Build-Factory へようこそ'"
 *   structural.AC-S2 -> "Lucide icons only (no emoji)"
 *   functional.AC-F1 -> "401 redirects to /login (S-001), no workspace data"
 *   functional.AC-F2 -> "skeleton role='status' aria-live='polite' while loading"
 *   regression       -> typed client calls GET /api/me/onboarding, POST advance / skip
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

import WelcomeFirstLoginPage from "@/app/(onboarding)/welcome/page";
import {
  ONBOARDING_ADVANCE_ENDPOINT,
  ONBOARDING_ENDPOINT,
  ONBOARDING_SKIP_ENDPOINT,
} from "@/api/onboarding";

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-39 S-048 ようこそ (welcome_first_login)", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-048' and exact h1 'Build-Factory へようこそ'", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        state: "welcome",
        current_step: "welcome",
        completed: false,
      }),
    );

    renderWithQueryClient(<WelcomeFirstLoginPage />);

    // Wait for the query to resolve (skeleton → content).
    await waitFor(() => {
      expect(screen.queryByTestId("welcome-content")).not.toBeNull();
    });

    const root = document.querySelector("[data-screen-id='S-048']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-027");
    expect(root?.getAttribute("data-screen-name")).toBe("welcome_first_login");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("Build-Factory へようこそ");

    // AC-S2: no emoji glyphs in the rendered DOM (Lucide icons only).
    // The emoji ranges below match the smartphone-typical pictographic blocks.
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F2: while data is being fetched the skeleton with role='status' + aria-live='polite' is rendered, then replaced", async () => {
    // Hold the fetch open until we manually resolve.
    let resolveFetch: (value: Response) => void;
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((res) => {
          resolveFetch = res;
        }),
    );

    renderWithQueryClient(<WelcomeFirstLoginPage />);

    const skeleton = await screen.findByTestId("welcome-skeleton");
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-live")).toBe("polite");
    // Content not yet present.
    expect(screen.queryByTestId("welcome-content")).toBeNull();

    // Resolve the fetch → skeleton should be replaced atomically with content.
    resolveFetch!(
      jsonResponse({
        state: "welcome",
        current_step: "welcome",
        completed: false,
      }),
    );

    await waitFor(() => {
      expect(screen.queryByTestId("welcome-content")).not.toBeNull();
    });
    expect(screen.queryByTestId("welcome-skeleton")).toBeNull();
  });

  it("AC-F1: 401 from GET /api/me/onboarding redirects to /login (S-001) and renders no workspace-scoped data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "UNAUTHORIZED", message: "missing token" } },
        { status: 401 },
      ),
    );

    renderWithQueryClient(<WelcomeFirstLoginPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledTimes(1);
    });
    expect(replaceMock.mock.calls[0][0]).toBe("/login");

    // AC-F1 second half: no workspace data is rendered (h1 / pillars absent).
    expect(screen.queryByTestId("welcome-content")).toBeNull();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("regression: typed client issues GET /api/me/onboarding on mount", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        state: "welcome",
        current_step: "welcome",
        completed: false,
      }),
    );

    renderWithQueryClient(<WelcomeFirstLoginPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(ONBOARDING_ENDPOINT);
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("regression: advance button posts {step:'welcome'} to /api/me/onboarding/advance then navigates", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          state: "welcome",
          current_step: "welcome",
          completed: false,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          { next_step: "setup", completed: false, current_step: "setup" },
          { status: 201 },
        ),
      )
      // Refetch after invalidation.
      .mockResolvedValueOnce(
        jsonResponse({
          state: "setup",
          current_step: "setup",
          completed: false,
        }),
      );

    renderWithQueryClient(<WelcomeFirstLoginPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("welcome-content")).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId("welcome-advance-button"));

    await waitFor(() => {
      // GET + POST advance (refetch on invalidation may fire later).
      expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    const advanceCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes(ONBOARDING_ADVANCE_ENDPOINT),
    );
    expect(advanceCall).toBeTruthy();
    const body = JSON.parse(String(advanceCall![1]?.body ?? "{}"));
    expect(body.step).toBe("welcome");
    expect(body).toHaveProperty("payload");

    await waitFor(() => expect(pushMock).toHaveBeenCalledTimes(1));
    expect(pushMock.mock.calls[0][0]).toBe("/onboarding/workspace-setup");
  });

  it("regression: skip button posts to /api/me/onboarding/skip then navigates", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          state: "welcome",
          current_step: "welcome",
          completed: false,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            skipped_at: "2026-05-17T00:00:00Z",
            next_step: "setup",
            completed: false,
          },
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          state: "setup",
          current_step: "setup",
          completed: false,
        }),
      );

    renderWithQueryClient(<WelcomeFirstLoginPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("welcome-content")).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId("welcome-skip-button"));

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    const skipCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes(ONBOARDING_SKIP_ENDPOINT),
    );
    expect(skipCall).toBeTruthy();
    expect(skipCall![1]?.method).toBe("POST");

    await waitFor(() => expect(pushMock).toHaveBeenCalledTimes(1));
    expect(pushMock.mock.calls[0][0]).toBe("/onboarding/workspace-setup");
  });
});
