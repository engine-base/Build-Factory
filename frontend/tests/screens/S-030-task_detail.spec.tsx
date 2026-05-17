/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-60 / S-030 — タスク詳細 (task_detail) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness; tsc strict mode
 *       picks them up once the Wave 2 frontend test ticket (T-V3-C-TEST-01) is
 *       installed. Pattern mirrors S-001 / S-028 / S-033 specs.
 *
 * Covers (mapped to T-V3-C-60 acceptance_criteria):
 *   structural.AC-S1  -> h1 == "POST /api/auth/signup 実装"
 *   structural.AC-S2  -> h2 set === {Description / 受け入れ基準 (EARS / 5 件) /
 *                                    セッション履歴 (3) / コメント (2)}
 *   structural.AC-S3  -> Lucide icons only (no emoji)
 *   functional.AC-F1  -> GET /api/tasks/{id} renders 2xx body;
 *                        4xx renders inline error empty state + toast
 *   functional.AC-F2  -> 401 redirects to /login (S-001); no workspace data
 *   functional.AC-F5  -> EARS validation gates AC persistence via @/api/task-detail
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
//                  and useParams payloads.
const pushMock = vi.fn();
const replaceMock = vi.fn();
const backMock = vi.fn();
const useParamsMock = vi.fn();

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

import TaskDetailPage from "@/app/(app)/task/[id]/page";
import {
  TaskDetailApiError,
  assertAllEarsValid,
  detectEarsForm,
} from "@/api/task-detail";

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

