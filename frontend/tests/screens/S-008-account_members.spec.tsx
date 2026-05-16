/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-08 / S-008 — メンバー管理 screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the new screen test harness; they are
 *       installed by the Wave 2 frontend test setup ticket (T-V3-C-TEST-01).
 *       Once installed, tsc strict mode picks them up automatically. This
 *       mirrors the pattern T-V3-C-11 (47ea1f7) and T-V3-C-04 (d728560) used.
 *
 * Covers (mapped to T-V3-C-08 acceptance_criteria):
 *   structural.AC-S1 -> "renders root with data-screen-id=S-008"
 *   structural.AC-S2 -> "renders h1 = メンバー管理"
 *   functional.AC-F1 -> "GET /api/accounts/{id}/members via typed client on mount"
 *   functional.AC-F2 -> "POST /api/accounts/{id}/invitations via typed client"
 *   functional.AC-F3 -> "DELETE /api/accounts/{id}/members/{user_id} via typed client"
 *   functional.AC-F4 -> "4xx/5xx -> non-technical toast referencing endpoint"
 *   functional.AC-F5 -> "429 surfaces rate-limit copy (20 / hour / account cap)"
 *   functional.AC-F6 -> "destructive action requires S-051 typed-name confirm dialog"
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

import AccountMembersPage from "@/app/(app)/settings/account/members/page";
import { toast } from "sonner";

const ACCOUNT_ID = "11111111-2222-3333-4444-555555555555";
const ALICE = {
  account_id: ACCOUNT_ID,
  user_id: "aaaa1111-0000-0000-0000-000000000001",
  role: "account_owner",
  email: "alice@engine-base.com",
  display_name: "alice",
  status: "active",
  last_login_at: "2 min ago",
  workspace_names: ["全 10 案件"],
};
const BOB = {
  account_id: ACCOUNT_ID,
  user_id: "bbbb2222-0000-0000-0000-000000000002",
  role: "workspace_admin",
  email: "bob@engine-base.com",
  display_name: "bob",
  status: "active",
  last_login_at: "8 min ago",
  workspace_names: ["ABC 社"],
};

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function errorResponse(status, detail, extraHeaders = {}) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AccountMembersPage />
    </QueryClientProvider>,
  );
}

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock;
  (toast.error).mockClear();
  (toast.success).mockClear();
  try {
    window.localStorage.clear();
    window.localStorage.setItem("bf.account_id", ACCOUNT_ID);
    window.localStorage.setItem("bf.access_token", "tok-test");
  } catch {
    /* jsdom only */
  }
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-08 S-008 メンバー管理", () => {
  it("AC-S1: renders root with data-screen-id='S-008'", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ members: [], total: 0 }));
    renderPage();
    const root = document.querySelector("[data-screen-id='S-008']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-004");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-08");
  });

  it("AC-S2: renders h1 with verbatim mock text 'メンバー管理'", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ members: [], total: 0 }));
    renderPage();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("メンバー管理");
  });

  it("AC-F1: GET /api/accounts/{id}/members via typed client on mount", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ members: [ALICE, BOB], total: 2 }),
    );
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(`/api/accounts/${ACCOUNT_ID}/members`);
    expect(init.method).toBe("GET");
    expect(init.headers.Authorization).toBe("Bearer tok-test");
    await waitFor(() =>
      expect(screen.getByText("alice@engine-base.com")).toBeTruthy(),
    );
  });

  it("AC-F2: POST /api/accounts/{id}/invitations via typed client on invite submit", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ members: [], total: 0 }))
      .mockResolvedValueOnce(
        jsonResponse(
          { invitation_token: "inv_abc", expires_at: "2026-06-01T00:00:00Z" },
          { status: 201 },
        ),
      );
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("invite-open"));
    fireEvent.change(screen.getByLabelText(/メールアドレス/), {
      target: { value: "new@example.com" },
    });
    const roleSelect = screen.getByLabelText(/ロール/);
    fireEvent.change(roleSelect, { target: { value: "admin" } });
    fireEvent.click(screen.getByTestId("invite-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(String(url)).toContain(`/api/accounts/${ACCOUNT_ID}/invitations`);
    expect(init.method).toBe("POST");
    const body = JSON.parse(String(init.body));
    expect(body.email).toBe("new@example.com");
    expect(body.role).toBe("admin");
  });

  it("AC-F3 + AC-F6: DELETE only after S-051 typed-name confirmation matches", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ members: [BOB], total: 1 }))
      .mockResolvedValueOnce(
        jsonResponse({ removed_at: "2026-05-16T00:00:00Z" }),
      );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("bob@engine-base.com")).toBeTruthy(),
    );

    fireEvent.click(screen.getByTestId(`remove-open-${BOB.user_id}`));

    // S-051 dialog must surface (Gate #8 indexes it via data-screen-id="S-051")
    const dialog = document.querySelector("[data-screen-id='S-051']");
    expect(dialog).not.toBeNull();

    const submit = screen.getByTestId("confirm-delete-submit");
    expect(submit.hasAttribute("disabled")).toBe(true);

    // Wrong name → still disabled, no DELETE call.
    fireEvent.change(screen.getByTestId("confirm-typed-name"), {
      target: { value: "wrong" },
    });
    expect(submit.hasAttribute("disabled")).toBe(true);

    // Correct name → submit enabled and DELETE issued.
    fireEvent.change(screen.getByTestId("confirm-typed-name"), {
      target: { value: BOB.display_name },
    });
    expect(submit.hasAttribute("disabled")).toBe(false);
    fireEvent.click(submit);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(String(url)).toContain(
      `/api/accounts/${ACCOUNT_ID}/members/${BOB.user_id}`,
    );
    expect(init.method).toBe("DELETE");
  });

  it("AC-F4: 5xx surfaces non-technical toast referencing endpoint, no stack", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(500, {
        code: "INTERNAL",
        message:
          "Traceback (most recent call last): File backend/x.py raise RuntimeError",
      }),
    );
    renderPage();
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const msg = String((toast.error).mock.calls[0][0]);
    expect(msg).toContain(`/api/accounts/${ACCOUNT_ID}/members`);
    expect(msg.toLowerCase()).not.toContain("traceback");
    expect(msg.toLowerCase()).not.toContain("runtimeerror");
  });

  it("AC-F5: 429 on POST invitations surfaces rate-limit copy (20 / hour cap)", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ members: [], total: 0 }))
      .mockResolvedValueOnce(
        errorResponse(
          429,
          { code: "RATE_LIMITED", message: "too many invitations", retry_after: 3600 },
          { "Retry-After": "3600" },
        ),
      );
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("invite-open"));
    fireEvent.change(screen.getByLabelText(/メールアドレス/), {
      target: { value: "spam@example.com" },
    });
    fireEvent.click(screen.getByTestId("invite-submit"));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    const msg = String((toast.error).mock.calls[0][0]);
    expect(msg).toContain(`/api/accounts/${ACCOUNT_ID}/invitations`);
    expect(msg).toMatch(/招待回数の上限|1 時間後/);
  });
});
