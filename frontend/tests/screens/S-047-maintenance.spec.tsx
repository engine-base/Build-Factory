/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-56 / S-047 — メンテナンス中 (maintenance) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 6 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness; tsc strict mode
 *       picks them up once the Wave 2 frontend test ticket (T-V3-C-TEST-01) is
 *       installed. Pattern mirrors S-001 / S-048 specs.
 *
 * Covers (mapped to T-V3-C-56 acceptance_criteria —逐語):
 *   structural.AC-S1 -> h1 === "メンテナンス中" + data-screen-id="S-047"
 *   structural.AC-S2 -> Lucide icons only (no emoji)
 *   functional.AC-F1 -> 401 redirects to /login (S-001), no workspace data
 *   functional.AC-F2 -> skeleton role="status" aria-live="polite" while loading,
 *                       then atomic swap to content
 *   middleware       -> isMaintenanceModeEnabled() + shouldBypassMaintenance()
 *                       parse env flag + bypass list correctly
 *   countdown        -> computeCountdown() returns elapsed / total / percent.
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

import MaintenancePage, {
  computeCountdown,
} from "@/app/maintenance/page";
import { MAINTENANCE_STATUS_ENDPOINT } from "@/lib/api/maintenance";
import {
  isMaintenanceModeEnabled,
  shouldBypassMaintenance,
} from "../../middleware";

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

const VALID_PAYLOAD = {
  status: "in_progress" as const,
  started_at: "2026-05-15T04:00:00+09:00",
  eta_at: "2026-05-15T06:00:00+09:00",
  items: [
    { label: "DB 移行 (v2.0 → v3.0)" },
    { label: "RLS policy 全 entity 補完" },
    { label: "Backend pyright strict 適用" },
  ],
  status_page_url: "https://status.engine-base.com",
};

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

