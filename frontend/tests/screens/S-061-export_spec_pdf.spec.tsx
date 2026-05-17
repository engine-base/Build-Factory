// @ts-nocheck
/**
 * T-V3-C-22 / S-061 — 仕様書 PDF (Export Spec PDF) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket
 *       (T-V3-C-TEST-01). Same convention as T-V3-C-17 / C-18 / C-19 / C-20.
 *
 * Covers (mapped to T-V3-C-22 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-061"
 *   structural.AC-S2  -> "h1 reads '受託 EC 構築 #4— 要件定義書 —'"
 *   structural.AC-S3  -> "h2 sections match screens.json[S-061].section_h2_texts"
 *   functional.AC-F1  -> "4xx/5xx surfaces non-technical toast referencing
 *                         endpoint without leaking server stack traces"
 *   functional.AC-F2  -> "POST /api/workspaces/{id}/exports queues spec_pdf job
 *                         and returns export_id within 1s"
 *   functional.AC-F3  -> "GET /api/exports/{id} returns download_url=null
 *                         while status is queued/running"
 *   regression.AC-R1  -> typed client `ExportApiError` carries the failing
 *                         endpoint without leaking server stack traces.
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

import ExportSpecPdfPage from "@/app/export/spec-pdf/page";
import {
  buildExportByIdEndpoint,
  buildExportsByWorkspaceEndpoint,
  ExportApiError,
} from "@/api/exports";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const PREVIEW_WORKSPACE_FALLBACK = "preview-workspace-0001";
const QUEUE_ENDPOINT = buildExportsByWorkspaceEndpoint(
  PREVIEW_WORKSPACE_FALLBACK,
);

const QUEUE_RESPONSE_OK = {
  export_id: "ex_01HFZK1JABCD9XYZ",
  status: "queued",
};

const STATUS_RESPONSE_QUEUED = {
  export: {
    id: "ex_01HFZK1JABCD9XYZ",
    type: "spec_pdf",
    status: "queued",
  },
  download_url: null,
};

const STATUS_RESPONSE_RUNNING = {
  export: {
    id: "ex_01HFZK1JABCD9XYZ",
    type: "spec_pdf",
    status: "running",
  },
  download_url: null,
};

function defaultFetchImpl(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const method = init?.method ?? "GET";
  const u = String(url);
  if (method === "POST" && u.endsWith(QUEUE_ENDPOINT)) {
    return Promise.resolve(jsonResponse(201, QUEUE_RESPONSE_OK));
  }
  if (method === "GET" && u.includes("/api/exports/")) {
    return Promise.resolve(jsonResponse(200, STATUS_RESPONSE_QUEUED));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-061 仕様書 PDF (T-V3-C-22)", () => {
  it("[Tier1 AC-S1] renders root with data-screen-id=\"S-061\"", () => {
    const { container } = render(<ExportSpecPdfPage />);
    const root = container.querySelector('[data-screen-id="S-061"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-031");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-22");
    expect(root?.getAttribute("data-phase")).toBe("Phase 1B");
    expect(root?.getAttribute("data-entities")).toBe("E-014");
  });

  it("[Tier1 AC-S2] displays an h1 matching screens.json[S-061].h1_text", () => {
    render(<ExportSpecPdfPage />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("受託 EC 構築 #4— 要件定義書 —");
  });

  it("[Tier1 AC-S3] renders h2 sections matching screens.json[S-061].section_h2_texts", () => {
    render(<ExportSpecPdfPage />);
    const h2s = screen.getAllByRole("heading", { level: 2 });
    const texts = h2s.map((el) => el.textContent?.trim());
    expect(texts).toContain("1. プロジェクト概要");
    expect(texts).toContain("2. Must 要件 (34 項目)");
    // cap 12 — keep within budget
    expect(h2s.length).toBeLessThanOrEqual(12);
  });

  it("[Tier2 AC-F2] clicking 'PDF ダウンロード' POSTs to /api/workspaces/{id}/exports with type=spec_pdf and surfaces export_id", async () => {
    render(<ExportSpecPdfPage />);
    const start = Date.now();
    const queueBtn = screen.getByTestId("pdf-queue-export");
    fireEvent.click(queueBtn);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(QUEUE_ENDPOINT);
    expect(init?.method).toBe("POST");
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body.type).toBe("spec_pdf");

    // export_id surfaced within reasonable time (AC-F2: <1s; test is in-process)
    const statusBanner = await screen.findByTestId("export-status-text");
    expect(statusBanner.textContent).toContain("ex_01HFZK1JABCD9XYZ");
    expect(Date.now() - start).toBeLessThan(1000);
  });

  it("[Tier2 AC-F3] while status is 'queued'/'running', download_url=null keeps the download CTA hidden", async () => {
    fetchMock.mockReset();
    let pollCallNo = 0;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      const method = init?.method ?? "GET";
      if (method === "POST" && u.endsWith(QUEUE_ENDPOINT)) {
        return Promise.resolve(jsonResponse(201, QUEUE_RESPONSE_OK));
      }
      if (method === "GET" && u.includes("/api/exports/")) {
        pollCallNo += 1;
        return Promise.resolve(
          jsonResponse(
            200,
            pollCallNo === 1 ? STATUS_RESPONSE_QUEUED : STATUS_RESPONSE_RUNNING,
          ),
        );
      }
      return Promise.resolve(jsonResponse(500, { detail: "x" }));
    });

    render(<ExportSpecPdfPage />);
    fireEvent.click(screen.getByTestId("pdf-queue-export"));
    await screen.findByTestId("export-status-text");

    fireEvent.click(screen.getByTestId("export-poll"));
    await waitFor(() =>
      expect(screen.getByTestId("export-status-text").textContent).toContain(
        "queued",
      ),
    );
    expect(
      screen.getByTestId("export-status-text").textContent,
    ).toContain("(null while queued/running)");
    expect(screen.queryByTestId("export-download-link")).toBeNull();

    fireEvent.click(screen.getByTestId("export-poll"));
    await waitFor(() =>
      expect(screen.getByTestId("export-status-text").textContent).toContain(
        "running",
      ),
    );
    expect(screen.queryByTestId("export-download-link")).toBeNull();
  });

  it("[Tier2 AC-F1] on 5xx, surfaces a non-technical toast referencing endpoint without leaking server stack traces", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(500, {
          detail:
            "Traceback (most recent call last):\n  File '/srv/app/exports.py', line 42\n    raise SQLError('db dead')",
        }),
      ),
    );

    render(<ExportSpecPdfPage />);
    fireEvent.click(screen.getByTestId("pdf-queue-export"));
    const toast = await screen.findByTestId("export-error");
    expect(toast.textContent).toContain(QUEUE_ENDPOINT);
    expect(toast.textContent).not.toMatch(/Traceback|SQLError|exports\.py/);
  });

  it("[Tier2 AC-F1] on 401, surfaces a 'sign-in required' message tagged with the endpoint", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "export.unauthorized", message: "no token" },
        }),
      ),
    );

    render(<ExportSpecPdfPage />);
    fireEvent.click(screen.getByTestId("pdf-queue-export"));
    const toast = await screen.findByTestId("export-error");
    expect(toast.textContent).toContain("サインインが必要です");
    expect(toast.textContent).toContain(QUEUE_ENDPOINT);
  });

  it("[API unit] ExportApiError.toUserMessage carries the failing endpoint without exposing server stack", () => {
    const endpoint = buildExportByIdEndpoint("ex_01HFZK1JABCD9XYZ");
    const err = new ExportApiError(
      "export.rate_limited",
      "rate limited (internal: stacktrace at /srv/app/exports.py:42)",
      429,
      endpoint,
    );
    expect(err.endpoint).toBe(endpoint);
    expect(err.status).toBe(429);
    const friendly = err.toUserMessage();
    expect(friendly).toContain(endpoint);
    expect(friendly).not.toMatch(/Traceback|stacktrace|exports\.py/);
  });
});
