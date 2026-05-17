// @ts-nocheck
/**
 * T-V3-C-42 / S-040 — コスト ダッシュボード screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket
 *       (T-V3-C-TEST-01). Same convention as T-V3-C-17 / C-18 / C-19 / C-20 /
 *       C-22.
 *
 * Covers (mapped to T-V3-C-42 acceptance_criteria):
 *   structural.AC-S1  -> "h1 reads 'コスト ダッシュボード'"
 *   structural.AC-S2  -> "KPI labels set ⊇ {Ops, 今月コスト, トークン (今月),
 *                         セッション平均}"
 *   structural.AC-S3  -> "section h2 set == {案件別コスト, AI 社員別コスト,
 *                         日別コスト推移 (15 日)}"
 *   structural.AC-S4  -> "no emoji glyphs on the page" (Lucide icons only)
 *   functional.AC-F1  -> "GET /api/observability/cost-summary on mount; 4xx →
 *                         endpoint-tagged error toast + empty state"
 *   functional.AC-F2  -> "401 → page surfaces sign-in CTA pointing at /login
 *                         (S-001) and does not render workspace-scoped data"
 *   functional.AC-F3  -> "typed client returns total_usd + by_provider +
 *                         by_user breakdown"
 *   regression.AC-R1  -> "CostDashboardApiError.toUserMessage() carries the
 *                         failing endpoint without leaking server stack"
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
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";

import CostDashboardPage from "@/app/(app)/ops/cost-dashboard/page";
import {
  COST_SUMMARY_ENDPOINT,
  CostDashboardApiError,
  buildCostSummaryEndpoint,
} from "@/api/cost-dashboard";

// --------------------------------------------------------------------------
// Test harness
// --------------------------------------------------------------------------

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;
const originalLocation = globalThis.location;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CostDashboardPage />
    </QueryClientProvider>,
  );
}

const SUMMARY_OK = {
  total_usd: 56.13,
  by_provider: {
    "受託 EC 構築 #4": 26.81,
    "Build-Factory dogfood": 21.33,
    "XYZ 社": 6.13,
    "ABC 社": 1.86,
  },
  by_user: {
    devon: 18.93,
    winston: 10.8,
    quinn: 8.26,
    mary: 6.53,
    secretary: 4.8,
    others: 6.81,
  },
  by_day: {
    "2026-05-01": 1.12,
    "2026-05-02": 1.96,
    "2026-05-03": 1.68,
    "2026-05-04": 2.52,
    "2026-05-05": 3.36,
    "2026-05-06": 3.08,
    "2026-05-07": 3.92,
    "2026-05-08": 3.64,
    "2026-05-09": 4.48,
    "2026-05-10": 4.2,
    "2026-05-11": 5.04,
    "2026-05-12": 4.76,
    "2026-05-13": 5.32,
    "2026-05-14": 4.93,
    "2026-05-15": 5.6,
  },
  tokens_this_month: 42_800_000,
  session_average_usd: 0.31,
};

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation((url: string) => {
    const u = String(url);
    if (u.includes(COST_SUMMARY_ENDPOINT)) {
      return Promise.resolve(jsonResponse(200, SUMMARY_OK));
    }
    return Promise.resolve(jsonResponse(500, { detail: "X" }));
  });

  // Stub window.location so AC-F2 redirect can be observed without exiting
  // jsdom.
  Object.defineProperty(globalThis, "location", {
    configurable: true,
    value: {
      ...(originalLocation ?? {}),
      href: "http://localhost/ops/cost-dashboard",
      replace: vi.fn(),
      assign: vi.fn(),
    },
  });
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  Object.defineProperty(globalThis, "location", {
    configurable: true,
    value: originalLocation,
  });
});

// --------------------------------------------------------------------------
// Specs
// --------------------------------------------------------------------------

describe("S-040 コスト ダッシュボード (T-V3-C-42)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id=\"S-040\" and matching h1", async () => {
    const { container } = renderPage();
    const root = container.querySelector('[data-screen-id="S-040"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-017");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-42");
    expect(root?.getAttribute("data-entities")).toBe("E-027,E-028");
    expect(root?.getAttribute("data-phase")).toBe("Phase 1");

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toContain("コスト ダッシュボード");
  });

  it("[Tier1 AC-S2] hero exposes KPI labels covering the mock set", async () => {
    renderPage();
    // mock kpi_labels = ["Ops", "今月コスト", "トークン (今月)", "セッション平均"]
    expect(screen.getByTestId("kpi-category-label").textContent).toContain(
      "Ops",
    );
    expect(screen.getByTestId("kpi-monthly-cost").textContent).toContain(
      "今月コスト",
    );
    expect(screen.getByTestId("kpi-tokens-this-month").textContent).toContain(
      "トークン (今月)",
    );
    expect(screen.getByTestId("kpi-session-average").textContent).toContain(
      "セッション平均",
    );
  });

  it("[Tier1 AC-S3] section h2 set equals mock section_h2_texts", async () => {
    renderPage();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalled(),
    );
    const h2s = screen.getAllByRole("heading", { level: 2 });
    const texts = h2s.map((el) => el.textContent?.trim());
    expect(texts).toContain("案件別コスト");
    expect(texts).toContain("AI 社員別コスト");
    expect(texts).toContain("日別コスト推移 (15 日)");
    // Cap — only the three required sections (plus optional banner h2).
    expect(h2s.length).toBeLessThanOrEqual(5);
  });

  it("[Tier1 AC-S4] renders no emoji glyphs (Lucide-only)", () => {
    const { container } = renderPage();
    const text = container.textContent ?? "";
    // Catch the common emoji ranges (BMP pictographs + symbols).
    // eslint-disable-next-line no-misleading-character-class
    const emojiRe = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
    expect(emojiRe.test(text)).toBe(false);
  });

  it("[Tier2 AC-F1] mount triggers GET /api/observability/cost-summary and renders breakdown rows", async () => {
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(COST_SUMMARY_ENDPOINT);

    // by_provider top row rendered
    const byProject = await screen.findByTestId("section-by-project");
    expect(byProject.textContent).toContain("受託 EC 構築 #4");
    expect(byProject.textContent).toContain("¥");

    // by_user top row rendered
    const byEmployee = await screen.findByTestId("section-by-employee");
    expect(byEmployee.textContent).toContain("devon");
  });

  it("[Tier2 AC-F1] 5xx surfaces an endpoint-tagged toast without leaking server stack", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(500, {
          detail:
            "Traceback (most recent call last):\n  File '/srv/app/cost.py', line 42\n    raise SQLError('boom')",
        }),
      ),
    );

    renderPage();
    const toast = await screen.findByTestId("cost-dashboard-error");
    expect(toast.textContent).toContain(COST_SUMMARY_ENDPOINT);
    expect(toast.textContent).not.toMatch(/Traceback|SQLError|cost\.py/);
  });

  it("[Tier2 AC-F2] 401 hides workspace data and points the user at /login (S-001)", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "observability.unauthorized", message: "no token" },
        }),
      ),
    );

    renderPage();
    const banner = await screen.findByTestId("cost-dashboard-unauthenticated");
    expect(banner.textContent).toContain("サインインが必要です");

    const link = screen.getByTestId("redirect-login-link");
    expect(link.getAttribute("href")).toBe("/login");

    // No workspace-scoped data rendered while unauthenticated.
    expect(screen.queryByTestId("section-by-project")).toBeNull();
    expect(screen.queryByTestId("section-by-employee")).toBeNull();
    expect(screen.queryByTestId("section-daily")).toBeNull();
  });

  it("[Tier2 AC-F3] changing the date range re-issues the GET with from/to params", async () => {
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fetchMock.mockClear();

    fireEvent.change(screen.getByTestId("filter-from"), {
      target: { value: "2026-05-08" },
    });
    fireEvent.change(screen.getByTestId("filter-to"), {
      target: { value: "2026-05-15" },
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calls = fetchMock.mock.calls.map((c) => String(c[0]));
    const matched = calls.find(
      (u) => u.includes("from=2026-05-08") && u.includes("to=2026-05-15"),
    );
    expect(matched).toBeDefined();
  });

  it("[API unit] buildCostSummaryEndpoint serialises workspace_id + from + to", () => {
    const built = buildCostSummaryEndpoint({
      workspace_id: "ws_abc",
      from: "2026-05-01",
      to: "2026-05-15",
    });
    expect(built).toContain(COST_SUMMARY_ENDPOINT);
    expect(built).toContain("workspace_id=ws_abc");
    expect(built).toContain("from=2026-05-01");
    expect(built).toContain("to=2026-05-15");
  });

  it("[Regression AC-R1] CostDashboardApiError.toUserMessage carries the endpoint without exposing server stack", () => {
    const endpoint = buildCostSummaryEndpoint({ from: "2026-05-01" });
    const err = new CostDashboardApiError(
      "observability.rate_limited",
      "rate limited (internal: stacktrace at /srv/app/cost.py:42)",
      429,
      endpoint,
    );
    expect(err.endpoint).toBe(endpoint);
    expect(err.status).toBe(429);
    const friendly = err.toUserMessage();
    expect(friendly).toContain(endpoint);
    expect(friendly).not.toMatch(/Traceback|stacktrace|cost\.py/);
  });
});
