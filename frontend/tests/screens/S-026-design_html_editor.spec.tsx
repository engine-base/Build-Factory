// @ts-nocheck
/**
 * T-V3-C-52 / S-026 — HTML エディタ (design_html_editor) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen
 *       test harness; they are wired by the Wave 2 frontend test setup
 *       ticket (T-V3-C-TEST-01). Same convention as T-V3-C-49 / C-51.
 *
 * Covers (mapped to T-V3-C-52 acceptance_criteria):
 *   structural.AC-S1  -> 'h1 reads "HTML エディタ"'
 *   structural.AC-S2  -> 'renders root with data-screen-id=S-026 + lucide-only'
 *   functional.AC-F1  -> 'GET /api/workspaces/{id}/mocks/{screen_id}/html on mount'
 *   functional.AC-F1  -> '4xx surfaces non-technical toast + empty state'
 *   functional.AC-F2  -> '401 -> router.replace("/login") + no workspace data rendered'
 *   functional.AC-F3  -> 'GET returns the latest version of mock html (2xx body rendered)'
 *   ai-edit           -> 'POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit on submit'
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

import DesignHtmlEditorPage from "@/app/(app)/spec/html-editor/page";

// --------------------------------------------------------------------------
// Next.js router + searchParams mocks
// --------------------------------------------------------------------------

const routerReplace = vi.fn();
const searchParamsGet = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplace,
    push: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => ({
    get: searchParamsGet,
  }),
}));

// --------------------------------------------------------------------------
// fetch mocking
// --------------------------------------------------------------------------

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const HTML_FIXTURE =
  "<!DOCTYPE html><html><body><h1>S-006 account dashboard</h1></body></html>";

function defaultFetchImpl(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const method = init?.method ?? "GET";
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.includes("/api/workspaces/") &&
    url.includes("/mocks/") &&
    url.endsWith("/html")
  ) {
    return Promise.resolve(jsonResponse(200, { html: HTML_FIXTURE, version: 3 }));
  }
  if (
    typeof url === "string" &&
    method === "POST" &&
    url.endsWith("/ai-edit")
  ) {
    return Promise.resolve(
      jsonResponse(201, {
        diff: "- old\n+ new",
        new_html: "<html><body><h1>ai-edited</h1></body></html>",
        tokens_used: 42,
      }),
    );
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  routerReplace.mockReset();
  searchParamsGet.mockReset();
  searchParamsGet.mockImplementation((key: string) => {
    if (key === "workspace") return "ws-test";
    if (key === "screen_id") return "S-006";
    return null;
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-026 HTML エディタ page (T-V3-C-52)", () => {
  it("AC-S2: renders root with data-screen-id='S-026' and ticket meta", async () => {
    const { container } = render(<DesignHtmlEditorPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-026"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-005b");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-52");
    expect(root?.getAttribute("data-entities")).toContain("E-022");
    expect(root?.getAttribute("data-entities")).toContain("E-021");
  });

  it("AC-S1: h1 reads 'HTML エディタ'", async () => {
    render(<DesignHtmlEditorPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("HTML エディタ");
  });

  it("AC-F1 / AC-F3: GET /mocks/{screen_id}/html on mount via typed client", async () => {
    render(<DesignHtmlEditorPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain(
      "/api/workspaces/ws-test/mocks/S-006/html",
    );
    expect((init ?? {}).method ?? "GET").toBe("GET");
    // 2xx body rendered into the editor (default mode = GUI -> iframe).
    await waitFor(() =>
      expect(screen.queryByTestId("editor-preview")).not.toBeNull(),
    );
    const iframe = screen.getByTestId("editor-preview") as HTMLIFrameElement;
    expect(iframe.getAttribute("srcDoc") ?? iframe.getAttribute("srcdoc")).toContain(
      "S-006 account dashboard",
    );
  });

  it("AC-F1: 4xx surfaces a non-technical toast referencing the endpoint", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(404, {
          detail: {
            code: "NOT_FOUND",
            message:
              "Traceback (most recent call last): File '/srv/app.py' line 99",
          },
        }),
      ),
    );

    render(<DesignHtmlEditorPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("editor-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("editor-error");
    expect(banner.textContent).toContain(
      "/api/workspaces/ws-test/mocks/S-006/html",
    );
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(banner.textContent?.toLowerCase()).not.toContain("/srv/app.py");
    // Empty state visible / no preview iframe rendered.
    expect(screen.queryByTestId("editor-empty")).not.toBeNull();
    expect(screen.queryByTestId("editor-preview")).toBeNull();
  });

  it("AC-F2: 401 redirects to /login and does not render workspace data", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "UNAUTHORIZED", message: "missing token" },
        }),
      ),
    );

    render(<DesignHtmlEditorPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    // No preview / no editor error toast / no draft visible.
    expect(screen.queryByTestId("editor-preview")).toBeNull();
    expect(screen.queryByTestId("editor-error")).toBeNull();
    expect(screen.queryByTestId("component-palette")).toBeNull();
  });

  it("POST ai-edit submits the prompt and renders the diff turn", async () => {
    render(<DesignHtmlEditorPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const promptInput = screen.getByTestId("ai-prompt") as HTMLTextAreaElement;
    fireEvent.change(promptInput, { target: { value: "Anomalies を目立たせて" } });
    fireEvent.click(screen.getByTestId("ai-submit"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [calledUrl, init] = fetchMock.mock.calls[1];
    expect(String(calledUrl)).toContain(
      "/api/workspaces/ws-test/mocks/S-006/ai-edit",
    );
    expect(init?.method).toBe("POST");
    const parsedBody = JSON.parse((init?.body as string) ?? "{}");
    expect(parsedBody.prompt).toBe("Anomalies を目立たせて");

    // Designer response visible in the chat log.
    await waitFor(() =>
      expect(screen.getByTestId("ai-chat-log").textContent).toContain(
        "+ new",
      ),
    );
  });

  it("HTML mode renders an editable textarea with the latest fetched body", async () => {
    render(<DesignHtmlEditorPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("editor-preview")).not.toBeNull(),
    );
    fireEvent.click(screen.getByTestId("mode-html"));
    const textarea = screen.getByTestId(
      "editor-textarea",
    ) as HTMLTextAreaElement;
    expect(textarea.value).toContain("S-006 account dashboard");
  });
});
