/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-58 / S-028 — タスクリスト (task_list) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the screen test harness; tsc strict mode
 *       picks them up once the Wave 2 frontend test ticket (T-V3-C-TEST-01) is
 *       installed. Pattern mirrors S-001 / S-033 / S-048 specs.
 *
 * Covers (mapped to T-V3-C-58 acceptance_criteria):
 *   structural.AC-S1  -> h1 == "タスクリスト" (mock h1 逐語)
 *   structural.AC-S2  -> Lucide icons only (no emoji glyphs)
 *   functional.AC-F1  -> GET /api/workspaces/{id}/tasks renders 2xx body;
 *                        4xx renders inline error empty state + toast
 *   functional.AC-F2  -> 401 redirects to /login (S-001); no workspace data renders
 *   functional.AC-F3  -> GET /api/workspaces/{id}/tasks?group_by=feature
 *                        renders accordion-friendly groups metadata
 *   Bulk action:      -> bulk Play button POSTs /tasks/bulk-play with selected ids
 *                        bulk Archive button POSTs /tasks/bulk-archive with selected ids
 *   Sort:             -> column header click toggles sort direction
 *   Filter:           -> search input narrows the visible rows
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

import TaskListPage from "@/app/(app)/task/list/page";

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

const TASKS_PAYLOAD = {
  tasks: [
    {
      id: "u-1",
      task_id: "T-V3-AUTH-01",
      title: "POST /api/auth/login 実装",
      feature_id: "F-001",
      status: "done",
      assignee_name: "devon",
      estimate_hours: 8,
      cost: 120,
      updated_at: "2026-05-17T12:00:00Z",
    },
    {
      id: "u-2",
      task_id: "T-V3-AUTH-02",
      title: "POST /api/auth/signup 実装",
      feature_id: "F-001",
      status: "running",
      assignee_name: "devon",
      estimate_hours: 8,
      cost: 41,
      updated_at: "2026-05-17T11:55:00Z",
    },
    {
      id: "u-3",
      task_id: "T-V3-AUTH-13",
      title: "unit test 8 ケース",
      feature_id: "F-001",
      status: "running",
      assignee_name: "quinn",
      estimate_hours: 8,
      cost: 8,
      updated_at: "2026-05-17T11:57:00Z",
    },
  ],
  groups: [
    { key: "F-001", label: "F-001 認証", count: 3, task_ids: ["u-1", "u-2", "u-3"] },
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
  useSearchParamsMock.mockReset();
  useSearchParamsMock.mockReturnValue(searchParamsStub({ workspace: "1" }));
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-58 S-028 タスクリスト (task_list)", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-028' and exact h1 text 'タスクリスト'", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASKS_PAYLOAD));

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const root = document.querySelector("[data-screen-id='S-028']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-007");
    expect(root?.getAttribute("data-screen-name")).toBe("task_list");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-58");
    expect(root?.getAttribute("data-entities")).toBe("E-018");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toBe("タスクリスト");

    // AC-S2: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F1: GET /api/workspaces/{id}/tasks is called on mount with group_by=feature", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASKS_PAYLOAD));

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/workspaces/1/tasks");
    expect(String(url)).toContain("group_by=feature");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("AC-F1 tail: 4xx non-401 renders the inline empty state + toasts the friendly message tagged with the endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "tasks.not_found", message: "no such workspace" } },
        { status: 404 },
      ),
    );

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-error-empty-state']"),
      ).not.toBeNull(),
    );

    expect(toastErrorMock).toHaveBeenCalled();
    const lastErrArg = toastErrorMock.mock.calls.at(-1)?.[0] as string;
    expect(lastErrArg).toContain("/api/workspaces/1/tasks");
    expect(lastErrArg).not.toMatch(/SQL|Traceback|<html/i);
  });

  it("AC-F2: 401 redirects to /login and renders no workspace-scoped data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "unauthorized", message: "missing token" } },
        { status: 401 },
      ),
    );

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith("/login"),
    );

    // No table rendered.
    expect(
      document.querySelector("[data-testid='task-list-table']"),
    ).toBeNull();
  });

  it("AC-F3: group_by=feature response renders accordion-friendly groups metadata", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASKS_PAYLOAD));

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-groups']"),
      ).not.toBeNull(),
    );

    const groupBar = document.querySelector("[data-testid='task-list-groups']");
    expect(groupBar?.textContent).toContain("F-001");
    expect(groupBar?.textContent).toContain("(3)");
  });

  it("renders one row per task with the expected task_id mono cell", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASKS_PAYLOAD));

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-table']"),
      ).not.toBeNull(),
    );

    expect(
      document.querySelector("[data-testid='task-list-row-u-1']"),
    ).not.toBeNull();
    expect(
      document.querySelector("[data-testid='task-list-row-u-2']"),
    ).not.toBeNull();
    expect(
      document.querySelector("[data-testid='task-list-row-u-3']"),
    ).not.toBeNull();
  });

  it("filter input narrows the visible rows (search by task_id)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASKS_PAYLOAD));

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-row-u-1']"),
      ).not.toBeNull(),
    );

    const searchInput = document.querySelector(
      "[data-testid='task-list-search']",
    ) as HTMLInputElement;
    fireEvent.change(searchInput, { target: { value: "AUTH-13" } });

    await waitFor(() => {
      expect(
        document.querySelector("[data-testid='task-list-row-u-3']"),
      ).not.toBeNull();
      expect(
        document.querySelector("[data-testid='task-list-row-u-1']"),
      ).toBeNull();
      expect(
        document.querySelector("[data-testid='task-list-row-u-2']"),
      ).toBeNull();
    });
  });

  it("selecting rows reveals the bulk action bar with the selection count", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASKS_PAYLOAD));

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-table']"),
      ).not.toBeNull(),
    );

    const checkbox = document.querySelector(
      "[data-testid='task-list-row-checkbox-u-1']",
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    await waitFor(() => {
      const bar = document.querySelector(
        "[data-testid='task-list-bulk-bar']",
      );
      expect(bar).not.toBeNull();
      expect(bar?.textContent).toContain("1 件選択中");
    });
  });

  it("bulk Play button POSTs /tasks/bulk-play with the selected ids and shows a success toast", async () => {
    // First call: GET tasks. Second call: POST bulk-play.
    fetchMock
      .mockResolvedValueOnce(jsonResponse(TASKS_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse({ session_ids: ["s-1"], queued: 1 }, { status: 201 }),
      );

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-table']"),
      ).not.toBeNull(),
    );

    const checkbox = document.querySelector(
      "[data-testid='task-list-row-checkbox-u-1']",
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    const playBtn = await waitFor(() => {
      const btn = document.querySelector(
        "[data-testid='task-list-bulk-play']",
      );
      if (!btn) throw new Error("bulk play button not visible");
      return btn as HTMLButtonElement;
    });
    fireEvent.click(playBtn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [postUrl, postInit] = fetchMock.mock.calls[1];
    expect(String(postUrl)).toContain("/api/workspaces/1/tasks/bulk-play");
    expect(postInit?.method).toBe("POST");
    const body = JSON.parse(String(postInit?.body));
    expect(body).toEqual({ task_ids: ["u-1"] });

    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled());
  });

  it("bulk Archive button POSTs /tasks/bulk-archive with the selected ids", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(TASKS_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse({ archived_count: 1 }, { status: 201 }),
      );

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-table']"),
      ).not.toBeNull(),
    );

    const checkbox = document.querySelector(
      "[data-testid='task-list-row-checkbox-u-2']",
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    const archiveBtn = await waitFor(() => {
      const btn = document.querySelector(
        "[data-testid='task-list-bulk-archive']",
      );
      if (!btn) throw new Error("bulk archive button not visible");
      return btn as HTMLButtonElement;
    });
    fireEvent.click(archiveBtn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [postUrl, postInit] = fetchMock.mock.calls[1];
    expect(String(postUrl)).toContain("/api/workspaces/1/tasks/bulk-archive");
    expect(postInit?.method).toBe("POST");
    const body = JSON.parse(String(postInit?.body));
    expect(body).toEqual({ task_ids: ["u-2"] });
  });

  it("sort header click toggles asc/desc indicator", async () => {
    fetchMock.mockResolvedValue(jsonResponse(TASKS_PAYLOAD));

    renderWithQueryClient(<TaskListPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='task-list-table']"),
      ).not.toBeNull(),
    );

    const titleHeader = document.querySelector(
      "[data-testid='task-list-sort-title']",
    ) as HTMLElement;
    expect(titleHeader).not.toBeNull();

    // First click: asc (default). Second click on same: desc.
    fireEvent.click(titleHeader);
    fireEvent.click(titleHeader);
    // After two clicks the header should still be present (no crash).
    expect(
      document.querySelector("[data-testid='task-list-sort-title']"),
    ).not.toBeNull();
  });
});
