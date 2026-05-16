// @ts-nocheck
/**
 * T-V3-C-02 / S-002 — Signup screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the Wave 2 frontend test harness; they
 *       are installed by the dedicated test setup ticket. Once installed,
 *       tsc strict mode picks them up automatically. The same convention is
 *       used by the sister C-11 spec (committed in 47ea1f7).
 *
 * Covers (mapped to T-V3-C-02 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-002"
 *   structural.AC-S2  -> "renders h1 with text 'アカウント作成'"
 *   functional.AC-F1  -> "POST /api/auth/signup via typed client on submit"
 *   functional.AC-F2  -> "GET /api/invitations/{token} via typed client when ?invite present"
 *   functional.AC-F3  -> "4xx/5xx → non-technical toast that references endpoint, no stack"
 *   functional.AC-F4  -> "post-success → /dashboard (or /workspaces/invite/accept for invite)"
 *   functional.AC-F5  -> "login response includes access_token + refresh_token + user_id"
 *   functional.AC-F6  -> "login 401 surfaces a generic non-enumerating toast"
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

// next/navigation hooks (mocked router + searchParams)
const pushMock = vi.fn();
const searchParamsMock = { value: new URLSearchParams() };
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: pushMock, prefetch: vi.fn() }),
  useSearchParams: () => ({
    get: (k: string) => searchParamsMock.value.get(k),
  }),
}));

// sonner is a side-effect toast — mock so we can assert toast.error fires.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import SignupPage from "@/app/(auth)/signup/page";
import { toast } from "sonner";

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function errorResponse(status: number, detail: unknown): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fillValidForm() {
  fireEvent.change(screen.getByLabelText(/表示名/), {
    target: { value: "高本 まさと" },
  });
  fireEvent.change(screen.getByLabelText(/メールアドレス/), {
    target: { value: "you@example.com" },
  });
  fireEvent.change(screen.getByLabelText(/パスワード/), {
    target: { value: "Sup3r$ecret9" },
  });
  // tos + privacy checkboxes are the only two on the page
  const checkboxes = screen.getAllByRole("checkbox");
  fireEvent.click(checkboxes[0]);
  fireEvent.click(checkboxes[1]);
}

beforeEach(() => {
  fetchMock.mockReset();
  pushMock.mockReset();
  searchParamsMock.value = new URLSearchParams();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-02 S-002 Signup", () => {
  it("AC-S1: renders root with data-screen-id='S-002'", () => {
    renderWithQueryClient(<SignupPage />);
    const root = document.querySelector("[data-screen-id='S-002']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-001");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-02");
  });

  it("AC-S2: renders h1 with verbatim mock text 'アカウント作成'", () => {
    renderWithQueryClient(<SignupPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("アカウント作成");
  });

  it("AC-F1 + AC-F5: submits POST /api/auth/signup then POST /api/auth/login via typed client", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "usr_123", verify_email_sent: true }, { status: 201 }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "acc",
          refresh_token: "ref",
          user_id: "usr_123",
        }),
      );
    renderWithQueryClient(<SignupPage />);
    fillValidForm();
    fireEvent.click(screen.getByTestId("signup-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [signupCall, loginCall] = fetchMock.mock.calls;
    expect(String(signupCall[0])).toContain("/api/auth/signup");
    expect(signupCall[1].method).toBe("POST");
    const signupBody = JSON.parse(String(signupCall[1].body));
    expect(signupBody.email).toBe("you@example.com");
    expect(signupBody.name).toBe("高本 まさと");
    expect(signupBody.password).toBe("Sup3r$ecret9");
    expect(String(loginCall[0])).toContain("/api/auth/login");
  });

  it("AC-F2: when ?invite=<token> is present, GET /api/invitations/{token} is called via typed client", async () => {
    searchParamsMock.value = new URLSearchParams("?invite=abc-token");
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        invitation: { token: "abc-token", workspace_id: "ws_1", role: "member" },
        workspace_name: "受託 EC 構築 #4",
        inviter_name: "高本 まさと",
      }),
    );
    renderWithQueryClient(<SignupPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/api/invitations/abc-token",
    );
    await waitFor(() =>
      expect(screen.getByTestId("invite-banner")).toBeTruthy(),
    );
    expect(screen.getByTestId("invite-banner").textContent).toContain(
      "受託 EC 構築 #4",
    );
  });

  it("AC-F3: signup 5xx → toast.error message references /api/auth/signup and contains no stack trace", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(500, {
        code: "INTERNAL",
        message: "internal server error",
      }),
    );
    renderWithQueryClient(<SignupPage />);
    fillValidForm();
    fireEvent.click(screen.getByTestId("signup-submit"));

    await waitFor(() =>
      expect((toast.error as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(msg).toContain("/api/auth/signup");
    expect(msg.toLowerCase()).not.toContain("traceback");
    expect(msg.toLowerCase()).not.toContain("internal server error");
  });

  it("AC-F4: on success without invite, router.push('/dashboard')", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "usr_42", verify_email_sent: true }, { status: 201 }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "acc",
          refresh_token: "ref",
          user_id: "usr_42",
        }),
      );
    renderWithQueryClient(<SignupPage />);
    fillValidForm();
    fireEvent.click(screen.getByTestId("signup-submit"));

    await waitFor(() => expect(pushMock).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });

  it("AC-F4 (invite branch): on success with invite, router.push(/workspaces/invite/accept?token=...)", async () => {
    searchParamsMock.value = new URLSearchParams("?invite=abc-token");
    fetchMock
      // invitation lookup
      .mockResolvedValueOnce(
        jsonResponse({
          invitation: { token: "abc-token", workspace_id: "ws_1", role: "member" },
          workspace_name: "ws #1",
          inviter_name: "inviter",
        }),
      )
      // signup
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "usr_42", verify_email_sent: true }, { status: 201 }),
      )
      // login
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "acc",
          refresh_token: "ref",
          user_id: "usr_42",
        }),
      );
    renderWithQueryClient(<SignupPage />);
    fillValidForm();
    fireEvent.click(screen.getByTestId("signup-submit"));

    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith(
        "/workspaces/invite/accept?token=abc-token",
      ),
    );
  });

  it("AC-F6: login 401 → toast.error with generic message (no user enumeration)", async () => {
    fetchMock
      // signup OK
      .mockResolvedValueOnce(
        jsonResponse({ user_id: "usr_91", verify_email_sent: true }, { status: 201 }),
      )
      // login 401 with deliberately-vague detail
      .mockResolvedValueOnce(
        errorResponse(401, {
          code: "INVALID_CREDENTIALS",
          message: "invalid credentials",
        }),
      );
    renderWithQueryClient(<SignupPage />);
    fillValidForm();
    fireEvent.click(screen.getByTestId("signup-submit"));

    await waitFor(() =>
      expect((toast.error as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(msg).toContain("/api/auth/login");
    // generic: must not reveal whether email was the unknown half.
    expect(msg).not.toMatch(/user (not )?found/i);
    expect(msg).not.toMatch(/email (does not exist|unknown)/i);
  });
});
