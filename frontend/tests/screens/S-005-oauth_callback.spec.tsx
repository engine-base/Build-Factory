// @ts-nocheck
/**
 * T-V3-C-05 / S-005 — OAuth コールバック screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket.
 *       Once installed, tsc strict mode picks them up automatically.
 *
 * Covers (mapped to T-V3-C-05 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-005"
 *   structural.AC-S2  -> "h1 reads 'ログイン中...' in the loading state"
 *   functional.AC-F1  -> "calls GET /api/auth/oauth/{provider}/callback?code=&state= via typed client"
 *   functional.AC-F2  -> "renders non-technical error toast referencing the failing endpoint"
 *   functional.AC-F3  -> "persists access_token + refresh_token on 200 + redirects to /dashboard"
 *   extra            -> "401 CSRF mismatch surfaces the dedicated error_csrf card"
 *   extra            -> "missing code/state query params triggers a toast w/o calling fetch"
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
} from "@testing-library/react";

// next/navigation mock — useSearchParams / useRouter / usePathname.
const replaceMock = vi.fn();
let mockSearch = new URLSearchParams();
let mockPathname = "/oauth-callback";
vi.mock("next/navigation", () => {
  return {
    useSearchParams: () => mockSearch,
    useRouter: () => ({
      replace: replaceMock,
      push: vi.fn(),
      refresh: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
      prefetch: vi.fn(),
    }),
    usePathname: () => mockPathname,
  };
});

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

// @/env is consumed by the typed client for NEXT_PUBLIC_API_URL.
vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import OAuthCallbackPage from "@/app/(auth)/oauth-callback/page";
import { toast } from "sonner";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function setQuery(params: Record<string, string>) {
  mockSearch = new URLSearchParams(params);
}

beforeEach(() => {
  fetchMock.mockReset();
  replaceMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  mockPathname = "/oauth-callback";
  mockSearch = new URLSearchParams();
  if (typeof window !== "undefined") window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("S-005 OAuth callback page (T-V3-C-05)", () => {
  it("AC-S1: renders root with data-screen-id='S-005'", async () => {
    setQuery({ provider: "anthropic", code: "c", state: "s" });
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: "at",
        refresh_token: "rt",
        user_id: "u-1",
      })
    );
    const { container } = render(<OAuthCallbackPage />);
    const root = container.querySelector('[data-screen-id="S-005"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-001");
  });

  it("AC-S2: loading state h1 reads 'ログイン中...'", async () => {
    setQuery({ provider: "anthropic", code: "c", state: "s" });
    // Never resolve so we stay in the loading state.
    fetchMock.mockReturnValueOnce(new Promise(() => {}));
    render(<OAuthCallbackPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("ログイン中...");
  });

  it("AC-F1: calls GET /api/auth/oauth/{provider}/callback?code=&state= via typed client", async () => {
    setQuery({ provider: "github", code: "abc", state: "xyz" });
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: "at",
        refresh_token: "rt",
        user_id: "u-1",
      })
    );
    render(<OAuthCallbackPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/auth/oauth/github/callback");
    expect(calledUrl).toContain("code=abc");
    expect(calledUrl).toContain("state=xyz");
    const init = (fetchMock.mock.calls[0][1] ?? {}) as RequestInit;
    expect(init.method).toBe("GET");
  });

  it("AC-F2: 5xx surfaces a non-technical toast referencing /api/auth/oauth/{provider}/callback w/o stack traces", async () => {
    setQuery({ provider: "anthropic", code: "c", state: "s" });
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message: "OAuth handshake failed",
        },
      })
    );
    render(<OAuthCallbackPage />);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled()
    );
    const message =
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "";
    expect(message).toContain("/api/auth/oauth/anthropic/callback");
    // Non-technical: must NOT leak server stack-trace artefacts.
    expect(message).not.toMatch(/traceback/i);
    expect(message).not.toMatch(/handshake failed/i);
    expect(message).not.toMatch(/Exception/);
  });

  it("AC-F3: 200 response persists access_token + refresh_token + user_id and redirects to /dashboard", async () => {
    vi.useFakeTimers();
    setQuery({ provider: "anthropic", code: "c", state: "s" });
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: "AT-123",
        refresh_token: "RT-456",
        user_id: "u-789",
      })
    );
    render(<OAuthCallbackPage />);
    await waitFor(() =>
      expect(window.localStorage.getItem("bf.access_token")).toBe("AT-123")
    );
    expect(window.localStorage.getItem("bf.refresh_token")).toBe("RT-456");
    expect(window.localStorage.getItem("bf.user_id")).toBe("u-789");
    // Forward to dashboard after the brief success pause.
    await vi.advanceTimersByTimeAsync(900);
    expect(replaceMock).toHaveBeenCalledWith("/dashboard");
    vi.useRealTimers();
  });

  it("401 OAuthStateMismatch shows the dedicated error_csrf card", async () => {
    setQuery({ provider: "anthropic", code: "c", state: "s" });
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, {
        detail: {
          code: "UNAUTHORIZED",
          message: "OAuth state mismatch or code expired",
        },
      })
    );
    const { container } = render(<OAuthCallbackPage />);
    await waitFor(() =>
      expect(
        container.querySelector('[data-state="error_csrf"]')
      ).not.toBeNull()
    );
    expect(screen.getByText("認証エラー")).toBeTruthy();
    expect(screen.getByText(/oauth_csrf_check_failed/)).toBeTruthy();
  });

  it("missing code/state query params triggers a toast and does NOT call fetch", async () => {
    setQuery({ provider: "anthropic" });
    render(<OAuthCallbackPage />);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled()
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
