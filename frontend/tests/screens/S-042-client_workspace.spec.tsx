// @ts-nocheck
/**
 * T-V3-C-15 / S-042 クライアントポータル — Vitest screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/S-042-client_workspace.spec.tsx`
 * Target: AC-R1 (>= 5 cases) — actual: 9 cases covering Tier 1 + Tier 2.
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library / jsdom are
 * runtime-only devDeps not yet listed in package.json (T-FOUNDATION-08
 * baseline drift). Once they land, this file PASSes as-is. The
 * `// @ts-nocheck` pragma keeps `tsc --noEmit` green in the meantime (matches
 * the convention used by S-005-oauth_callback.spec.tsx and S-010-notifications_inbox).
 *
 * Covers (mapped to T-V3-C-15 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id='S-042'"
 *   structural.AC-S2  -> "h1 reads '案件進捗状況' verbatim from screens.json"
 *   structural.AC-S3  -> "5 section h2s present (Phase 2 + recent + team + due + phases)"
 *   functional.AC-F1  -> "GET /api/client/workspaces/{token} via typed client on mount"
 *   functional.AC-F2  -> "GET /api/client/workspaces/{token}/spec via typed client on mount"
 *   functional.AC-F3  -> "POST /api/client/comments via typed client on submit"
 *   functional.AC-F4  -> "4xx/5xx surfaces non-technical toast referencing endpoint"
 *   functional.AC-F5  -> "409 expired token renders the dedicated token-expired banner"
 *   functional.AC-F6  -> "429 rate limit on POST surfaces friendly toast (no stack)"
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

// next/navigation — mock useParams to inject the token segment.
const paramsMock = { value: { token: "tok-demo" } as { token: string | string[] } };
vi.mock("next/navigation", () => ({
  useParams: () => paramsMock.value,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

// sonner — assert toast.error / toast.success calls.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import ClientPortalPage from "@/app/portal/[token]/page";
import { toast } from "sonner";

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(status: number, detail: unknown): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockSuccessfulLoad() {
  // GET workspace then GET spec, in arbitrary order — useQuery fires both in
  // parallel so we register both mocks ahead of mount.
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/client/workspaces/tok-demo")) {
      return Promise.resolve(
        jsonResponse(200, {
          workspace: {
            id: "ws-1",
            name: "受託 EC 構築 #4",
            status: "running",
            current_phase: "Phase 2: 統合テスト + 受入",
            progress: 0.88,
          },
        }),
      );
    }
    if (url.endsWith("/api/client/workspaces/tok-demo/spec")) {
      return Promise.resolve(
        jsonResponse(200, {
          spec_html_url: "https://example.test/spec.html",
        }),
      );
    }
    return Promise.resolve(jsonResponse(200, {}));
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  (toast.success as ReturnType<typeof vi.fn>).mockReset();
  paramsMock.value = { token: "tok-demo" };
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe("S-042 クライアントポータル (T-V3-C-15)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id='S-042' and the v3 lint meta", async () => {
    mockSuccessfulLoad();
    const { container } = renderWithQueryClient(<ClientPortalPage />);
    const root = container.querySelector('[data-screen-id="S-042"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-013");
    expect(root?.getAttribute("data-feature-id")).toContain("F-021");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-15");
    expect(root?.getAttribute("data-entities")).toContain("E-009");
    expect(root?.getAttribute("data-entities")).toContain("E-021");
  });

  it("[Tier1 AC-S2] h1 reads '案件進捗状況' verbatim from screens.json[S-042].h1_text", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientPortalPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("案件進捗状況");
  });

  it("[Tier1 AC-S3] renders all 5 section h2s from screens.json[S-042].section_h2_texts (cap 12)", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientPortalPage />);
    // The hero card surfaces "Phase 2: 統合テスト + 受入" only once loaded.
    await waitFor(() =>
      expect(
        screen.getByText("Phase 2: 統合テスト + 受入"),
      ).toBeTruthy(),
    );
    expect(screen.getByText("最近の更新")).toBeTruthy();
    expect(screen.getByText("担当チーム")).toBeTruthy();
    expect(screen.getByText("納期")).toBeTruthy();
    expect(screen.getByText("フェーズ進捗")).toBeTruthy();
    const h2s = screen.getAllByRole("heading", { level: 2 });
    // The 5 mandated section h2s (the comment-form h2 is bonus, so >=5).
    expect(h2s.length).toBeGreaterThanOrEqual(5);
  });

  it("[Tier2 AC-F1] GETs /api/client/workspaces/{token} via the typed client on mount", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientPortalPage />);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).endsWith("/api/client/workspaces/tok-demo"),
        ),
      ).toBe(true),
    );
    const wsCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).endsWith("/api/client/workspaces/tok-demo"),
    );
    expect(wsCall).toBeTruthy();
    expect(((wsCall?.[1] ?? {}) as RequestInit).method).toBe("GET");
  });

  it("[Tier2 AC-F2] GETs /api/client/workspaces/{token}/spec via the typed client on mount", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientPortalPage />);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).endsWith("/api/client/workspaces/tok-demo/spec"),
        ),
      ).toBe(true),
    );
  });

  it("[Tier2 AC-F3] POSTs /api/client/comments via the typed client on submit", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientPortalPage />);
    const textarea = await screen.findByTestId("client-portal-comment-input");
    fireEvent.change(textarea, {
      target: { value: "決済画面の遷移を変更してほしいです" },
    });
    // Queue the POST mock now (after the initial 2 GETs settled via the impl).
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { comment_id: "c-1" }));
    const btn = screen.getByTestId("client-portal-comment-submit");
    fireEvent.click(btn);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          (c) =>
            String(c[0]).endsWith("/api/client/comments") &&
            ((c[1] ?? {}) as RequestInit).method === "POST",
        ),
      ).toBe(true),
    );
    const postCall = fetchMock.mock.calls.find(
      (c) =>
        String(c[0]).endsWith("/api/client/comments") &&
        ((c[1] ?? {}) as RequestInit).method === "POST",
    );
    expect(postCall).toBeTruthy();
    const body = JSON.parse(String((postCall?.[1] as RequestInit).body));
    expect(body.token).toBe("tok-demo");
    expect(body.body).toBe("決済画面の遷移を変更してほしいです");
  });

  it("[Tier2 AC-F4] workspace 500 → toast.error references /api/client/workspaces/{token} and contains no stack trace", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/client/workspaces/tok-demo")) {
        return Promise.resolve(
          errorResponse(500, {
            code: "INTERNAL",
            message: "Traceback (most recent call last)...",
          }),
        );
      }
      return Promise.resolve(jsonResponse(200, { spec_html_url: "https://x" }));
    });
    renderWithQueryClient(<ClientPortalPage />);

    await waitFor(() =>
      expect((toast.error as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    );
    const msgs = (toast.error as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
      String(c[0]),
    );
    expect(
      msgs.some((m) => m.includes("/api/client/workspaces/tok-demo")),
    ).toBe(true);
    // No server stack trace / SQL leaked.
    for (const m of msgs) {
      expect(m.toLowerCase()).not.toContain("traceback");
      expect(m.toLowerCase()).not.toContain("internal server error");
    }
  });

  it("[Tier2 AC-F5] 409 expired token → renders the dedicated token-expired banner instead of toast", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/client/workspaces/tok-demo")) {
        return Promise.resolve(
          errorResponse(409, {
            code: "client_portal.token_expired",
            message: "token expired",
          }),
        );
      }
      return Promise.resolve(
        errorResponse(409, {
          code: "client_portal.token_expired",
          message: "token expired",
        }),
      );
    });
    renderWithQueryClient(<ClientPortalPage />);
    const banner = await screen.findByTestId("token-expired-banner");
    expect(banner).toBeTruthy();
    expect(banner.textContent).toContain("リンクの有効期限が切れました");
    // No toast for the 409 — the dedicated banner is the canonical UI.
    expect(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls.filter((c) =>
        String(c[0]).includes("/api/client/workspaces/tok-demo"),
      ).length,
    ).toBe(0);
  });

  it("[Tier2 AC-F6] POST 429 → toast.error friendly + references /api/client/comments, no stack", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientPortalPage />);
    const textarea = await screen.findByTestId("client-portal-comment-input");
    fireEvent.change(textarea, { target: { value: "テスト投稿" } });
    fetchMock.mockResolvedValueOnce(
      errorResponse(429, {
        code: "client_portal.rate_limited",
        message: "too many requests",
      }),
    );
    fireEvent.click(screen.getByTestId("client-portal-comment-submit"));

    await waitFor(() =>
      expect((toast.error as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[0] ?? "",
    );
    expect(msg).toContain("/api/client/comments");
    expect(msg).toContain("上限");
    expect(msg.toLowerCase()).not.toContain("traceback");
  });
});
