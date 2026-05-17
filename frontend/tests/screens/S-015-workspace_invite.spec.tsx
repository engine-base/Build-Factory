/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-64 / S-015 — メンバー招待 (workspace_invite) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness; tsc strict mode
 *       picks them up once the Wave 2 frontend test ticket (T-V3-C-TEST-01) is
 *       installed. Pattern mirrors S-028 / S-033 specs.
 *
 * Covers (mapped to T-V3-C-64 acceptance_criteria):
 *   structural.AC-S1   -> h1 == "メンバーを招待" (mock h1 逐語)
 *   structural.AC-S2   -> section h2 set == {"新規招待","送信済み招待 (pending)"}
 *   structural.AC-S3   -> Lucide icons only (no emoji glyphs)
 *   functional.AC-F1   -> POST /api/workspaces/{id}/invitations on submit;
 *                         2xx renders, 4xx renders empty state + toast
 *   functional.AC-F2   -> 401 redirects to /login (S-001); no data renders
 *   functional.AC-F3   -> PUT /api/accounts/{id} update plan from the typed client
 *   Revoke:            -> DELETE /api/workspaces/{id}/invitations/{token}
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

// next/navigation: stub router so we can assert push/replace targets (AC-F2)
//                  and useParams payloads.
const pushMock = vi.fn();
const replaceMock = vi.fn();
const backMock = vi.fn();
const useParamsMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    back: backMock,
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useParams: () => useParamsMock(),
}));

// sonner: capture toast.error / toast.success so we can assert error UX.
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

import WorkspaceInvitePage from "@/app/(app)/workspace/[id]/invite/page";
import {
  updateAccountPlan,
  type WorkspaceInvitation,
} from "@/api/workspace-invite";

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

const PENDING: WorkspaceInvitation[] = [
  {
    token: "tok_abc12345",
    email: "aki@new-member.com",
    role: "contributor",
    status: "pending",
    invited_by: "masato",
    invited_at: new Date(Date.now() - 2 * 86400 * 1000).toISOString(),
    expires_at: new Date(Date.now() + 5 * 86400 * 1000).toISOString(),
    workspace_id: 1,
  },
];

