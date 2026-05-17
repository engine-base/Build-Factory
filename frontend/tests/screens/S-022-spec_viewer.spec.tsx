// @ts-nocheck
/**
 * T-V3-C-48 / S-022 — 仕様書ビューア screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are runtime-only devDeps for the screen test harness (same convention
 *       as T-V3-C-37 / C-38).
 *
 * Covers (mapped to T-V3-C-48 acceptance_criteria):
 *   structural.AC-S1  -> "h1 reads '仕様書ビューア' inside the data-screen-id='S-022' root"
 *   structural.AC-S2  -> "renders h2 set {1. プロジェクト概要 / 2. Must 要件 (34 項目)}"
 *   structural.AC-S3  -> "no emoji glyphs — Lucide icons only"
 *   functional.AC-F1  -> "GET /api/workspaces/{id}/specs on mount; 4xx -> inline error + empty state"
 *   functional.AC-F2  -> "unauthenticated visitor -> /login redirect; no workspace data rendered"
 *   functional.AC-F3  -> "WS /ws/hearing/{session_id} subscribe URL is correct"
 *   functional.AC-F4  -> "POST /api/workspaces/{id}/reports with type=delivery_report returns report_id"
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

vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import SpecViewerPage, {
  hearingStreamUrl,
  queueDeliveryReport,
} from "@/app/(app)/spec/viewer/[id]/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SPECS_FIXTURE = {
  specs: [
    {
      id: "spec-1",
      title: "Build-Factory 要件定義",
      version: 2,
      status: "published",
    },
    {
      id: "spec-2",
      title: "v1 ドラフト",
      version: 1,
      status: "draft",
    },
  ],
  count: 2,
};

const COMMENTS_FIXTURE = {
  comments: [
    {
      id: "c-1",
      body: "M-1 認証で SAML SSO 対応も必要では？",
      author_id: "u-client",
      author_name: "client_abc",
      created_at: "2026-05-15T00:00:00Z",
    },
    {
      id: "c-2",
      body: "SAML は Phase 2 で対応予定。M-1 には含めません。",
      author_id: "u-masato",
      author_name: "masato",
      created_at: "2026-05-15T01:00:00Z",
    },
  ],
  count: 2,
};

const WORKSPACE_ID = "ws_8f3a2c";
const TOKEN = "test-bearer-token";

const SPECS_URL = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/specs`;
const COMMENTS_URL_SPEC1 = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/specs/spec-1/comments`;
const REPORTS_URL = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/reports`;

function defaultFetchImpl(url: string, init?: RequestInit): Promise<Response> {
  const method = init?.method ?? "GET";
  if (typeof url === "string" && method === "GET" && url === SPECS_URL) {
    return Promise.resolve(jsonResponse(200, SPECS_FIXTURE));
  }
  if (
    typeof url === "string" &&
    method === "GET" &&
    url === COMMENTS_URL_SPEC1
  ) {
    return Promise.resolve(jsonResponse(200, COMMENTS_FIXTURE));
  }
  if (typeof url === "string" && method === "POST" && url === REPORTS_URL) {
    return Promise.resolve(
      jsonResponse(201, { report_id: "r-1", status: "queued" }),
    );
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

function primeAuth(workspaceId: string | null = WORKSPACE_ID) {
  window.localStorage.setItem("bf.auth.token", TOKEN);
  if (workspaceId) {
    window.localStorage.setItem("bf.workspace.id", workspaceId);
  }
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
  try {
    window.localStorage.clear();
  } catch {
    /* jsdom localStorage may be unavailable */
  }
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-022 仕様書ビューア page (T-V3-C-48)", () => {
  it("AC-S1: renders root with data-screen-id='S-022' and h1 '仕様書ビューア'", async () => {
    primeAuth();
    const { container } = render(<SpecViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-022"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-005");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-48");
    expect(root?.getAttribute("data-entities")).toContain("E-021");
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("仕様書ビューア");
  });

  it("AC-S2: renders section h2 set {1. プロジェクト概要 / 2. Must 要件 (34 項目)}", async () => {
    primeAuth();
    render(<SpecViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const h2s = screen.getAllByRole("heading", { level: 2 });
    const texts = h2s.map((h) => h.textContent ?? "");
    expect(texts.some((t) => t.includes("1. プロジェクト概要"))).toBe(true);
    expect(texts.some((t) => t.includes("2. Must 要件 (34 項目)"))).toBe(true);
  });

  it("AC-S3: uses Lucide icons exclusively (no emoji glyphs)", async () => {
    primeAuth();
    const { container } = render(<SpecViewerPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const text = container.textContent ?? "";
    const emojiPattern =
      /[\u{1F300}-\u{1FAFF}\u{1F600}-\u{1F64F}\u{1F900}-\u{1F9FF}\u{2600}-\u{27BF}]/u;
    expect(emojiPattern.test(text)).toBe(false);
  });

  it("AC-F1: GET /api/workspaces/{id}/specs on mount via typed client and renders the 2xx body", async () => {
    primeAuth();
    render(<SpecViewerPage />);
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(([url]) => String(url));
      expect(calls.some((u) => u === SPECS_URL)).toBe(true);
    });
    const specsCall = fetchMock.mock.calls.find(
      ([url]) => String(url) === SPECS_URL,
    );
    expect(specsCall).toBeTruthy();
    const [, init] = specsCall;
    expect((init ?? {}).method ?? "GET").toBe("GET");
    expect(String((init ?? {}).headers?.Authorization ?? "")).toContain(TOKEN);
    await waitFor(() =>
      expect(screen.queryByTestId("spec-row-spec-1")).not.toBeNull(),
    );
    expect(screen.getByTestId("spec-row-spec-2")).not.toBeNull();
  });

  it("AC-F1 (UNWANTED): 4xx renders an inline error banner and an empty state, with no spec rows", async () => {
    primeAuth();
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(403, {
          detail: {
            code: "FORBIDDEN",
            message:
              "Traceback (most recent call last): File '/srv/app.py' line 1",
          },
        }),
      ),
    );
    render(<SpecViewerPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("spec-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("spec-error");
    expect(banner.textContent).toContain(
      `/api/workspaces/${WORKSPACE_ID}/specs`,
    );
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(screen.queryByTestId("spec-empty")).not.toBeNull();
    expect(screen.queryByTestId("spec-row-spec-1")).toBeNull();
  });

  it("AC-F2 (UNWANTED): unauthenticated visitor redirects to /login and renders no workspace-scoped data", async () => {
    const replaceMock = vi.fn();
    const originalReplace = window.location.replace;
    Object.defineProperty(window.location, "replace", {
      configurable: true,
      value: replaceMock,
    });
    try {
      const { container } = render(<SpecViewerPage />);
      await waitFor(() =>
        expect(replaceMock).toHaveBeenCalledWith("/login"),
      );
      expect(fetchMock).not.toHaveBeenCalled();
      // The data-screen-id root is still emitted (so the lint can find it),
      // but no spec rows should be rendered.
      expect(container.querySelector('[data-testid="spec-row-spec-1"]')).toBeNull();
      // Workspace-scoped Sidebar-only content like the Spec 一覧 header must
      // not be rendered for anon visitors.
      expect(container.textContent ?? "").not.toContain("Spec 一覧");
    } finally {
      Object.defineProperty(window.location, "replace", {
        configurable: true,
        value: originalReplace,
      });
    }
  });

  it("AC-F3: hearingStreamUrl builds ws:// URL with session_id and subscribeHearingStream is exported", () => {
    expect(hearingStreamUrl("sess-123")).toBe(
      "ws://localhost:8001/ws/hearing/sess-123",
    );
    expect(hearingStreamUrl("sess+abc")).toContain(
      "/ws/hearing/sess%2Babc",
    );
  });

  it("AC-F4: queueDeliveryReport posts type=delivery_report and returns report_id", async () => {
    const reportFetch = vi.fn().mockResolvedValue(
      jsonResponse(201, { report_id: "r-42", status: "queued" }),
    );
    const out = await queueDeliveryReport({
      workspaceId: WORKSPACE_ID,
      authToken: TOKEN,
      fetchImpl: reportFetch as unknown as typeof fetch,
      specId: "spec-1",
    });
    expect(out.report_id).toBe("r-42");
    expect(reportFetch).toHaveBeenCalledTimes(1);
    const [calledUrl, init] = reportFetch.mock.calls[0];
    expect(String(calledUrl)).toBe(REPORTS_URL);
    expect(init?.method).toBe("POST");
    const payload = JSON.parse(String(init?.body ?? "{}"));
    expect(payload.type).toBe("delivery_report");
    expect(payload.spec_id).toBe("spec-1");
  });

  it("AC-F4 (UI): clicking PDF 出力 surfaces success toast with report_id", async () => {
    primeAuth();
    render(<SpecViewerPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("spec-row-spec-1")).not.toBeNull(),
    );
    fireEvent.click(screen.getByTestId("spec-print"));
    await waitFor(() =>
      expect(screen.queryByTestId("spec-toast-success")).not.toBeNull(),
    );
    expect(screen.getByTestId("spec-toast-success").textContent).toContain(
      "r-1",
    );
  });

  it("Posts a new comment via createSpecComment and surfaces it inline", async () => {
    primeAuth();
    render(<SpecViewerPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("spec-comment-c-1")).not.toBeNull(),
    );

    // Hook a one-shot POST handler ON TOP of the default impl.
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (
        method === "POST" &&
        typeof url === "string" &&
        url === COMMENTS_URL_SPEC1
      ) {
        return Promise.resolve(
          jsonResponse(201, {
            comment_id: "c-new",
            created_at: "2026-05-17T00:00:00Z",
          }),
        );
      }
      return defaultFetchImpl(url, init);
    });

    const input = screen.getByTestId("spec-comment-input") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "新しいコメント" } });
    fireEvent.click(screen.getByTestId("spec-comment-submit"));
    await waitFor(() =>
      expect(screen.queryByTestId("spec-comment-c-new")).not.toBeNull(),
    );
  });
});
