/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-55 / S-046 — 403 Forbidden (forbidden_403) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness; tsc strict
 *       mode picks them up once the Wave 2 frontend test ticket
 *       (T-V3-C-TEST-01) is installed. Pattern mirrors S-001 / S-048 specs.
 *
 * Covers (mapped to T-V3-C-55 acceptance_criteria):
 *   structural.AC-S1 -> "h1 == 'アクセス権限がありません'"
 *   structural.AC-S2 -> "Lucide icons only (no emoji)"
 *   functional.AC-F1 -> "401 redirects to /login (S-001), no workspace data"
 *   functional.AC-F2 -> "skeleton role='status' aria-live='polite' while loading"
 *   regression       -> typed client calls GET /api/me, POST role-requests
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

import Forbidden403Page from "@/app/forbidden/page";
import {
  ME_ENDPOINT,
  ROLE_REQUEST_ENDPOINT_PREFIX,
} from "@/lib/api/forbidden-403";

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

describe("T-V3-C-55 S-046 アクセス権限がありません (forbidden_403)", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-046' and exact h1 'アクセス権限がありません', no emoji glyphs", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        role: "monitor",
        workspace_id: 42,
        display_name: "ユーザー A",
      }),
    );

    renderWithQueryClient(<Forbidden403Page />);

    // Wait for the query to resolve (skeleton → content).
    await waitFor(() => {
      expect(screen.queryByTestId("forbidden-content")).not.toBeNull();
    });

    const root = document.querySelector("[data-screen-id='S-046']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-screen-name")).toBe("forbidden_403");
    expect(root?.getAttribute("data-screen-category")).toBe("system");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("アクセス権限がありません");

    // AC-S2: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);

    // Role mismatch explanation present (current + required).
    expect(
      screen.queryByTestId("forbidden-current-role")?.textContent,
    ).toBe("monitor");
    expect(
      screen.queryByTestId("forbidden-required-role")?.textContent,
    ).toBe("workspace_admin");
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

    renderWithQueryClient(<Forbidden403Page />);

    const skeleton = await screen.findByTestId("forbidden-skeleton");
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-live")).toBe("polite");
    // Content not yet present.
    expect(screen.queryByTestId("forbidden-content")).toBeNull();

    // Resolve the fetch → skeleton should be replaced atomically with content.
    resolveFetch!(
      jsonResponse({
        role: "monitor",
        workspace_id: 42,
      }),
    );

    await waitFor(() => {
      expect(screen.queryByTestId("forbidden-content")).not.toBeNull();
    });
    expect(screen.queryByTestId("forbidden-skeleton")).toBeNull();
  });

  it("AC-F1: 401 from GET /api/me redirects to /login (S-001) and renders no workspace-scoped data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "UNAUTHORIZED", message: "missing token" } },
        { status: 401 },
      ),
    );

    renderWithQueryClient(<Forbidden403Page />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledTimes(1);
    });
    expect(replaceMock.mock.calls[0][0]).toBe("/login");

    // AC-F1 second half: no workspace-scoped data is rendered.
    expect(screen.queryByTestId("forbidden-content")).toBeNull();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.queryByTestId("forbidden-role-card")).toBeNull();
  });

  it("regression: typed client issues GET /api/me on mount", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        role: "developer",
        workspace_id: 7,
      }),
    );

    renderWithQueryClient(<Forbidden403Page />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(ME_ENDPOINT);
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("regression: request access button POSTs to /api/workspaces/{id}/role-requests with requested_role=workspace_admin", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          role: "monitor",
          workspace_id: 42,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          { requested_at: "2026-05-17T00:00:00Z" },
          { status: 201 },
        ),
      );

    renderWithQueryClient(<Forbidden403Page />);

    await waitFor(() =>
      expect(screen.queryByTestId("forbidden-content")).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId("forbidden-request-access-button"));

    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    const reqCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).startsWith(`${ROLE_REQUEST_ENDPOINT_PREFIX}/42/role-requests`),
    );
    expect(reqCall).toBeTruthy();
    expect(reqCall![1]?.method).toBe("POST");
    const body = JSON.parse(String(reqCall![1]?.body ?? "{}"));
    expect(body.requested_role).toBe("workspace_admin");

    // Button should reflect the "依頼を送信しました" idempotent state.
    await waitFor(() => {
      const btn = screen.getByTestId("forbidden-request-access-button");
      expect(btn.textContent).toContain("依頼を送信しました");
      expect((btn as HTMLButtonElement).disabled).toBe(true);
    });
  });

  it("regression: dashboard button navigates to /dashboard", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        role: "monitor",
        workspace_id: 42,
      }),
    );

    renderWithQueryClient(<Forbidden403Page />);

    await waitFor(() =>
      expect(screen.queryByTestId("forbidden-content")).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId("forbidden-dashboard-button"));

    expect(pushMock).toHaveBeenCalledTimes(1);
    expect(pushMock.mock.calls[0][0]).toBe("/dashboard");
  });
});
