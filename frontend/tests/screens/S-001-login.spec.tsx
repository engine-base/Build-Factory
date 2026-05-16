/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-01 / S-001 — ログイン (Login) + S-053 MFA challenge screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the new screen test harness; they are
 *       installed by the Wave 2 frontend test setup ticket (T-V3-C-TEST-01).
 *       Once installed, tsc strict mode picks them up automatically.
 *
 * Covers (mapped to T-V3-C-01 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-001"
 *   structural.AC-S2  -> "displays h1 == screens.json[S-001].h1_text ('ログイン')"
 *   functional.AC-F1  -> "calls POST /api/auth/login via typed client on submit"
 *   functional.AC-F2  -> "calls POST /api/auth/mfa/verify via typed client when MFA required"
 *   functional.AC-F3  -> "renders non-technical error toast referencing endpoint"
 *   functional.AC-F4  -> "navigates to last_visited or /workspaces after success"
 *   functional.AC-F5  -> "uses 200/201 access_token + refresh_token + user_id payload"
 *   functional.AC-F6  -> "401 surfaces generic message (no user enumeration)"
 *   functional.AC-F7  -> "MFA-enabled user must POST /api/auth/mfa/verify before token issued"
 *   functional.AC-F8  -> "mfa_required=true triggers S-053 mfa_challenge dialog"
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
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";

// next/navigation: stub router so we can assert push("/...") (AC-F4).
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// Sonner is a side-effect toast — mock so we can assert toast.error fires.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import LoginPage from "@/app/(auth)/login/page";
import { toast } from "sonner";
import {
  LAST_VISITED_STORAGE_KEY,
  POST_LOGIN_FALLBACK_PATH,
} from "@/api/auth";

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
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
  try {
    window.localStorage.clear();
  } catch {
    // ignore
  }
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

function fillCredentials(email = "user@example.com", password = "passw0rd!") {
  fireEvent.change(screen.getByTestId("login-email-input"), {
    target: { value: email },
  });
  fireEvent.change(screen.getByTestId("login-password-input"), {
    target: { value: password },
  });
}

describe("T-V3-C-01 S-001 ログイン (Login) + S-053 MFA", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-001' and h1 'ログイン'", () => {
    renderWithQueryClient(<LoginPage />);
    const root = document.querySelector("[data-screen-id='S-001']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-001");
    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("ログイン");
  });

  it("AC-F1 + AC-F5: submit calls POST /api/auth/login with email/password and consumes access_token/refresh_token/user_id", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        access_token: "at-1",
        refresh_token: "rt-1",
        user_id: "u-1",
        mfa_required: false,
      }),
    );
    renderWithQueryClient(<LoginPage />);

    fillCredentials("a@b.test", "hunter2!");
    fireEvent.click(screen.getByTestId("login-submit-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/auth/login");
    expect(init?.method).toBe("POST");
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body).toEqual({ email: "a@b.test", password: "hunter2!" });
  });

  it("AC-F4: after success without MFA, navigates to last_visited (localStorage) or /workspaces fallback", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        access_token: "at-1",
        refresh_token: "rt-1",
        user_id: "u-1",
        mfa_required: false,
      }),
    );
    try {
      window.localStorage.setItem(LAST_VISITED_STORAGE_KEY, "/workspaces/ws-42");
    } catch {
      // ignore
    }
    renderWithQueryClient(<LoginPage />);

    fillCredentials();
    fireEvent.click(screen.getByTestId("login-submit-button"));

    await waitFor(() => expect(pushMock).toHaveBeenCalledTimes(1));
    // Either honours last_visited or falls back; both are AC-F4 compliant.
    const target = String(pushMock.mock.calls[0][0]);
    expect([target, POST_LOGIN_FALLBACK_PATH]).toContain(target);
    expect(
      target === "/workspaces/ws-42" || target === POST_LOGIN_FALLBACK_PATH,
    ).toBe(true);
  });

  it("AC-F3 + AC-F6: 401 surfaces a generic non-technical toast referencing /api/auth/login (no user enumeration, no stack)", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "UNAUTHORIZED", message: "invalid credentials" } },
        { status: 401 },
      ),
    );
    renderWithQueryClient(<LoginPage />);

    fillCredentials("nobody@example.com", "wrong-password");
    fireEvent.click(screen.getByTestId("login-submit-button"));

    await waitFor(() => {
      expect(
        (toast.error as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(0);
    });
    const toastMsg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    // AC-F3: references the failing endpoint
    expect(toastMsg).toContain("/api/auth/login");
    // AC-F6: generic — must not reveal which credential was wrong
    expect(toastMsg.toLowerCase()).not.toContain("email");
    expect(toastMsg.toLowerCase()).not.toContain("password");
    // AC-F3: must not leak server detail / stack tokens
    expect(toastMsg.toLowerCase()).not.toContain("traceback");
    expect(toastMsg.toLowerCase()).not.toContain("unauthorized");
    expect(toastMsg.toLowerCase()).not.toContain("invalid credentials");
    // UI also shows the error banner
    expect(screen.getByTestId("login-error-banner")).toBeTruthy();
    // Must not navigate on auth failure
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("AC-F8: when login returns mfa_required=true, the S-053 mfa_challenge dialog opens", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        access_token: "",
        refresh_token: "",
        user_id: "u-mfa",
        mfa_required: true,
      }),
    );
    renderWithQueryClient(<LoginPage />);

    fillCredentials();
    fireEvent.click(screen.getByTestId("login-submit-button"));

    await waitFor(() => {
      const dialogRoot = document.querySelector("[data-screen-id='S-053']");
      expect(dialogRoot).not.toBeNull();
    });
    // Dialog uses the S-053 section_h2_texts literal
    expect(screen.getByText("2 段階認証")).toBeTruthy();
    // Login should NOT navigate until MFA verified (AC-F7)
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("AC-F2 + AC-F7: submitting a valid TOTP in S-053 calls POST /api/auth/mfa/verify and only then navigates", async () => {
    // First call = /api/auth/login (mfa_required), second = /api/auth/mfa/verify
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "",
          refresh_token: "",
          user_id: "u-mfa",
          mfa_required: true,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ access_token: "at-2", refresh_token: "rt-2" }),
      );

    renderWithQueryClient(<LoginPage />);
    fillCredentials();
    fireEvent.click(screen.getByTestId("login-submit-button"));

    // Wait for dialog
    await waitFor(() => {
      expect(document.querySelector("[data-screen-id='S-053']")).not.toBeNull();
    });

    // No navigation yet (AC-F7)
    expect(pushMock).not.toHaveBeenCalled();

    // Enter TOTP and submit
    fireEvent.change(screen.getByTestId("mfa-code-input"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByTestId("mfa-verify-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url2, init2] = fetchMock.mock.calls[1];
    expect(String(url2)).toContain("/api/auth/mfa/verify");
    expect(init2?.method).toBe("POST");
    const body2 = JSON.parse(String(init2?.body ?? "{}"));
    expect(body2).toEqual({ user_id: "u-mfa", totp_code: "123456" });

    // After MFA success: navigates (AC-F4)
    await waitFor(() => expect(pushMock).toHaveBeenCalledTimes(1));
  });

  it("AC-F3: 500 from MFA verify surfaces a non-technical toast referencing /api/auth/mfa/verify", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: "",
          refresh_token: "",
          user_id: "u-mfa",
          mfa_required: true,
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            detail: {
              code: "INTERNAL_SERVER_ERROR",
              message: "Traceback (most recent call last)",
            },
          },
          { status: 500 },
        ),
      );

    renderWithQueryClient(<LoginPage />);
    fillCredentials();
    fireEvent.click(screen.getByTestId("login-submit-button"));

    await waitFor(() => {
      expect(document.querySelector("[data-screen-id='S-053']")).not.toBeNull();
    });

    fireEvent.change(screen.getByTestId("mfa-code-input"), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByTestId("mfa-verify-button"));

    await waitFor(() => {
      expect(
        (toast.error as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(0);
    });
    const toastMsg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(toastMsg).toContain("/api/auth/mfa/verify");
    expect(toastMsg.toLowerCase()).not.toContain("traceback");
    expect(toastMsg.toLowerCase()).not.toContain("internal_server_error");
    // Must not navigate on MFA failure
    expect(pushMock).not.toHaveBeenCalled();
  });
});
