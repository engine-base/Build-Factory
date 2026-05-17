// @ts-nocheck
/**
 * T-V3-C-41 / S-050 — AI 社員紹介 (onboarding step 3 / 3) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen test
 *       harness, wired by T-V3-C-TEST-01. Same convention as T-V3-C-17 / 22 / 25.
 *
 * Covers (mapped to T-V3-C-41 acceptance_criteria — 逐語):
 *   structural.AC-S1 -> "h1 reads 'AI 社員チームと一緒に' (mock parity)"
 *   structural.AC-S2 -> "Lucide icons only, no emoji glyphs"
 *   functional.AC-F1 -> "401 unauthenticated visitor -> redirect /login;
 *                        no workspace-scoped data rendered"
 *   functional.AC-F2 -> "skeleton (role=status aria-live=polite) while
 *                        loading; replaced atomically once data arrives"
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

vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import AiEmployeeIntroductionPage from "@/app/(onboarding)/ai-introduction/page";
import { ONBOARDING_GET_ENDPOINT } from "@/api/onboarding";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;
const originalAssign =
  typeof window !== "undefined" ? window.location.assign : undefined;
const originalReplace =
  typeof window !== "undefined" ? window.location.replace : undefined;
const locationReplaceSpy = vi.fn();
const locationAssignSpy = vi.fn();

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  locationReplaceSpy.mockReset();
  locationAssignSpy.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  if (typeof window !== "undefined") {
    // Some test runners freeze window.location; rebuild minimal stubs.
    try {
      Object.defineProperty(window.location, "replace", {
        configurable: true,
        value: locationReplaceSpy,
      });
      Object.defineProperty(window.location, "assign", {
        configurable: true,
        value: locationAssignSpy,
      });
    } catch {
      // ignore — fallback paths still log via spies via re-assignment below.
      (window.location as { replace?: unknown }).replace = locationReplaceSpy;
      (window.location as { assign?: unknown }).assign = locationAssignSpy;
    }
    // Pre-seed an auth token by default — individual tests override.
    try {
      window.localStorage.setItem("bf.access_token", "test-token");
    } catch {
      /* ignore */
    }
  }
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  if (typeof window !== "undefined") {
    if (originalAssign) {
      try {
        Object.defineProperty(window.location, "assign", {
          configurable: true,
          value: originalAssign,
        });
      } catch {
        /* ignore */
      }
    }
    if (originalReplace) {
      try {
        Object.defineProperty(window.location, "replace", {
          configurable: true,
          value: originalReplace,
        });
      } catch {
        /* ignore */
      }
    }
    try {
      window.localStorage.removeItem("bf.access_token");
    } catch {
      /* ignore */
    }
  }
});

async function renderLoaded() {
  fetchMock.mockResolvedValueOnce(
    jsonResponse(200, {
      state: "in_progress",
      current_step: "ai_employee_intro",
      completed: false,
    }),
  );
  const utils = render(<AiEmployeeIntroductionPage />);
  await waitFor(() =>
    expect(
      utils.container.querySelector('[data-view-state="loaded"]'),
    ).not.toBeNull(),
  );
  return utils;
}

