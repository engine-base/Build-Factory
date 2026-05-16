/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-04 / S-004 — MFA セットアップ screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the new screen test harness; they are
 *       installed by the Wave 2 frontend test setup ticket (T-V3-C-TEST-01).
 *       Once installed, tsc strict mode picks them up automatically. This
 *       mirrors the pattern T-V3-C-11 used for S-011 (commit 47ea1f7).
 *
 * Covers (mapped to T-V3-C-04 acceptance_criteria):
 *   structural.AC-S1 -> "renders root with data-screen-id=S-004"
 *   structural.AC-S2 -> "renders h1 = 2 段階認証 (MFA) を有効化"
 *   structural.AC-S3 -> "renders both Step 1 / Step 2 h2 headings"
 *   functional.AC-F1 -> "calls POST /api/auth/mfa/enroll via typed client"
 *   functional.AC-F2 -> "calls POST /api/auth/mfa/verify via typed client"
 *   functional.AC-F3 -> "renders non-technical error toast referencing endpoint"
 *   functional.AC-F4 -> "verify is required before access_token is issued"
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

import MfaSetupPage from "@/app/(auth)/mfa-setup/page";
import { toast } from "sonner";
import {
  AUTH_MFA_ENROLL_ENDPOINT,
  AUTH_MFA_VERIFY_ENDPOINT,
} from "@/api/auth";

const FAKE_USER_ID = "550e8400-e29b-41d4-a716-446655440000";
const FAKE_QR_URL =
  "otpauth://totp/Build-Factory:demo@engine-base.com?secret=JBSWY3DPEHPK3PXP&issuer=Build-Factory";
const FAKE_BACKUP_CODES = [
  "a3f28b91",
  "7d4ce208",
  "5a912f6b",
  "b8c3d172",
  "e6091a5d",
  "c247f8b3",
  "9b153c8e",
  "4f72a190",
  "d83b6e25",
  "1c9e7f48",
];

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
  (toast.success as ReturnType<typeof vi.fn>).mockClear();

  // Seed user_id so AC-F4 (verify path) can issue the request.
  try {
    window.localStorage.clear();
    window.localStorage.setItem("bf.user_id", FAKE_USER_ID);
  } catch {
    // jsdom may throw in private-mode; tests for that path live elsewhere.
  }
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function renderPage() {
  return render(<MfaSetupPage />);
}

