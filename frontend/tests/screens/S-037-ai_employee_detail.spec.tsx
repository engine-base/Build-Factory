// @ts-nocheck
/**
 * T-V3-C-13 / S-037 — AI 社員 詳細 screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the Wave 2 frontend test harness; they
 *       are installed by the dedicated test setup ticket. The S-002 sister
 *       spec uses the same convention.
 *
 * Covers (mapped to T-V3-C-13 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-037"
 *   structural.AC-S2  -> "renders h1 with text 'devon (Senior Dev)'"
 *   structural.AC-S3  -> "renders 3 h2 section headings from screens.json[S-037]"
 *   functional.AC-F1  -> "GET /api/ai-employees/{id} via typed client on mount"
 *   functional.AC-F2  -> "PUT /api/ai-employees/{id} via typed client on edit"
 *   functional.AC-F3  -> "POST /api/ai-employees/{id}/test via typed client on click"
 *   functional.AC-F4  -> "4xx/5xx → non-technical toast that references endpoint, no stack leak"
 *   functional.AC-F5  -> "/clone-from-user 403 (clone opt-in FALSE) surfaces non-tech 403 toast"
 *   functional.AC-F6  -> "/test 429 (rate-limited) surfaces non-tech wait toast"
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

// next/navigation hooks (mock useParams to return our employee id)
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "emp_devon" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => "/ai/employees/emp_devon",
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

import AIEmployeeDetailPage from "@/app/ai/employees/[id]/page";
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

const DETAIL_BODY = {
  employee: {
    id: "emp_devon",
    name: "devon",
    role: "Senior Backend / Frontend エンジニア",
    department: "Dev",
    parent_employee: "secretary",
    status: "active",
    persona: "実装速度と品質のバランスを重視",
    system_prompt:
      "あなたは Build-Factory の Senior Dev 'devon' です。",
    model: "claude-opus-4-7",
    cloned_from_user_id: null,
    cost_summary: {
      monthly_total_jpy: 2840,
      tasks_done: 23,
      avg_per_task_jpy: 123,
      tokens_used: 128000,
      cache_hit_rate: 0.68,
    },
    execution_history: [
      {
        session_id: "sess_a3f8c2",
        task_id: "T-V3-AUTH-02",
        status: "running",
        cost_jpy: 41,
        ran_at: "2026-05-16T12:00:00Z",
      },
    ],
  },
  skills: [
    { id: "sk-1", name: "implement-api" },
    { id: "sk-2", name: "implement-frontend" },
  ],
};

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
  (toast.success as ReturnType<typeof vi.fn>).mockClear();
  (toast.info as ReturnType<typeof vi.fn>).mockClear();
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-13 S-037 AI 社員 詳細", () => {
  it("AC-S1: renders root with data-screen-id='S-037'", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(DETAIL_BODY));
    renderWithQueryClient(<AIEmployeeDetailPage />);

    const root = document.querySelector("[data-screen-id='S-037']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-003");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-13");
  });

  it("AC-S2: renders h1 with verbatim mock text 'devon (Senior Dev)'", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(DETAIL_BODY));
    renderWithQueryClient(<AIEmployeeDetailPage />);

    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("devon (Senior Dev)");
  });

  it("AC-S3: renders 3 h2 section headings from screens.json[S-037]", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(DETAIL_BODY));
    renderWithQueryClient(<AIEmployeeDetailPage />);

    const h2s = screen.getAllByRole("heading", { level: 2 });
    const texts = h2s.map((h) => (h.textContent ?? "").trim());
    // Allow icon prefixes — assert substring.
    expect(texts.some((t) => t.includes("Persona / System Prompt"))).toBe(true);
    expect(texts.some((t) => t.includes("スキル (8)"))).toBe(true);
    expect(texts.some((t) => t.includes("実行履歴 (今月 87 件)"))).toBe(true);
  });

  it("AC-F1: mounts → GET /api/ai-employees/{id} via typed client", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(DETAIL_BODY));
    renderWithQueryClient(<AIEmployeeDetailPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [getCall] = fetchMock.mock.calls;
    expect(String(getCall[0])).toContain("/api/ai-employees/emp_devon");
    expect(getCall[1].method).toBe("GET");
  });

  it("AC-F2: edit button → PUT /api/ai-employees/{id} via typed client", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(DETAIL_BODY))
      .mockResolvedValueOnce(
        jsonResponse({ id: "emp_devon", updated_at: "2026-05-16T13:00:00Z" }),
      );
    renderWithQueryClient(<AIEmployeeDetailPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId("edit-employee"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const putCall = fetchMock.mock.calls[1];
    expect(String(putCall[0])).toContain("/api/ai-employees/emp_devon");
    expect(putCall[1].method).toBe("PUT");
  });

  it("AC-F3: test button → POST /api/ai-employees/{id}/test via typed client", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(DETAIL_BODY))
      .mockResolvedValueOnce(
        jsonResponse({
          output: "pong",
          tokens_used: 12,
          cost_usd: 0.0003,
        }),
      );
    renderWithQueryClient(<AIEmployeeDetailPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId("test-invocation"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const testCall = fetchMock.mock.calls[1];
    expect(String(testCall[0])).toContain(
      "/api/ai-employees/emp_devon/test",
    );
    expect(testCall[1].method).toBe("POST");
  });

  it("AC-F4: GET 500 → toast.error references /api/ai-employees/emp_devon, no stack leak", async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(500, {
        code: "INTERNAL",
        message: "Traceback (most recent call last): File ...",
      }),
    );
    renderWithQueryClient(<AIEmployeeDetailPage />);

    await waitFor(() =>
      expect((toast.error as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(msg).toContain("/api/ai-employees/emp_devon");
    expect(msg.toLowerCase()).not.toContain("traceback");
    expect(msg.toLowerCase()).not.toContain("file ");
  });

  it("AC-F5: clone /clone-from-user 403 (opt-in FALSE) → toast.error references endpoint without leaking detail", async () => {
    // Detail body must include cloned_from_user_id to render the clone button.
    const cloneable = {
      ...DETAIL_BODY,
      employee: { ...DETAIL_BODY.employee, cloned_from_user_id: "usr_abc" },
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(cloneable))
      .mockResolvedValueOnce(
        errorResponse(403, {
          code: "CLONE_OPT_IN_REQUIRED",
          message: "clone opt-in not granted",
        }),
      );
    renderWithQueryClient(<AIEmployeeDetailPage />);

    await waitFor(() =>
      expect(screen.getByTestId("clone-from-user")).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId("clone-from-user"));

    await waitFor(() =>
      expect((toast.error as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(msg).toContain("/api/ai-employees/emp_devon/clone-from-user");
    // 403 friendly message — must not echo backend code/message verbatim.
    expect(msg).not.toContain("CLONE_OPT_IN_REQUIRED");
    expect(msg).not.toContain("clone opt-in not granted");
  });

  it("AC-F6: /test 429 (rate-limited) → toast.error references /test and includes 待 (non-technical wait copy)", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(DETAIL_BODY))
      .mockResolvedValueOnce(
        errorResponse(429, {
          code: "RATE_LIMITED",
          message: "rate limit exceeded: 20/min/workspace",
        }),
      );
    renderWithQueryClient(<AIEmployeeDetailPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId("test-invocation"));

    await waitFor(() =>
      expect((toast.error as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    );
    const msg = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0],
    );
    expect(msg).toContain("/api/ai-employees/emp_devon/test");
    expect(msg).toMatch(/上限|待っ|しばらく/);
    expect(msg).not.toContain("20/min/workspace");
  });
});
