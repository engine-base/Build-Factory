/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-63 / S-014 — 案件メンバー (workspace_members) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen
 *       test harness; tsc strict mode picks them up once the Wave 2 frontend
 *       test ticket (T-V3-C-TEST-01) is installed. Pattern mirrors
 *       S-001 / S-008 / S-028 / S-033 specs.
 *
 * Covers (mapped to T-V3-C-63 acceptance_criteria):
 *   structural.AC-S1  -> h1 == "案件メンバー" (mock h1 逐語コピー)
 *   structural.AC-S2  -> Lucide icons only (no emoji glyphs)
 *   functional.AC-F1  -> GET /api/workspaces/{id}/members renders 2xx body;
 *                        4xx renders inline error toast + empty state.
 *   functional.AC-F2  -> 401 redirects to /login (S-001); no workspace data
 *                        renders on the unauthenticated branch.
 *   functional.AC-F3  -> Role change PUTs
 *                        /api/workspaces/{id}/members/{user_id}/role; the
 *                        backend emits the account_updated audit log
 *                        (T-V3-B-06).
 *   functional.AC-F4  -> Access surface (OR across role default_permissions
 *                        and member custom_permissions, F-021) is enforced
 *                        server-side: a 403 surfaces as the friendly toast
 *                        without bypassing the check client-side.
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

// next/navigation — stub the router so we can assert /login replace for
// AC-F2 and resolve useParams() to a known workspace id.
const replaceMock = vi.fn();
const pushMock = vi.fn();
const useParamsMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useParams: () => useParamsMock(),
  useSearchParams: () => ({ get: () => null }),
}));

import WorkspaceMembersPage from "@/app/(app)/workspace/[id]/members/page";

const WORKSPACE_ID = "11111111-2222-3333-4444-555555555555";

const ALICE = {
  workspace_id: WORKSPACE_ID,
  user_id: "aaaa1111-0000-0000-0000-000000000001",
  role: "owner",
  display_name: "alice",
  email: "alice@engine-base.com",
  custom_permissions: { edit_spec: true, approve_red_line: false },
  visible_tabs: ["spec", "task", "review"],
  last_active_at: "2 min ago",
};
const BOB = {
  workspace_id: WORKSPACE_ID,
  user_id: "bbbb2222-0000-0000-0000-000000000002",
  role: "member",
  display_name: "bob",
  email: "bob@engine-base.com",
  custom_permissions: {},
  visible_tabs: ["spec"],
  last_active_at: "3h",
};

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function errorResponse(status, detail) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceMembersPage />
    </QueryClientProvider>,
  );
}

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock;
  replaceMock.mockReset();
  pushMock.mockReset();
  useParamsMock.mockReset();
  useParamsMock.mockReturnValue({ id: WORKSPACE_ID });
  try {
    window.localStorage.clear();
    window.localStorage.setItem("bf.access_token", "tok-test");
  } catch {
    /* jsdom only */
  }
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-63 S-014 案件メンバー", () => {
  it("AC-S1: renders root with data-screen-id='S-014' and h1 = 案件メンバー", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ members: [] }));
    renderPage();
    const root = document.querySelector("[data-screen-id='S-014']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-004");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-63");
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("案件メンバー");
  });

  it("AC-S2: uses Lucide icons exclusively (no emoji glyphs)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ members: [ALICE] }));
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = document.querySelector("[data-screen-id='S-014']");
    expect(root).not.toBeNull();
    // Lucide icons render as inline <svg class="lucide …">. The mock uses
    // user-plus / trash-2 / users / alert-triangle / arrow-left etc.
    const svgs = root!.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThan(0);
    // No emoji code points may appear in the rendered text content.
    const text = root!.textContent ?? "";
    const emojiPattern =
      /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F2FF}]/u;
    expect(emojiPattern.test(text)).toBe(false);
  });

  it("AC-F1 (2xx): GET /api/workspaces/{id}/members renders members on mount", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ members: [ALICE, BOB] }),
    );
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(`/api/workspaces/${WORKSPACE_ID}/members`);
    expect(init.method).toBe("GET");
    expect(init.headers.Authorization).toBe("Bearer tok-test");
    await waitFor(() =>
      expect(screen.getByText("alice@engine-base.com")).toBeTruthy(),
    );
    await waitFor(() =>
      expect(screen.getByText("bob@engine-base.com")).toBeTruthy(),
    );
  });

  it("AC-F1 (4xx): inline error toast + empty state on 403 forbidden", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(403, {
        code: "FORBIDDEN",
        message: "you are not a member of this workspace",
      }),
    );
    renderPage();
    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='members-error-toast']"),
      ).not.toBeNull(),
    );
    const toast = document.querySelector(
      "[data-testid='members-error-toast']",
    );
    expect(toast?.textContent).toContain(
      `/api/workspaces/${WORKSPACE_ID}/members`,
    );
    // The empty state must also be present so no workspace-scoped data leaks.
    expect(
      document.querySelector("[data-testid='members-empty-state']"),
    ).not.toBeNull();
    // 4xx never triggers the /login redirect.
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("AC-F2: 401 unauthenticated -> router.replace('/login') and no workspace data renders", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(401, { code: "UNAUTHORIZED", message: "missing token" }),
    );
    renderPage();
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    // The page guard keeps rendering an empty data-screen-id root so the
    // workspace table is never painted; assert no member row leaks through.
    expect(
      document.querySelector("[data-testid='members-table-body']"),
    ).toBeNull();
  });

  it("AC-F3 + AC-F4: PUT /api/workspaces/{id}/members/{user_id}/role on role change", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ members: [ALICE, BOB] }))
      .mockResolvedValueOnce(
        jsonResponse({ role: "admin", updated_at: "2026-05-17T00:00:00Z" }),
      );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("bob@engine-base.com")).toBeTruthy(),
    );
    const select = document.querySelector(
      `[data-testid='role-select-${BOB.user_id}']`,
    );
    expect(select).not.toBeNull();
    fireEvent.change(select, { target: { value: "admin" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(String(url)).toContain(
      `/api/workspaces/${WORKSPACE_ID}/members/${BOB.user_id}/role`,
    );
    expect(init.method).toBe("PUT");
    const body = JSON.parse(String(init.body));
    expect(body.role).toBe("admin");
    expect(init.headers.Authorization).toBe("Bearer tok-test");
  });

  it("AC-F4: 403 on role mutation surfaces friendly toast, no client-side bypass", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ members: [ALICE, BOB] }))
      .mockResolvedValueOnce(
        errorResponse(403, {
          code: "FORBIDDEN",
          message: "OR-policy denied by role + custom permissions",
        }),
      );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("bob@engine-base.com")).toBeTruthy(),
    );
    const select = document.querySelector(
      `[data-testid='role-select-${BOB.user_id}']`,
    );
    fireEvent.change(select, { target: { value: "admin" } });
    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='members-error-toast']"),
      ).not.toBeNull(),
    );
    const toast = document.querySelector(
      "[data-testid='members-error-toast']",
    );
    expect(toast?.textContent).toContain(
      `/api/workspaces/${WORKSPACE_ID}/members/${BOB.user_id}/role`,
    );
    // No stack-trace leak.
    expect(toast?.textContent?.toLowerCase()).not.toContain("traceback");
    // 403 does NOT trigger /login redirect (only 401 does).
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
