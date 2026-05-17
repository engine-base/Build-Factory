/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-44 / S-033 — PR レビュー (pr_review) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness; tsc strict mode
 *       picks them up once the Wave 2 frontend test ticket (T-V3-C-TEST-01) is
 *       installed. Pattern mirrors S-001 / S-048 specs.
 *
 * Covers (mapped to T-V3-C-44 acceptance_criteria):
 *   structural.AC-S1  -> h1 == "feat: requirements editor + EARS notation parser"
 *   structural.AC-S2  -> Lucide icons only (no emoji)
 *   functional.AC-F1  -> GET /api/workspaces/{id}/prs/{pr_number} renders 2xx body;
 *                        4xx renders inline error empty state + toast
 *   functional.AC-F2  -> 401 redirects to /login (S-001); no workspace data renders
 *   functional.AC-F3  -> POST /api/prs/{id}/merge wires through the merge button
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
//                  and useParams / useSearchParams payloads.
const pushMock = vi.fn();
const replaceMock = vi.fn();
const backMock = vi.fn();
const useParamsMock = vi.fn();
const useSearchParamsMock = vi.fn();

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
  useSearchParams: () => useSearchParamsMock(),
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

import PrReviewPage from "@/app/(app)/review/[pr_id]/page";

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

function searchParamsStub(entries: Record<string, string> = {}) {
  return {
    get: (key: string) => entries[key] ?? null,
  };
}

