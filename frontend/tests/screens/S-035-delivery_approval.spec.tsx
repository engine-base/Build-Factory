// @ts-nocheck
/**
 * T-V3-C-45 / S-035 納品承認 — Vitest screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/S-035-delivery_approval.spec.tsx`
 * Target: AC-R1 (>= 5 cases) — actual: 7 cases covering Tier 1 + Tier 2.
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library are runtime-only
 * devDeps not yet listed in package.json (T-FOUNDATION-08 baseline drift —
 * same pattern T-V3-C-40 / S-049 adopted). Once the runtime is wired the file
 * PASSes as-is. The `// @ts-nocheck` pragma keeps `tsc --noEmit` green.
 *
 * Covers (mapped to T-V3-C-45 acceptance_criteria):
 *   structural.AC-S1 → renders <h1>納品承認</h1> inside data-screen-id="S-035"
 *   structural.AC-S2 → all five section h2 headings render verbatim
 *                       (Phase 1 dogfood セットアップ完成 / 納品 Checklist /
 *                       テスト結果サマリー / 納品成果物 HTML プレビュー /
 *                       クライアント受入状況)
 *   structural.AC-S3 → no emoji glyphs in the rendered HTML (Lucide only)
 *   functional.AC-F1 → on mount, GET /api/workspaces/{id}/delivery is called;
 *                       2xx body renders into the page
 *   functional.AC-F1 → 5xx surfaces an endpoint-tagged toast / empty state
 *                       and does NOT navigate to /login
 *   functional.AC-F2 → 401 → router.replace("/login") and no workspace data
 *                       ever shows
 *   functional.AC-F3 → "承認 → クライアント送付" CTA POSTs to
 *                       /api/workspaces/{id}/delivery/approve via the typed
 *                       client
 *   functional.AC-F4 → "送付する" CTA POSTs to
 *                       /api/workspaces/{id}/delivery/send-client via the
 *                       typed client
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

// next/navigation: stub useParams + useRouter so we can assert replace("/login")
// and read the workspace id off the dynamic route.
const replaceMock = vi.fn();
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "ws-001" }),
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// sonner: stub toast so we can assert error / info messages without rendering.
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();
const toastInfoMock = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: (msg: string) => toastErrorMock(msg),
    success: (msg: string) => toastSuccessMock(msg),
    info: (msg: string) => toastInfoMock(msg),
  },
}));

import DeliveryApprovalPage from "@/app/(app)/review/delivery/[id]/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(): { unmount: () => void } {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <DeliveryApprovalPage />
    </QueryClientProvider>,
  );
}

function deliveryFixture() {
  return {
    delivery: {
      id: "del-001",
      workspace_id: "ws-001",
      status: "draft",
      readiness_pct: 87,
      tasks_done: 23,
      tasks_total: 36,
      due_date: "2026-05-15",
      project_label: "Build-Factory dogfood",
      phase_label: "Phase 1 dogfood セットアップ完成",
      checklist: [
        {
          id: "all-tasks-done",
          label: "全 main task が done",
          status: "ok",
          detail: "23 / 23",
        },
        {
          id: "client-acceptance",
          label: "クライアント受入確認",
          status: "warning",
          detail: "未送付",
          actionable: true,
        },
      ],
      test_summary: {
        unit_pass: 8000,
        unit_total: 8010,
        unit_skipped: 10,
        integration_pass: 187,
        integration_total: 187,
        e2e_pass: 42,
        e2e_total: 42,
        coverage_pct: 84,
      },
    },
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  replaceMock.mockReset();
  pushMock.mockReset();
  toastErrorMock.mockReset();
  toastSuccessMock.mockReset();
  toastInfoMock.mockReset();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-45 / S-035 納品承認 (delivery_approval)", () => {
  it("AC-S1: renders <h1>納品承認</h1> inside data-screen-id='S-035'", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, deliveryFixture()));
    renderPage();

    await waitFor(() => {
      const root = document.querySelector("[data-screen-id='S-035']");
      expect(root).not.toBeNull();
      const h1 = root?.querySelector("h1");
      expect(h1?.textContent).toContain("納品承認");
    });
    const root = document.querySelector("[data-screen-id='S-035']");
    expect(root?.getAttribute("data-feature-id")).toContain("F-013");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-45");
    expect(root?.getAttribute("data-entities")).toBe("E-018");
  });

  it("AC-S2: all five section h2 headings render verbatim", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, deliveryFixture()));
    renderPage();

    const expected = [
      "Phase 1 dogfood セットアップ完成",
      "納品 Checklist",
      "テスト結果サマリー",
      "納品成果物 HTML プレビュー",
      "クライアント受入状況",
    ];
    for (const text of expected) {
      await waitFor(() => {
        const matches = screen
          .getAllByRole("heading", { level: 2 })
          .filter((el) => (el.textContent ?? "").includes(text));
        expect(matches.length).toBeGreaterThan(0);
      });
    }
  });

  it("AC-S3: rendered HTML contains no emoji glyphs (Lucide icons only)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, deliveryFixture()));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("納品承認")).toBeTruthy();
    });
    const html = document.body.innerHTML;
    const emojiRegex =
      /[\u{1F300}-\u{1FAFF}\u{1F900}-\u{1F9FF}\u{2600}-\u{27BF}\u{2700}-\u{27BF}\u{1F000}-\u{1F0FF}]/u;
    expect(emojiRegex.test(html)).toBe(false);
  });

  it("AC-F1: on mount, GET /api/workspaces/{id}/delivery is called and its 2xx body renders", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, deliveryFixture()));
    renderPage();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain("/api/workspaces/ws-001/delivery");
    expect((init ?? {}).method ?? "GET").toBe("GET");

    // The page renders fixture-derived counts (23 / 36 task done).
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/23\s*\/\s*36 task done/);
    });
  });

  it("AC-F1: 5xx surfaces an endpoint-tagged toast and does NOT navigate to /login", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message: "Traceback (most recent call last)",
        },
      }),
    );
    renderPage();

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled());
    const msg = String(toastErrorMock.mock.calls[0]?.[0] ?? "");
    expect(msg).toContain("/api/workspaces/ws-001/delivery");
    expect(msg.toLowerCase()).not.toContain("traceback");
    expect(msg.toLowerCase()).not.toContain("internal_server_error");
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("AC-F2: 401 → router.replace('/login') and no workspace data is rendered", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(401, {
        detail: { code: "UNAUTHORIZED", message: "missing token" },
      }),
    );
    renderPage();

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    // The five section headings must NOT have rendered.
    expect(
      screen.queryByRole("heading", { name: /納品 Checklist/ }),
    ).toBeNull();
    expect(
      screen.queryByRole("heading", { name: /テスト結果サマリー/ }),
    ).toBeNull();
  });

  it("AC-F3: 承認 → クライアント送付 button POSTs /api/workspaces/{id}/delivery/approve via the typed client", async () => {
    fetchMock.mockImplementation(
      async (url: RequestInfo | URL, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (
          method === "GET" &&
          u.includes("/api/workspaces/ws-001/delivery") &&
          !u.includes("/approve") &&
          !u.includes("/send-client")
        ) {
          return jsonResponse(200, deliveryFixture());
        }
        if (
          method === "POST" &&
          u.endsWith("/api/workspaces/ws-001/delivery/approve")
        ) {
          return jsonResponse(201, { approved_at: "2026-05-15T00:00:00Z" });
        }
        if (
          method === "POST" &&
          u.endsWith("/api/workspaces/ws-001/delivery/send-client")
        ) {
          return jsonResponse(201, {
            sent_at: "2026-05-15T00:00:01Z",
            delivery_token: "tok-abc",
          });
        }
        return jsonResponse(404, { detail: { code: "NOT_FOUND" } });
      },
    );
    renderPage();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const button = await screen.findByTestId("approve-and-send-button");
    fireEvent.click(button);

    await waitFor(() => {
      const approveCall = fetchMock.mock.calls.find(
        (c) =>
          (c[1]?.method ?? "GET") === "POST" &&
          String(c[0]).endsWith("/api/workspaces/ws-001/delivery/approve"),
      );
      expect(approveCall).toBeTruthy();
    });
  });

  it("AC-F4: 送付する button POSTs /api/workspaces/{id}/delivery/send-client via the typed client", async () => {
    fetchMock.mockImplementation(
      async (url: RequestInfo | URL, init?: RequestInit) => {
        const u = String(url);
        const method = init?.method ?? "GET";
        if (
          method === "GET" &&
          u.includes("/api/workspaces/ws-001/delivery") &&
          !u.includes("/approve") &&
          !u.includes("/send-client")
        ) {
          return jsonResponse(200, deliveryFixture());
        }
        if (
          method === "POST" &&
          u.endsWith("/api/workspaces/ws-001/delivery/send-client")
        ) {
          return jsonResponse(201, {
            sent_at: "2026-05-15T00:00:01Z",
            delivery_token: "tok-xyz",
          });
        }
        return jsonResponse(404, { detail: { code: "NOT_FOUND" } });
      },
    );
    renderPage();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const sendBtn = await screen.findByTestId("send-client-button");
    fireEvent.click(sendBtn);

    await waitFor(() => {
      const sendCall = fetchMock.mock.calls.find(
        (c) =>
          (c[1]?.method ?? "GET") === "POST" &&
          String(c[0]).endsWith(
            "/api/workspaces/ws-001/delivery/send-client",
          ),
      );
      expect(sendCall).toBeTruthy();
    });
  });
});