const TASK_PAYLOAD = {
  task: {
    id: "11111111-1111-1111-1111-111111111111",
    task_id: "T-V3-AUTH-02",
    title: "POST /api/auth/signup 実装",
    status: "running",
    feature_id: "F-001",
    description:
      "email + password + display_name で User + Account + AccountMember を 1 transaction で作成。",
    workspace_id: 1,
    assignee: "devon",
    assignee_name: "devon (AI)",
    estimate_hours: 8,
    cost_jpy: 41,
    created_at: "5/14 18:23",
    dependencies: [
      { task_id: "T-V3-AUTH-01", title: "login API", status: "done" },
    ],
    related_screens: [
      { id: "S-002", label: "signup" },
      { id: "S-001", label: "login" },
    ],
  },
  acceptance_criteria: [
    {
      id: "ac-1",
      ears_form: "EVENT-DRIVEN",
      text: "When valid email+password+display_name is POSTed, the system shall create User + Account + AccountMember atomically and return 201 with JWT.",
    },
    {
      id: "ac-2",
      ears_form: "UNWANTED",
      text: "If email is taken, the system shall return 409 (email_taken).",
    },
  ],
  sessions: [
    {
      id: "sess_a3f8c2",
      status: "running",
      assignee: "devon",
      cost_jpy: 41,
      elapsed_label: "12 min",
    },
  ],
  comments: [
    {
      id: 1,
      body: "transaction で User + Account 作成は OK だけど、rollback テストを忘れずに。",
      author: "winston",
      author_name: "winston",
      created_at: "25 min",
    },
  ],
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
  useParamsMock.mockReturnValue({
    id: "11111111-1111-1111-1111-111111111111",
  });
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-60 S-030 タスク詳細 (task_detail)", () => {
  it("AC-S1 + AC-S2 + AC-S3: renders data-screen-id='S-030', exact h1 text, expected h2 set, and no emoji glyphs", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASK_PAYLOAD));

    renderWithQueryClient(<TaskDetailPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const root = document.querySelector("[data-screen-id='S-030']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-006,F-007,F-025");
    expect(root?.getAttribute("data-screen-name")).toBe("task_detail");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-60");

    // AC-S1: h1 == "POST /api/auth/signup 実装"
    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("POST /api/auth/signup 実装");

    // AC-S2: section h2 set
    const h2s = Array.from(root?.querySelectorAll("h2") ?? []).map((h) =>
      h.textContent?.trim(),
    );
    const required = new Set([
      "Description",
      "受け入れ基準 (EARS / 5 件)",
      "セッション履歴 (3)",
      "コメント (2)",
    ]);
    for (const r of required) {
      expect(h2s).toContain(r);
    }

    // AC-S3: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F1: GET /api/tasks/{id} is called on mount", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASK_PAYLOAD));

    renderWithQueryClient(<TaskDetailPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(
      "/api/tasks/11111111-1111-1111-1111-111111111111",
    );
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("AC-F1 tail: 4xx non-401 renders the inline empty state + toasts the friendly message tagged with the endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "tasks.not_found", message: "no such task" } },
        { status: 404 },
      ),
    );

    renderWithQueryClient(<TaskDetailPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("task-error-empty-state")).not.toBeNull();
    });
    // Toast was raised with the failing endpoint embedded.
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledTimes(1));
    expect(String(toastErrorMock.mock.calls[0][0])).toContain(
      "/api/tasks/11111111-1111-1111-1111-111111111111",
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

    renderWithQueryClient(<TaskDetailPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledTimes(1);
    });
    expect(replaceMock.mock.calls[0][0]).toBe("/login");

    // AC-F2 second half: no workspace-scoped data is rendered.
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.queryByTestId("task-meta-panel")).toBeNull();
    expect(screen.queryByTestId("task-play-button")).toBeNull();
  });

  it("AC-F1 success: clicking Play POSTs to /api/tasks/{id}/play", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(TASK_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse(
          { session_id: "deadbeef-cafe-babe-feed-facecafebabe" },
          { status: 201 },
        ),
      )
      .mockResolvedValue(jsonResponse(TASK_PAYLOAD));

    renderWithQueryClient(<TaskDetailPage />);

    const playBtn = (await screen.findByTestId(
      "task-play-button",
    )) as HTMLButtonElement;
    await waitFor(() => expect(playBtn.disabled).toBe(false));
    fireEvent.click(playBtn);

    await waitFor(() => {
      const playCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes(
          "/api/tasks/11111111-1111-1111-1111-111111111111/play",
        ),
      );
      expect(playCall).toBeTruthy();
      expect(playCall?.[1]?.method).toBe("POST");
    });
    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled());
  });

  it("regression: submitting a comment POSTs to /api/tasks/{id}/comments", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(TASK_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse({ comment_id: "c-1" }, { status: 201 }),
      )
      .mockResolvedValue(jsonResponse(TASK_PAYLOAD));

    renderWithQueryClient(<TaskDetailPage />);

    const input = (await screen.findByTestId(
      "task-comment-input",
    )) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "LGTM, please proceed" } });

    fireEvent.click(screen.getByTestId("task-comment-submit"));

    await waitFor(() => {
      const commentCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes(
          "/api/tasks/11111111-1111-1111-1111-111111111111/comments",
        ),
      );
      expect(commentCall).toBeTruthy();
      const body = JSON.parse(String(commentCall?.[1]?.body ?? "{}"));
      expect(body.body).toBe("LGTM, please proceed");
    });
  });

  it("AC-F5: EARS validation rejects malformed AC and accepts the 5 valid forms (detectEarsForm + assertAllEarsValid)", () => {
    // The 5 EARS forms must each be detected.
    expect(detectEarsForm("The system shall log every request.")).toBe(
      "UBIQUITOUS",
    );
    expect(
      detectEarsForm(
        "When the user clicks save, the system shall persist the form.",
      ),
    ).toBe("EVENT-DRIVEN");
    expect(
      detectEarsForm(
        "While streaming, the system shall buffer up to 4KB of output.",
      ),
    ).toBe("STATE-DRIVEN");
    expect(
      detectEarsForm(
        "Where MFA is enabled, the system shall require a TOTP code.",
      ),
    ).toBe("OPTIONAL");
    expect(
      detectEarsForm(
        "If the workspace is suspended, the system shall not allow play.",
      ),
    ).toBe("UNWANTED");

    // Non-EARS text → null.
    expect(detectEarsForm("save the form please")).toBeNull();

    // assertAllEarsValid throws TaskDetailApiError(422) for any non-EARS item.
    expect(() =>
      assertAllEarsValid([
        { text: "When X happens, the system shall do Y." },
        { text: "just do something" }, // invalid
      ]),
    ).toThrow(TaskDetailApiError);

    // All valid → no throw.
    expect(() =>
      assertAllEarsValid([
        { text: "The system shall log every request." },
        { text: "If X, the system shall not allow Y." },
      ]),
    ).not.toThrow();
  });
});