describe("T-V3-C-56 S-047 メンテナンス中 (maintenance)", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-047' and exact h1 'メンテナンス中'", async () => {
    fetchMock.mockResolvedValue(jsonResponse(VALID_PAYLOAD));

    renderWithQueryClient(<MaintenancePage />);

    // Wait for the query to resolve (skeleton → content).
    await waitFor(() => {
      expect(screen.queryByTestId("maintenance-content")).not.toBeNull();
    });

    const root = document.querySelector("[data-screen-id='S-047']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-screen-name")).toBe("maintenance");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-56");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("メンテナンス中");

    // AC-S2: no emoji glyphs in the rendered DOM (Lucide icons only).
    // The emoji ranges below match the smartphone-typical pictographic blocks.
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F2: while data is being fetched the skeleton with role='status' + aria-live='polite' is rendered, then replaced atomically", async () => {
    // Hold the fetch open until we manually resolve.
    let resolveFetch: (value: Response) => void;
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((res) => {
          resolveFetch = res;
        }),
    );

    renderWithQueryClient(<MaintenancePage />);

    const skeleton = await screen.findByTestId("maintenance-skeleton");
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-live")).toBe("polite");
    // Content not yet present.
    expect(screen.queryByTestId("maintenance-content")).toBeNull();

    // Resolve the fetch → skeleton should be replaced atomically with content.
    resolveFetch!(jsonResponse(VALID_PAYLOAD));

    await waitFor(() => {
      expect(screen.queryByTestId("maintenance-content")).not.toBeNull();
    });
    expect(screen.queryByTestId("maintenance-skeleton")).toBeNull();
  });

  it("AC-F1: 401 from GET /api/system/maintenance redirects to /login (S-001) and renders no workspace data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "UNAUTHORIZED", message: "missing token" } },
        { status: 401 },
      ),
    );

    renderWithQueryClient(<MaintenancePage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledTimes(1);
    });
    expect(replaceMock.mock.calls[0][0]).toBe("/login");

    // AC-F1 second half: no workspace data is rendered (h1 / ETA / items absent).
    expect(screen.queryByTestId("maintenance-content")).toBeNull();
    expect(screen.queryByTestId("maintenance-eta")).toBeNull();
    expect(screen.queryByTestId("maintenance-items")).toBeNull();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("regression: typed client issues GET /api/system/maintenance on mount and renders ETA countdown + status link", async () => {
    fetchMock.mockResolvedValue(jsonResponse(VALID_PAYLOAD));

    renderWithQueryClient(<MaintenancePage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(MAINTENANCE_STATUS_ENDPOINT);
    expect(init?.method ?? "GET").toBe("GET");

    await waitFor(() =>
      expect(screen.queryByTestId("maintenance-content")).not.toBeNull(),
    );

    // ETA countdown is rendered with elapsed / total minutes and progress bar.
    expect(screen.getByTestId("maintenance-eta")).not.toBeNull();
    expect(screen.getByTestId("maintenance-elapsed").textContent).toMatch(
      /\d+ 分 \/ 120 分/,
    );
    const progress = screen.getByTestId("maintenance-progress");
    expect(progress.getAttribute("role")).toBe("progressbar");
    expect(progress.getAttribute("aria-valuemax")).toBe("100");
    // Status page link to status.engine-base.com.
    const link = screen.getByTestId("maintenance-status-link") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("https://status.engine-base.com");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("computeCountdown: returns elapsed / total / percent / overdue from start+eta window", () => {
    // 120 minute window, current time = start + 42min → 42/120 ≈ 35%.
    const start = "2026-05-15T04:00:00+09:00";
    const eta = "2026-05-15T06:00:00+09:00";
    const now = new Date("2026-05-15T04:42:00+09:00");
    const r = computeCountdown({ started_at: start, eta_at: eta }, now);
    expect(r.totalMinutes).toBe(120);
    expect(r.elapsedMinutes).toBe(42);
    expect(r.progressPercent).toBe(35);
    expect(r.isOverdue).toBe(false);

    // Overdue case — 130min after start → clamps progress to 100 and flags overdue.
    const overdueNow = new Date("2026-05-15T06:10:00+09:00");
    const r2 = computeCountdown({ started_at: start, eta_at: eta }, overdueNow);
    expect(r2.progressPercent).toBe(100);
    expect(r2.isOverdue).toBe(true);
  });

  it("middleware: isMaintenanceModeEnabled() parses truthy / falsy env flags + shouldBypassMaintenance() preserves the bypass list", () => {
    expect(isMaintenanceModeEnabled({ MAINTENANCE_MODE: "1" })).toBe(true);
    expect(isMaintenanceModeEnabled({ MAINTENANCE_MODE: "true" })).toBe(true);
    expect(isMaintenanceModeEnabled({ MAINTENANCE_MODE: "on" })).toBe(true);
    expect(isMaintenanceModeEnabled({ MAINTENANCE_MODE: "0" })).toBe(false);
    expect(isMaintenanceModeEnabled({ MAINTENANCE_MODE: "" })).toBe(false);
    expect(isMaintenanceModeEnabled({})).toBe(false);
    // Fallback to NEXT_PUBLIC_MAINTENANCE when the server-side flag is unset.
    expect(
      isMaintenanceModeEnabled({ NEXT_PUBLIC_MAINTENANCE: "yes" }),
    ).toBe(true);

    // The bypass list keeps /_next/*, /favicon.ico, /maintenance, and the
    // status endpoint reachable so the page itself can render + monitoring
    // probes don't loop on 503.
    expect(shouldBypassMaintenance("/maintenance")).toBe(true);
    expect(shouldBypassMaintenance("/_next/static/chunks/foo.js")).toBe(true);
    expect(shouldBypassMaintenance("/favicon.ico")).toBe(true);
    expect(shouldBypassMaintenance("/api/system/maintenance")).toBe(true);
    // Everything else gets the 503 maintenance gate.
    expect(shouldBypassMaintenance("/")).toBe(false);
    expect(shouldBypassMaintenance("/workspaces")).toBe(false);
    expect(shouldBypassMaintenance("/api/audit-logs")).toBe(false);
  });
});
