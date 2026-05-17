/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-57-3 / S-027 — タスク Kanban filter & search screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are *runtime-only* devDeps for the new screen test harness; they are
 *       installed by the Wave 2 frontend test setup ticket (T-V3-C-TEST-01).
 *       Once installed, tsc strict mode picks them up automatically. Mirrors
 *       the pattern used by S-008 / S-033 / S-048 specs in this directory.
 *
 * Covers (mapped to T-V3-C-57-3 acceptance_criteria):
 *   structural.AC-S1 -> "sticky FilterBar above accordion with 4 inputs"
 *   structural.AC-S2 -> "active-filter badge count + 'Clear filters' button"
 *   functional.AC-F1 -> "250ms debounce + URL search params mirror"
 *   functional.AC-F2 -> "empty state per accordion section + Reset CTA"
 *   functional.AC-F3 -> "truncate text search at 200 chars / no API beyond 200"
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
  fireEvent,
  cleanup,
  act,
  renderHook,
  waitFor,
} from "@testing-library/react";

import TaskKanbanPage from "@/app/(app)/task/kanban/page";
import {
  KanbanFilterBar,
  EMPTY_KANBAN_FILTER,
  KANBAN_SEARCH_MAX_LEN,
  KANBAN_FILTER_DEBOUNCE_MS,
  countActiveFilters,
  filterStateFromSearchParams,
  filterStateToSearchParams,
  truncateQuery,
} from "@/app/(app)/task/kanban/filter";
import { useKanbanFilter } from "@/app/(app)/task/kanban/use-kanban-filter";

// --- shared fixtures ------------------------------------------------------

const FEATURE_OPTIONS = [
  { value: "F-001", label: "認証" },
  { value: "F-004", label: "メンバー" },
  { value: "F-007", label: "タスク" },
];
const ASSIGNEE_OPTIONS = [
  { value: "devon", label: "devon" },
  { value: "quinn", label: "quinn" },
];

