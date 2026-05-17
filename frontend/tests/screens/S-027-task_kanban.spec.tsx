// @ts-nocheck
/**
 * T-V3-C-57-1 / S-027 — タスク Kanban (task_kanban) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen
 *       test harness; they are wired by the Wave 2 frontend test setup
 *       ticket (T-V3-C-TEST-01). Same convention as T-V3-C-38 / C-39 /
 *       C-12 / C-51.
 *
 * Covers (mapped to T-V3-C-57-1 acceptance_criteria — see
 * docs/audit/2026-05-16_v3/T-V3-C-57-1.md):
 *   structural.AC-S1 -> 'h1 reads "タスク Kanban"'
 *   structural.AC-S2 -> 'renders root with data-screen-id="S-027"'
 *   structural.AC-S2 -> 'feature-grouped accordion × 4 columns per section'
 *   structural.AC-S3 -> 'default-expands only in-progress feature accordions;
 *                        all-done / all-todo features collapsed by default'
 *   functional.AC-F1 -> 'GET /api/workspaces/{id}/tasks?group_by=feature via
 *                        typed client on mount; 2xx renders accordion'
 *   functional.AC-F2 -> '401 -> redirect /login + no workspace data rendered'
 *   functional.AC-F3 -> 'skeleton accordion with role="status" aria-live="polite"
 *                        while data is loading'
 *   functional.AC-F4 -> '403 -> render 403 page (S-046) instead of partial data'
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

import TaskKanbanPage from "@/app/(app)/task/kanban/page";
import { aggregateKanban } from "@/hooks/use-kanban-board";

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

// Tasks fixture covering all 4 columns and 3 features:
//   F-001 (mixed: in_progress + todo + review + done) — default expanded.
//   F-002 (all done)                                  — default collapsed.
//   F-003 (all todo)                                  — default collapsed.
const TASKS_FIXTURE = {
  tasks: [
    { id: "T-AUTH-01", title: "POST /api/auth/login", feature_id: "F-001", status: "done" },
    { id: "T-AUTH-02", title: "POST /api/auth/signup", feature_id: "F-001", status: "in_progress" },
    { id: "T-AUTH-03", title: "/login page.tsx", feature_id: "F-001", status: "todo", estimate_hours: 4 },
    { id: "T-AUTH-04", title: "RLS policy migration", feature_id: "F-001", status: "review" },
    { id: "T-WS-01", title: "GET workspaces", feature_id: "F-002", status: "done" },
    { id: "T-WS-02", title: "POST workspaces", feature_id: "F-002", status: "completed" },
    { id: "T-SPEC-01", title: "spec viewer", feature_id: "F-003", status: "todo" },
    { id: "T-SPEC-02", title: "spec editor", feature_id: "F-003", status: "pending" },
  ],
  groups: [
    { id: "F-001", name: "Supabase 基盤 + 認証", count: 4 },
    { id: "F-002", name: "Workspace 管理", count: 2 },
    { id: "F-003", name: "Spec viewer", count: 2 },
  ],
};

function defaultFetchImpl(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const method = init?.method ?? "GET";
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.includes("/api/workspaces/") &&
    url.includes("/tasks")
  ) {
    return Promise.resolve(jsonResponse(200, TASKS_FIXTURE));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  routerReplace.mockReset();
  searchParamsGet.mockReset();
  searchParamsGet.mockImplementation((key: string) =>
    key === "workspace_id" ? "ws-test" : null,
  );
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-027 タスク Kanban page (T-V3-C-57-1)", () => {
  it("AC-S2: renders root with data-screen-id='S-027'", async () => {
    const { container } = render(<TaskKanbanPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-027"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-007");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-57-1");
    expect(root?.getAttribute("data-entities")).toContain("E-018");
  });

  it("AC-S1: h1 reads 'タスク Kanban'", async () => {
    render(<TaskKanbanPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("タスク Kanban");
  });

  it("AC-S2: renders one accordion section per feature with 4 columns each (NOT a flat 6-column board)", async () => {
    const { container } = render(<TaskKanbanPage />);
    await waitFor(() =>
      expect(container.querySelectorAll("[data-kanban-section]").length).toBe(3),
    );
    const sections = container.querySelectorAll("[data-kanban-section]");
    sections.forEach((section) => {
      const cols = section.querySelectorAll("[data-kanban-column]");
      expect(cols.length).toBe(4);
      const colKinds = Array.from(cols).map((c) =>
        c.getAttribute("data-kanban-column"),
      );
      expect(colKinds).toEqual(["todo", "in_progress", "review", "done"]);
    });
    // Hermes-flat 6-column guard: at most 4 columns directly under any section.
    const totalColumns = container.querySelectorAll(
      "[data-kanban-section] [data-kanban-column]",
    );
    expect(totalColumns.length).toBe(3 * 4);
  });

  it("AC-S3: only in-progress (mixed) features are default-expanded; all-done and all-todo features are collapsed", async () => {
    const { container } = render(<TaskKanbanPage />);
    await waitFor(() =>
      expect(container.querySelectorAll("[data-kanban-section]").length).toBe(3),
    );
    const f1 = container.querySelector(
      '[data-kanban-section][data-feature-id="F-001"]',
    ) as HTMLDetailsElement | null;
    const f2 = container.querySelector(
      '[data-kanban-section][data-feature-id="F-002"]',
    ) as HTMLDetailsElement | null;
    const f3 = container.querySelector(
      '[data-kanban-section][data-feature-id="F-003"]',
    ) as HTMLDetailsElement | null;
    expect(f1?.getAttribute("data-default-expanded")).toBe("true");
    expect(f1?.open).toBe(true);
    expect(f2?.getAttribute("data-default-expanded")).toBe("false");
    expect(f2?.open).toBe(false);
    expect(f3?.getAttribute("data-default-expanded")).toBe("false");
    expect(f3?.open).toBe(false);
  });

  it("AC-F1: GET /api/workspaces/{id}/tasks?group_by=feature on mount via typed client", async () => {
    render(<TaskKanbanPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain("/api/workspaces/ws-test/tasks");
    expect(String(calledUrl)).toContain("group_by=feature");
    expect((init ?? {}).method ?? "GET").toBe("GET");
    // Tasks rendered into the board.
    await waitFor(() =>
      expect(screen.queryByText("POST /api/auth/login")).not.toBeNull(),
    );
    expect(screen.getByText("POST /api/auth/signup")).not.toBeNull();
    expect(screen.getByText("/login page.tsx")).not.toBeNull();
    expect(screen.getByText("RLS policy migration")).not.toBeNull();
  });

  it("AC-F2: 401 from GET /tasks redirects to /login and does not render workspace-scoped data", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "UNAUTHORIZED", message: "missing token" },
        }),
      ),
    );

    render(<TaskKanbanPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    // No section, no error toast, no skeleton — only the aria-hidden shell.
    expect(screen.queryByTestId("kanban-error")).toBeNull();
    expect(screen.queryByTestId("kanban-skeleton")).toBeNull();
    expect(screen.queryByText("POST /api/auth/login")).toBeNull();
  });

  it("AC-F3: skeleton accordion with role='status' aria-live='polite' while loading", async () => {
    // Defer the fetch resolution to keep the page in the loading state.
    let resolveFetch: (response: Response) => void = () => {};
    fetchMock.mockReset();
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        }),
    );

    render(<TaskKanbanPage />);

    const skeleton = await waitFor(() => screen.getByTestId("kanban-skeleton"));
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-live")).toBe("polite");

    // Resolve so the test does not leak a pending promise.
    resolveFetch(jsonResponse(200, TASKS_FIXTURE));
    await waitFor(() => expect(screen.queryByTestId("kanban-skeleton")).toBeNull());
  });

  it("AC-F4: 403 from GET /tasks renders the 403 page (S-046) instead of partial data", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(403, {
          detail: { code: "FORBIDDEN", message: "not a workspace member" },
        }),
      ),
    );

    const { container } = render(<TaskKanbanPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("kanban-forbidden")).not.toBeNull(),
    );
    // No partial accordion rendered.
    expect(container.querySelector("[data-kanban-section]")).toBeNull();
    expect(screen.queryByText("POST /api/auth/login")).toBeNull();
    // Inline 403 includes a link to S-046 for "詳細を確認".
    expect(
      container.querySelector('a[href="/forbidden"]'),
    ).not.toBeNull();
  });
});

// --------------------------------------------------------------------------
// Pure-function coverage for aggregateKanban (no React render needed)
// --------------------------------------------------------------------------

describe("aggregateKanban (T-V3-C-57-1 — view-model)", () => {
  it("buckets tasks into Todo / In Progress / Review / Done", () => {
    const sections = aggregateKanban(TASKS_FIXTURE as any);
    expect(sections).toHaveLength(3);
    const f1 = sections.find((s) => s.feature_id === "F-001")!;
    expect(f1.columns.todo).toHaveLength(1);
    expect(f1.columns.in_progress).toHaveLength(1);
    expect(f1.columns.review).toHaveLength(1);
    expect(f1.columns.done).toHaveLength(1);
    expect(f1.total).toBe(4);
  });

  it("groups tasks without feature_id into 'ungrouped' bucket", () => {
    const sections = aggregateKanban({
      tasks: [{ id: "T-ORPHAN", title: "orphan", status: "todo" }],
      groups: [],
    } as any);
    expect(sections).toHaveLength(1);
    expect(sections[0].feature_id).toBe("ungrouped");
    expect(sections[0].columns.todo).toHaveLength(1);
  });

  it("preserves backend group order then alphabetises trailing features", () => {
    const sections = aggregateKanban({
      tasks: [
        { id: "T-A", title: "a", feature_id: "F-B", status: "todo" },
        { id: "T-B", title: "b", feature_id: "F-A", status: "todo" },
        { id: "T-C", title: "c", feature_id: "F-Z", status: "todo" },
      ],
      groups: [
        { id: "F-A", name: "Alpha" },
        { id: "F-B", name: "Bravo" },
      ],
    } as any);
    expect(sections.map((s) => s.feature_id)).toEqual(["F-A", "F-B", "F-Z"]);
  });
});