const PR_PAYLOAD = {
  pr: {
    id: 283,
    pr_number: 283,
    title: "feat: requirements editor + EARS notation parser",
    state: "Open",
    base_branch: "main",
    head_branch: "feature/T-V3-SCR-06",
    author: "devon",
    author_name: "devon (AI)",
    workspace_id: 1,
    html_review_url: "https://example.test/pr-283-review.html",
    ai_review_summary:
      "EARS notation parser は 5 形式全部対応 / lint #17-19 全 PASS / coverage 84%",
    approved_at: null,
    merged_at: null,
  },
  comments: [
    {
      id: 1,
      body: "この parseEars 関数、5 形式の検出は良いですが UNWANTED の If パターンが見当たりません。",
      anchor_file: "frontend/src/components/EarsParser.tsx",
      anchor_line: 5,
      author: "reviewer",
      author_name: "reviewer",
      created_at: "2026-05-17T12:00:00Z",
    },
  ],
  files: [
    {
      filename: "frontend/src/components/EarsParser.tsx",
      additions: 128,
      deletions: 0,
      patch: "+ // EARS notation parser",
    },
  ],
  checks: { passed: 19, failed: 0 },
};

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  pushMock.mockReset();
  replaceMock.mockReset();
  backMock.mockReset();
  toastErrorMock.mockReset();
  toastSuccessMock.mockReset();
  useParamsMock.mockReset();
  useSearchParamsMock.mockReset();
  useParamsMock.mockReturnValue({ pr_id: "283" });
  useSearchParamsMock.mockReturnValue(searchParamsStub({ workspace: "1" }));
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-44 S-033 PR レビュー (pr_review)", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-033' and exact h1 text 'feat: requirements editor + EARS notation parser'", async () => {
    fetchMock.mockResolvedValue(jsonResponse(PR_PAYLOAD));

    renderWithQueryClient(<PrReviewPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const root = document.querySelector("[data-screen-id='S-033']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-013");
    expect(root?.getAttribute("data-screen-name")).toBe("pr_review");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-44");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe(
      "feat: requirements editor + EARS notation parser",
    );

    // AC-S2: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F1: GET /api/workspaces/{id}/prs/{pr_number} is called on mount", async () => {
    fetchMock.mockResolvedValue(jsonResponse(PR_PAYLOAD));

    renderWithQueryClient(<PrReviewPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/workspaces/1/prs/283");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("AC-F1 tail: 4xx non-401 renders the inline empty state + toasts the friendly message tagged with the endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "prs.not_found", message: "no such pr" } },
        { status: 404 },
      ),
    );

    renderWithQueryClient(<PrReviewPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("pr-error-empty-state")).not.toBeNull();
    });
    // Toast was raised with the failing endpoint embedded.
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledTimes(1));
    expect(String(toastErrorMock.mock.calls[0][0])).toContain(
      "/api/workspaces/1/prs/283",
    );
    // Did NOT redirect to /login (that path is reserved for 401, AC-F2).
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("AC-F2: 401 redirects to /login (S-001) and renders no workspace-scoped data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "UNAUTHORIZED", message: "missing token" } },
        { status: 401 },
      ),
    );

    renderWithQueryClient(<PrReviewPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledTimes(1);
    });
    expect(replaceMock.mock.calls[0][0]).toBe("/login");

    // AC-F2 second half: no workspace data is rendered (h1 / merge button absent).
    expect(screen.queryByTestId("pr-merge-button")).toBeNull();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("AC-F3: clicking Merge POSTs to /api/prs/{id}/merge with the selected merge_method", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PR_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse(
          { merged_at: "2026-05-17T12:00:00Z", sha: "deadbeefcafebabe" },
          { status: 201 },
        ),
      )
      // Refetch after invalidation (may or may not fire before assertions).
      .mockResolvedValue(jsonResponse(PR_PAYLOAD));

    renderWithQueryClient(<PrReviewPage />);

    // Wait for the page to surface the merge button (depends on pr.id presence).
    const mergeBtn = (await screen.findByTestId(
      "pr-merge-button",
    )) as HTMLButtonElement;
    expect(mergeBtn.disabled).toBe(false);

    // Switch to a non-default merge_method to assert the body field flows through.
    const select = screen.getByTestId(
      "pr-merge-method-select",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "merge" } });
    fireEvent.click(mergeBtn);

    await waitFor(() => {
      const mergeCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/api/prs/283/merge"),
      );
      expect(mergeCall).toBeTruthy();
    });
    const mergeCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes("/api/prs/283/merge"),
    );
    expect(mergeCall?.[1]?.method).toBe("POST");
    const body = JSON.parse(String(mergeCall?.[1]?.body ?? "{}"));
    expect(body.merge_method).toBe("merge");

    // Success toast surfaced.
    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled());
  });

  it("regression: clicking Approve POSTs to /api/prs/{id}/approve", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PR_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse({ approved_at: "2026-05-17T12:00:00Z" }, { status: 201 }),
      )
      .mockResolvedValue(jsonResponse(PR_PAYLOAD));

    renderWithQueryClient(<PrReviewPage />);

    const approveBtn = await screen.findByTestId("pr-approve-button");
    fireEvent.click(approveBtn);

    await waitFor(() => {
      const approveCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/api/prs/283/approve"),
      );
      expect(approveCall).toBeTruthy();
      expect(approveCall?.[1]?.method).toBe("POST");
    });
  });

  it("regression: switching to Conversation tab and submitting a comment POSTs to /api/prs/{id}/comments", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PR_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse({ comment_id: "c-1" }, { status: 201 }),
      )
      .mockResolvedValue(jsonResponse(PR_PAYLOAD));

    renderWithQueryClient(<PrReviewPage />);

    // Switch to the Conversation tab (the comment composer lives there).
    fireEvent.click(await screen.findByTestId("pr-tab-conversation"));

    const input = (await screen.findByTestId(
      "pr-comment-input",
    )) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "LGTM, please merge" } });

    fireEvent.click(screen.getByTestId("pr-comment-submit"));

    await waitFor(() => {
      const commentCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/api/prs/283/comments"),
      );
      expect(commentCall).toBeTruthy();
      const body = JSON.parse(String(commentCall?.[1]?.body ?? "{}"));
      expect(body.body).toBe("LGTM, please merge");
    });
  });
});