describe("S-050 AI 社員紹介 page (T-V3-C-41)", () => {
  it("AC-S1: renders root with data-screen-id='S-050' and h1 'AI 社員チームと一緒に'", async () => {
    const utils = await renderLoaded();
    const root = utils.container.querySelector('[data-screen-id="S-050"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-027");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-41");

    const h1 = screen.getByRole("heading", { level: 1 });
    // 逐語: docs/mocks/2026-05-15_v3/onboarding/S-050-ai-employee-intro.html h1
    expect(h1.textContent).toBe("AI 社員チームと一緒に");
  });

  it("AC-S2: uses Lucide icons (svg/lucide-*) and no emoji glyphs are rendered", async () => {
    const utils = await renderLoaded();
    // Lucide renders <svg class="lucide ..."> nodes. Confirm at least one is
    // present (Sparkles + Check + ArrowLeft are all in the mock).
    const svgs = utils.container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThan(0);
    let lucideFound = false;
    svgs.forEach((node) => {
      const cls = node.getAttribute("class") ?? "";
      if (cls.includes("lucide")) lucideFound = true;
    });
    expect(lucideFound).toBe(true);

    // Emoji audit: scan the rendered text for the common emoji ranges the
    // design-tokens.md §8 lint forbids. The mock uses initials (SC / MR / ...),
    // not emojis.
    const text = utils.container.textContent ?? "";
    // Surrogate pair / emoji range (U+1F300..U+1FAFF) + ✓✔️▶︎ etc.
    // eslint-disable-next-line no-misleading-character-class, no-control-regex
    const emojiRegex = /[\u{1F300}-\u{1FAFF}☀-➿✀-➿]/u;
    expect(emojiRegex.test(text)).toBe(false);
  });

  it("AC-F2: STATE-DRIVEN — skeleton with role=status aria-live=polite during fetch, replaced once loaded", async () => {
    let resolveOk: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveOk = resolve;
    });
    fetchMock.mockReturnValueOnce(pending);

    const utils = render(<AiEmployeeIntroductionPage />);

    // Skeleton is present with the correct accessibility wiring.
    const skeleton = await waitFor(() =>
      utils.getByTestId("ai-intro-skeleton"),
    );
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-live")).toBe("polite");
    expect(utils.container.querySelector('[data-view-state="loading"]')).not.toBeNull();
    // Loaded persona grid is NOT yet present.
    expect(utils.queryByTestId("ai-intro-loaded")).toBeNull();

    // Resolve the pending GET → atomic swap.
    resolveOk(
      jsonResponse(200, {
        state: "in_progress",
        current_step: "ai_employee_intro",
        completed: false,
      }),
    );

    await waitFor(() => {
      expect(utils.queryByTestId("ai-intro-skeleton")).toBeNull();
    });
    expect(utils.getByTestId("ai-intro-loaded")).not.toBeNull();
    expect(
      utils.container.querySelector('[data-view-state="loaded"]'),
    ).not.toBeNull();
  });

  it("AC-F1: UNWANTED — 401 -> redirects to /login and renders zero persona cards", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, {
        detail: { code: "UNAUTHORIZED", message: "missing token" },
      }),
    );
    const utils = render(<AiEmployeeIntroductionPage />);

    // Wait for the unauthorized placeholder view to render.
    await waitFor(() => {
      expect(
        utils.container.querySelector('[data-view-state="unauthorized"]'),
      ).not.toBeNull();
    });

    // Redirect to /login was requested.
    await waitFor(() => {
      const calls = [
        ...locationReplaceSpy.mock.calls.map((c) => String(c[0] ?? "")),
        ...locationAssignSpy.mock.calls.map((c) => String(c[0] ?? "")),
      ];
      expect(calls.some((url) => url.endsWith("/login"))).toBe(true);
    });

    // No workspace-scoped data leaked: persona-card-*, ai-intro-loaded,
    // and h1 'AI 社員チームと一緒に' must NOT be present in this state.
    expect(utils.queryByTestId("ai-intro-loaded")).toBeNull();
    expect(utils.queryByTestId("persona-card-secretary")).toBeNull();
    expect(utils.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("AC-F0: GET /api/me/onboarding is called via the typed client on mount", async () => {
    await renderLoaded();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(ONBOARDING_GET_ENDPOINT);
    expect((init as RequestInit | undefined)?.method).toBe("GET");
  });

  it("renders all 10 BMAD personas in the loaded grid (mock parity)", async () => {
    const utils = await renderLoaded();
    const expected = [
      "secretary",
      "mary",
      "preston",
      "winston",
      "sally",
      "devon",
      "quinn",
      "reviewer",
      "brand",
      "mockup",
    ];
    expected.forEach((id) => {
      expect(utils.queryByTestId(`persona-card-${id}`)).not.toBeNull();
    });
  });

  it("error path: 500 -> surfaces non-technical error banner with retry", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message:
            "Traceback (most recent call last) ... psycopg2.errors.UndefinedTable",
        },
      }),
    );
    const utils = render(<AiEmployeeIntroductionPage />);

    await waitFor(() => {
      expect(utils.queryByTestId("ai-intro-error")).not.toBeNull();
    });
    const banner = utils.getByTestId("ai-intro-error");
    const text = banner.textContent ?? "";
    expect(text).toContain("/api/me/onboarding");
    // AC-F1 spirit (no stack-trace leak): error path must not surface the raw
    // server traceback even though S-050 itself only spec'd the unauthorized
    // branch — defence in depth.
    expect(text).not.toMatch(/traceback/i);
    expect(text).not.toMatch(/psycopg2/i);

    // Retry button is wired.
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { current_step: "ai_employee_intro" }),
    );
    fireEvent.click(utils.getByTestId("ai-intro-retry"));
    await waitFor(() => {
      expect(
        utils.container.querySelector('[data-view-state="loaded"]'),
      ).not.toBeNull();
    });
  });

  it("primary CTA navigates to /dashboard after POST /api/me/onboarding/advance", async () => {
    const utils = await renderLoaded();
    // The advance POST resolves successfully.
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, { next_step: "dashboard", completed: true }),
    );
    fireEvent.click(utils.getByTestId("ai-intro-advance"));
    await waitFor(() => {
      const calls = locationAssignSpy.mock.calls.map((c) => String(c[0] ?? ""));
      expect(calls.some((u) => u.endsWith("/dashboard"))).toBe(true);
    });
  });
});
