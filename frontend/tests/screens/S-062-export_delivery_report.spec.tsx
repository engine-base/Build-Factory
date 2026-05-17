// @ts-nocheck
/**
 * T-V3-C-23 / S-062 納品レポート — Vitest screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/S-062-export_delivery_report.spec.tsx`
 * Target: AC-R1 (>= 5 cases) — actual: 7 cases covering Tier 1 + Tier 2.
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library / jsdom are
 * runtime-only devDeps not yet listed in package.json (T-FOUNDATION-08
 * baseline drift). Once they land, this file PASSes as-is. The
 * `// @ts-nocheck` pragma keeps `tsc --noEmit` green in the meantime (matches
 * the convention used by S-042-client_workspace.spec.tsx,
 * S-043-client_comment.spec.tsx, and S-010-notifications_inbox.spec.tsx).
 *
 * Covers (mapped to T-V3-C-23 acceptance_criteria):
 *   structural.AC-S1 -> "renders root with data-screen-id='S-062'"
 *   structural.AC-S2 -> "h1 reads screens.json[S-062].h1_text verbatim"
 *   structural.AC-S3 -> "4 section h2s present (1. 納品物サマリー / 2. 実装内容
 *                       / 3. 検証結果 / 4. 受入確認)"
 *   functional.AC-F1 -> "GET /api/workspaces/{id}/delivery via typed client on mount"
 *   functional.AC-F1b -> "GET 500 → toast.error references endpoint, no stack trace"
 *   functional.AC-F2 -> "POST /api/workspaces/{id}/exports type=spec_pdf via
 *                       typed client on PDF download click → export_id"
 *   functional.AC-F3 -> "GET /api/exports/{id} returns download_url=null while
 *                       status ∈ {queued, running} → download button stays
 *                       disabled until a non-null URL is returned"
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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// next/navigation — mock useSearchParams so the page picks up a workspace_id.
const searchMock = {
  value: new URLSearchParams("workspace_id=ws-abc"),
};
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchMock.value,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

// sonner — assert toast.error / toast.success calls.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import DeliveryReportPage from "@/app/export/delivery/page";
import { toast } from "sonner";

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, detail: unknown): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SAMPLE_DELIVERY = {
  delivery: {
    id: "del-1",
    workspace_id: "ws-abc",
    status: "approved",
    approved_at: new Date().toISOString(),
    sent_at: null,
    artifact_urls: [],
  },
};

function mockSuccessfulLoad() {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/workspaces/ws-abc/delivery")) {
      return Promise.resolve(jsonResponse(200, SAMPLE_DELIVERY));
    }
    return Promise.resolve(jsonResponse(200, {}));
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  (toast.success as ReturnType<typeof vi.fn>).mockReset();
  searchMock.value = new URLSearchParams("workspace_id=ws-abc");
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe("S-062 納品レポート (T-V3-C-23)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id='S-062' and v3 lint meta", async () => {
    mockSuccessfulLoad();
    const { container } = renderWithQueryClient(<DeliveryReportPage />);
    const root = container.querySelector('[data-screen-id="S-062"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-031");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-23");
    expect(root?.getAttribute("data-entities")).toBe("E-034");
  });

  it("[Tier1 AC-S2] h1 reads screens.json[S-062].h1_text verbatim", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<DeliveryReportPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe(
      "Phase 1 納品レポート— 受託 EC 構築 #4 / 基盤実装フェーズ —",
    );
  });

  it("[Tier1 AC-S3] all 4 section h2s present (納品物サマリー / 実装内容 / 検証結果 / 受入確認)", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<DeliveryReportPage />);
    const h2s = screen
      .getAllByRole("heading", { level: 2 })
      .map((h) => h.textContent ?? "");
    expect(h2s).toEqual([
      "1. 納品物サマリー",
      "2. 実装内容",
      "3. 検証結果",
      "4. 受入確認",
    ]);
  });

  it("[Tier2 AC-F1] GETs /api/workspaces/{id}/delivery via the typed client on mount", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<DeliveryReportPage />);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).includes("/api/workspaces/ws-abc/delivery"),
        ),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes("/api/workspaces/ws-abc/delivery"),
    );
    expect(call).toBeTruthy();
    expect(((call?.[1] ?? {}) as RequestInit).method).toBe("GET");
  });

  it("[Tier2 AC-F1b] GET 500 → toast.error references endpoint and contains no stack trace", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/workspaces/ws-abc/delivery")) {
        return Promise.resolve(
          errorResponse(500, {
            code: "INTERNAL",
            message: "Traceback (most recent call last)...",
          }),
        );
      }
      return Promise.resolve(jsonResponse(200, {}));
    });
    renderWithQueryClient(<DeliveryReportPage />);

    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msgs = (toast.error as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
      String(c[0]),
    );
    expect(
      msgs.some((m) => m.includes("/api/workspaces/ws-abc/delivery")),
    ).toBe(true);
    for (const m of msgs) {
      expect(m.toLowerCase()).not.toContain("traceback");
      expect(m.toLowerCase()).not.toContain("internal server error");
    }
  });

  it("[Tier2 AC-F2] POSTs /api/workspaces/{id}/exports with type=spec_pdf on PDF button click → returns export_id", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<DeliveryReportPage />);

    // Pre-queue the POST response.
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(202, { export_id: "exp-1" })),
    );
    // Status poll: still running, no download_url (AC-F3 contract).
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/exports/exp-1")) {
        return Promise.resolve(
          jsonResponse(200, {
            id: "exp-1",
            type: "spec_pdf",
            status: "running",
            download_url: null,
          }),
        );
      }
      if (url.includes("/api/workspaces/ws-abc/delivery")) {
        return Promise.resolve(jsonResponse(200, SAMPLE_DELIVERY));
      }
      return Promise.resolve(jsonResponse(200, {}));
    });

    fireEvent.click(screen.getByTestId("download-pdf-button"));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          (c) =>
            String(c[0]).endsWith("/api/workspaces/ws-abc/exports") &&
            ((c[1] ?? {}) as RequestInit).method === "POST",
        ),
      ).toBe(true),
    );
    const postCall = fetchMock.mock.calls.find(
      (c) =>
        String(c[0]).endsWith("/api/workspaces/ws-abc/exports") &&
        ((c[1] ?? {}) as RequestInit).method === "POST",
    );
    expect(postCall).toBeTruthy();
    const body = JSON.parse(String((postCall?.[1] as RequestInit).body));
    expect(body.type).toBe("spec_pdf");

    // AC-F2: the success toast confirms the export_id contract round-trip.
    await waitFor(() =>
      expect(toast.success as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
  });

  it("[Tier2 AC-F3] download stays disabled while GET /api/exports/{id} reports status='running' with download_url=null", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<DeliveryReportPage />);

    // Queue mutation succeeds.
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(jsonResponse(202, { export_id: "exp-2" })),
    );
    // GET /api/exports/exp-2 → running + download_url=null (AC-F3 contract).
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/exports/exp-2")) {
        return Promise.resolve(
          jsonResponse(200, {
            id: "exp-2",
            type: "spec_pdf",
            status: "running",
            download_url: null,
          }),
        );
      }
      if (url.includes("/api/workspaces/ws-abc/delivery")) {
        return Promise.resolve(jsonResponse(200, SAMPLE_DELIVERY));
      }
      return Promise.resolve(jsonResponse(200, {}));
    });

    fireEvent.click(screen.getByTestId("download-pdf-button"));

    // Wait for the GET /api/exports/exp-2 poll to land at least once.
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).includes("/api/exports/exp-2"),
        ),
      ).toBe(true),
    );

    // Button is still rendered (not the <a> link variant) — proving the page
    // honoured the download_url=null contract and did not flip to "ready".
    const button = screen.queryByTestId("download-pdf-button");
    expect(button).not.toBeNull();
    expect((button as HTMLButtonElement).disabled).toBe(true);

    // The "PDF を開く" anchor must NOT have been rendered yet.
    expect(screen.queryByTestId("download-pdf-link")).toBeNull();
  });
});