beforeEach(() => {
  try {
    window.history.replaceState(null, "", "/task/kanban");
  } catch {
    /* jsdom only */
  }
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

// =========================================================================
//  Page-level rendering (AC-S1, AC-S2 — full integration through hook)
// =========================================================================

describe("T-V3-C-57-3 S-027 タスク Kanban filter & search — page", () => {
  it("AC-S1: page mounts with data-screen-id='S-027' + sticky FilterBar 4 inputs", () => {
    render(<TaskKanbanPage />);
    const root = document.querySelector("[data-screen-id='S-027']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-007");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-57-3");

    // The 4 input surfaces (text query + 3 multi-selects) must exist.
    expect(screen.getByTestId("kanban-filter-bar")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-query")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-feature")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-status")).toBeTruthy();
    expect(screen.getByTestId("kanban-filter-assignee")).toBeTruthy();
  });

  it("AC-S2: at least one active filter surfaces badge + 'Clear filters' button", () => {
    render(<TaskKanbanPage />);

    // No filters active → no badge / no clear button.
    expect(document.querySelector("[data-testid='kanban-filter-active-count']")).toBeNull();
    expect(document.querySelector("[data-testid='kanban-filter-clear']")).toBeNull();

    // Type a query → badge appears with count == 1.
    const input = screen.getByTestId("kanban-filter-query");
    fireEvent.change(input, { target: { value: "auth" } });

    const badge = screen.getByTestId("kanban-filter-active-count");
    expect(badge).toBeTruthy();
    expect(badge.textContent || "").toContain("1");
    expect(screen.getByTestId("kanban-filter-clear")).toBeTruthy();

    // Click Clear filters → badge gone.
    fireEvent.click(screen.getByTestId("kanban-filter-clear"));
    expect(document.querySelector("[data-testid='kanban-filter-active-count']")).toBeNull();
  });
});

// =========================================================================
//  FilterBar pure component (AC-S1, AC-S2, AC-F3)
// =========================================================================

describe("T-V3-C-57-3 KanbanFilterBar — controlled component", () => {
  it("AC-F3: input maxLength + truncateQuery cap at KANBAN_SEARCH_MAX_LEN", () => {
    const onChange = vi.fn();
    render(
      <KanbanFilterBar
        featureOptions={FEATURE_OPTIONS}
        assigneeOptions={ASSIGNEE_OPTIONS}
        value={EMPTY_KANBAN_FILTER}
        onChange={onChange}
      />,
    );
    const input = screen.getByTestId("kanban-filter-query") as HTMLInputElement;
    expect(input.maxLength).toBe(KANBAN_SEARCH_MAX_LEN);

    // Simulate an attempt to set a value longer than the cap: the onChange
    // payload must be truncated to KANBAN_SEARCH_MAX_LEN.
    const tooLong = "a".repeat(KANBAN_SEARCH_MAX_LEN + 50);
    fireEvent.change(input, { target: { value: tooLong } });
    const last = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(last.query.length).toBe(KANBAN_SEARCH_MAX_LEN);

    // And the pure helper behaves the same.
    expect(truncateQuery(tooLong).length).toBe(KANBAN_SEARCH_MAX_LEN);
    expect(truncateQuery("ok").length).toBe(2);
  });

  it("AC-S2: countActiveFilters counts distinct populated inputs", () => {
    expect(countActiveFilters(EMPTY_KANBAN_FILTER)).toBe(0);
    expect(
      countActiveFilters({
        features: ["F-001"],
        statuses: [],
        assignees: [],
        query: "",
      }),
    ).toBe(1);
    expect(
      countActiveFilters({
        features: ["F-001"],
        statuses: ["todo"],
        assignees: ["devon"],
        query: "auth",
      }),
    ).toBe(4);
    // Whitespace-only query does not count.
    expect(
      countActiveFilters({
        features: [],
        statuses: [],
        assignees: [],
        query: "   ",
      }),
    ).toBe(0);
  });

  it("AC-S1: feature chip toggle calls onChange with toggled featureId", () => {
    const onChange = vi.fn();
    render(
      <KanbanFilterBar
        featureOptions={FEATURE_OPTIONS}
        assigneeOptions={ASSIGNEE_OPTIONS}
        value={EMPTY_KANBAN_FILTER}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("kanban-filter-feature-F-001"));
    expect(onChange).toHaveBeenCalledWith({
      ...EMPTY_KANBAN_FILTER,
      features: ["F-001"],
    });
  });
});

// =========================================================================
//  Hook (AC-F1, AC-F3)
// =========================================================================

describe("T-V3-C-57-3 useKanbanFilter — debounce + URL sync", () => {
  it("AC-F1: debouncedState updates only after KANBAN_FILTER_DEBOUNCE_MS", () => {
    const { result } = renderHook(() =>
      useKanbanFilter({ syncUrl: false }),
    );
    act(() => {
      result.current.setQuery("a");
    });
    // Same tick: state changed, debouncedState NOT yet.
    expect(result.current.state.query).toBe("a");
    expect(result.current.debouncedState.query).toBe("");

    // Advance just under the debounce window — still no commit.
    act(() => {
      vi.advanceTimersByTime(KANBAN_FILTER_DEBOUNCE_MS - 1);
    });
    expect(result.current.debouncedState.query).toBe("");

    // Cross the threshold → commit.
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(result.current.debouncedState.query).toBe("a");
  });

  it("AC-F1: URL search params mirror committed state (replaceState)", () => {
    const { result } = renderHook(() => useKanbanFilter({ syncUrl: true }));
    act(() => {
      result.current.toggleFeature("F-007");
      result.current.toggleStatus("todo");
      result.current.setQuery("kanban");
    });
    act(() => {
      vi.advanceTimersByTime(KANBAN_FILTER_DEBOUNCE_MS + 5);
    });
    const sp = new URLSearchParams(window.location.search);
    expect(sp.get("feature")).toBe("F-007");
    expect(sp.get("status")).toBe("todo");
    expect(sp.get("q")).toBe("kanban");
  });

  it("AC-F3: setQuery truncates to KANBAN_SEARCH_MAX_LEN; debounce never fires with longer payload", () => {
    const { result } = renderHook(() => useKanbanFilter({ syncUrl: false }));
    act(() => {
      result.current.setQuery("x".repeat(KANBAN_SEARCH_MAX_LEN + 100));
    });
    expect(result.current.state.query.length).toBe(KANBAN_SEARCH_MAX_LEN);
    act(() => {
      vi.advanceTimersByTime(KANBAN_FILTER_DEBOUNCE_MS + 5);
    });
    expect(result.current.debouncedState.query.length).toBe(
      KANBAN_SEARCH_MAX_LEN,
    );
  });
});

// =========================================================================
//  URL serde round-trip + Empty state (AC-F1, AC-F2)
// =========================================================================

describe("T-V3-C-57-3 URL serde + empty state", () => {
  it("AC-F1: filterStateToSearchParams + filterStateFromSearchParams round-trip", () => {
    const original = {
      features: ["F-001", "F-007"],
      statuses: ["todo", "review"],
      assignees: ["devon"],
      query: "rls migration",
    };
    const sp = filterStateToSearchParams(original);
    const back = filterStateFromSearchParams(sp);
    expect(back.features).toEqual(original.features);
    expect(back.statuses).toEqual(original.statuses);
    expect(back.assignees).toEqual(original.assignees);
    expect(back.query).toBe(original.query);
  });

  it("AC-F1: filterStateFromSearchParams drops unknown status values", () => {
    const sp = new URLSearchParams("status=todo,bogus,review");
    const back = filterStateFromSearchParams(sp);
    expect(back.statuses).toEqual(["todo", "review"]);
  });

  it("AC-F2: empty state surfaces + Reset CTA clears filter via real page", async () => {
    render(<TaskKanbanPage />);
    // Narrow to a value that matches no feature label / id.
    fireEvent.change(screen.getByTestId("kanban-filter-query"), {
      target: { value: "no-such-feature-zzz" },
    });
    await waitFor(() => {
      expect(screen.getByTestId("kanban-filter-empty")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("kanban-filter-reset"));
    // After reset, empty state vanishes (placeholder list is non-empty).
    await waitFor(() => {
      expect(
        document.querySelector("[data-testid='kanban-filter-empty']"),
      ).toBeNull();
    });
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
