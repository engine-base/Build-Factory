/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-43 / S-041 — 監査ログ (Audit Log Viewer) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (AC-R1, coverage >= 70%).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the new screen test harness; they are
 *       installed by the Wave 2 frontend test setup ticket (T-V3-C-TEST-01).
 *       Once installed, tsc strict mode picks them up automatically.
 *
 * 3-tier AC coverage (mapped to T-V3-C-43.acceptance_criteria):
 *   structural.AC-S1  -> "renders h1 with exact text '監査ログ'"
 *   structural.AC-S2  -> "uses Lucide icons only (no emoji glyphs in DOM)"
 *   functional.AC-F1  -> "GET /api/audit-logs on mount + 4xx toast + empty state"
 *   functional.AC-F2  -> "401 redirects to /login and renders no workspace data"
 *   functional.AC-F3  -> "read-only page; server writes audit_log per mutation"
 *                        (asserted via the typed client surface: no PATCH/POST
 *                         calls originate from this page).
 *   extra             -> "filter selects bubble into the query string"
 *   extra             -> "CSV / JSON export trigger the correct endpoints"
 *   extra             -> "free-text query narrows visible rows client-side"
 *   extra             -> "selecting a row reveals before/after diff card"
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

// Mock sonner toast — sonner is loaded as a side-effect singleton in real app.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

// Mock next/navigation router — capture redirect calls for AC-F2.
const routerReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplace,
    push: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
}));

import AuditLogViewerPage from "@/app/(app)/ops/audit-logs/page";
import { toast } from "sonner";

const ITEMS_FIXTURE = [
  {
    id: 101,
    workspace_id: 1,
    actor_user_id: "masato",
    actor_persona: null,
    action: "user.login",
    resource_type: "users",
    resource_id: 1,
    payload: { ip_address: "203.0.113.42" },
    success: true,
    created_at: "2026-05-15T14:34:21.000Z",
  },
  {
    id: 102,
    workspace_id: 1,
    actor_user_id: "devon",
    actor_persona: "devon",
    action: "task.update",
    resource_type: "tasks",
    resource_id: 1042,
    payload: { before: { status: "running" }, after: { status: "done" } },
    success: true,
    created_at: "2026-05-15T14:32:18.000Z",
  },
  {
    id: 103,
    workspace_id: 1,
    actor_user_id: null,
    actor_persona: "system",
    action: "redline.violation",
    resource_type: "sessions",
    resource_id: 991,
    payload: { summary: "DROP query detected → session killed" },
    success: false,
    created_at: "2026-05-15T14:10:05.000Z",
  },
];

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function textResponse(body, init = {}) {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/csv" },
    ...init,
  });
}