describe("T-V3-C-04 S-004 MFA セットアップ", () => {
  it("AC-S1: renders root with data-screen-id='S-004'", () => {
    renderPage();
    const root = document.querySelector("[data-screen-id='S-004']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-001");
    expect(root?.getAttribute("data-entities")).toContain("E-001");
  });

  it("AC-S2: renders h1 = '2 段階認証 (MFA) を有効化'", () => {
    renderPage();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent?.trim()).toBe("2 段階認証 (MFA) を有効化");
  });

  it("AC-S3: renders both Step 1 / Step 2 h2 headings", () => {
    renderPage();
    const h2s = screen.getAllByRole("heading", { level: 2 });
    const texts = h2s.map((el) => (el.textContent ?? "").trim());
    expect(
      texts.some((t) => t.includes("Step 1. 認証アプリで QR をスキャン")),
    ).toBe(true);
    expect(
      texts.some((t) => t.includes("Step 2. 6 桁のコードで確認")),
    ).toBe(true);
  });

  it("AC-F1: calls POST /api/auth/mfa/enroll via the typed client on QR button", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { qr_code_url: FAKE_QR_URL, backup_codes: FAKE_BACKUP_CODES },
        { status: 201 },
      ),
    );
    renderPage();

    fireEvent.click(screen.getByTestId("mfa-enroll-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(AUTH_MFA_ENROLL_ENDPOINT);
    expect((init as RequestInit).method).toBe("POST");
    const body = JSON.parse(String((init as RequestInit).body));
    expect(typeof body.totp_secret).toBe("string");
    // Base32 alphabet, 16-128 chars (matches backend MfaEnrollRequest pattern).
    expect(body.totp_secret).toMatch(/^[A-Z2-7]{16,128}$/);
  });

  it("AC-F2 + AC-F4: calls POST /api/auth/mfa/verify with the entered TOTP code before tokens are persisted", async () => {
    // First call: enroll (issues QR + backup codes).
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { qr_code_url: FAKE_QR_URL, backup_codes: FAKE_BACKUP_CODES },
        { status: 201 },
      ),
    );
    // Second call: verify (issues access + refresh tokens).
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          access_token: "at_fake_access_token",
          refresh_token: "rt_fake_refresh_token",
        },
        { status: 201 },
      ),
    );
    renderPage();

    fireEvent.click(screen.getByTestId("mfa-enroll-button"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByTestId("mfa-code-input"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByTestId("mfa-verify-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(String(url)).toContain(AUTH_MFA_VERIFY_ENDPOINT);
    expect((init as RequestInit).method).toBe("POST");
    const verifyBody = JSON.parse(String((init as RequestInit).body));
    expect(verifyBody).toEqual({
      user_id: FAKE_USER_ID,
      totp_code: "123456",
    });

    // AC-F4: access_token only persisted *after* verify resolves.
    await waitFor(() => {
      expect(window.localStorage.getItem("bf.access_token")).toBe(
        "at_fake_access_token",
      );
    });
    expect(window.localStorage.getItem("bf.refresh_token")).toBe(
      "rt_fake_refresh_token",
    );
  });

  it("AC-F3: surfaces a non-technical error toast referencing the failing endpoint on 5xx (no stack-trace leak)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          detail: {
            code: "internal_server_error",
            message: "traceback (most recent call last)...",
          },
        },
        { status: 500 },
      ),
    );
    renderPage();

    fireEvent.click(screen.getByTestId("mfa-enroll-button"));

    await waitFor(() => {
      expect(
        (toast.error as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(0);
    });
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(msg).toContain(AUTH_MFA_ENROLL_ENDPOINT);
    // Must not leak a server stack trace nor internal error code.
    expect(msg.toLowerCase()).not.toContain("traceback");
    expect(msg.toLowerCase()).not.toContain("internal_server_error");
  });

  it("AC-F3 (verify path): error toast references /api/auth/mfa/verify on 401 without leaking", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { qr_code_url: FAKE_QR_URL, backup_codes: FAKE_BACKUP_CODES },
        { status: 201 },
      ),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { detail: { code: "invalid_totp", message: "wrong code" } },
        { status: 401 },
      ),
    );
    renderPage();

    fireEvent.click(screen.getByTestId("mfa-enroll-button"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByTestId("mfa-code-input"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByTestId("mfa-verify-button"));

    await waitFor(() => {
      expect(
        (toast.error as ReturnType<typeof vi.fn>).mock.calls.length,
      ).toBeGreaterThan(0);
    });
    const lastMsg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[0] ?? "",
    );
    expect(lastMsg).toContain(AUTH_MFA_VERIFY_ENDPOINT);
    expect(lastMsg.toLowerCase()).not.toContain("invalid_totp");
    // AC-F4: no access_token persisted on failed verify.
    expect(window.localStorage.getItem("bf.access_token")).toBeNull();
  });

  it("Backup codes appear after a successful verify (Stage 3 progression)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { qr_code_url: FAKE_QR_URL, backup_codes: FAKE_BACKUP_CODES },
        { status: 201 },
      ),
    );
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { access_token: "at_x", refresh_token: "rt_x" },
        { status: 201 },
      ),
    );
    renderPage();

    fireEvent.click(screen.getByTestId("mfa-enroll-button"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId("mfa-code-input"), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByTestId("mfa-verify-button"));

    await waitFor(() => {
      const list = screen.queryByTestId("mfa-backup-codes-list");
      expect(list).not.toBeNull();
    });
    const list = screen.getByTestId("mfa-backup-codes-list");
    expect(list.querySelectorAll("li").length).toBe(FAKE_BACKUP_CODES.length);
  });
});