const LIST_PAYLOAD = { invitations: PENDING };

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  pushMock.mockReset();
  replaceMock.mockReset();
  backMock.mockReset();
  toastErrorMock.mockReset();
  toastSuccessMock.mockReset();
  useParamsMock.mockReset();
  useParamsMock.mockReturnValue({ id: "1" });
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-64 S-015 メンバー招待 (workspace_invite)", () => {
  it("AC-S1 + AC-S2 + AC-S3: renders with data-screen-id='S-015', exact h1, two section h2, and no emoji glyphs", async () => {
    fetchMock.mockResolvedValue(jsonResponse(LIST_PAYLOAD));

    renderWithQueryClient(<WorkspaceInvitePage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const root = document.querySelector("[data-screen-id='S-015']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-004");
    expect(root?.getAttribute("data-screen-name")).toBe("workspace_invite");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-64");
    expect(root?.getAttribute("data-entities")).toBe("E-043");

    // AC-S1 — h1 逐語.
    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("メンバーを招待");

    // AC-S2 — section h2 set == {"新規招待","送信済み招待 (pending)"}.
    const h2s = Array.from(root?.querySelectorAll("h2") ?? []).map(
      (h) => h.textContent?.trim() ?? "",
    );
    expect(new Set(h2s)).toEqual(new Set(["新規招待", "送信済み招待 (pending)"]));

    // AC-S3 — no emoji glyphs in the rendered DOM (Lucide only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F1: submitting the form POSTs /api/workspaces/{id}/invitations with the typed body and toasts success", async () => {
    // First call is the GET list (mount); second call is the POST submit.
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ invitations: [] }))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            token: "tok_new1",
            invitation_url: "https://app.example.com/invitation?token=tok_new1",
            expires_at: new Date(Date.now() + 7 * 86400 * 1000).toISOString(),
            email: "alice@example.com",
            role: "contributor",
          },
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ invitations: [] }));

    renderWithQueryClient(<WorkspaceInvitePage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const emailsInput = document.querySelector(
      "[data-testid='workspace-invite-emails']",
    ) as HTMLTextAreaElement;
    fireEvent.change(emailsInput, { target: { value: "alice@example.com" } });

    const form = document.querySelector(
      "[data-testid='workspace-invite-form']",
    ) as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [postUrl, postInit] = fetchMock.mock.calls[1];
    expect(String(postUrl)).toContain("/api/workspaces/1/invitations");
    expect(postInit?.method).toBe("POST");
    const body = JSON.parse(String(postInit?.body));
    expect(body.email).toBe("alice@example.com");
    expect(body.role).toBe("contributor");
    expect(body.expires_in_days).toBe(7);

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalled();
    });
  });

  it("AC-F1 tail: 4xx non-401 from the GET list renders the inline empty state + toasts the friendly message tagged with the endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: "workspaces.not_found",
            message: "no such workspace",
          },
        },
        { status: 404 },
      ),
    );

    renderWithQueryClient(<WorkspaceInvitePage />);

    await waitFor(() =>
      expect(
        document.querySelector(
          "[data-testid='workspace-invite-error-empty-state']",
        ),
      ).not.toBeNull(),
    );

    expect(toastErrorMock).toHaveBeenCalled();
    const lastErrArg = toastErrorMock.mock.calls.at(-1)?.[0] as string;
    expect(lastErrArg).toContain("/api/workspaces/1/invitations");
    expect(lastErrArg).not.toMatch(/SQL|Traceback|<html/i);
  });

  it("AC-F2: 401 redirects to /login and renders no workspace-scoped data (no pending table)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "unauthorized", message: "missing token" } },
        { status: 401 },
      ),
    );

    renderWithQueryClient(<WorkspaceInvitePage />);

    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith("/login"),
    );

    // No pending-table rendered after the unauth gate flips.
    await waitFor(() =>
      expect(
        document.querySelector(
          "[data-testid='workspace-invite-pending-table']",
        ),
      ).toBeNull(),
    );
    expect(
      document.querySelector(
        "[data-testid='workspace-invite-unauthorized']",
      ),
    ).not.toBeNull();
  });

  it("AC-F3: updateAccountPlan PUTs /api/accounts/{id} with the typed body", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { id: 42, plan: "pro", updated_at: "2026-05-17T00:00:00Z" },
        { status: 200 },
      ),
    );

    const result = await updateAccountPlan(42, { plan: "pro" });
    expect(result.plan).toBe("pro");

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/accounts/42");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ plan: "pro" });
  });

  it("renders a row per pending invitation with the expected email cell + revoke button", async () => {
    fetchMock.mockResolvedValue(jsonResponse(LIST_PAYLOAD));

    renderWithQueryClient(<WorkspaceInvitePage />);

    await waitFor(() =>
      expect(
        document.querySelector(
          "[data-testid='workspace-invite-pending-table']",
        ),
      ).not.toBeNull(),
    );

    const row = document.querySelector(
      "[data-testid='workspace-invite-row-tok_abc12345']",
    );
    expect(row).not.toBeNull();
    expect(row?.textContent).toContain("aki@new-member.com");
    expect(row?.textContent).toContain("contributor");

    expect(
      document.querySelector(
        "[data-testid='workspace-invite-revoke-tok_abc12345']",
      ),
    ).not.toBeNull();
  });

  it("revoke flow: confirm + DELETE /invitations/{token}", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(LIST_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse(
          { revoked_at: new Date().toISOString() },
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ invitations: [] }));

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWithQueryClient(<WorkspaceInvitePage />);

    await waitFor(() =>
      expect(
        document.querySelector(
          "[data-testid='workspace-invite-revoke-tok_abc12345']",
        ),
      ).not.toBeNull(),
    );

    const revokeBtn = document.querySelector(
      "[data-testid='workspace-invite-revoke-tok_abc12345']",
    ) as HTMLButtonElement;
    fireEvent.click(revokeBtn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [delUrl, delInit] = fetchMock.mock.calls[1];
    expect(String(delUrl)).toContain(
      "/api/workspaces/1/invitations/tok_abc12345",
    );
    expect(delInit?.method).toBe("DELETE");

    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled());
    confirmSpy.mockRestore();
  });

  it("AC-F1: empty emails input refuses to submit and toasts the validation message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ invitations: [] }));

    renderWithQueryClient(<WorkspaceInvitePage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const emailsInput = document.querySelector(
      "[data-testid='workspace-invite-emails']",
    ) as HTMLTextAreaElement;
    // Bypass HTML5 required validation so we can assert the empty-state handler.
    emailsInput.removeAttribute("required");
    fireEvent.change(emailsInput, { target: { value: "   " } });

    const form = document.querySelector(
      "[data-testid='workspace-invite-form']",
    ) as HTMLFormElement;
    fireEvent.submit(form);

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled());
    // No POST should have been made — only the initial GET.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