function renderWithQueryClient(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock;
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
  routerReplace.mockClear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-43 S-041 監査ログ", () => {
  it("AC-S1: renders h1 with the exact text '監査ログ' and data-screen-id='S-041'", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
    );
    renderWithQueryClient(<AuditLogViewerPage />);

    const h1 = await screen.findByRole("heading", { level: 1 });
    expect(h1.textContent ?? "").toContain("監査ログ");
    const root = document.querySelector("[data-screen-id='S-041']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-018");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-43");
  });

  it("AC-S2: uses Lucide icons only — no emoji glyphs in the rendered DOM", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0 }));
    renderWithQueryClient(<AuditLogViewerPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const text = document.body.textContent ?? "";
    // Emoji range (BMP + supplementary planes). lucide-react renders <svg>
    // elements, so a clean tree must contain zero emoji code points.
    const emojiRe = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
    expect(emojiRe.test(text)).toBe(false);
    // sanity: at least one lucide svg is present (icons rendered).
    expect(document.querySelectorAll("svg").length).toBeGreaterThan(0);
  });

  it("AC-F1: calls GET /api/audit-logs on mount and renders rows", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
    );
    renderWithQueryClient(<AuditLogViewerPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/api/audit-logs");
    expect(
      await screen.findByTestId(`audit-log-row-${ITEMS_FIXTURE[0].id}`),
    ).toBeTruthy();
  });

  it("AC-F1: surfaces a non-technical error toast referencing /api/audit-logs on 4xx + empty state", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: "filter_too_broad",
            message: "internal traceback should never appear here",
          },
        },
        { status: 422 },
      ),
    );
    renderWithQueryClient(<AuditLogViewerPage />);

    await waitFor(() => {
      expect(
        (toast.error as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(0);
    });
    const toastMsg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(toastMsg).toContain("/api/audit-logs");
    expect(toastMsg.toLowerCase()).not.toContain("traceback");
    expect(toastMsg.toLowerCase()).not.toContain("filter_too_broad");
    // empty state visible
    expect(screen.getByTestId("audit-log-empty")).toBeTruthy();
  });

  it("AC-F2: 401 redirects to /login and renders no workspace-scoped rows", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "UNAUTHORIZED", message: "auth required" } },
        { status: 401 },
      ),
    );
    renderWithQueryClient(<AuditLogViewerPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    // No row should be rendered — table body shows the empty state instead.
    expect(screen.queryByTestId("audit-log-row-101")).toBeNull();
    expect(screen.queryByTestId("audit-log-row-102")).toBeNull();
  });

  it("AC-F3: this page is read-only — only GET calls hit /api/audit-logs*", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
    );
    renderWithQueryClient(<AuditLogViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    for (const call of fetchMock.mock.calls) {
      const url = String(call[0]);
      const init = (call[1] ?? {}) as RequestInit;
      const method = (init.method ?? "GET").toUpperCase();
      expect(method).toBe("GET");
      expect(url).toMatch(/\/api\/audit-logs(\b|\/)/);
    }
  });

  it("filter selects bubble into the /api/audit-logs query string", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
    );
    renderWithQueryClient(<AuditLogViewerPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId("audit-log-filter-action"), {
      target: { value: "update" },
    });
    fireEvent.change(screen.getByTestId("audit-log-filter-user"), {
      target: { value: "masato" },
    });

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(
        calls.some(
          (u) => u.includes("action=update") && u.includes("user_id=masato"),
        ),
      ).toBe(true);
    });
  });

  it("CSV export triggers GET /api/audit-logs/export.csv", async () => {
    fetchMock.mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/api/audit-logs/export.csv")) {
        return Promise.resolve(textResponse("id,action\n101,user.login\n"));
      }
      return Promise.resolve(
        jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
      );
    });
    renderWithQueryClient(<AuditLogViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("audit-log-export-csv"));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).includes("/api/audit-logs/export.csv"),
        ),
      ).toBe(true);
    });
  });

  it("JSON export triggers GET /api/audit-logs/export.json", async () => {
    fetchMock.mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/api/audit-logs/export.json")) {
        return Promise.resolve(
          jsonResponse({ json_body: ITEMS_FIXTURE }),
        );
      }
      return Promise.resolve(
        jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
      );
    });
    renderWithQueryClient(<AuditLogViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("audit-log-export-json"));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).includes("/api/audit-logs/export.json"),
        ),
      ).toBe(true);
    });
  });

  it("free-text query narrows visible rows client-side", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
    );
    renderWithQueryClient(<AuditLogViewerPage />);
    await waitFor(() =>
      expect(screen.getByTestId("audit-log-row-101")).toBeTruthy(),
    );

    fireEvent.change(screen.getByTestId("audit-log-filter-query"), {
      target: { value: "redline" },
    });

    await waitFor(() => {
      expect(screen.queryByTestId("audit-log-row-101")).toBeNull();
      expect(screen.queryByTestId("audit-log-row-102")).toBeNull();
      expect(screen.getByTestId("audit-log-row-103")).toBeTruthy();
    });
  });

  it("selecting a row reveals the before/after diff card", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: ITEMS_FIXTURE, total: ITEMS_FIXTURE.length }),
    );
    renderWithQueryClient(<AuditLogViewerPage />);

    const row = await screen.findByTestId("audit-log-row-102");
    fireEvent.click(row);

    const diff = await screen.findByTestId("audit-log-diff");
    expect(diff.textContent ?? "").toContain("Before");
    expect(diff.textContent ?? "").toContain("After");
  });
});
