// @ts-nocheck
/**
 * T-V3-C-16 / S-043 クライアントコメント — Vitest screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/S-043-client_comment.spec.tsx`
 * Target: AC-R1 (>= 5 cases) — actual: 7 cases covering Tier 1 + Tier 2.
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library / jsdom are
 * runtime-only devDeps not yet listed in package.json (T-FOUNDATION-08
 * baseline drift). Once they land, this file PASSes as-is. The
 * `// @ts-nocheck` pragma keeps `tsc --noEmit` green in the meantime
 * (matches the convention used by S-042-client_workspace.spec.tsx and
 * S-010-notifications_inbox.spec.tsx).
 *
 * Covers (mapped to T-V3-C-16 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id='S-043'"
 *   structural.AC-S2  -> "h1 reads 'M-1 認証で SAML SSO 対応も必要では？' verbatim"
 *   functional.AC-F1  -> "GET /api/client/comments/{thread_id} via typed client on mount"
 *   functional.AC-F2  -> "POST /api/client/comments via typed client on reply submit"
 *   functional.AC-F3  -> "POST /api/comments/{id}/resolve via typed client on resolve click"
 *   functional.AC-F4  -> "4xx/5xx surfaces non-technical toast referencing endpoint"
 *   functional.AC-F5  -> "POST 429 → friendly rate-limit toast (no stack)"
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

// next/navigation — mock useParams + useSearchParams to inject the token /
// thread_id segments.
const paramsMock = { value: { token: "tok-demo" } as { token: string | string[] } };
const searchMock = {
  value: new URLSearchParams("thread_id=thread-1"),
};
vi.mock("next/navigation", () => ({
  useParams: () => paramsMock.value,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => searchMock.value,
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

import ClientCommentsPage from "@/app/portal/[token]/comments/page";
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

const SAMPLE_COMMENTS = {
  comments: [
    {
      id: "c-root",
      thread_id: "thread-1",
      body: "M-1 認証で SAML SSO 対応も必要では？社内 ID 管理が SAML ベースなので。",
      author_name: "client_abc",
      created_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    },
    {
      id: "c-reply-1",
      thread_id: "thread-1",
      body: "SAML は Phase 2 で対応予定です。",
      author_name: "masato",
      created_at: new Date(Date.now() - 2 * 86_400_000 + 3600_000).toISOString(),
    },
  ],
};

function mockSuccessfulLoad() {
  fetchMock.mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/client/comments/thread-1")) {
      return Promise.resolve(jsonResponse(200, SAMPLE_COMMENTS));
    }
    return Promise.resolve(jsonResponse(200, { comments: [] }));
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  (toast.success as ReturnType<typeof vi.fn>).mockReset();
  paramsMock.value = { token: "tok-demo" };
  searchMock.value = new URLSearchParams("thread_id=thread-1");
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

// --------------------------------------------------------------------------
// Tests
// --------------------------------------------------------------------------

describe("S-043 クライアントコメント (T-V3-C-16)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id='S-043' and v3 lint meta", async () => {
    mockSuccessfulLoad();
    const { container } = renderWithQueryClient(<ClientCommentsPage />);
    const root = container.querySelector('[data-screen-id="S-043"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-013");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-16");
    expect(root?.getAttribute("data-entities")).toBe("E-033");
  });

  it("[Tier1 AC-S2] h1 reads 'M-1 認証で SAML SSO 対応も必要では？' verbatim from screens.json[S-043].h1_text", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientCommentsPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("M-1 認証で SAML SSO 対応も必要では？");
  });

  it("[Tier2 AC-F1] GETs /api/client/comments/{thread_id} via the typed client on mount", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientCommentsPage />);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).includes("/api/client/comments/thread-1"),
        ),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes("/api/client/comments/thread-1"),
    );
    expect(call).toBeTruthy();
    expect(((call?.[1] ?? {}) as RequestInit).method).toBe("GET");
    // The typed client appends `?token=...` for the thread GET.
    expect(String(call?.[0])).toContain("token=tok-demo");
  });

  it("[Tier2 AC-F2] POSTs /api/client/comments via the typed client on reply submit", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientCommentsPage />);
    const textarea = await screen.findByTestId("client-comment-reply-input");
    fireEvent.change(textarea, {
      target: { value: "了解です。Phase 2 でお願いします" },
    });
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { comment_id: "c-2" }));
    fireEvent.click(screen.getByTestId("client-comment-reply-submit"));

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
    expect(body.thread_id).toBe("thread-1");
    expect(body.body).toBe("了解です。Phase 2 でお願いします");
  });

  it("[Tier2 AC-F3] POSTs /api/comments/{id}/resolve via the typed client on resolve click", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientCommentsPage />);
    // Wait for comments to load so the root id is known.
    await screen.findByTestId("comment-root");
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { id: "c-root", resolved_at: new Date().toISOString() }),
    );
    fireEvent.click(screen.getByTestId("resolve-thread-submit"));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          (c) =>
            String(c[0]).endsWith("/api/comments/c-root/resolve") &&
            ((c[1] ?? {}) as RequestInit).method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("[Tier2 AC-F4] GET 500 → toast.error references /api/client/comments/{thread_id} and contains no stack trace", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/client/comments/thread-1")) {
        return Promise.resolve(
          errorResponse(500, {
            code: "INTERNAL",
            message: "Traceback (most recent call last)...",
          }),
        );
      }
      return Promise.resolve(jsonResponse(200, { comments: [] }));
    });
    renderWithQueryClient(<ClientCommentsPage />);

    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msgs = (toast.error as ReturnType<typeof vi.fn>).mock.calls.map((c) =>
      String(c[0]),
    );
    expect(
      msgs.some((m) => m.includes("/api/client/comments/thread-1")),
    ).toBe(true);
    for (const m of msgs) {
      expect(m.toLowerCase()).not.toContain("traceback");
      expect(m.toLowerCase()).not.toContain("internal server error");
    }
  });

  it("[Tier2 AC-F5] POST 429 → toast.error friendly + references /api/client/comments, no stack", async () => {
    mockSuccessfulLoad();
    renderWithQueryClient(<ClientCommentsPage />);
    const textarea = await screen.findByTestId("client-comment-reply-input");
    fireEvent.change(textarea, { target: { value: "テスト投稿" } });
    fetchMock.mockResolvedValueOnce(
      errorResponse(429, {
        code: "client_portal.rate_limited",
        message: "too many requests",
      }),
    );
    fireEvent.click(screen.getByTestId("client-comment-reply-submit"));

    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls.at(-1)?.[0] ?? "",
    );
    expect(msg).toContain("/api/client/comments");
    expect(msg).toContain("上限");
    expect(msg.toLowerCase()).not.toContain("traceback");
  });
});
